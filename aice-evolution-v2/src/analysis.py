"""Phase 3 analysis: trend vector, Pareto gaps, evolvability."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Iterable

from .map_elites import Individual, RunResult
from .schema import GeneSchema


@dataclass
class TrendVector:
    """Signed total movement per ordinal axis along the lineage of the best
    champion. A positive number means the champion moved up the ordinal
    scale (e.g. type_safety: none -> high)."""
    deltas: dict[str, float]
    new_axis_values: list[tuple[str, str]]
    path: list[str]   # individual ids, oldest first

    def normalized(self) -> dict[str, float]:
        total = sum(abs(v) for v in self.deltas.values())
        if total == 0:
            return dict(self.deltas)
        return {k: v / total for k, v in self.deltas.items()}


def best_champion(result: RunResult) -> Individual:
    return max(result.champions(), key=lambda i: i.composite)


def deepest_top_champion(result: RunResult, top_k: int = 5) -> Individual:
    """Among top-K by composite, pick the one with the longest lineage. This
    avoids the trivial 'lucky seed wins' case where the best champion has
    no parents and the trend vector ends up all-zero."""
    champs = sorted(result.champions(), key=lambda i: -i.composite)[:top_k]
    if not champs:
        return best_champion(result)
    by_id = {ind.id: ind for ind in result.population}

    def depth(ind: Individual) -> int:
        d, cur = 0, ind
        seen = {cur.id}
        while cur.parents:
            p = by_id.get(cur.parents[0])
            if p is None or p.id in seen:
                break
            seen.add(p.id)
            cur = p
            d += 1
        return d

    return max(champs, key=lambda i: (depth(i), i.composite))


def lineage_path(result: RunResult, individual: Individual) -> list[Individual]:
    idx = {ind.id: ind for ind in result.population}
    path = [individual]
    cur = individual
    while cur.parents:
        parent = idx.get(cur.parents[0])
        if parent is None:
            break
        path.append(parent)
        cur = parent
    path.reverse()
    return path


def extract_trend(result: RunResult) -> TrendVector:
    schema = result.schema
    champ = deepest_top_champion(result)
    path = lineage_path(result, champ)
    deltas: dict[str, float] = {axis: 0.0 for axis in schema.ordinal_axes.keys()}
    for prev, nxt in zip(path, path[1:]):
        for axis in schema.ordinal_axes.keys():
            ip = schema.ordinal_index(axis, prev.genome.get(axis, ""))
            inn = schema.ordinal_index(axis, nxt.genome.get(axis, ""))
            if ip is not None and inn is not None:
                span = max(1, len(schema.ordinal_axes[axis]) - 1)
                deltas[axis] += (inn - ip) / span

    seen: set[tuple[str, str]] = set()
    seed_genome = path[0].genome
    for axis, val in seed_genome.items():
        seen.add((axis, val))
    new_pairs: list[tuple[str, str]] = []
    for ind in path[1:]:
        for axis, val in ind.genome.items():
            key = (axis, val)
            if key not in seen:
                seen.add(key)
                new_pairs.append(key)

    return TrendVector(deltas=deltas, new_axis_values=new_pairs, path=[i.id for i in path])


def all_cells(schema: GeneSchema, cell_axes: list[str]) -> list[dict[str, str]]:
    """Cartesian product of allowed values for each cell axis."""
    value_lists = [schema.axes.get(axis, []) for axis in cell_axes]
    return [dict(zip(cell_axes, combo)) for combo in itertools.product(*value_lists)]


def cell_descriptor_id(descriptor: dict[str, str]) -> str:
    return "|".join(f"{k}={v}" for k, v in descriptor.items())


@dataclass
class PareteGap:
    descriptor: dict[str, str]
    near_score: float           # max composite of any neighbor cell
    distance_to_filled: int     # min hamming distance to a filled cell
    coherent: bool


def find_gaps(result: RunResult, cell_axes: list[str]) -> list[PareteGap]:
    schema = result.schema
    cells = all_cells(schema, cell_axes)
    filled_ids = set(result.elite_map.keys())
    by_id = {ind.id: ind for ind in result.population}
    score_by_cell: dict[str, float] = {
        cell: by_id[ind_id].composite for cell, ind_id in result.elite_map.items()
    }

    gaps: list[PareteGap] = []
    for desc in cells:
        cid = cell_descriptor_id(desc)
        if cid in filled_ids:
            continue
        # neighbors = cells that differ on exactly 1 axis
        best = 0.0
        min_dist = len(cell_axes)
        for filled_cid, score in score_by_cell.items():
            filled_desc = dict(part.split("=", 1) for part in filled_cid.split("|"))
            dist = sum(1 for k in cell_axes if filled_desc.get(k) != desc.get(k))
            if dist == 1 and score > best:
                best = score
            if dist < min_dist:
                min_dist = dist
        # check coherence with a neutral genome filled in the missing axes
        filler = dict(desc)
        for axis in schema.axis_names():
            if axis not in filler:
                filler[axis] = schema.axes[axis][0]
        coherent = schema.is_coherent(filler)
        gaps.append(PareteGap(descriptor=desc, near_score=best, distance_to_filled=min_dist, coherent=coherent))

    # surface high-promise gaps first
    gaps.sort(key=lambda g: (-g.near_score, g.distance_to_filled))
    return gaps


@dataclass
class MetaFitness:
    individual_id: str
    components: dict[str, float]


def evolvability_score(result: RunResult) -> dict[str, int]:
    """Number of descendants per individual."""
    children: dict[str, int] = {ind.id: 0 for ind in result.population}
    for ind in result.population:
        for p in ind.parents:
            if p in children:
                children[p] += 1
    # transitive closure (BFS)
    descendants: dict[str, int] = dict(children)
    by_parents: dict[str, list[str]] = {ind.id: [] for ind in result.population}
    for ind in result.population:
        for p in ind.parents:
            by_parents.setdefault(p, []).append(ind.id)
    for ind in result.population:
        seen: set[str] = set()
        stack = list(by_parents.get(ind.id, []))
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(by_parents.get(cur, []))
        descendants[ind.id] = len(seen)
    return descendants


def compute_meta_fitness(result: RunResult, trend: TrendVector) -> dict[str, MetaFitness]:
    schema = result.schema
    champs = result.champions()
    descendants = evolvability_score(result)

    # Reference centroid from existing paradigms (assembler..ParallelOOP) for novelty
    paradigms = schema.axes.get("paradigm", [])

    trend_norm = trend.normalized()
    trend_axes = list(trend_norm.keys())

    out: dict[str, MetaFitness] = {}
    max_desc = max(descendants.values()) if descendants else 1
    for ind in champs:
        # trend_alignment: dot product of (this individual's ordinal direction
        # from the best-champion seed) with the trend vector.
        seed = result.population[0]
        align_num = 0.0
        align_den = 0.0
        for axis in trend_axes:
            ip = schema.ordinal_index(axis, seed.genome.get(axis, ""))
            ic = schema.ordinal_index(axis, ind.genome.get(axis, ""))
            if ip is None or ic is None:
                continue
            span = max(1, len(schema.ordinal_axes[axis]) - 1)
            d = (ic - ip) / span
            align_num += d * trend_norm[axis]
            align_den += abs(d)
        trend_alignment = align_num / align_den if align_den else 0.0

        # novelty: hamming distance of paradigm+representation+effect+ownership
        # from the nearest "classic paradigm" centroid (uses PARADIGM_CLUSTER).
        from .operators import PARADIGM_CLUSTER

        novelty = 1.0
        for p in paradigms:
            cluster = PARADIGM_CLUSTER.get(p, {})
            if not cluster:
                continue
            mismatch = sum(1 for k, v in cluster.items() if ind.genome.get(k) != v)
            novelty = min(novelty, mismatch / max(1, len(cluster)))
        # invert: closer to a known paradigm = lower novelty
        novelty = 1.0 - (1.0 - novelty)
        novelty = min(1.0, novelty)

        # frontier_coverage: heuristic — how many "advanced" axes did this ind
        # populate (high ordinal value)?
        coverage = 0.0
        for axis, order in schema.ordinal_axes.items():
            ic = schema.ordinal_index(axis, ind.genome.get(axis, ""))
            if ic is None:
                continue
            span = max(1, len(order) - 1)
            coverage += ic / span
        coverage /= max(1, len(schema.ordinal_axes))

        ev = descendants.get(ind.id, 0) / max(1, max_desc)

        comps = {
            "trend_alignment": max(0.0, min(1.0, (trend_alignment + 1) / 2)),
            "frontier_coverage": coverage,
            "novelty": novelty,
            "evolvability": ev,
            "cross_task_generality": ind.fitness_components.get("cross_task_generality", 0.0),
            "implementability": ind.fitness_components.get("implementability", 0.0),
        }
        out[ind.id] = MetaFitness(individual_id=ind.id, components=comps)
    return out


def pareto_layers(meta: dict[str, MetaFitness]) -> list[list[str]]:
    """Non-dominated sorting on meta-fitness components (all maximized)."""
    items = list(meta.values())
    layers: list[list[str]] = []
    remaining = list(items)
    while remaining:
        front: list[MetaFitness] = []
        for x in remaining:
            dominated = False
            for y in remaining:
                if x is y:
                    continue
                if _dominates(y.components, x.components):
                    dominated = True
                    break
            if not dominated:
                front.append(x)
        layers.append([f.individual_id for f in front])
        remaining = [r for r in remaining if r not in front]
        if not front:
            break
    return layers


def _dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    keys = set(a.keys()) | set(b.keys())
    not_worse = all(a.get(k, 0.0) >= b.get(k, 0.0) for k in keys)
    strictly_better = any(a.get(k, 0.0) > b.get(k, 0.0) for k in keys)
    return not_worse and strictly_better
