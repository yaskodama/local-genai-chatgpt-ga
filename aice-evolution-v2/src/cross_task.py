"""Phase 7: cross-task aggregation.

Reads N <name>.ranking.json + <name>.lineage.json pairs from a batch run
and identifies which gene axes show consistent evolutionary direction
across task domains. The stable-direction set is the strongest signal
the framework can give for "next-generation language" prediction."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunSummary:
    name: str
    ranking_path: Path
    lineage_path: Path
    trend_normalized: dict[str, float]
    top_individual_ids: list[str]   # union over scenarios' top-3
    individuals: dict[str, dict]     # id -> lineage record


@dataclass
class AxisStats:
    axis: str
    values: list[float]
    mean: float
    std: float
    positive_count: int
    negative_count: int
    sign_agreement: float
    stability: float    # |mean| / (std + ε)


@dataclass
class CrossTaskResult:
    runs: list[RunSummary]
    axis_stats: list[AxisStats]
    consensus_genome: dict[str, tuple[str, int, int]]  # axis -> (winner_value, votes, total)
    universal_threshold: float = 0.75    # sign-agreement to call an axis "universal"


def _load_run(ranking_path: Path) -> RunSummary:
    name = ranking_path.stem.replace(".ranking", "")
    lineage_path = ranking_path.with_name(f"{name}.lineage.json")
    if not lineage_path.exists():
        raise FileNotFoundError(f"missing lineage for {name}: expected {lineage_path}")
    rk = json.loads(ranking_path.read_text(encoding="utf-8"))
    lin = json.loads(lineage_path.read_text(encoding="utf-8"))
    by_id = {ind["id"]: ind for ind in lin}
    top_ids: list[str] = []
    for scenario in rk.get("rankings", []):
        for entry in scenario.get("entries", []):
            iid = entry.get("individual_id")
            if iid and iid not in top_ids:
                top_ids.append(iid)
    return RunSummary(
        name=name,
        ranking_path=ranking_path,
        lineage_path=lineage_path,
        trend_normalized=dict(rk.get("trend", {}).get("normalized", {})),
        top_individual_ids=top_ids,
        individuals=by_id,
    )


def _axis_stats(axis: str, values: list[float]) -> AxisStats:
    n = len(values)
    if n == 0:
        return AxisStats(axis, [], 0.0, 0.0, 0, 0, 0.0, 0.0)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(var)
    eps = 0.05
    positives = sum(1 for v in values if v > eps)
    negatives = sum(1 for v in values if v < -eps)
    zero = n - positives - negatives
    sign_agreement = max(positives, negatives, zero) / n
    stability = abs(mean) / (std + 0.01)
    return AxisStats(axis, values, mean, std, positives, negatives, sign_agreement, stability)


def _consensus_genome(runs: list[RunSummary]) -> dict[str, tuple[str, int, int]]:
    """Per axis, the value most frequently chosen by Pareto-top candidates
    across all runs. Returns axis -> (winner_value, votes, total)."""
    axis_votes: dict[str, Counter] = {}
    for run in runs:
        for iid in run.top_individual_ids:
            ind = run.individuals.get(iid)
            if not ind:
                continue
            genome = ind.get("genome", {})
            if isinstance(genome, str):
                # AIPL lineage stores genome as "axis=val|axis=val|..."
                pairs = [p.split("=", 1) for p in genome.split("|") if "=" in p]
                genome = {k: v for k, v in pairs}
            for axis, val in genome.items():
                axis_votes.setdefault(axis, Counter())[val] += 1
    out: dict[str, tuple[str, int, int]] = {}
    for axis, counter in axis_votes.items():
        total = sum(counter.values())
        winner, votes = counter.most_common(1)[0]
        out[axis] = (winner, votes, total)
    return out


def aggregate(ranking_paths: list[Path]) -> CrossTaskResult:
    runs = [_load_run(p) for p in ranking_paths]
    axes = set()
    for r in runs:
        axes.update(r.trend_normalized.keys())
    axis_stats = [
        _axis_stats(a, [r.trend_normalized.get(a, 0.0) for r in runs])
        for a in sorted(axes)
    ]
    axis_stats.sort(key=lambda s: -s.stability)
    consensus = _consensus_genome(runs)
    return CrossTaskResult(runs=runs, axis_stats=axis_stats, consensus_genome=consensus)


def write_report(result: CrossTaskResult, out_dir: str | Path, name: str) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"{name}.cross_task.report.md"
    json_path = out / f"{name}.cross_task.json"

    universal: list[AxisStats] = [s for s in result.axis_stats if s.sign_agreement >= result.universal_threshold and abs(s.mean) > 0.05]
    noisy:     list[AxisStats] = [s for s in result.axis_stats if s.sign_agreement < result.universal_threshold]

    lines: list[str] = []
    lines.append(f"# {name} — Cross-Task Trend Aggregation")
    lines.append("")
    lines.append("対象 runs:")
    for r in result.runs:
        lines.append(f"- `{r.name}`  (trend axes: {len(r.trend_normalized)}, top候補: {len(r.top_individual_ids)})")
    lines.append("")

    lines.append("## 1. 軸ごとのタスク横断安定性")
    lines.append("")
    lines.append("| axis | mean | std | +n / -n / 0n | sign-agree | stability |")
    lines.append("|------|------|-----|---------------|------------|-----------|")
    n_runs = len(result.runs)
    for s in result.axis_stats:
        zeros = n_runs - s.positive_count - s.negative_count
        sign_str = f"{s.positive_count} / {s.negative_count} / {zeros}"
        lines.append(
            f"| `{s.axis}` | {s.mean:+.2f} | {s.std:.2f} | {sign_str} | "
            f"{s.sign_agreement:.0%} | {s.stability:.2f} |"
        )
    lines.append("")

    lines.append("## 2. Universal direction (タスクを超えて方向が一致する軸)")
    lines.append("")
    if not universal:
        lines.append("- (該当なし — 全軸が task-specific)")
    else:
        for s in universal:
            direction = "+" if s.mean > 0 else "-"
            lines.append(f"- `{s.axis}`: {direction}{abs(s.mean):.2f}  (sign-agree {s.sign_agreement:.0%}, runs {s.positive_count}↑/{s.negative_count}↓)")
    lines.append("")

    lines.append("## 3. Task-specific noise (タスク依存で方向が定まらない軸)")
    lines.append("")
    if not noisy:
        lines.append("- (なし)")
    else:
        for s in noisy:
            lines.append(f"- `{s.axis}`: mean {s.mean:+.2f}, std {s.std:.2f}, sign-agree {s.sign_agreement:.0%}")
    lines.append("")

    lines.append("## 4. Consensus genome (Pareto-top の多数決)")
    lines.append("")
    lines.append("| axis | winner | votes / total |")
    lines.append("|------|--------|---------------|")
    for axis, (winner, votes, total) in sorted(result.consensus_genome.items()):
        lines.append(f"| `{axis}` | `{winner}` | {votes} / {total} |")
    lines.append("")

    lines.append("## 5. 結論 (機械的な抽出)")
    lines.append("")
    if universal:
        lines.append(
            f"タスク {len(result.runs)} 種を横断して、次の {len(universal)} 軸が"
            "**普遍的な進化方向**を示しています。これらは個別タスクのノイズではなく "
            "「次世代言語が満たすべき真の圧力」とみなせます:"
        )
        for s in universal:
            direction = "+" if s.mean > 0 else "-"
            lines.append(f"  - `{s.axis}` を {direction}{abs(s.mean):.2f} だけ進める")
        lines.append("")
    consensus_str = ", ".join(f"{a}={v}" for a, (v, *_rest) in sorted(result.consensus_genome.items()))
    lines.append(f"Consensus genome: `{consensus_str}`")
    lines.append("")
    lines.append("単一の「正解」は出ませんが、上記の軸は **複数のタスクで再現** したので "
                 "task-specific バイアスの可能性は低いです。")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    json_dump = {
        "name": name,
        "runs": [r.name for r in result.runs],
        "axis_stats": [
            {
                "axis": s.axis,
                "values": s.values,
                "mean": s.mean,
                "std": s.std,
                "positive_count": s.positive_count,
                "negative_count": s.negative_count,
                "sign_agreement": s.sign_agreement,
                "stability": s.stability,
            }
            for s in result.axis_stats
        ],
        "universal_axes": [s.axis for s in universal],
        "noisy_axes": [s.axis for s in noisy],
        "consensus_genome": {a: {"value": v, "votes": votes, "total": total} for a, (v, votes, total) in result.consensus_genome.items()},
    }
    json_path.write_text(json.dumps(json_dump, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"cross_report": md_path, "cross_json": json_path}
