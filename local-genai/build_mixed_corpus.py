"""Build the 30 MB mixed English/Japanese corpus selected by GA evolution.

The script is intentionally offline-first. It does not download data; instead
it combines local English and Japanese text files, validates UTF-8 output, and
writes a sidecar SHA-256 file consumed by common.load_corpus().

Default inputs:
  English : corpus/tinyshake_10MB.txt
  Japanese: corpus/ja_sources/*.txt

Example:
  python build_mixed_corpus.py \
    --ja-source /path/to/japanese_1.txt \
    --ja-source /path/to/japanese_2.txt \
    --allow-repeat
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_EN_SOURCE = HERE / "corpus" / "tinyshake_10MB.txt"
DEFAULT_JA_GLOB = HERE / "corpus" / "ja_sources" / "*.txt"
DEFAULT_OUT = HERE / "corpus" / "tinyshake_ja_30MB.txt"
TARGET_BYTES = 30_000_000


def normalize_text(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _run_segmenter_command(cmd: list[str], text: str) -> str:
    proc = subprocess.run(
        cmd,
        input=text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Japanese segmenter failed: {' '.join(cmd)}\n{proc.stderr.strip()}"
        )
    return proc.stdout


def _run_mecab_python(text: str) -> str | None:
    try:
        import MeCab  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        tagger = MeCab.Tagger("-Owakati")
        return tagger.parse(text)
    except RuntimeError as e:
        raise RuntimeError(f"MeCab Python module failed with -Owakati: {e}") from e


def segment_japanese(text: str, segmenter: str) -> str:
    if segmenter == "none":
        return text
    if segmenter == "mekabu":
        exe = shutil.which("mekabu")
        if exe is None:
            raise RuntimeError(
                "Mekabu was requested for Japanese segmentation, but `mekabu` "
                "was not found on PATH. Install Mekabu, or run with "
                "--ja-segmenter none for an unsegmented smoke corpus."
            )
        return _run_segmenter_command([exe], text)
    if segmenter == "mecab":
        exe = shutil.which("mecab")
        if exe is not None:
            return _run_segmenter_command([exe, "-Owakati"], text)
        parsed = _run_mecab_python(text)
        if parsed is not None:
            return parsed
        raise RuntimeError(
            "MeCab is required for Japanese segmentation, but neither the "
            "`mecab` command nor the Python `MeCab` module was found."
        )
    raise ValueError(f"unknown Japanese segmenter: {segmenter}")


def read_sources(
    paths: list[Path],
    label: str,
    ja_segmenter: str,
) -> tuple[list[bytes], list[dict[str, object]]]:
    pieces: list[bytes] = []
    records: list[dict[str, object]] = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"{label} source not found: {path}")
        text = normalize_text(path.read_bytes())
        source_sha = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        if label == "JA":
            text = segment_japanese(text, ja_segmenter)
        raw = text.encode("utf-8", errors="ignore")
        if raw.strip():
            pieces.append(raw)
            records.append({
                "label": label,
                "path": str(path),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_sha256": source_sha,
                "segmenter": ja_segmenter if label == "JA" else "none",
            })
            print(f"  + {label:<2} {path} ({len(raw):,} bytes)")
    return pieces, records


def expand_to_target(pieces: list[bytes], target: int, label: str, allow_repeat: bool) -> bytes:
    sep = b"\n\n"
    combined = sep.join(pieces)
    if len(combined) >= target:
        return combined[:target]
    if not allow_repeat:
        raise RuntimeError(
            f"{label} text has {len(combined):,} bytes, needs {target:,}. "
            "Add more source files or pass --allow-repeat for a smoke-test corpus."
        )
    repeats = (target // max(1, len(combined))) + 1
    return (sep.join([combined] * repeats))[:target]


def interleave_chunks(en: bytes, ja: bytes, chunk_bytes: int, target_bytes: int) -> bytes:
    out = bytearray()
    en_pos = 0
    ja_pos = 0
    while len(out) < target_bytes:
        if en_pos < len(en):
            out.extend(en[en_pos : en_pos + chunk_bytes])
            out.extend(b"\n")
            en_pos += chunk_bytes
        if ja_pos < len(ja):
            out.extend(ja[ja_pos : ja_pos + chunk_bytes])
            out.extend(b"\n")
            ja_pos += chunk_bytes
        if en_pos >= len(en) and ja_pos >= len(ja):
            break
    return bytes(out[:target_bytes])


def default_ja_sources() -> list[Path]:
    return sorted(DEFAULT_JA_GLOB.parent.glob(DEFAULT_JA_GLOB.name))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--en-source", action="append", type=Path, default=[])
    p.add_argument("--ja-source", action="append", type=Path, default=[])
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--target-bytes", type=int, default=TARGET_BYTES)
    p.add_argument("--ja-ratio", type=float, default=0.40)
    p.add_argument("--chunk-bytes", type=int, default=8192)
    p.add_argument(
        "--ja-segmenter",
        choices=["mekabu", "mecab", "none"],
        default="mecab",
        help="Japanese word segmenter. Default is MeCab.",
    )
    p.add_argument("--allow-repeat", action="store_true")
    args = p.parse_args()

    if not 0.05 <= args.ja_ratio <= 0.95:
        raise ValueError("--ja-ratio must be between 0.05 and 0.95")

    en_sources = args.en_source or [DEFAULT_EN_SOURCE]
    ja_sources = args.ja_source or default_ja_sources()
    if not ja_sources:
        print(
            "No Japanese sources found. Add UTF-8 .txt files under "
            f"{DEFAULT_JA_GLOB.parent} or pass --ja-source PATH.",
            file=sys.stderr,
        )
        return 2

    print(f"target: {args.target_bytes:,} bytes")
    print(f"mix   : {1.0 - args.ja_ratio:.0%} English / {args.ja_ratio:.0%} Japanese")
    print(f"ja segmenter: {args.ja_segmenter}")
    en_target = int(args.target_bytes * (1.0 - args.ja_ratio))
    ja_target = args.target_bytes - en_target

    en_pieces, en_records = read_sources(en_sources, "EN", "none")
    ja_pieces, ja_records = read_sources(ja_sources, "JA", args.ja_segmenter)
    en = expand_to_target(en_pieces, en_target, "English", args.allow_repeat)
    ja = expand_to_target(ja_pieces, ja_target, "Japanese", args.allow_repeat)
    mixed = interleave_chunks(en, ja, args.chunk_bytes, args.target_bytes)
    if len(mixed) != args.target_bytes:
        raise RuntimeError(f"internal error: expected {args.target_bytes}, got {len(mixed)}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(mixed)
    sha = hashlib.sha256(mixed).hexdigest()
    sha_path = args.out.with_suffix(args.out.suffix + ".sha256")
    sha_path.write_text(f"{sha}  {args.out.name}\n", encoding="utf-8")
    manifest_path = args.out.with_suffix(args.out.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps({
        "output": str(args.out),
        "output_bytes": len(mixed),
        "output_sha256": sha,
        "target_bytes": args.target_bytes,
        "ja_ratio": args.ja_ratio,
        "chunk_bytes": args.chunk_bytes,
        "allow_repeat": args.allow_repeat,
        "japanese_segmenter": args.ja_segmenter,
        "english_target_bytes": en_target,
        "japanese_target_bytes": ja_target,
        "english_source_bytes": sum(r["bytes"] for r in en_records),
        "japanese_source_bytes": sum(r["bytes"] for r in ja_records),
        "sources": en_records + ja_records,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"wrote {args.out} ({len(mixed):,} bytes)")
    print(f"sha256 = {sha}")
    print(f"sidecar = {sha_path}")
    print(f"manifest = {manifest_path}")
    print()
    print("Next training command:")
    print(
        "  python train_stage8_bpe.py --corpus 30MB_MIXED_EN_JA "
        "--vocab-size 2048 --ctx 256 --depth 6 --d-model 128 "
        "--out-name transformer_ga_bpe2048_ja30mb.pt "
        "--tokenizer-name tokenizer_ga_bpe2048_ja30mb.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
