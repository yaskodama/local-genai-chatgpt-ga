"""Phase 6a: LLM-backed evaluator that replaces (or wraps) the mock one.

Uses the existing `aipl_ai.call_ai` from python-aipl, which honours
ABCL_AI_PROVIDER / ABCL_AI_TOKEN_BUDGET / ABCL_AI_MAX_CONCURRENT etc.
With ABCL_AI_PROVIDER=mock the calls return canned text so the
pipeline runs without a real API key (and without spending tokens)."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from .schema import GeneSchema
from .evaluator import (
    evaluate as mock_evaluate,
    composite_fitness as mock_composite,
    TASK_PROFILES,
)


_REPO = Path(__file__).resolve().parents[2]
_PYABCL = _REPO / "src" / "python-aipl"
if str(_PYABCL) not in sys.path:
    sys.path.insert(0, str(_PYABCL))

try:  # noqa: SIM105
    import aipl_ai  # type: ignore
    _AI_OK = True
except ImportError:
    _AI_OK = False


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_score(text: str) -> float:
    """Extract the first number in [0, 1] from an LLM response. Falls back
    to 0.5 if nothing parseable is found, which is a deliberately neutral
    prior — neither rewards nor penalizes when the model is uncooperative."""
    if not text:
        return 0.5
    m = _NUM_RE.search(text)
    if not m:
        return 0.5
    raw = m.group(0)
    try:
        v = float(raw)
    except ValueError:
        return 0.5
    # Tolerate "75" meaning 75% only when the captured token has no decimal
    # point and lies in (1, 100]. Decimals like 1.5 just clamp to 1.0.
    if "." not in raw and v > 1.0 and v <= 100.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def reviewer_score_ai(
    persona: str,
    genome: dict[str, str],
    task: str,
    profile: dict[str, str],
) -> float:
    if not _AI_OK:
        return 0.5
    genome_str = ", ".join(f"{k}={v}" for k, v in genome.items())
    profile_str = ", ".join(f"{k}={v}" for k, v in profile.items())
    prompt = (
        f"評価対象の遺伝子: {genome_str}\n"
        f"タスク: {task} (理想プロファイル: {profile_str})\n\n"
        "このタスクに対するこの遺伝子の suitability を 0.0 から 1.0 の単一の "
        "decimal number で返してください。説明や前置きは禁止。数値1つだけ。"
    )
    try:
        reply = aipl_ai.call_ai(prompt, system=persona, max_tokens=16)
    except Exception:
        return 0.5
    return parse_score(reply)


def evaluate_ai(
    genome: dict[str, str],
    schema: GeneSchema,
    tasks: list[str],
    reviewers: list[dict],
) -> dict[str, float]:
    """LLM-backed counterpart of evaluator.evaluate(). Falls back to the
    mock per-task fit when the AI call fails or is the mock provider."""
    base = mock_evaluate(genome, schema, tasks)

    if not _AI_OK:
        return base

    per_task: dict[str, float] = {}
    for t in tasks:
        prof = TASK_PROFILES.get(t, {})
        scores: list[tuple[float, float]] = []  # (score, weight)
        for r in reviewers:
            persona = r.get("persona", "あなたは評価レビュアーです。")
            weight = float(r.get("weight", 1.0 / max(1, len(reviewers))))
            s = reviewer_score_ai(persona, genome, t, prof)
            scores.append((s, weight))
        wsum = sum(w for _, w in scores) or 1.0
        weighted = sum(s * w for s, w in scores) / wsum
        per_task[f"task::{t}"] = weighted

    out = dict(base)
    out.update(per_task)
    if per_task:
        out["cross_task_generality"] = sum(per_task.values()) / len(per_task)
        out["paradigm_match"] = max(per_task.values())
    return out


def composite_fitness_ai(scores: dict[str, float]) -> float:
    return mock_composite(scores)
