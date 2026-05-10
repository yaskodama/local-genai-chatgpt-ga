"""Train the AIPL-evolved I10-style genome on the 10KB corpus and
compare to the existing R2 LSTM checkpoint.

Genome (from AIPL lineage I10):
  single_block_transformer / d_model=192 / n_heads=4 / ctx=128
  positional=learned_absolute / norm=rmsnorm / regularization=none
  training=maximum_likelihood_sgd

Saves the trained transformer to out/evolved_transformer.pt for chat.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

import torch

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import load_corpus, split_corpus
from candidates.transformer_real import train_and_eval


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="100KB", choices=["10KB", "100KB"])
    p.add_argument("--device", default="cpu", choices=["cpu", "mps"])
    args = p.parse_args()

    raw = load_corpus(args.corpus)
    train, holdout = split_corpus(raw)
    print(f"corpus: {args.corpus} ({len(raw)} bytes)  "
          f"train {len(train)}  holdout {len(holdout)}")

    spec = {"d_model": 128, "n_heads": 4, "ctx": 128,
            "depth": 4, "dropout": 0.05}
    print(f"genome: {spec}  device: {args.device}")
    print(f"training a {spec['depth']}-block Transformer ...")

    result = train_and_eval(d_model=spec["d_model"], n_heads=spec["n_heads"],
                              ctx=spec["ctx"],
                              depth=spec["depth"], dropout=spec["dropout"],
                              steps=6000,
                              train_bytes=train, holdout_bytes=holdout,
                              device=args.device)

    print()
    print(f"params         : {result['params']:,}")
    print(f"best holdout ppl: {result['holdout_ppl']:.3f} (at step {result['best_step']})")
    print(f"train time      : {result['train_time_sec']}s")

    out_dir = HERE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = out_dir / "evolved_transformer.pt"
    torch.save({
        "name": "I10_TinyTransformer",
        "style": "single_block_transformer_learned_pos_rmsnorm",
        "config": result["config"],
        "state_dict": result["model_state"],
        "holdout_ppl": result["holdout_ppl"],
        "params": result["params"],
        "source": "AIPL lineage I10 (LocalGenAIScaledEvolutionJP.abcl)",
    }, ckpt)
    print(f"saved → {ckpt}")

    # Compare to existing R2 LSTM
    r2_ckpt = out_dir / "charrnn_winner.pt"
    if r2_ckpt.exists():
        r2 = torch.load(r2_ckpt, weights_only=False, map_location="cpu")
        print()
        print("===== comparison =====")
        print(f"  Stage 2 R2 LSTM    : ppl {r2['holdout_ppl']:.3f}  params {r2['params']:,}")
        print(f"  Stage 3 I10 Tx     : ppl {result['holdout_ppl']:.3f}  params {result['params']:,}")
        delta = r2["holdout_ppl"] - result["holdout_ppl"]
        sign = "↓" if delta > 0 else "↑"
        print(f"  delta              : {sign} {abs(delta):.3f} ppl")


if __name__ == "__main__":
    main()
