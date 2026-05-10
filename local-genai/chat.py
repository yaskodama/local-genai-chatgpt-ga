"""Interactive chat with the stage-1 n-gram LLM.

Trains a trigram-with-bigram-backoff model on the pinned corpus and
samples a continuation from the prompt the user types.

Usage:
    python3 local-genai/chat.py                       # interactive REPL
    python3 local-genai/chat.py "the early bird"      # single shot
    python3 local-genai/chat.py -t 0.7 -m 200 "..."   # temperature, max chars

Flags:
    -t, --temperature  sampling temperature (default 1.0; <1 sharper, >1 flatter)
    -m, --max-chars    max bytes generated (default 200)
    -s, --seed         RNG seed (default 0)
    --model            'trigram_backoff' (default) | 'bigram'
"""

from __future__ import annotations
import argparse
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import load_corpus, split_corpus
from candidates.ngram_real import NGram, TrigramWithBackoff


def build_model(kind: str):
    raw = load_corpus()
    train, _ = split_corpus(raw)
    if kind == "trigram_backoff":
        m = TrigramWithBackoff(alpha=0.5)
        m.train(train)
        return m, "trigram+bigram backoff (alpha=0.5)"
    if kind == "bigram":
        m = NGram(2, alpha=1.0)
        m.train(train)
        return m, "bigram laplace (alpha=1.0)"
    raise ValueError(f"unknown model kind: {kind}")


def _next_byte(model, ctx_bytes: bytes, rng: random.Random,
               temperature: float) -> int:
    if isinstance(model, TrigramWithBackoff):
        ctx_3 = tuple(ctx_bytes[-2:]) if len(ctx_bytes) >= 2 else None
        d = None
        if ctx_3 is not None:
            d = model.tri.counts.get(ctx_3)
        if not d and len(ctx_bytes) >= 1:
            d = model.bi.counts.get((ctx_bytes[-1],))
    else:
        if model.n == 1:
            d = model.counts.get(())
        else:
            ctx = tuple(ctx_bytes[-(model.n - 1):])
            d = model.counts.get(ctx) if len(ctx_bytes) >= model.n - 1 else None

    if not d:
        return rng.randrange(256)

    keys = list(d.keys())
    weights = list(d.values())
    if temperature != 1.0:
        weights = [w ** (1.0 / max(temperature, 1e-3)) for w in weights]
    return rng.choices(keys, weights=weights, k=1)[0]


def generate(model, prompt: str, max_chars: int = 200,
             temperature: float = 1.0, seed: int = 0) -> str:
    rng = random.Random(seed)
    seed_bytes = prompt.encode("utf-8") or b". "
    out = bytearray(seed_bytes)
    for _ in range(max_chars):
        nxt = _next_byte(model, bytes(out), rng, temperature)
        out.append(nxt)
        if nxt == ord(".") and len(out) - len(seed_bytes) >= 20:
            break
        if nxt == ord("\n"):
            break
    return out[len(seed_bytes):].decode("utf-8", errors="replace")


def parse_args():
    p = argparse.ArgumentParser(description="chat with the local-genai stage-1 n-gram")
    p.add_argument("prompt", nargs="*", help="single-shot prompt; omit for REPL")
    p.add_argument("-t", "--temperature", type=float, default=1.0)
    p.add_argument("-m", "--max-chars", type=int, default=200)
    p.add_argument("-s", "--seed", type=int, default=0)
    p.add_argument("--model", choices=["trigram_backoff", "bigram"],
                   default="trigram_backoff")
    return p.parse_args()


def main():
    args = parse_args()
    model, label = build_model(args.model)
    if args.prompt:
        prompt = " ".join(args.prompt)
        cont = generate(model, prompt,
                        max_chars=args.max_chars,
                        temperature=args.temperature,
                        seed=args.seed)
        print(prompt + cont)
        return

    print(f"# local-genai chat — {label}")
    print(f"# corpus = local-genai/corpus/tiny_corpus.txt (9.5KB, SHA-256 pinned)")
    print(f"# temperature={args.temperature}  max_chars={args.max_chars}  seed={args.seed}")
    print("# empty line or Ctrl-D exits.")
    turn = 0
    while True:
        try:
            prompt = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not prompt:
            break
        cont = generate(model, prompt,
                        max_chars=args.max_chars,
                        temperature=args.temperature,
                        seed=args.seed + turn)
        print(prompt + cont)
        turn += 1


if __name__ == "__main__":
    main()
