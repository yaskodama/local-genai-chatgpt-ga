"""Audit the generated mixed English/Japanese corpus.

The audit is intentionally simple and dependency-free. It checks basic byte
stats, script mix, source manifest, and repeated chunk ratio so smoke corpora
are not mistaken for final training data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from common import CORPORA, load_corpus


def script_counts(text: str) -> dict[str, int]:
    counts = {
        "ascii": 0,
        "hiragana": 0,
        "katakana": 0,
        "cjk": 0,
        "other": 0,
    }
    for ch in text:
        code = ord(ch)
        if code < 128:
            counts["ascii"] += 1
        elif 0x3040 <= code <= 0x309F:
            counts["hiragana"] += 1
        elif 0x30A0 <= code <= 0x30FF:
            counts["katakana"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["cjk"] += 1
        else:
            counts["other"] += 1
    return counts


def repeated_chunk_ratio(raw: bytes, chunk_size: int) -> float:
    if len(raw) < chunk_size:
        return 0.0
    chunks = [
        hashlib.sha256(raw[i : i + chunk_size]).digest()
        for i in range(0, len(raw) - chunk_size + 1, chunk_size)
    ]
    if not chunks:
        return 0.0
    return 1.0 - (len(set(chunks)) / len(chunks))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--corpus", default="30MB_MIXED_EN_JA")
    p.add_argument("--chunk-size", type=int, default=4096)
    p.add_argument("--out", type=Path, default=HERE / "reports" / "mixed_corpus_audit.json")
    args = p.parse_args()

    raw = load_corpus(args.corpus)
    spec = CORPORA[args.corpus]
    manifest_path = spec.path.with_suffix(spec.path.suffix + ".manifest.json")
    manifest = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    text = raw.decode("utf-8", errors="ignore")
    counts = script_counts(text)
    total_chars = max(1, sum(counts.values()))
    japanese_chars = counts["hiragana"] + counts["katakana"] + counts["cjk"]
    repeat_ratio = repeated_chunk_ratio(raw, args.chunk_size)
    source_bytes = int(manifest.get("japanese_source_bytes", 0) or 0)
    allow_repeat = bool(manifest.get("allow_repeat", False))
    segmenter = manifest.get("japanese_segmenter", "unknown")
    smoke = allow_repeat or source_bytes < 5_000_000 or repeat_ratio > 0.20

    report = {
        "corpus": args.corpus,
        "path": str(spec.path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "manifest": str(manifest_path) if manifest_path.exists() else None,
        "allow_repeat": allow_repeat,
        "japanese_segmenter": segmenter,
        "japanese_source_bytes": source_bytes,
        "script_counts": counts,
        "japanese_char_ratio": japanese_chars / total_chars,
        "ascii_char_ratio": counts["ascii"] / total_chars,
        "repeated_chunk_ratio": repeat_ratio,
        "chunk_size": args.chunk_size,
        "quality_flag": "smoke_only" if smoke else "trainable_source_mix",
        "recommendation": (
            "Replace the Japanese seed with larger licensed Japanese text, segment with MeCab, and rebuild without --allow-repeat."
            if smoke
            else "Corpus source mix is suitable for the next training run."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"quality_flag: {report['quality_flag']}")
    print(f"bytes: {len(raw):,}")
    print(f"japanese_char_ratio: {report['japanese_char_ratio']:.3f}")
    print(f"repeated_chunk_ratio: {repeat_ratio:.3f}")
    print(f"report -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
