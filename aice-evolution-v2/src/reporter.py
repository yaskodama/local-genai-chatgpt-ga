"""Markdown + JSON reporter for the run output."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .analysis import MetaFitness, PareteGap, TrendVector
from .map_elites import RunResult
from .ranking import ScenarioRanking
from .operators import PARADIGM_CLUSTER


def _nearest_paradigm(genome: dict[str, str]) -> tuple[str, list[str]]:
    """Closest classical paradigm and the axis values that exceed it."""
    best_p, best_match = None, -1
    for p, cluster in PARADIGM_CLUSTER.items():
        match = sum(1 for k, v in cluster.items() if genome.get(k) == v)
        if match > best_match:
            best_match = match
            best_p = p
    extras = []
    if best_p:
        cluster = PARADIGM_CLUSTER[best_p]
        for k, v in genome.items():
            if k in cluster and cluster[k] != v:
                extras.append(f"{k}: {cluster[k]} -> {v}")
    return best_p or "?", extras


def _genome_inline(genome: dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in genome.items())


def write_report(
    out_dir: str | Path,
    name: str,
    spec: dict[str, Any],
    result: RunResult,
    trend: TrendVector,
    gaps: list[PareteGap],
    meta: dict[str, MetaFitness],
    rankings: list[ScenarioRanking],
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    by_id = {ind.id: ind for ind in result.population}

    md_path = out / f"{name}.report.md"
    rank_path = out / f"{name}.ranking.json"

    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append("")
    lines.append(f"> {spec.get('task','')}")
    lines.append("")

    # Section 1: trajectory
    lines.append("## 1. 発見された進化軌跡 (best champion lineage)")
    lines.append("")
    lines.append(f"系譜長: {len(trend.path)} 世代分")
    lines.append("")
    lines.append("| step | id | gen | operator | paradigm | type_safety | concurrency_model |")
    lines.append("|------|----|-----|----------|----------|-------------|-------------------|")
    for i, iid in enumerate(trend.path):
        ind = by_id.get(iid)
        if ind is None:
            continue
        lines.append(
            f"| {i} | `{iid}` | {ind.generation} | `{ind.operator}` | "
            f"{ind.genome.get('paradigm','?')} | "
            f"{ind.genome.get('type_safety','?')} | "
            f"{ind.genome.get('concurrency_model','?')} |"
        )
    lines.append("")

    # Section 2: trend vector
    lines.append("## 2. 進化方向ベクトル (signed total movement, normalized)")
    lines.append("")
    norm = trend.normalized()
    if norm:
        for axis, v in sorted(norm.items(), key=lambda kv: -abs(kv[1])):
            sign = "+" if v >= 0 else "-"
            lines.append(f"- `{axis}`: {sign}{abs(v):.2f}")
    else:
        lines.append("- (空: ordinal 軸を持つ遷移がなかった)")
    lines.append("")
    if trend.new_axis_values:
        lines.append("**Lineage 内で新しく現れた (axis, value) ペア**:")
        for axis, val in trend.new_axis_values:
            lines.append(f"- `{axis} = {val}`")
    lines.append("")

    # Section 3: Pareto gaps
    lines.append("## 3. Pareto フロンティア — 未充填セル (top 5 promising gaps)")
    lines.append("")
    lines.append("| descriptor | 隣接セル最高 composite | 距離 | コヒーレント |")
    lines.append("|-----------|------------------------|------|--------------|")
    for g in gaps[:5]:
        if not g.coherent:
            continue
        desc = ", ".join(f"{k}={v}" for k, v in g.descriptor.items())
        lines.append(f"| {desc} | {g.near_score:.2f} | {g.distance_to_filled} | {'yes' if g.coherent else 'no'} |")
    lines.append("")

    # Section 4: rankings per scenario
    lines.append("## 4. ランキング（シナリオ別）")
    lines.append("")
    for r in rankings:
        lines.append(f"### Scenario: {r.scenario}")
        weights_str = ", ".join(f"{k}={v}" for k, v in r.weights.items())
        lines.append(f"_重み: {weights_str}_")
        lines.append("")
        lines.append("| rank | id | paradigm | composite | Pareto層 | win-rate |")
        lines.append("|------|----|----------|-----------|----------|----------|")
        for i, e in enumerate(r.entries, start=1):
            ind = by_id.get(e.individual_id)
            paradigm = ind.genome.get("paradigm", "?") if ind else "?"
            lines.append(
                f"| {i} | `{e.individual_id}` | {paradigm} | "
                f"{e.composite:.3f} | {e.pareto_rank} | {e.pairwise_win_rate:.0%} |"
            )
        lines.append("")

    # Section 5: top candidate detail (union of #1 from each scenario)
    lines.append("## 5. 上位候補の詳細")
    lines.append("")
    seen: set[str] = set()
    for r in rankings:
        if not r.entries:
            continue
        e = r.entries[0]
        if e.individual_id in seen:
            continue
        seen.add(e.individual_id)
        ind = by_id.get(e.individual_id)
        if ind is None:
            continue
        nearest, extras = _nearest_paradigm(ind.genome)
        lines.append(f"### {e.individual_id}  ({r.scenario} の1位)")
        lines.append(f"- 遺伝子: `{_genome_inline(ind.genome)}`")
        lines.append(f"- セル: `{ind.cell}`")
        lines.append(f"- composite (run-内): {ind.composite:.3f}")
        lines.append(f"- 最近傍既存パラダイム: **{nearest}**")
        if extras:
            lines.append(f"- 越えている軸: {', '.join(extras)}")
        m = meta.get(e.individual_id)
        if m:
            comp_str = ", ".join(f"{k}={v:.2f}" for k, v in m.components.items())
            lines.append(f"- meta-fitness: {comp_str}")
        per_task = {k: v for k, v in ind.fitness_components.items() if k.startswith("task::")}
        if per_task:
            lines.append("- タスク別スコア: " + ", ".join(f"{k.split('::',1)[1]}={v:.2f}" for k, v in per_task.items()))
        lines.append("")

    # Section 5b: Phase 9 discoveries (only present when open_axes=true)
    schema = result.schema
    if schema.discovered_values or schema.discovered_axes:
        lines.append("## 5b. Phase 9 — 動的に発見された軸 / 値")
        lines.append("")
        if schema.discovered_axes:
            lines.append("**新規 axis (LLM が提案):**")
            for axis in schema.discovered_axes:
                lines.append(f"- `{axis}` (許容値: {', '.join(schema.axes.get(axis, []))})")
            lines.append("")
        if schema.discovered_values:
            lines.append("**既存 axis に追加された新値:**")
            for axis, values in schema.discovered_values.items():
                lines.append(f"- `{axis}`: {', '.join(values)}")
            lines.append("")

    # Section 6: caveat
    lines.append("## 6. 留保 (uncertainty)")
    lines.append("")
    lines.append(
        "シナリオ間で順位が入れ替わる候補は、外的条件次第でいずれの方向にも"
        "有力です。単一の正解はなく、本レポートは meta-fitness 重み選択への"
        "依存を保持したまま提示しています。"
    )
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    rank_dump = {
        "trend": {
            "deltas": trend.deltas,
            "normalized": trend.normalized(),
            "new_axis_values": trend.new_axis_values,
            "path": trend.path,
        },
        "gaps": [asdict(g) for g in gaps],
        "meta_fitness": {iid: m.components for iid, m in meta.items()},
        "rankings": [
            {
                "scenario": r.scenario,
                "weights": r.weights,
                "entries": [asdict(e) for e in r.entries],
            }
            for r in rankings
        ],
        "discoveries": {
            "axes": list(schema.discovered_axes),
            "values": {k: list(v) for k, v in schema.discovered_values.items()},
        },
    }
    rank_path.write_text(json.dumps(rank_dump, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"report": md_path, "ranking": rank_path}
