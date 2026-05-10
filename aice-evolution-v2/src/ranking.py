"""Multi-scenario ranking: weighted scalar per scenario + Pareto layer +
pairwise win-rate. Phase 6 adds an LLM-backed pairwise judge alongside
the deterministic logistic proxy."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .analysis import MetaFitness, pareto_layers
from .map_elites import RunResult


_REPO = Path(__file__).resolve().parents[2]
_PYABCL = _REPO / "src" / "python-aipl"
if str(_PYABCL) not in sys.path:
    sys.path.insert(0, str(_PYABCL))

try:
    import aipl_ai  # type: ignore
    _AI_OK = True
except ImportError:
    _AI_OK = False


@dataclass
class RankedEntry:
    individual_id: str
    composite: float
    pareto_rank: int
    pairwise_win_rate: float


@dataclass
class ScenarioRanking:
    scenario: str
    weights: dict[str, float]
    entries: list[RankedEntry]


def scenario_composite(meta: MetaFitness, weights: dict[str, float]) -> float:
    return sum(meta.components.get(k, 0.0) * w for k, w in weights.items())


def pairwise_winrate_proxy(scores: dict[str, float]) -> dict[str, float]:
    """Deterministic placeholder. Use composite differences as a proxy for
    LLM pairwise win-probability. Cheap, no API calls."""
    ids = list(scores.keys())
    out: dict[str, float] = {i: 0.0 for i in ids}
    if len(ids) < 2:
        return {i: 1.0 for i in ids}
    for i in ids:
        wins = 0
        for j in ids:
            if i == j:
                continue
            diff = scores[i] - scores[j]
            wins += 1 if diff > 0 else (0 if diff < 0 else 0.5)
        out[i] = wins / max(1, len(ids) - 1)
    return out


def _judge_persona(scenario: str) -> str:
    return (
        "あなたは次世代プログラミング言語候補の比較レビュアーです。"
        f"シナリオ '{scenario}' の観点で、より有力な候補を選んでください。"
        "回答は 'A' または 'B' の1文字のみ。説明や前置きは禁止。"
    )


def pairwise_winrate_ai(
    scenario: str,
    scores: dict[str, float],
    genomes: dict[str, dict[str, str]],
    cache: dict[tuple[str, str, str], str] | None = None,
) -> dict[str, float]:
    """Real LLM pairwise judging via aipl_ai.call_ai. Falls back to the
    deterministic proxy if the AI client isn't available.

    `cache` is keyed on (scenario, sorted_pair) so that re-running with
    different weights doesn't re-incur token cost. Pass {} to enable."""
    if not _AI_OK:
        return pairwise_winrate_proxy(scores)
    if cache is None:
        cache = {}
    persona = _judge_persona(scenario)
    ids = list(scores.keys())
    if len(ids) < 2:
        return {i: 1.0 for i in ids}
    wins: dict[str, float] = {i: 0.0 for i in ids}
    for i_idx, i in enumerate(ids):
        for j_idx, j in enumerate(ids):
            if i_idx >= j_idx:
                continue
            key = (scenario, i, j) if i < j else (scenario, j, i)
            cached = cache.get(key)
            if cached is None:
                ga = ", ".join(f"{k}={v}" for k, v in genomes[i].items())
                gb = ", ".join(f"{k}={v}" for k, v in genomes[j].items())
                prompt = f"候補A: {ga}\n候補B: {gb}\n\nどちらが有力ですか? 'A' または 'B' のみで答えてください。"
                try:
                    reply = aipl_ai.call_ai(prompt, system=persona, max_tokens=4)
                except Exception:
                    reply = ""
                first_a = reply.upper().find("A")
                first_b = reply.upper().find("B")
                if first_a >= 0 and (first_b < 0 or first_a < first_b):
                    cached = "A"
                elif first_b >= 0:
                    cached = "B"
                else:
                    cached = "tie"
                cache[key] = cached
            # decode result back to (i, j) frame regardless of canonical order
            if i < j:
                i_wins = (cached == "A")
                j_wins = (cached == "B")
            else:
                i_wins = (cached == "B")
                j_wins = (cached == "A")
            if i_wins:
                wins[i] += 1
            elif j_wins:
                wins[j] += 1
            else:
                wins[i] += 0.5
                wins[j] += 0.5
    n = len(ids) - 1
    return {i: wins[i] / max(1, n) for i in ids}


def rank_scenario(
    scenario: str,
    weights: dict[str, float],
    meta: dict[str, MetaFitness],
    layers: list[list[str]],
    top_k: int,
    winrate_fn: Callable[[str, dict[str, float]], dict[str, float]] | None = None,
) -> ScenarioRanking:
    composites = {iid: scenario_composite(m, weights) for iid, m in meta.items()}
    if winrate_fn is None:
        winrates = pairwise_winrate_proxy(composites)
    else:
        winrates = winrate_fn(scenario, composites)
    rank_of: dict[str, int] = {}
    for rank, layer in enumerate(layers, start=1):
        for iid in layer:
            rank_of[iid] = rank

    entries = sorted(
        (
            RankedEntry(
                individual_id=iid,
                composite=composites[iid],
                pareto_rank=rank_of.get(iid, len(layers) + 1),
                pairwise_win_rate=winrates.get(iid, 0.0),
            )
            for iid in meta.keys()
        ),
        key=lambda e: (e.pareto_rank, -e.composite, -e.pairwise_win_rate),
    )
    return ScenarioRanking(scenario=scenario, weights=weights, entries=entries[:top_k])


def rank_all(
    spec: dict[str, Any],
    result: RunResult,
    meta: dict[str, MetaFitness],
    use_ai_pairwise: bool = False,
) -> list[ScenarioRanking]:
    layers = pareto_layers(meta)
    scenario_weights = spec["ranking"].get("scenario_weights", {})
    scenarios = spec["ranking"].get("scenarios", list(scenario_weights.keys()))
    top_k = int(spec["ranking"].get("top_k", 3))

    winrate_fn: Callable[[str, dict[str, float]], dict[str, float]] | None = None
    if use_ai_pairwise:
        by_id = {ind.id: ind for ind in result.population}
        cache: dict[tuple[str, str, str], str] = {}

        def _ai_winrate(scenario: str, scores: dict[str, float]) -> dict[str, float]:
            genomes = {iid: by_id[iid].genome for iid in scores.keys() if iid in by_id}
            return pairwise_winrate_ai(scenario, scores, genomes, cache)

        winrate_fn = _ai_winrate

    return [
        rank_scenario(s, scenario_weights.get(s, {}), meta, layers, top_k, winrate_fn)
        for s in scenarios
    ]
