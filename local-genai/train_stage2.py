"""Run stage 2 (CharRNN) training for real, score with the same 3
reviewers, save the winner's checkpoint to out/charrnn_winner.pt.

Usage:
    local-genai/.venv/bin/python local-genai/train_stage2.py
    local-genai/.venv/bin/python local-genai/train_stage2.py --device mps
"""

from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

import torch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import load_corpus, split_corpus
from candidates.charrnn_real import run_all, SPECS
from reviewers import review_all
from stages import STAGES


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="cpu",
                   choices=["cpu", "mps"])
    p.add_argument("--corpus", default="10KB", choices=["10KB", "100KB"])
    return p.parse_args()


def main():
    args = parse_args()
    device = args.device
    if device == "mps" and not torch.backends.mps.is_available():
        print("[warn] mps not available, falling back to cpu")
        device = "cpu"

    raw = load_corpus(args.corpus)
    train, holdout = split_corpus(raw)
    print(f"corpus: {len(raw)} bytes  train {len(train)}  holdout {len(holdout)}")
    print(f"device: {device}")
    print()

    print("===== CharRNN (stage 2, real training) =====")
    t0 = time.time()
    measured = run_all(train, holdout, device=device)
    print(f"  total train time: {time.time() - t0:.1f}s")
    print()

    stage2 = next(s for s in STAGES if s["name"] == "CharRNN")
    cand_by_name = {c["name"]: c for c in stage2["candidates"]}

    results = []
    for m in measured:
        cand = dict(cand_by_name[m["name"]])
        est = {
            "params": m["params_observed"],
            "param_class": "100K",
            "param_budget": 200_000,
            "over_budget": m["params_observed"] > 200_000,
            "expected_holdout_ppl": round(m["holdout_ppl"], 3),
            "flops_per_token": 2 * m["params_observed"],
            "train_time_min_estimate": round(m["train_time_sec"] / 60, 2),
            "inference_throughput_factor": 1.0,
            "coherence_violations": [],
            "measurement_kind": f"real_pytorch_training_on_{device}",
        }
        review = review_all(est, cand)
        results.append({"genome": cand, "estimate": est,
                        "review": review,
                        "model_state": m["model_state"],
                        "config": m["config"]})

    for r in results:
        g, est, rv = r["genome"], r["estimate"], r["review"]
        print(f"  [{g['name']:<4}] ppl={est['expected_holdout_ppl']:>7}  "
              f"params={est['params']:>9,}  "
              f"q={rv['quality']['total']}/12  "
              f"e={rv['efficiency']['total']}/12  "
              f"r={rv['reproducibility']['total']}/10  "
              f"norm={rv['normalized_total']:.3f}  "
              f"({est['train_time_min_estimate']:.1f}min)")
    print()

    winner = min(results, key=lambda r: r["estimate"]["expected_holdout_ppl"])
    by_score = max(results, key=lambda r: r["review"]["normalized_total"])
    print(f"  best ppl       → {winner['genome']['name']} "
          f"(ppl={winner['estimate']['expected_holdout_ppl']})")
    print(f"  best norm score → {by_score['genome']['name']} "
          f"(norm={by_score['review']['normalized_total']:.3f})")
    pick = by_score
    print(f"  → winner (by reviewer score): {pick['genome']['name']}")
    print()

    out_dir = HERE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_dir / "charrnn_winner.pt"
    torch.save({
        "name": pick["genome"]["name"],
        "style": pick["genome"]["style"],
        "config": pick["config"],
        "state_dict": pick["model_state"],
        "holdout_ppl": pick["estimate"]["expected_holdout_ppl"],
        "params": pick["estimate"]["params"],
    }, ckpt_path)
    print(f"saved winner checkpoint → {ckpt_path}")

    # Also write the JSON archive (without state_dict for readability).
    archive = []
    for r in results:
        archive.append({
            "genome": r["genome"],
            "estimate": r["estimate"],
            "review": r["review"],
            "config": r["config"],
        })
    json_path = out_dir / "stage_CharRNN_real.json"
    json_path.write_text(json.dumps(archive, indent=2, ensure_ascii=False),
                         encoding="utf-8")
    print(f"saved archive json → {json_path}")


if __name__ == "__main__":
    main()
