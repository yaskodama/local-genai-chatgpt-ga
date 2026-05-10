"""Stage 4 — depth-4 Transformer on 1MB corpus, ctx=BPTT=256.

Goal: close the gap to the R2 LSTM champion (holdout ppl 5.23 on 100KB)
by giving the transformer (a) full-context training (BPTT == ctx) and
(b) a corpus large enough that overfitting is no longer the dominant
failure mode of stages 3.

Genome:
  d_model=192, n_heads=6, depth=4, ffn_mult=4, ctx=256, bptt=256
  positional=learned_absolute, norm=rmsnorm, regularization=dropout 0.1
  training=adamw + warmup + cosine decay + grad clip 1.0
  corpus_size=1MB
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
    p.add_argument("--corpus", default="1MB", choices=["10KB", "100KB", "1MB"])
    p.add_argument("--device", default="mps", choices=["cpu", "mps"])
    p.add_argument("--d-model", type=int, default=192)
    p.add_argument("--n-heads", type=int, default=6)
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--ctx", type=int, default=256)
    p.add_argument("--bptt", type=int, default=256)
    p.add_argument("--batch", type=int, default=24)
    p.add_argument("--steps", type=int, default=8000)
    p.add_argument("--lr", type=float, default=2e-3)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--eval-every", type=int, default=400)
    p.add_argument("--warmup", type=int, default=600)
    p.add_argument("--out-name", default="transformer_stage4.pt")
    args = p.parse_args()

    raw = load_corpus(args.corpus)
    train, holdout = split_corpus(raw)
    print(f"corpus: {args.corpus} ({len(raw)} bytes)  "
          f"train {len(train)}  holdout {len(holdout)}")

    spec = {
        "d_model": args.d_model, "n_heads": args.n_heads,
        "depth": args.depth, "ctx": args.ctx,
        "bptt": args.bptt, "batch": args.batch,
        "dropout": args.dropout, "lr": args.lr,
        "steps": args.steps, "warmup": args.warmup,
    }
    print(f"genome: {spec}")
    print(f"device: {args.device}")
    print(f"training Stage-4 transformer ...", flush=True)

    result = train_and_eval(
        d_model=args.d_model, n_heads=args.n_heads, ctx=args.ctx,
        depth=args.depth, dropout=args.dropout,
        steps=args.steps, train_bytes=train, holdout_bytes=holdout,
        device=args.device,
        bptt=args.bptt, batch=args.batch, lr=args.lr,
        eval_every=args.eval_every, warmup=args.warmup,
        verbose=True,
    )

    print()
    print(f"params         : {result['params']:,}")
    print(f"best holdout ppl: {result['holdout_ppl']:.3f} (at step {result['best_step']})")
    print(f"train time      : {result['train_time_sec']}s")

    out_dir = HERE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = out_dir / args.out_name
    torch.save({
        "name": "Stage4_FullCtx_Transformer",
        "style": f"depth{args.depth}_d{args.d_model}_h{args.n_heads}_ctx{args.ctx}_rmsnorm_learned_pos",
        "config": result["config"],
        "state_dict": result["model_state"],
        "holdout_ppl": result["holdout_ppl"],
        "params": result["params"],
        "corpus": args.corpus,
        "source": "Stage 4 — full-context transformer on 1MB corpus",
    }, ckpt)
    print(f"saved → {ckpt}")

    # Save metrics JSON for evolve.py / scorers — derive name from out_name
    stem = Path(args.out_name).stem
    suffix = stem.replace("transformer_", "").replace("_smoke", "")
    metrics_path = out_dir / f"stage_{suffix}_real.json"
    metrics = {
        "name": "Stage4_FullCtx_Transformer",
        "corpus": args.corpus,
        "config": result["config"],
        "params": result["params"],
        "holdout_ppl": result["holdout_ppl"],
        "best_step": result["best_step"],
        "train_time_sec": result["train_time_sec"],
        "source": "Stage 4 — full-context transformer on 1MB corpus",
    }
    metrics_path.write_text(json.dumps(metrics, indent=2))
    print(f"metrics → {metrics_path}")

    # Compare to existing R2 LSTM champion
    r2_ckpt = out_dir / "charrnn_winner.pt"
    if r2_ckpt.exists():
        r2 = torch.load(r2_ckpt, weights_only=False, map_location="cpu")
        print()
        print("===== comparison =====")
        print(f"  Stage 2 R2 LSTM   : ppl {r2['holdout_ppl']:.3f}  params {r2['params']:,}")
        print(f"  Stage 4 Tx (1MB)  : ppl {result['holdout_ppl']:.3f}  params {result['params']:,}")
        delta = r2["holdout_ppl"] - result["holdout_ppl"]
        sign = "↓ better" if delta > 0 else "↑ worse"
        print(f"  delta             : {sign} by {abs(delta):.3f} ppl")


if __name__ == "__main__":
    main()
