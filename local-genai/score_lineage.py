"""Re-score the 76-individual lineage produced by the AIPL .abcl
orchestrator using the Python design_estimator + 3 reviewers, and
identify the top feasible candidate (corpus_size_class=10KB so we
can train it locally without downloading anything).

Usage:
    python3 local-genai/score_lineage.py
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from candidates.design_estimator import estimate
from reviewers import review_all


REPO = HERE.parent
LINEAGE = REPO / "aice-evolution-v2/examples/out/LocalGenAIScaledEvolutionJP.abcl_lineage.json"


# Map lineage axis values to the genome dict the design_estimator expects.
PARAM_CLASS_MAP = {
    "32K": "32K", "200K": "100K", "500K": "1M",
    "2M": "3M", "3M": "3M", "6M": "10M",
}

REGULARIZATION_MAP = {
    "none": "none", "dropout_005": "dropout", "dropout_010": "dropout",
}


def parse_genome(s: str) -> dict:
    pairs = [p.split("=", 1) for p in s.split("|") if "=" in p]
    return {k: v for k, v in pairs}


def to_design_genome(g: dict, name: str) -> dict:
    """Translate lineage genome to the dict shape design_estimator wants."""
    fam = g.get("model_family", "ngram_count")
    pcls = PARAM_CLASS_MAP.get(g.get("param_class", "1M"), "1M")
    out = {
        "name": name,
        "model_family": fam,
        "param_class": pcls,
        "positional": g.get("positional", "none"),
        "normalization": g.get("normalization", "none"),
        "regularization": REGULARIZATION_MAP.get(g.get("regularization", "none"), "none"),
        "inference_optimization": g.get("inference_optimization", "none"),
        "training_paradigm": g.get("training_paradigm", "maximum_likelihood_sgd"),
        "self_evolution": g.get("self_evolution", "none"),
        "engine": g.get("engine", "pytorch_mps"),
        "corpus_size_class": g.get("corpus_size_class", "10KB"),
        "data_per_param_health": g.get("data_per_param_health", "below_50_overfit_warning"),
        # transformer defaults — used by params formula
        "depth": 4,
        "n_heads": 4,
        "d_model": 192,
        "ffn_mult": 4,
        "vocab": 256,
        "ctx": 128,
        "tied_embedding": True,
        "seed": 42,
        "corpus_pinned": True,
        "uses_external_api": False,
        "single_script": True,
        "deps": ["python>=3.11", "pytorch==2.x"],
    }
    return out


def feasibility(g: dict) -> tuple[bool, str]:
    """Can we actually train this locally right now?"""
    if g.get("data_per_param_health") == "below_50_overfit_warning":
        return False, "data/param < 50 (overfit)"
    if g.get("corpus_size_class") not in ("10KB",):
        return False, f"corpus {g.get('corpus_size_class')} not locally available"
    if g.get("model_family") not in ("char_rnn", "single_block_transformer",
                                     "multi_block_transformer"):
        return False, f"model_family={g.get('model_family')} not implemented locally"
    if g.get("training_paradigm") not in ("maximum_likelihood_sgd",
                                          "count_normalize"):
        return False, f"training_paradigm={g.get('training_paradigm')} not implemented locally"
    return True, "feasible"


def main():
    if not LINEAGE.exists():
        print(f"missing lineage at {LINEAGE}")
        print("first run:")
        print("  cd aice-evolution-v2/examples && mkdir -p out && \\")
        print("    AIPL_AI_PROVIDER=mock python3 ../../src/python-aipl/aipl_main.py \\")
        print("    LocalGenAIScaledEvolutionJP.abcl")
        sys.exit(1)

    individuals = json.loads(LINEAGE.read_text(encoding="utf-8"))
    print(f"loaded {len(individuals)} individuals from {LINEAGE.name}")
    print()

    scored = []
    for ind in individuals:
        gd = parse_genome(ind["genome"])
        design = to_design_genome(gd, ind["id"])
        est = estimate(design)
        review = review_all(est, design)
        feasible, reason = feasibility(gd)
        scored.append({
            "id": ind["id"],
            "cell": ind["cell"],
            "genome_axes": gd,
            "design": design,
            "estimate": est,
            "review": review,
            "feasible": feasible,
            "reason": reason,
        })

    scored.sort(key=lambda r: r["review"]["normalized_total"], reverse=True)

    print("===== top 10 by reviewer score (any feasibility) =====")
    for s in scored[:10]:
        f = "✓" if s["feasible"] else "✗"
        print(f"  {f} {s['id']:<4} norm={s['review']['normalized_total']:.3f}  "
              f"ppl_est={s['estimate']['expected_holdout_ppl']:>5}  "
              f"params={s['estimate']['params']:>9,}  "
              f"corpus={s['genome_axes'].get('corpus_size_class'):>6}  "
              f"family={s['genome_axes'].get('model_family')}")
        if not s["feasible"]:
            print(f"       reason: {s['reason']}")

    feasibles = [s for s in scored if s["feasible"]]
    print()
    print(f"===== feasible (locally trainable) candidates: {len(feasibles)} / {len(scored)} =====")
    for s in feasibles[:10]:
        print(f"  {s['id']:<4} norm={s['review']['normalized_total']:.3f}  "
              f"ppl_est={s['estimate']['expected_holdout_ppl']:>5}  "
              f"family={s['genome_axes'].get('model_family')}  "
              f"corpus={s['genome_axes'].get('corpus_size_class')}  "
              f"paradigm={s['genome_axes'].get('training_paradigm')}")

    if feasibles:
        winner = feasibles[0]
        print()
        print(f"===== feasible winner: {winner['id']} =====")
        print(json.dumps({
            "id": winner["id"],
            "cell": winner["cell"],
            "genome_axes": winner["genome_axes"],
            "estimate": winner["estimate"],
            "review_total": winner["review"]["normalized_total"],
        }, indent=2, ensure_ascii=False))

        out_path = HERE / "out" / "lineage_top.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({
            "winner": winner,
            "feasible_count": len(feasibles),
            "total_individuals": len(scored),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print()
        print(f"wrote scored top → {out_path}")


if __name__ == "__main__":
    main()
