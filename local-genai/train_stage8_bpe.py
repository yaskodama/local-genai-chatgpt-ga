"""Stage 8 — BPE tokenizer + transformer on 10MB or mixed GA corpora.

Hypothesis: a 1024-token BPE tokenizer should compress the ~10 MB corpus
to ~2-3 MB of tokens (avg ~4 bytes/token), giving the transformer
roughly 4x effective context per fixed sequence length without changing
its architecture.

We compare in bits-per-byte (BPB), which is the standard
tokenizer-agnostic metric:

    BPB = (total cross-entropy in nats on holdout) /
          (ln(2) * total_bytes_in_holdout)

So a byte-level model with ppl 4.04 corresponds to
BPB = log2(4.04) ≈ 2.01.  Stage-8-BPE will be a win if its BPB on the
same 10 MB tail (measured in raw bytes) is < 2.01.

Output:
    out/tokenizer_stage8_bpe.json    (BPE merges + vocab)
    out/transformer_stage8_bpe.pt    (trained model)
    out/stage_stage8_bpe_real.json   (metrics + recipe)
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

from common import load_corpus, split_corpus


def train_tokenizer(train_bytes: bytes, vocab_size: int, save_path: Path):
    try:
        from tokenizers import Tokenizer
        from tokenizers.models import BPE
        from tokenizers.trainers import BpeTrainer
        from tokenizers.pre_tokenizers import ByteLevel
        from tokenizers.decoders import ByteLevel as ByteLevelDecoder
    except ImportError as e:
        sys.exit(f"need tokenizers package: pip install tokenizers (error: {e})")

    tok = Tokenizer(BPE(unk_token="<unk>"))
    tok.pre_tokenizer = ByteLevel(add_prefix_space=False)
    tok.decoder = ByteLevelDecoder()
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        special_tokens=["<unk>"],
        initial_alphabet=ByteLevel.alphabet(),
        show_progress=False,
    )
    # Tokenizers API expects an iterator of strings.
    # Split corpus into lines so the trainer doesn't see one giant string.
    text = train_bytes.decode("utf-8", errors="replace")
    lines = text.split("\n")
    tok.train_from_iterator(lines, trainer)
    tok.save(str(save_path))
    return tok


def encode_corpus(tok, raw: bytes) -> list[int]:
    text = raw.decode("utf-8", errors="replace")
    # Encode line-by-line so very long inputs don't blow memory; concat IDs.
    ids: list[int] = []
    for line in text.split("\n"):
        ids.extend(tok.encode(line + "\n").ids)
    return ids


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="10MB",
                   choices=["10KB", "100KB", "1MB", "10MB", "30MB_MIXED_EN_JA"])
    p.add_argument("--vocab-size", type=int, default=1024)
    p.add_argument("--device", default="mps", choices=["cpu", "mps"])
    p.add_argument("--d-model", type=int, default=128)
    p.add_argument("--n-heads", type=int, default=4)
    p.add_argument("--depth", type=int, default=6)
    p.add_argument("--ctx", type=int, default=256)
    p.add_argument("--bptt", type=int, default=256)
    p.add_argument("--batch", type=int, default=24)
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--lr", type=float, default=2e-3)
    p.add_argument("--dropout", type=float, default=0.1)
    p.add_argument("--label-smoothing", type=float, default=0.05)
    p.add_argument("--weight-decay", type=float, default=0.05)
    p.add_argument("--eval-every", type=int, default=500)
    p.add_argument("--warmup", type=int, default=1500)
    p.add_argument("--min-lr-frac", type=float, default=0.005)
    p.add_argument("--pos-encoding", default="rope", choices=["learned", "rope"])
    p.add_argument("--out-name", default="transformer_stage8_bpe.pt")
    p.add_argument("--tokenizer-name", default="tokenizer_stage8_bpe.json")
    args = p.parse_args()

    try:
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from candidates.transformer_real import TinyTransformer
    except ImportError as e:
        sys.exit(f"need torch package: pip install torch (error: {e})")

    out_dir = HERE / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    tok_path = out_dir / args.tokenizer_name

    raw = load_corpus(args.corpus)
    train_bytes, holdout_bytes = split_corpus(raw)
    print(f"corpus: {args.corpus} ({len(raw):,} bytes)  "
          f"train {len(train_bytes):,}  holdout {len(holdout_bytes):,}")

    print(f"training BPE tokenizer (target vocab {args.vocab_size}) ...",
          flush=True)
    t0 = time.time()
    tok = train_tokenizer(train_bytes, args.vocab_size, tok_path)
    print(f"  tokenizer trained in {time.time() - t0:.1f}s, "
          f"saved to {tok_path.name}")
    print(f"  vocab size: {tok.get_vocab_size()}")

    print("encoding corpus ...", flush=True)
    t0 = time.time()
    train_ids = encode_corpus(tok, train_bytes)
    hold_ids = encode_corpus(tok, holdout_bytes)
    print(f"  train: {len(train_bytes):,} bytes → {len(train_ids):,} tokens "
          f"({len(train_bytes) / len(train_ids):.2f} bytes/token)")
    print(f"  hold : {len(holdout_bytes):,} bytes → {len(hold_ids):,} tokens "
          f"({len(holdout_bytes) / len(hold_ids):.2f} bytes/token)")
    print(f"  encode time: {time.time() - t0:.1f}s")

    bytes_per_holdout_token = len(holdout_bytes) / len(hold_ids)

    vocab_size = tok.get_vocab_size()
    if args.bptt > args.ctx:
        raise ValueError(f"bptt {args.bptt} > ctx {args.ctx}")

    device = args.device
    if device == "mps" and not torch.backends.mps.is_available():
        print("[warn] mps not available, falling back to cpu")
        device = "cpu"

    torch.manual_seed(42)
    train_t = torch.tensor(train_ids, dtype=torch.long, device=device)
    hold_t = torch.tensor(hold_ids, dtype=torch.long, device=device)

    # _make_batches inlined: reshape train tensor into [batch, length_per_batch]
    n_full = (train_t.size(0) // args.batch) * args.batch
    train_buf = train_t[:n_full].view(args.batch, -1)
    seq_len = train_buf.size(1)
    print(f"  train_buf: {tuple(train_buf.shape)}  seq_len/batch row: {seq_len}")

    # We need TinyTransformer to accept a different vocab.
    # The current class hardcodes VOCAB=256. Monkeypatch via subclass:
    class VocabTransformer(TinyTransformer):
        pass
    # Replace embed + (potentially) pos to use the new vocab.
    model = VocabTransformer(d_model=args.d_model, n_heads=args.n_heads,
                              ffn_mult=4, ctx=args.ctx, depth=args.depth,
                              dropout=args.dropout,
                              pos_encoding=args.pos_encoding).to(device)
    # Swap out the byte-level embed for a BPE one.
    model.embed = nn.Embedding(vocab_size, args.d_model).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"  model params (vocab={vocab_size}): {n_params:,}")

    opt = torch.optim.AdamW(model.parameters(), lr=args.lr,
                             weight_decay=args.weight_decay)

    def _eval_holdout() -> tuple[float, float]:
        """Return (ppl_per_token, bits_per_byte)."""
        model.eval()
        total_nll, count = 0.0, 0
        chunk = args.ctx
        with torch.no_grad():
            for i in range(0, hold_t.size(0) - 1, chunk):
                seg = hold_t[i : i + chunk + 1]
                if seg.size(0) < 2:
                    break
                x = seg[:-1].unsqueeze(0)
                y = seg[1:].unsqueeze(0)
                logits = model(x)
                # use last dim = vocab_size
                nll = F.cross_entropy(
                    logits.reshape(-1, vocab_size),
                    y.reshape(-1), reduction="sum"
                ).item()
                total_nll += nll
                count += y.numel()
        model.train()
        ppl_tok = math.exp(total_nll / max(1, count))
        # bits-per-byte = total_nats / (ln2 * total_bytes_in_holdout_window)
        bytes_in_window = count * bytes_per_holdout_token
        bpb = total_nll / (math.log(2) * max(1, bytes_in_window))
        return ppl_tok, bpb

    LR_MAX = args.lr
    LR_MIN_FRAC = args.min_lr_frac
    GRAD_CLIP = 1.0

    print(f"training transformer ({args.steps} steps) ...", flush=True)
    t0 = time.time()
    model.train()
    cursor = 0
    best_ppl_tok = float("inf")
    best_bpb = float("inf")
    best_state = None
    best_step = 0
    for step in range(args.steps):
        if cursor + args.bptt + 1 > seq_len:
            cursor = 0
        x = train_buf[:, cursor : cursor + args.bptt]
        y = train_buf[:, cursor + 1 : cursor + args.bptt + 1]
        cursor += args.bptt
        if y.size(1) < args.bptt:
            cursor = 0
            continue
        logits = model(x)
        loss = F.cross_entropy(
            logits.reshape(-1, vocab_size), y.reshape(-1),
            label_smoothing=args.label_smoothing,
        )
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        if step < args.warmup:
            cur_lr = LR_MAX * (step + 1) / args.warmup
        else:
            progress = (step - args.warmup) / max(1, args.steps - args.warmup)
            cur_lr = LR_MAX * (
                LR_MIN_FRAC + (1 - LR_MIN_FRAC) * 0.5 * (1 + math.cos(math.pi * progress))
            )
        for g in opt.param_groups:
            g["lr"] = cur_lr
        opt.step()
        if (step + 1) % args.eval_every == 0:
            ppl_tok, bpb = _eval_holdout()
            if bpb < best_bpb:
                best_ppl_tok = ppl_tok
                best_bpb = bpb
                best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
                best_step = step + 1
            print(f"  step {step+1:>5}  loss {loss.item():.3f}  "
                  f"ppl_tok {ppl_tok:.3f}  bpb {bpb:.3f}  "
                  f"best_bpb {best_bpb:.3f}@{best_step}", flush=True)

    train_time = time.time() - t0
    if best_state is not None:
        model.load_state_dict(best_state)

    print()
    print(f"params         : {n_params:,}")
    print(f"best bpb       : {best_bpb:.4f} (≈ ppl_per_byte {2**best_bpb:.3f}) "
          f"@ step {best_step}")
    print(f"best ppl/token : {best_ppl_tok:.3f}")
    print(f"train time     : {train_time:.1f}s")

    ckpt = out_dir / args.out_name
    torch.save({
        "name": "Stage8_BPE_Transformer",
        "style": f"depth{args.depth}_d{args.d_model}_bpe{vocab_size}",
        "config": {
            "d_model": args.d_model, "n_heads": args.n_heads,
            "ctx": args.ctx, "ffn_mult": 4, "depth": args.depth,
            "dropout": args.dropout, "bptt": args.bptt, "batch": args.batch,
            "lr": args.lr, "steps": args.steps, "warmup": args.warmup,
            "weight_decay": args.weight_decay,
            "label_smoothing": args.label_smoothing,
            "min_lr_frac": args.min_lr_frac,
            "pos_encoding": args.pos_encoding,
            "vocab_size": vocab_size,
            "tokenizer": args.tokenizer_name,
            "bytes_per_token_holdout": bytes_per_holdout_token,
        },
        "state_dict": model.state_dict(),
        "holdout_ppl_token": best_ppl_tok,
        "holdout_bpb": best_bpb,
        "holdout_ppl_byte_equiv": 2 ** best_bpb,
        "params": n_params,
        "corpus": args.corpus,
        "source": "Stage-8-BPE: 1024-vocab byte-level BPE + same recipe",
    }, ckpt)
    print(f"saved → {ckpt}")

    # Derive metrics filename from --out-name so different runs don't clobber.
    out_stem = Path(args.out_name).stem.replace("transformer_", "")
    metrics = out_dir / f"stage_{out_stem}_real.json"
    metrics.write_text(json.dumps({
        "name": "Stage8_BPE_Transformer",
        "params": n_params,
        "vocab_size": vocab_size,
        "bytes_per_token_avg_holdout": bytes_per_holdout_token,
        "best_bpb": best_bpb,
        "best_ppl_byte_equiv": 2 ** best_bpb,
        "best_ppl_token": best_ppl_tok,
        "best_step": best_step,
        "train_time_sec": round(train_time, 2),
        "config": {
            "d_model": args.d_model, "depth": args.depth,
            "steps": args.steps, "corpus": args.corpus,
            "dropout": args.dropout, "label_smoothing": args.label_smoothing,
            "weight_decay": args.weight_decay,
            "min_lr_frac": args.min_lr_frac,
            "pos_encoding": args.pos_encoding,
        },
    }, indent=2))
    print(f"metrics → {metrics}")

    # Compare to byte-level champion (Stage-7-deeper-extend)
    bl_path = out_dir / "transformer_stage7_deeper_extend.pt"
    if bl_path.exists():
        bl = torch.load(bl_path, weights_only=False, map_location="cpu")
        bl_ppl = bl["holdout_ppl"]
        bl_bpb = math.log2(bl_ppl)
        print()
        print("===== bits-per-byte comparison =====")
        print(f"  byte-level (7-deeper-extend, 1.22M): bpb {bl_bpb:.3f}  (ppl {bl_ppl:.3f})")
        print(f"  BPE        (Stage-8-BPE,    {n_params/1e6:.2f}M): bpb {best_bpb:.3f}  "
              f"(ppl/byte ≈ {2**best_bpb:.3f})")
        delta = bl_bpb - best_bpb
        sign = "↓ better" if delta > 0 else "↑ worse"
        print(f"  delta: {sign} by {abs(delta):.3f} bpb")


if __name__ == "__main__":
    main()
