"""Apples-to-apples comparison of all real checkpoints on the SAME holdout.

The Stage-2 LSTM was trained on a 100KB corpus and its reported ppl is
against that 100KB holdout (5KB). Stage-4 was trained on the 1MB corpus
and its ppl is against the 1MB holdout (55KB). To pick a true champion
we re-evaluate every checkpoint on a fixed holdout (the 1MB tail).
"""

from __future__ import annotations
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


def main():
    raw = load_corpus("1MB")
    train, holdout = split_corpus(raw)
    print(f"shared holdout: 1MB tail, {len(holdout)} bytes")
    hold_t = torch.tensor(list(holdout), dtype=torch.long)

    rows = []

    # Stage 2 — RNN family
    for fname, label in [("charrnn_winner.pt", "100KB"), ("charrnn_1MB.pt", "1MB")]:
        path = HERE / "out" / fname
        if not path.exists():
            continue
        ckpt = torch.load(path, weights_only=False, map_location="cpu")
        cfg = ckpt["config"]
        model = CharRNN(hidden=cfg["hidden"], cell=cfg["cell"],
                        dropout=cfg["dropout"], tied=cfg["tied"])
        model.load_state_dict(ckpt["state_dict"])
        ppl_1mb = _eval_lstm(model, hold_t)
        rows.append({
            "name": f"{ckpt['name']}_{label}",
            "params": ckpt["params"],
            "trained_on": ckpt.get("corpus", label),
            "ppl_reported": ckpt["holdout_ppl"],
            "ppl_on_1MB_tail": ppl_1mb,
        })

    # Stage 3 — Transformer I10 (single-block, ctx=128)
    s3_path = HERE / "out" / "evolved_transformer.pt"
    if s3_path.exists():
        ckpt = torch.load(s3_path, weights_only=False, map_location="cpu")
        cfg = ckpt["config"]
        model = TinyTransformer(d_model=cfg["d_model"], n_heads=cfg["n_heads"],
                                ffn_mult=cfg.get("ffn_mult", 4),
                                ctx=cfg["ctx"], depth=cfg.get("depth", 1),
                                dropout=cfg.get("dropout", 0.0))
        model.load_state_dict(ckpt["state_dict"])
        ppl_1mb = _eval_transformer(model, hold_t, ctx=cfg["ctx"])
        rows.append({
            "name": ckpt["name"],
            "params": ckpt["params"],
            "trained_on": ckpt.get("corpus", "100KB"),
            "ppl_reported": ckpt["holdout_ppl"],
            "ppl_on_1MB_tail": ppl_1mb,
        })

    # Stage 4 / 4b — full-context transformers on 1MB
    for fname, label in [("transformer_stage4.pt", "Stage4"),
                          ("transformer_stage4b.pt", "Stage4b")]:
        path = HERE / "out" / fname
        if not path.exists():
            continue
        ckpt = torch.load(path, weights_only=False, map_location="cpu")
        cfg = ckpt["config"]
        model = TinyTransformer(d_model=cfg["d_model"], n_heads=cfg["n_heads"],
                                ffn_mult=cfg.get("ffn_mult", 4),
                                ctx=cfg["ctx"], depth=cfg.get("depth", 1),
                                dropout=cfg.get("dropout", 0.0))
        model.load_state_dict(ckpt["state_dict"])
        ppl_1mb = _eval_transformer(model, hold_t, ctx=cfg["ctx"])
        rows.append({
            "name": f"{label}_{ckpt['name']}",
            "params": ckpt["params"],
            "trained_on": ckpt.get("corpus", "?"),
            "ppl_reported": ckpt["holdout_ppl"],
            "ppl_on_1MB_tail": ppl_1mb,
        })

    print()
    print(f"{'name':<32} {'params':>10} {'trained_on':>10} {'reported_ppl':>14} {'1MB_tail_ppl':>14}")
    for r in rows:
        print(f"{r['name']:<32} {r['params']:>10,} {str(r['trained_on']):>10} "
              f"{r['ppl_reported']:>14.3f} {r['ppl_on_1MB_tail']:>14.3f}")

    print()
    best = min(rows, key=lambda r: r["ppl_on_1MB_tail"])
    print(f"=> champion (1MB tail): {best['name']}  ppl {best['ppl_on_1MB_tail']:.3f}")


if __name__ == "__main__":
    main()
