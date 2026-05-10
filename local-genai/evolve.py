"""Main evolution driver.

Walks the 7 stages.  For stage 1 (NGramFreq) it runs the actual
n-gram training/eval on the pinned corpus; for stages 2–7 it derives
holdout_ppl + budgets from the genome via the design estimator.
Each stage:
  - generates 3 candidates (from stages.py)
  - estimates / measures
  - scores via 3 reviewers
  - picks the candidate with the highest normalized review total
  - writes JSON archive to out/

Run:
    python3 local-genai/evolve.py
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import load_corpus, split_corpus, CORPUS_SHA256
from candidates.design_estimator import estimate
from candidates.ngram_real import run_all as run_ngrams
from reviewers import review_all
from stages import STAGES


OUT_DIR = HERE / "out"


def evaluate_stage_1(stage):
    raw = load_corpus()
    train, holdout = split_corpus(raw)
    print(f"  corpus: {len(raw)} bytes, train {len(train)}, holdout {len(holdout)}")
    measured = run_ngrams(train, holdout)
    measured_by_name = {m["name"]: m for m in measured}

    results = []
    for cand in stage["candidates"]:
        m = measured_by_name[cand["name"]]
        est = {
            "params": m["params_observed"],
            "param_class": cand["param_class"],
            "param_budget": 64_000,
            "over_budget": m["params_observed"] > 64_000,
            "expected_holdout_ppl": round(m["holdout_ppl"], 3),
            "flops_per_token": 2,
            "train_time_min_estimate": 0.05,
            "inference_throughput_factor": 1.0,
            "coherence_violations": [],
            "measurement_kind": "real_ngram_training_on_pinned_corpus",
        }
        review = review_all(est, cand)
        results.append({"genome": cand, "estimate": est, "review": review})
    return results


def evaluate_stage_n(stage):
    results = []
    for cand in stage["candidates"]:
        est = estimate(cand)
        est["measurement_kind"] = "design_estimator_formula"
        review = review_all(est, cand)
        results.append({"genome": cand, "estimate": est, "review": review})
    return results


def pick_winner(results):
    best = max(results, key=lambda r: r["review"]["normalized_total"])
    return best


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"corpus sha256 = {CORPUS_SHA256}")
    print(f"stages: {len(STAGES)}")
    print()

    archive = []
    parent = None
    for stage in STAGES:
        print(f"===== {stage['name']} (branch={stage['branch']}, "
              f"param_class={stage['param_class']}) =====")
        if stage["real_train"]:
            results = evaluate_stage_1(stage)
        else:
            results = evaluate_stage_n(stage)

        for r in results:
            g, est, rv = r["genome"], r["estimate"], r["review"]
            print(f"  [{g['name']:<4}] ppl={est['expected_holdout_ppl']:>6}  "
                  f"params={est['params']:>9,}  "
                  f"q={rv['quality']['total']}/12  "
                  f"e={rv['efficiency']['total']}/12  "
                  f"r={rv['reproducibility']['total']}/10  "
                  f"norm={rv['normalized_total']:.3f}")

        winner = pick_winner(results)
        print(f"  → winner: {winner['genome']['name']} "
              f"({winner['genome']['style']}) "
              f"normalized_total={winner['review']['normalized_total']:.3f}")
        if winner["estimate"]["coherence_violations"]:
            print(f"    coherence_violations: "
                  f"{winner['estimate']['coherence_violations']}")
        print()

        archive_entry = {
            "stage": stage["name"],
            "branch": stage["branch"],
            "parent": parent,
            "winner": winner,
            "all_candidates": results,
        }
        archive.append(archive_entry)
        out_path = OUT_DIR / f"stage_{stage['name']}.json"
        out_path.write_text(json.dumps(archive_entry, indent=2,
                                       ensure_ascii=False), encoding="utf-8")
        parent = winner["genome"]["name"]

    final_path = OUT_DIR / "final_archive.json"
    final_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False),
                          encoding="utf-8")

    print("===== summary =====")
    for entry in archive:
        w = entry["winner"]
        print(f"  {entry['stage']:<18} winner={w['genome']['name']:<4} "
              f"ppl={w['estimate']['expected_holdout_ppl']:>6}  "
              f"params={w['estimate']['params']:>9,}  "
              f"score={w['review']['normalized_total']:.3f}")

    print()
    print(f"final archive: {final_path}")
    print(f"per-stage archives: {OUT_DIR}/stage_*.json")


if __name__ == "__main__":
    main()
