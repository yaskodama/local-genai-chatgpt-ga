"""Shared utilities: corpus loader, byte tokenizer, perplexity helpers."""

import hashlib
import math
import os
import random
from pathlib import Path

HERE = Path(__file__).parent
CORPUS_PATH = HERE / "corpus" / "tiny_corpus.txt"
CORPUS_SHA256 = "9614a5a4d3f6474f004c982e8a2e89f8bdbda367fe55edc6d9d52d72cc48593e"

SEED = 42


def load_corpus() -> bytes:
    raw = CORPUS_PATH.read_bytes()
    h = hashlib.sha256(raw).hexdigest()
    if h != CORPUS_SHA256:
        raise RuntimeError(f"corpus hash mismatch: expected {CORPUS_SHA256}, got {h}")
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
