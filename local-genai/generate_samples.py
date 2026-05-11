"""Generate a fixed set of sample completions from the current champion
(Stage-7-deeper-extend) for qualitative inspection.

The model is a 1.22M-param byte-level transformer trained on a 10 MB
Shakespeare + King James Bible corpus. It is NOT an instruction-tuned
chatbot — it autocompletes whatever bytes it sees in the same Early
Modern English style as its training corpus. We pick 20 prompts of
mixed flavour (modern questions, Shakespearean half-lines, KJV
incantations, single words, names) and let the model run for ~300
characters per prompt at a moderate temperature.

Output: local-genai/samples/samples_stage7_deeper_extend.md
"""

from __future__ import annotations
import sys
from pathlib import Path

import torch
import torch.nn.functional as F

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from candidates.transformer_real import TinyTransformer

CHECKPOINT = HERE / "out" / "transformer_stage7_deeper_extend.pt"
OUT_PATH = HERE / "samples" / "samples_stage7_deeper_extend.md"

VOCAB = 256
MAX_CHARS = 320
TEMPERATURES = (0.6, 0.85, 1.05)  # one row per temperature per prompt
SEED = 7

PROMPTS = [
    # Modern English questions — the model can't answer, will continue.
    "Please explain the use of artificial intelligence in education.",
    "What is the meaning of life?",
    "Describe how a transformer neural network works.",
    "Write a short poem about autumn rain.",
    # Famous Shakespeare half-lines — model should know how to continue.
    "To be, or not to be,",
    "All the world's a stage,",
    "If music be the food of love,",
    "What light through yonder window breaks?",
    # KJV-style openings.
    "In the beginning",
    "And it came to pass",
    "Blessed are the meek,",
    "The Lord is my shepherd;",
    # Single short tokens.
    "Love",
    "Hark!",
    # Names / scene headers.
    "ROMEO. ",
    "HAMLET. To-day",
    "ENTER three Witches.",
    # Cross-distribution probes (Japanese / code / numbers).
    "let x = 1 + 2",
    "こんにちは",
    "1, 2, 3, 4,",
]


@torch.no_grad()
def generate(model: TinyTransformer, prompt_bytes: bytes,
             max_chars: int, temperature: float, seed: int,
             device: str) -> bytes:
    g = torch.Generator(device=device).manual_seed(seed)
    model.eval()
    seq = list(prompt_bytes)
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
    return bytes(out)


def main():
    if not CHECKPOINT.exists():
        sys.exit(f"checkpoint not found: {CHECKPOINT}")
    print(f"loading {CHECKPOINT.name} ...")
    ckpt = torch.load(CHECKPOINT, weights_only=False, map_location="cpu")
    cfg = ckpt["config"]
    print(f"  config: {cfg}")
    print(f"  params: {ckpt['params']:,}  reported ppl: {ckpt['holdout_ppl']:.3f}")

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"  device: {device}")
    model = TinyTransformer(
        d_model=cfg["d_model"], n_heads=cfg["n_heads"],
        ffn_mult=cfg.get("ffn_mult", 4),
        ctx=cfg["ctx"], depth=cfg.get("depth", 1),
        dropout=0.0,  # eval-time dropout off
        pos_encoding=cfg.get("pos_encoding", "learned"),
    ).to(device)
    model.load_state_dict(ckpt["state_dict"])

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Sample generations — Stage-7-deeper-extend\n")
    lines.append(f"Checkpoint: `{CHECKPOINT.name}` "
                 f"({ckpt['params']:,} params, reported ppl "
                 f"{ckpt['holdout_ppl']:.3f} on 10MB tail)\n")
    lines.append(
        "The model is a byte-level autoregressive transformer trained\n"
        "on 10 MB of Shakespeare + King James Bible. It is NOT an\n"
        "instruction-tuned chatbot — it continues whatever bytes it\n"
        "is fed, in the same Early Modern English style as its\n"
        "training data.\n\n"
        f"Each prompt is run at three temperatures "
        f"({', '.join(str(t) for t in TEMPERATURES)}), "
        f"generating {MAX_CHARS} bytes per sample with seed {SEED}.\n"
    )

    for i, prompt in enumerate(PROMPTS, start=1):
        print(f"  [{i:>2}/{len(PROMPTS)}] {prompt[:50]!r}", flush=True)
        lines.append(f"\n## {i}. `{prompt}`\n")
        for temp in TEMPERATURES:
            cont = generate(
                model,
                prompt.encode("utf-8", errors="replace"),
                max_chars=MAX_CHARS, temperature=temp,
                seed=SEED, device=device,
            )
            cont_str = cont.decode("utf-8", errors="replace")
            lines.append(f"### temperature {temp}\n")
            lines.append("```\n")
            lines.append(prompt + cont_str + "\n")
            lines.append("```\n")

    OUT_PATH.write_text("".join(lines), encoding="utf-8")
    print()
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
