"""Stage 1 — n-gram with Laplace smoothing.  Pure-stdlib (no torch).

Three candidates:
  N1  char_bigram_laplace        n=2, alpha=1.0
  N2  char_trigram_with_backoff  n=3, alpha=0.5, falls back to bigram on miss
  N3  byte_unigram_only          n=1, alpha=1.0  (failure baseline)

Each candidate trains on the train split, evaluates on the holdout
split, and returns a real (measured) perplexity.
"""

from __future__ import annotations
import math
from collections import defaultdict


VOCAB = 256


class NGram:
    def __init__(self, n: int, alpha: float):
        self.n = n
        self.alpha = alpha
        self.counts: dict[tuple, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.context_totals: dict[tuple, int] = defaultdict(int)

    def train(self, data: bytes) -> None:
        n = self.n
        if n == 1:
            for b in data:
                self.counts[()][b] += 1
                self.context_totals[()] += 1
            return
        for i in range(len(data) - n + 1):
            ctx = tuple(data[i : i + n - 1])
            nxt = data[i + n - 1]
            self.counts[ctx][nxt] += 1
            self.context_totals[ctx] += 1

    def neg_log_prob(self, ctx: tuple, nxt: int) -> float:
        d = self.counts.get(ctx, {})
        total = self.context_totals.get(ctx, 0) + self.alpha * VOCAB
        cnt = d.get(nxt, 0) + self.alpha
        return -math.log(cnt / total)

    def eval_neg_log_prob_nats(self, data: bytes) -> tuple[float, int]:
        n = self.n
        total = 0.0
        count = 0
        if n == 1:
            for b in data:
                total += self.neg_log_prob((), b)
                count += 1
            return total, count
        for i in range(n - 1, len(data)):
            ctx = tuple(data[i - n + 1 : i])
            total += self.neg_log_prob(ctx, data[i])
            count += 1
        return total, count


class TrigramWithBackoff:
    """N3 trigram with Laplace + bigram backoff when context unseen."""

    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.tri = NGram(3, alpha)
        self.bi = NGram(2, alpha)

    def train(self, data: bytes) -> None:
        self.tri.train(data)
        self.bi.train(data)

    def neg_log_prob(self, ctx: tuple, nxt: int) -> float:
        if ctx in self.tri.context_totals:
            return self.tri.neg_log_prob(ctx, nxt)
        return self.bi.neg_log_prob(ctx[1:], nxt)

    def eval_neg_log_prob_nats(self, data: bytes) -> tuple[float, int]:
        total, count = 0.0, 0
        for i in range(2, len(data)):
            ctx = (data[i - 2], data[i - 1])
            total += self.neg_log_prob(ctx, data[i])
            count += 1
        return total, count


def candidate_N1(train_bytes, holdout_bytes):
    m = NGram(2, alpha=1.0)
    m.train(train_bytes)
    nlp, count = m.eval_neg_log_prob_nats(holdout_bytes)
    ppl = math.exp(nlp / count)
    params = sum(len(d) for d in m.counts.values())
    return {"name": "N1", "style": "char_bigram_laplace",
            "n": 2, "alpha": 1.0, "params_observed": params,
            "holdout_ppl": ppl}


def candidate_N2(train_bytes, holdout_bytes):
    m = TrigramWithBackoff(alpha=0.5)
    m.train(train_bytes)
    nlp, count = m.eval_neg_log_prob_nats(holdout_bytes)
    ppl = math.exp(nlp / count)
    params = sum(len(d) for d in m.tri.counts.values()) + sum(
        len(d) for d in m.bi.counts.values())
    return {"name": "N2", "style": "char_trigram_with_backoff",
            "n": 3, "alpha": 0.5, "params_observed": params,
            "holdout_ppl": ppl}


def candidate_N3(train_bytes, holdout_bytes):
    m = NGram(1, alpha=1.0)
    m.train(train_bytes)
    nlp, count = m.eval_neg_log_prob_nats(holdout_bytes)
    ppl = math.exp(nlp / count)
    params = len(m.counts[()])
    return {"name": "N3", "style": "byte_unigram_only",
            "n": 1, "alpha": 1.0, "params_observed": params,
            "holdout_ppl": ppl}


def run_all(train_bytes, holdout_bytes):
    return [candidate_N1(train_bytes, holdout_bytes),
            candidate_N2(train_bytes, holdout_bytes),
            candidate_N3(train_bytes, holdout_bytes)]
