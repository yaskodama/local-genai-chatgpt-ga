"""3 deterministic reviewers matching the .aice rubrics.

Quality:        4 axes × 0-3 = 12 points  (focus: expected_holdout_ppl)
Efficiency:     4 axes × 0-3 = 12 points  (focus: ppl/param + budgets)
Reproducibility: 5 axes × 0-2 = 10 points (focus: seed/corpus/deps/api/script)

Each reviewer returns a dict with axis-level scores and a total.
"""

from __future__ import annotations


def quality_review(estimate: dict, genome: dict) -> dict:
    ppl = estimate["expected_holdout_ppl"]
    if   ppl < 3.5: ppl_score = 3
    elif ppl < 4.5: ppl_score = 2
    elif ppl < 6.0: ppl_score = 1
    else:           ppl_score = 0

    plausible = 3
    if genome.get("regularization") == "dropout" and genome.get("param_class") == "100K":
        plausible -= 1
    if genome.get("normalization") == "none" and genome["model_family"] not in (
            "ngram_count", "char_rnn"):
        plausible -= 1

    degeneracy = 3
    if genome.get("regularization") == "none" and genome.get("param_class") in ("3M", "10M"):
        degeneracy -= 1
    if genome.get("ctx", 128) > 512:
        degeneracy -= 1

    size_appropriate = 3
    if estimate["over_budget"]:
        size_appropriate = 0
    elif estimate["params"] < estimate["param_budget"] * 0.4:
        size_appropriate = 2

    total = ppl_score + plausible + degeneracy + size_appropriate
    return {
        "reviewer": "Quality",
        "axes": {
            "ppl_score": ppl_score,
            "loss_trajectory_plausibility": plausible,
            "degeneracy_resistance": degeneracy,
            "generation_appropriate_size": size_appropriate,
        },
        "total": total,
        "max": 12,
    }


def efficiency_review(estimate: dict, genome: dict) -> dict:
    ppl = estimate["expected_holdout_ppl"]
    params = estimate["params"]
    ppl_per_param = 3
    if params > 0:
        ratio = ppl / (params ** 0.25)
        if   ratio < 0.10: ppl_per_param = 3
        elif ratio < 0.13: ppl_per_param = 2
        elif ratio < 0.20: ppl_per_param = 1
        else:              ppl_per_param = 0

    within_budget = 0 if estimate["over_budget"] else 3

    if   estimate["train_time_min_estimate"] <= 15: train_time = 3
    elif estimate["train_time_min_estimate"] <= 25: train_time = 2
    elif estimate["train_time_min_estimate"] <= 30: train_time = 1
    else:                                            train_time = 0

    inf = estimate["inference_throughput_factor"]
    if   inf >= 6.0: inference = 3
    elif inf >= 4.0: inference = 2
    elif inf >= 2.0: inference = 1
    else:            inference = 0

    total = ppl_per_param + within_budget + train_time + inference
    return {
        "reviewer": "Efficiency",
        "axes": {
            "ppl_per_param": ppl_per_param,
            "within_param_budget": within_budget,
            "train_time_under_30min": train_time,
            "inference_optimization": inference,
        },
        "total": total,
        "max": 12,
    }


def reproducibility_review(estimate: dict, genome: dict) -> dict:
    seed_fixed = 2 if genome.get("seed") == 42 else 1
    corpus_pinned = 2 if genome.get("corpus_pinned") else 0
    no_external_api = 2 if not genome.get("uses_external_api", False) else 0

    deps = genome.get("deps", [])
    allowed = {"python", "pytorch", "numpy"}
    if all(any(a in d.lower() for a in allowed) for d in deps):
        minimal_deps = 2
    else:
        minimal_deps = 1
    if not deps:
        minimal_deps = 0

    single_script = 2 if genome.get("single_script", False) else 1

    coherence_penalty = -2 if estimate["coherence_violations"] else 0
    over_budget_penalty = -3 if estimate["over_budget"] else 0

    total = (seed_fixed + corpus_pinned + no_external_api + minimal_deps +
             single_script + coherence_penalty + over_budget_penalty)
    return {
        "reviewer": "Reproducibility",
        "axes": {
            "seed_fixed": seed_fixed,
            "corpus_pinned": corpus_pinned,
            "no_external_api": no_external_api,
            "minimal_deps": minimal_deps,
            "single_script": single_script,
            "coherence_penalty": coherence_penalty,
            "over_budget_penalty": over_budget_penalty,
        },
        "total": total,
        "max": 10,
    }


def review_all(estimate: dict, genome: dict) -> dict:
    q = quality_review(estimate, genome)
    e = efficiency_review(estimate, genome)
    r = reproducibility_review(estimate, genome)
    norm = q["total"] / q["max"] + e["total"] / e["max"] + r["total"] / r["max"]
    return {
        "quality": q,
        "efficiency": e,
        "reproducibility": r,
        "normalized_total": round(norm, 4),
    }
