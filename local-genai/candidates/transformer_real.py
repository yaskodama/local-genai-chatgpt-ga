"""Stage 3 — single-block Transformer (PyTorch).

Spec follows the AIPL-evolved I10 genome:
  positional   = learned_absolute
  normalization= rmsnorm
  regularization= none
  inference_opt= kv_cache (eval/inference only — no impact on training)
  training     = maximum_likelihood_sgd
  param_class  = 500K
  corpus_size  = 10KB

Architecture:
  Embed(256, d) + LearnedPositional(ctx, d)
  → RMSNorm → MultiHeadAttention(h=4)
  → RMSNorm → FFN(d, 4d, d)
  → RMSNorm → tied projection back to 256
"""

from __future__ import annotations
import math
import time
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


VOCAB = 256
SEED = 42
BPTT = 64
BATCH = 32
LR = 3e-3
WD = 0.01
STEPS = 6000
WARMUP = 400
GRAD_CLIP = 1.0
EVAL_EVERY = 200
LR_MIN_FRAC = 0.1


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float = 1e-6):
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x):
        rms = x.pow(2).mean(-1, keepdim=True).add(self.eps).sqrt()
        return self.weight * x / rms


class MultiHeadAttention(nn.Module):
    def __init__(self, d_model: int, n_heads: int):
        super().__init__()
        assert d_model % n_heads == 0
        self.h = n_heads
        self.dh = d_model // n_heads
        self.qkv = nn.Linear(d_model, 3 * d_model, bias=False)
        self.proj = nn.Linear(d_model, d_model, bias=False)

    def forward(self, x):
        B, T, D = x.shape
        qkv = self.qkv(x).reshape(B, T, 3, self.h, self.dh).permute(2, 0, 3, 1, 4)
        q, k, v = qkv[0], qkv[1], qkv[2]
        att = q @ k.transpose(-2, -1) / math.sqrt(self.dh)
        mask = torch.tril(torch.ones(T, T, device=x.device, dtype=torch.bool))
        att = att.masked_fill(~mask, float("-inf"))
        att = F.softmax(att, dim=-1)
        y = (att @ v).transpose(1, 2).reshape(B, T, D)
        return self.proj(y)


class TransformerBlock(nn.Module):
    def __init__(self, d_model: int, n_heads: int, ffn_mult: int):
        super().__init__()
        self.norm1 = RMSNorm(d_model)
        self.attn = MultiHeadAttention(d_model, n_heads)
        self.norm2 = RMSNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, ffn_mult * d_model),
            nn.GELU(),
            nn.Linear(ffn_mult * d_model, d_model),
        )

    def forward(self, x):
        x = x + self.attn(self.norm1(x))
        x = x + self.ffn(self.norm2(x))
        return x


class TinyTransformer(nn.Module):
    def __init__(self, d_model: int = 192, n_heads: int = 4,
                 ffn_mult: int = 4, ctx: int = 128, depth: int = 1,
                 dropout: float = 0.0):
        super().__init__()
        self.ctx = ctx
        self.embed = nn.Embedding(VOCAB, d_model)
        self.pos = nn.Embedding(ctx, d_model)
        self.drop = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        self.blocks = nn.ModuleList([
            TransformerBlock(d_model, n_heads, ffn_mult) for _ in range(depth)
        ])
        self.norm = RMSNorm(d_model)

    def forward(self, x):
        B, T = x.shape
        pos_idx = torch.arange(T, device=x.device).unsqueeze(0).expand(B, T)
        h = self.drop(self.embed(x) + self.pos(pos_idx))
        for blk in self.blocks:
            h = blk(h)
        h = self.norm(h)
        return h @ self.embed.weight.T


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def _make_batches(buf, batch, bptt):
    n_full = (buf.size(0) // batch) * batch
    return buf[:n_full].view(batch, -1)


def train_and_eval(d_model: int, n_heads: int, ctx: int,
                   train_bytes: bytes, holdout_bytes: bytes,
                   depth: int = 1, dropout: float = 0.0,
                   steps: int = STEPS,
                   device: str = "cpu",
                   bptt: int | None = None,
                   batch: int | None = None,
                   lr: float | None = None,
                   eval_every: int | None = None,
                   warmup: int | None = None,
                   weight_decay: float | None = None,
                   label_smoothing: float = 0.0,
                   min_lr_frac: float | None = None,
                   verbose: bool = False) -> dict:
    bptt = bptt or BPTT
    batch = batch or BATCH
    lr = lr if lr is not None else LR
    eval_every = eval_every or EVAL_EVERY
    warmup = warmup if warmup is not None else WARMUP
    wd = weight_decay if weight_decay is not None else WD
    min_lr_frac = min_lr_frac if min_lr_frac is not None else LR_MIN_FRAC
    if bptt > ctx:
        raise ValueError(f"bptt ({bptt}) must be <= ctx ({ctx}) since pos embedding is sized to ctx")

    torch.manual_seed(SEED)
    train_t = torch.tensor(list(train_bytes), dtype=torch.long, device=device)
    hold_t = torch.tensor(list(holdout_bytes), dtype=torch.long, device=device)
    train_buf = _make_batches(train_t, batch, bptt)
    seq_len = train_buf.size(1)

    model = TinyTransformer(d_model=d_model, n_heads=n_heads,
                             ffn_mult=4, ctx=ctx, depth=depth,
                             dropout=dropout).to(device)
    n_params = count_params(model)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)

    def _eval_holdout() -> float:
        model.eval()
        total_nll, count = 0.0, 0
        chunk = ctx
        with torch.no_grad():
            for i in range(0, hold_t.size(0) - 1, chunk):
                seg = hold_t[i : i + chunk + 1]
                if seg.size(0) < 2:
                    break
                x = seg[:-1].unsqueeze(0)
                y = seg[1:].unsqueeze(0)
                logits = model(x)
                nll = F.cross_entropy(logits.reshape(-1, VOCAB),
                                       y.reshape(-1), reduction="sum").item()
                total_nll += nll
                count += y.numel()
        model.train()
        return math.exp(total_nll / max(1, count))

    t0 = time.time()
    model.train()
    cursor = 0
    best_ppl = float("inf")
    best_state = None
    best_step = 0
    for step in range(steps):
        if cursor + bptt + 1 > seq_len:
            cursor = 0
        x = train_buf[:, cursor : cursor + bptt]
        y = train_buf[:, cursor + 1 : cursor + bptt + 1]
        cursor += bptt
        if y.size(1) < bptt:
            cursor = 0
            continue
        logits = model(x)
        loss = F.cross_entropy(logits.reshape(-1, VOCAB), y.reshape(-1),
                               label_smoothing=label_smoothing)
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        # warmup + cosine decay
        if step < warmup:
            cur_lr = lr * (step + 1) / warmup
        else:
            progress = (step - warmup) / max(1, steps - warmup)
            cur_lr = lr * (min_lr_frac + (1 - min_lr_frac) * 0.5 * (1 + math.cos(math.pi * progress)))
        for g in opt.param_groups:
            g["lr"] = cur_lr
        opt.step()
        if (step + 1) % eval_every == 0:
            ppl = _eval_holdout()
            if ppl < best_ppl:
                best_ppl = ppl
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                best_step = step + 1
            if verbose:
                print(f"  step {step+1:>5}  loss {loss.item():.3f}  holdout ppl {ppl:.3f}  best {best_ppl:.3f}@{best_step}", flush=True)
    train_time = time.time() - t0
    if best_state is not None:
        model.load_state_dict(best_state)
    return {
        "params": n_params,
        "holdout_ppl": best_ppl,
        "best_step": best_step,
        "train_time_sec": round(train_time, 2),
        "model_state": model.state_dict(),
        "config": {"d_model": d_model, "n_heads": n_heads,
                   "ctx": ctx, "ffn_mult": 4,
                   "depth": depth, "dropout": dropout,
                   "bptt": bptt, "batch": batch, "lr": lr,
                   "steps": steps, "warmup": warmup,
                   "weight_decay": wd, "label_smoothing": label_smoothing,
                   "min_lr_frac": min_lr_frac},
    }


@torch.no_grad()
def generate(model: nn.Module, prompt: bytes, max_chars: int = 200,
             temperature: float = 1.0, seed: int = 0,
             device: str = "cpu") -> bytes:
    g = torch.Generator(device=device).manual_seed(seed)
    model.eval()
    if not prompt:
        prompt = b". "
    seq = list(prompt)
    out = bytearray()
    for _ in range(max_chars):
        ctx_in = seq[-model.ctx:]
        x = torch.tensor([ctx_in], dtype=torch.long, device=device)
        logits = model(x)
        last = logits[0, -1] / max(temperature, 1e-3)
        probs = F.softmax(last, dim=-1)
        nxt = int(torch.multinomial(probs, 1, generator=g).item())
        out.append(nxt)
        seq.append(nxt)
        if nxt == ord(".") and len(out) >= 20:
            break
        if nxt == ord("\n"):
            break
    return bytes(out)
