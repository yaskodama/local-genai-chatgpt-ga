"""Stage 2 — real CharRNN training with PyTorch.

Three candidates matching the .aice:
  R1  single_layer_GRU_tied        GRU,  hidden=128, tied embedding
  R2  single_layer_LSTM_untied     LSTM, hidden=128, untied
  R3  GRU_with_input_dropout       GRU,  hidden=128, tied, dropout=0.1

Each candidate trains on the pinned corpus split (95% train / 5% holdout)
with deterministic seed and reports a measured holdout perplexity.
"""

from __future__ import annotations
import math
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))


VOCAB = 256
SEED = 42
BPTT = 64
BATCH = 32
LR = 3e-3
WD = 0.01
STEPS = 1500
WARMUP = 100
GRAD_CLIP = 1.0
EVAL_EVERY = 100


class CharRNN(nn.Module):
    """Embed → optional dropout → GRU/LSTM → tied/untied output projection."""

    def __init__(self, hidden: int = 128, cell: str = "GRU",
                 dropout: float = 0.0, tied: bool = True):
        super().__init__()
        self.tied = tied
        self.embed = nn.Embedding(VOCAB, hidden)
        self.drop = nn.Dropout(dropout) if dropout > 0 else nn.Identity()
        if cell == "GRU":
            self.rnn = nn.GRU(hidden, hidden, batch_first=True)
        elif cell == "LSTM":
            self.rnn = nn.LSTM(hidden, hidden, batch_first=True)
        else:
            raise ValueError(cell)
        if not tied:
            self.proj = nn.Linear(hidden, VOCAB)

    def forward(self, x: torch.Tensor, h=None):
        e = self.drop(self.embed(x))
        out, h = self.rnn(e, h)
        if self.tied:
            logits = out @ self.embed.weight.T
        else:
            logits = self.proj(out)
        return logits, h


def count_params(m: nn.Module) -> int:
    return sum(p.numel() for p in m.parameters())


def _make_batches(buf: torch.Tensor, batch: int, bptt: int):
    """Split 1-D byte tensor into [batch, length] sequential blocks."""
    n_full = (buf.size(0) // batch) * batch
    buf = buf[:n_full].view(batch, -1)
    return buf


def train_one(spec: dict, train_bytes: bytes, holdout_bytes: bytes,
              device: str = "cpu") -> dict:
    torch.manual_seed(SEED)
    train_t = torch.tensor(list(train_bytes), dtype=torch.long, device=device)
    hold_t = torch.tensor(list(holdout_bytes), dtype=torch.long, device=device)

    train_buf = _make_batches(train_t, BATCH, BPTT)
    seq_len = train_buf.size(1)

    model = CharRNN(hidden=spec["hidden"], cell=spec["cell"],
                    dropout=spec["dropout"], tied=spec["tied"]).to(device)
    n_params = count_params(model)
    opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WD)
    loss_fn = nn.CrossEntropyLoss()

    def _eval_holdout() -> float:
        model.eval()
        with torch.no_grad():
            x = hold_t[:-1].unsqueeze(0)
            y = hold_t[1:].unsqueeze(0)
            logits, _ = model(x)
            nll = loss_fn(logits.reshape(-1, VOCAB), y.reshape(-1)).item()
        model.train()
        return math.exp(nll)

    t0 = time.time()
    model.train()
    cursor = 0
    last_loss = None
    best_ppl = float("inf")
    best_state = None
    best_step = 0
    for step in range(STEPS):
        if cursor + BPTT + 1 > seq_len:
            cursor = 0
        x = train_buf[:, cursor : cursor + BPTT]
        y = train_buf[:, cursor + 1 : cursor + BPTT + 1]
        cursor += BPTT
        if y.size(1) < BPTT:
            cursor = 0
            continue
        logits, _ = model(x)
        loss = loss_fn(logits.reshape(-1, VOCAB), y.reshape(-1))
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        for g in opt.param_groups:
            g["lr"] = LR * min(1.0, (step + 1) / WARMUP)
        opt.step()
        last_loss = loss.item()

        if (step + 1) % EVAL_EVERY == 0:
            ppl_now = _eval_holdout()
            if ppl_now < best_ppl:
                best_ppl = ppl_now
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                best_step = step + 1

    train_time = time.time() - t0

    if best_state is not None:
        model.load_state_dict(best_state)
    ppl = best_ppl if best_state is not None else _eval_holdout()

    return {
        "name": spec["name"],
        "style": spec["style"],
        "params_observed": n_params,
        "holdout_ppl": ppl,
        "best_step": best_step,
        "train_time_sec": round(train_time, 2),
        "final_train_loss": round(last_loss or 0, 4),
        "model_state": model.state_dict(),
        "config": {"hidden": spec["hidden"], "cell": spec["cell"],
                   "dropout": spec["dropout"], "tied": spec["tied"]},
    }


SPECS = [
    {"name": "R1", "style": "single_layer_GRU_tied",
     "hidden": 128, "cell": "GRU", "dropout": 0.0, "tied": True},
    {"name": "R2", "style": "single_layer_LSTM_untied",
     "hidden": 128, "cell": "LSTM", "dropout": 0.0, "tied": False},
    {"name": "R3", "style": "GRU_with_input_dropout",
     "hidden": 128, "cell": "GRU", "dropout": 0.1, "tied": True},
]


def run_all(train_bytes: bytes, holdout_bytes: bytes, device: str = "cpu"):
    return [train_one(spec, train_bytes, holdout_bytes, device) for spec in SPECS]


@torch.no_grad()
def generate(model: nn.Module, prompt: bytes, max_chars: int = 200,
             temperature: float = 1.0, seed: int = 0,
             device: str = "cpu") -> bytes:
    g = torch.Generator(device=device).manual_seed(seed)
    model.eval()
    if not prompt:
        prompt = b". "
    x = torch.tensor(list(prompt), dtype=torch.long, device=device).unsqueeze(0)
    logits, h = model(x)
    out = bytearray()
    last = logits[0, -1] / max(temperature, 1e-3)
    for _ in range(max_chars):
        probs = torch.softmax(last, dim=-1)
        nxt = int(torch.multinomial(probs, 1, generator=g).item())
        out.append(nxt)
        if nxt == ord(".") and len(out) >= 20:
            break
        if nxt == ord("\n"):
            break
        x = torch.tensor([[nxt]], dtype=torch.long, device=device)
        logits, h = model(x, h)
        last = logits[0, -1] / max(temperature, 1e-3)
    return bytes(out)
