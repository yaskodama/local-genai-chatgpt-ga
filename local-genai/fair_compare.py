"""Apples-to-apples comparison of all real checkpoints on the SAME holdout.

Each model reports a perplexity against whatever holdout it was trained
with — different sizes, different texts. To pick a true champion we
re-evaluate every checkpoint on one shared holdout. By default we use
the 1MB-corpus tail (~55KB) for backward compatibility with the legacy
benchmark; pass --corpus 10MB for the larger, more recent benchmark
(~500KB tail of the 10MB Shakespeare + KJV corpus).
"""

from __future__ import annotations
import argparse
import math
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import load_corpus, split_corpus
from candidates.charrnn_real import CharRNN
from candidates.transformer_real import TinyTransformer

VOCAB = 256


def _eval_lstm(model: CharRNN, hold_t: torch.Tensor) -> float:
    model.eval()
    with torch.no_grad():
        x = hold_t[:-1].unsqueeze(0)
        y = hold_t[1:].unsqueeze(0)
        logits, _ = model(x)
        nll = F.cross_entropy(logits.reshape(-1, VOCAB),
                              y.reshape(-1), reduction="sum").item()
        count = y.numel()
    return math.exp(nll / max(1, count))


def _eval_transformer(model: TinyTransformer, hold_t: torch.Tensor,
                      ctx: int) -> float:
    """Sliding-window eval. We feed the model ctx-byte windows; for each
    window the loss target is the next ctx bytes. To avoid double-counting,
    we step by ctx (non-overlapping). The first byte of holdout has no
    history so we drop one byte at the boundary."""
    model.eval()
    total_nll, count = 0.0, 0
    with torch.no_grad():
        for i in range(0, hold_t.size(0) - 1, ctx):
            seg = hold_t[i : i + ctx + 1]
            if seg.size(0) < 2:
                break
            x = seg[:-1].unsqueeze(0)
            y = seg[1:].unsqueeze(0)
            logits = model(x)
            nll = F.cross_entropy(logits.reshape(-1, VOCAB),
                                  y.reshape(-1), reduction="sum").item()
            total_nll += nll
            count += y.numel()
    return math.exp(total_nll / max(1, count))


TRANSFORMER_CHECKPOINTS = [
    # 1MB-trained transformers (Stage-3 / 4 series)
    ("transformer_stage4.pt", "Stage4"),
    ("transformer_stage4b.pt", "Stage4b"),
    ("transformer_stage4c.pt", "Stage4c"),
    ("transformer_stage4d_orth.pt", "Stage4d_orth"),
    ("transformer_stage4e.pt", "Stage4e"),
    ("transformer_stage4f_mini.pt", "Stage4f_mini"),
    ("transformer_stage4f_extend.pt", "Stage4f_extend"),
    ("transformer_stage4g.pt", "Stage4g"),
    ("transformer_stage5_rope.pt", "Stage5_RoPE"),
    # 10MB-trained transformers (Stage-6 series; auto-included when present)
    ("transformer_stage6a.pt", "Stage6a"),
    ("transformer_stage6b_rope.pt", "Stage6b_RoPE"),
    ("transformer_stage6c_large.pt", "Stage6c_large"),
    ("transformer_stage6d_large_rope.pt", "Stage6d_large_RoPE"),
    ("transformer_stage7_deeper.pt", "Stage7_deeper"),
    ("transformer_stage7_deeper_extend.pt", "Stage7_deeper_extend"),
    ("transformer_stage8_wider.pt", "Stage8_wider"),
]

LSTM_CHECKPOINTS = [
    ("charrnn_winner.pt", "100KB"),
    ("charrnn_1MB.pt", "1MB"),
    ("charrnn_10MB.pt", "10MB"),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="1MB", choices=["1MB", "10MB"],
                   help="which corpus tail to use as the shared holdout")
    p.add_argument("--device", default="cpu", choices=["cpu", "mps"])
    args = p.parse_args()

    raw = load_corpus(args.corpus)
    train, holdout = split_corpus(raw)
    print(f"shared holdout: {args.corpus} tail, {len(holdout):,} bytes")
    hold_t = torch.tensor(list(holdout), dtype=torch.long, device=args.device)
    col = f"ppl_on_{args.corpus}_tail"

    rows = []

    # Stage 2 — RNN family
    for fname, label in LSTM_CHECKPOINTS:
        path = HERE / "out" / fname
        if not path.exists():
            continue
        ckpt = torch.load(path, weights_only=False, map_location=args.device)
        cfg = ckpt["config"]
        model = CharRNN(hidden=cfg["hidden"], cell=cfg["cell"],
                        dropout=cfg["dropout"], tied=cfg["tied"]).to(args.device)
        model.load_state_dict(ckpt["state_dict"])
        ppl = _eval_lstm(model, hold_t)
        rows.append({
            "name": f"{ckpt['name']}_{label}",
            "params": ckpt["params"],
            "trained_on": ckpt.get("corpus", label),
            "ppl_reported": ckpt["holdout_ppl"],
            col: ppl,
        })

    # Stage 3 — Transformer I10 (legacy, single-block, ctx=128)
    s3_path = HERE / "out" / "evolved_transformer.pt"
    if s3_path.exists():
        ckpt = torch.load(s3_path, weights_only=False, map_location=args.device)
        cfg = ckpt["config"]
        model = TinyTransformer(d_model=cfg["d_model"], n_heads=cfg["n_heads"],
                                ffn_mult=cfg.get("ffn_mult", 4),
                                ctx=cfg["ctx"], depth=cfg.get("depth", 1),
                                dropout=cfg.get("dropout", 0.0),
                                pos_encoding=cfg.get("pos_encoding", "learned")).to(args.device)
        model.load_state_dict(ckpt["state_dict"])
        ppl = _eval_transformer(model, hold_t, ctx=cfg["ctx"])
        rows.append({
            "name": ckpt["name"],
            "params": ckpt["params"],
            "trained_on": ckpt.get("corpus", "100KB"),
            "ppl_reported": ckpt["holdout_ppl"],
            col: ppl,
        })

    # Stage 4 series + Stage 5 (RoPE) + Stage 6 (10MB) — full-context transformers
    for fname, label in TRANSFORMER_CHECKPOINTS:
        path = HERE / "out" / fname
        if not path.exists():
            continue
        ckpt = torch.load(path, weights_only=False, map_location=args.device)
        cfg = ckpt["config"]
        model = TinyTransformer(d_model=cfg["d_model"], n_heads=cfg["n_heads"],
                                ffn_mult=cfg.get("ffn_mult", 4),
                                ctx=cfg["ctx"], depth=cfg.get("depth", 1),
                                dropout=cfg.get("dropout", 0.0),
                                pos_encoding=cfg.get("pos_encoding", "learned")).to(args.device)
        model.load_state_dict(ckpt["state_dict"])
        ppl = _eval_transformer(model, hold_t, ctx=cfg["ctx"])
        rows.append({
            "name": f"{label}_{ckpt['name']}",
            "params": ckpt["params"],
            "trained_on": ckpt.get("corpus", "?"),
            "ppl_reported": ckpt["holdout_ppl"],
            col: ppl,
        })

    print()
    print(f"{'name':<42} {'params':>10} {'trained_on':>10} {'reported_ppl':>14} {col:>16}")
    for r in rows:
        print(f"{r['name']:<42} {r['params']:>10,} {str(r['trained_on']):>10} "
              f"{r['ppl_reported']:>14.3f} {r[col]:>16.3f}")

    print()
    best = min(rows, key=lambda r: r[col])
    print(f"=> champion ({args.corpus} tail): {best['name']}  ppl {best[col]:.3f}")


if __name__ == "__main__":
    main()
