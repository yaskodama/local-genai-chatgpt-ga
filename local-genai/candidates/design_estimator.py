"""Design estimator: predicts (params, holdout_ppl, train_time_min,
inference_throughput) from a genome dict, deterministically.

The constants come from the .aice expected_delta / param_count_estimate
fields.  Stages 2–7 use this estimator instead of real training so the
evolution loop can run end-to-end without GPUs.

Genome keys (subset, varies per stage):
  model_family : ngram_count | char_rnn | single_block_transformer |
                 multi_block_transformer | distilled_compact |
                 preference_tuned_compact | self_evolving_compact
  depth        : int (block count, 0 for ngram/rnn)
  n_heads      : int
  d_model      : int
  ffn_mult     : int
  vocab        : int (default 256)
  ctx          : int
  positional   : none | implicit_recurrence | learned_absolute |
                 rope | sinusoidal
  normalization: none | layernorm | rmsnorm
  regularization: none | dropout
  inference_optimization: none | kv_cache | kv_cache_plus_int8
  training_paradigm: count_normalize | maximum_likelihood_sgd |
                     distillation | distillation_plus_dpo |
                     self_proposed_mutation
  param_class  : 32K | 100K | 1M | 3M | 10M
  engine       : numpy_only | pytorch_cpu | pytorch_cpu_or_mps |
                 pytorch_mps
  tied_embedding : bool
"""

from __future__ import annotations
import hashlib

VOCAB = 256

BASE_PPL_BY_CLASS = {
    "32K":  9.0,
    "100K": 6.5,
    "1M":   5.2,
    "3M":   4.1,
    "10M":  3.9,
}

PARAM_BUDGET_BY_CLASS = {
    "32K":  64_000,
    "100K": 200_000,
    "1M":   1_500_000,
    "3M":   4_000_000,
    "10M":  12_000_000,
}

ENGINE_TRAIN_TIME_FACTOR = {
    "numpy_only":         0.0001,
    "pytorch_cpu":        2.5,
    "pytorch_cpu_or_mps": 1.0,
    "pytorch_mps":        0.7,
}


def _params_transformer(g: dict) -> int:
    d = g["d_model"]
    L = g.get("depth", 1)
    F = g.get("ffn_mult", 4)
    ctx = g.get("ctx", 128)
    tied = g.get("tied_embedding", True)
    pos = g.get("positional", "rope")

    embed = VOCAB * d
    if not tied:
        embed += VOCAB * d
    pos_params = 0
    if pos == "learned_absolute":
        pos_params = ctx * d
    block = 4 * d * d + 2 * d * F * d
    norm = 2 * d if g.get("normalization") in ("layernorm", "rmsnorm") else 0
    return embed + pos_params + L * (block + norm)


def _params(g: dict) -> int:
    fam = g["model_family"]
    if fam == "ngram_count":
        return 256 * 256
    if fam == "char_rnn":
        e = g.get("embed_dim", 64)
        h = g.get("hidden_dim", 128)
        cell = g.get("cell", "GRU")
        gate_count = 3 if cell == "GRU" else 4
        return VOCAB * e + gate_count * (e + h) * h + (h * VOCAB if not g.get("tied_embedding", True) else 0)
    return _params_transformer(g)


def _coherence_violations(g: dict) -> list[str]:
    v = []
    fam = g["model_family"]
    if fam in ("single_block_transformer", "multi_block_transformer",
               "distilled_compact", "preference_tuned_compact",
               "self_evolving_compact"):
        if g.get("normalization", "none") == "none":
            v.append("transformer_without_normalization")
        if g.get("positional", "none") == "none":
            v.append("transformer_without_positional")
    if fam == "multi_block_transformer" and g.get("regularization") != "dropout":
        v.append("deep_transformer_without_dropout")
    if g.get("training_paradigm") == "distillation" and fam not in (
            "distilled_compact", "multi_block_transformer"):
        v.append("distillation_paradigm_mismatch")
    if g.get("training_paradigm") == "distillation_plus_dpo" and fam != "preference_tuned_compact":
        v.append("dpo_paradigm_mismatch")
    if g.get("training_paradigm") == "self_proposed_mutation" and fam != "self_evolving_compact":
        v.append("self_evolve_paradigm_mismatch")
    return v


def _seed_jitter(g: dict, scale: float) -> float:
    """Tiny deterministic jitter so equally-rated candidates differ."""
    h = hashlib.sha256(repr(sorted(g.items())).encode()).digest()
    raw = int.from_bytes(h[:4], "big") / 2**32
    return (raw - 0.5) * 2 * scale


def estimate(g: dict) -> dict:
    pcls = g.get("param_class", "1M")
    base = BASE_PPL_BY_CLASS[pcls]

    bonus = 0.0
    if g.get("positional") == "rope":      bonus -= 0.10
    if g.get("normalization") == "rmsnorm":bonus -= 0.05
    if g.get("regularization") == "dropout":
        bonus -= 0.20 if pcls in ("1M", "3M", "10M") else +0.30

    tp = g.get("training_paradigm", "maximum_likelihood_sgd")
    if tp == "distillation":              bonus -= 0.30
    if tp == "distillation_plus_dpo":     bonus -= 0.10
    if tp == "self_proposed_mutation":    bonus -= 0.05

    fam = g["model_family"]
    if fam == "self_evolving_compact":    bonus -= 0.05

    violations = _coherence_violations(g)
    penalty = 1.0 * len(violations)

    ppl = base + bonus + penalty + _seed_jitter(g, 0.05)
    ppl = max(2.5, ppl)

    params = _params(g)
    over_budget = params > PARAM_BUDGET_BY_CLASS[pcls]

    flops_per_token = 2 * params + g.get("ctx", 128) * g.get("depth", 1) * 4 * g.get("d_model", 1)
    train_steps = g.get("steps", 4000)
    train_factor = ENGINE_TRAIN_TIME_FACTOR.get(g.get("engine", "pytorch_cpu_or_mps"), 1.0)
    train_time_min = (params / 1e7) * train_factor * (train_steps / 4000) * 25.0
    train_time_min = max(0.05, train_time_min)

    infer_factor = 1.0
    if g.get("inference_optimization") in ("kv_cache", "kv_cache_plus_int8"):
        infer_factor = 4.0
    if g.get("inference_optimization") == "kv_cache_plus_int8":
        infer_factor = 6.0

    return {
        "params": params,
        "param_class": pcls,
        "param_budget": PARAM_BUDGET_BY_CLASS[pcls],
        "over_budget": over_budget,
        "expected_holdout_ppl": round(ppl, 3),
        "flops_per_token": flops_per_token,
        "train_time_min_estimate": round(train_time_min, 2),
        "inference_throughput_factor": infer_factor,
        "coherence_violations": violations,
    }
