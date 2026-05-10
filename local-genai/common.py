"""Shared utilities: corpus loader, byte tokenizer, perplexity helpers."""

import hashlib
import math
import os
import random
from pathlib import Path

HERE = Path(__file__).parent

CORPORA = {
    "10KB": (
        HERE / "corpus" / "tiny_corpus.txt",
        "9614a5a4d3f6474f004c982e8a2e89f8bdbda367fe55edc6d9d52d72cc48593e",
    ),
    "100KB": (
        HERE / "corpus" / "tinyshake_100KB.txt",
        "caad989adf87f2482e346c9a77d1fb03c6c033aa8689e2e97aee2de90b0f8839",
    ),
}

CORPUS_PATH = CORPORA["10KB"][0]
CORPUS_SHA256 = CORPORA["10KB"][1]

SEED = 42


def load_corpus(size_class: str = "10KB") -> bytes:
    path, expected_hash = CORPORA[size_class]
    raw = path.read_bytes()
    h = hashlib.sha256(raw).hexdigest()
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
