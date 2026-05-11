"""Dependency-free n-gram baseline for any registered corpus.

This does not replace the evolved BPE transformer. It gives a quick measured
baseline and verifies that a corpus can be loaded, split, and evaluated without
PyTorch or tokenizers.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from candidates.ngram_real import run_all
from common import load_corpus, split_corpus


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="10KB")
    p.add_argument(
        "--limit-bytes",
        type=int,
        default=2_000_000,
        help="limit loaded corpus bytes for a fast baseline; 0 means full corpus",
    )
    p.add_argument("--out-name", default="stage_ngram_baseline_mixed.json")
    args = p.parse_args()

    raw = load_corpus(args.corpus)
    full_bytes = len(raw)
    if args.limit_bytes and len(raw) > args.limit_bytes:
        raw = raw[: args.limit_bytes]

    train, holdout = split_corpus(raw)
    print(
        f"corpus: {args.corpus} full={full_bytes:,} used={len(raw):,} "
        f"train={len(train):,} holdout={len(holdout):,}"
    )

    t0 = time.time()
    results = run_all(train, holdout)
    elapsed = time.time() - t0
    for r in results:
        bpb = math.log2(r["holdout_ppl"])
        print(
            f"  {r['name']:<2} {r['style']:<24} "
            f"ppl={r['holdout_ppl']:.3f} bpb={bpb:.3f} "
            f"params={r['params_observed']:,}"
        )

    out_dir = HERE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / args.out_name
    out_path.write_text(
        json.dumps(
            {
                "corpus": args.corpus,
                "full_bytes": full_bytes,
                "used_bytes": len(raw),
                "train_bytes": len(train),
                "holdout_bytes": len(holdout),
                "train_time_sec": round(elapsed, 3),
                "results": [
                    {
                        **r,
                        "holdout_bpb": math.log2(r["holdout_ppl"]),
                    }
                    for r in results
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"metrics -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
