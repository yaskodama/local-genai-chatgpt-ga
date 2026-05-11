"""Generate sample completions from the evolved GA BPE2048 model."""

from __future__ import annotations

import sys
from pathlib import Path
import argparse

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from chat import build_model, generate

OUT_PATH = HERE / "samples" / "samples_ga_bpe2048_ja30mb.md"

PROMPTS = [
    "こんにちは。今日は",
    "生成AIを進化させるには",
    "日本語対応のために必要なことは",
    "このモデルに入力すると",
    "進化計算の結果として",
    "英語と日本語を混ぜると",
    "小さなローカル生成AIは",
    "学習データを増やした場合",
    "ユーザー: 明日の予定を考えて",
    "質問: Transformerとは何ですか。",
    "要約してください:",
    "Pythonで簡単な関数を書くと",
    "To be, or not to be,",
    "All the world's a stage,",
    "In the beginning",
    "The model learns from",
    "Please explain local AI",
    "local-genai は",
    "BPE tokenizer",
    "1, 2, 3, 4,",
]

TEMPERATURES = (0.6, 0.85, 1.05)
MAX_CHARS = 320


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="ga_bpe2048", choices=["ga_bpe2048", "ga_bpe2048_mecab"])
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args()

    model, label = build_model(args.model)
    out_path = args.out or (
        HERE / "samples" / (
            "samples_ga_bpe2048_ja30mb_mecab.md"
            if args.model == "ga_bpe2048_mecab"
            else "samples_ga_bpe2048_ja30mb.md"
        )
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# Sample generations - {args.model} 30MB mixed corpus\n\n")
    lines.append(f"Model: `{label}`\n\n")
    lines.append(
        "This model is an autoregressive continuation model, not an "
        "instruction-tuned assistant. The current mixed corpus was generated "
        "with a repeated Japanese smoke seed, so these samples validate the "
        "inference path more than final Japanese quality.\n"
    )

    for i, prompt in enumerate(PROMPTS, start=1):
        print(f"[{i}/{len(PROMPTS)}] {prompt}", flush=True)
        lines.append(f"\n## {i}. `{prompt}`\n\n")
        for temp in TEMPERATURES:
            text = generate(
                model,
                prompt,
                max_chars=MAX_CHARS,
                temperature=temp,
                seed=100 + i,
            )
            lines.append(f"### temperature {temp}\n\n")
            lines.append("```text\n")
            lines.append(prompt + text + "\n")
            lines.append("```\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
