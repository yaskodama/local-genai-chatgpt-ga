"""Shared utilities: corpus loader, byte tokenizer, perplexity helpers."""

import hashlib
import math
import os
import random
from pathlib import Path
from typing import NamedTuple

HERE = Path(__file__).parent


class CorpusSpec(NamedTuple):
    path: Path
    expected_hash: str | None
    sidecar_hash: bool = False


CORPORA = {
    "10KB": CorpusSpec(
        HERE / "corpus" / "tiny_corpus.txt",
        "9614a5a4d3f6474f004c982e8a2e89f8bdbda367fe55edc6d9d52d72cc48593e",
    ),
    "100KB": CorpusSpec(
        HERE / "corpus" / "tinyshake_100KB.txt",
        "caad989adf87f2482e346c9a77d1fb03c6c033aa8689e2e97aee2de90b0f8839",
    ),
    "1MB": CorpusSpec(
        HERE / "corpus" / "tinyshake_1MB.txt",
        "86c4e6aa9db7c042ec79f339dcb96d42b0075e16b8fc2e86bf0ca57e2dc565ed",
    ),
    "10MB": CorpusSpec(
        HERE / "corpus" / "tinyshake_10MB.txt",
        "76bd8e4cd4be37ee1853452b115de6889863cb431bcc6a5244d7632055794bff",
    ),
    "30MB_MIXED_EN_JA": CorpusSpec(
        HERE / "corpus" / "tinyshake_ja_30MB.txt",
        None,
        True,
    ),
}

CORPUS_PATH = CORPORA["10KB"][0]
CORPUS_SHA256 = CORPORA["10KB"][1]

SEED = 42


def load_corpus(size_class: str = "10KB") -> bytes:
    spec = CORPORA[size_class]
    raw = spec.path.read_bytes()
    h = hashlib.sha256(raw).hexdigest()
    expected_hash = spec.expected_hash
    if spec.sidecar_hash:
        hash_path = spec.path.with_suffix(spec.path.suffix + ".sha256")
        if not hash_path.exists():
            raise RuntimeError(
                f"corpus {size_class} is missing sidecar hash: {hash_path}"
            )
        expected_hash = hash_path.read_text(encoding="utf-8").strip().split()[0]
    if h != expected_hash:
        raise RuntimeError(f"corpus {size_class} hash mismatch: expected {expected_hash}, got {h}")
    return raw


def split_corpus(raw: bytes, train_frac: float = 0.95) -> tuple[bytes, bytes]:
    cut = int(len(raw) * train_frac)
    return raw[:cut], raw[cut:]


def make_rng() -> random.Random:
    return random.Random(SEED)


def perplexity_from_neg_log_prob_nats(total_neg_log_prob: float, count: int) -> float:
    if count == 0:
        return float("inf")
    return math.exp(total_neg_log_prob / count)
