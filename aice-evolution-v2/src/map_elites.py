"""MAP-Elites runner with full lineage tracking."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable

from .schema import GeneSchema
from .evaluator import evaluate as mock_evaluate, composite_fitness as mock_composite
from .operators import (
    random_genome,
    pick_op,
    MUTATION_REGISTRY,
    CROSSOVER_REGISTRY,
)


EvaluateFn = Callable[[dict[str, str], GeneSchema, list[str]], dict[str, float]]
CompositeFn = Callable[[dict[str, float]], float]


@dataclass
class Individual:
    id: str
    genome: dict[str, str]
    cell: str
    fitness_components: dict[str, float]
    composite: float
    generation: int
    parents: list[str] = field(default_factory=list)
    operator: str = ""


def cell_id(genome: dict[str, str], cell_axes: list[str]) -> str:
    return "|".join(f"{axis}={genome.get(axis, '?')}" for axis in cell_axes)


@dataclass
class RunResult:
    spec: dict[str, Any]
    schema: GeneSchema
    population: list[Individual]
    elite_map: dict[str, str]   # cell_id -> individual id

    def champions(self) -> list[Individual]:
        idx = {ind.id: ind for ind in self.population}
        return [idx[i] for i in self.elite_map.values()]


def run(
    spec: dict[str, Any],
    schema: GeneSchema,
    evaluate_fn: EvaluateFn | None = None,
    composite_fn: CompositeFn | None = None,
) -> RunResult:
    evaluate = evaluate_fn or mock_evaluate
    composite_fitness = composite_fn or mock_composite
    rng = random.Random(spec["search"].get("rng_seed", 0))
    cell_axes = spec["search"]["cell_axes"]
    seed_count = spec["search"]["seed_count"]
    generations = spec["search"]["generations"]

    population: list[Individual] = []
    elite: dict[str, str] = {}
    next_id = [0]

    def fresh_id() -> str:
        next_id[0] += 1
        return f"I{next_id[0]:04d}"

    def consider(ind: Individual) -> bool:
        existing_id = elite.get(ind.cell)
        population.append(ind)
        if existing_id is None:
            elite[ind.cell] = ind.id
            return True
        existing = next(p for p in population if p.id == existing_id)
        if ind.composite > existing.composite:
            elite[ind.cell] = ind.id
            return True
        return False

    tasks = spec["evaluation"]["tasks"]

    # 1) seed
    for _ in range(seed_count):
        g = random_genome(schema, rng)
        f = evaluate(g, schema, tasks)
        ind = Individual(
            id=fresh_id(),
            genome=g,
            cell=cell_id(g, cell_axes),
            fitness_components=f,
            composite=composite_fitness(f),
            generation=0,
            parents=[],
            operator="seed",
        )
        consider(ind)

    # 2) evolution loop
    for gen in range(1, generations + 1):
        # pick a random elite as parent
        parent_id = rng.choice(list(elite.values()))
        parent = next(p for p in population if p.id == parent_id)

        op_kind = "mutation"
        op_name = ""
        # ~30% crossover when there are >= 2 elites
        if len(elite) >= 2 and rng.random() < 0.3:
            other_id = rng.choice([i for i in elite.values() if i != parent_id])
            other = next(p for p in population if p.id == other_id)
            op = pick_op(spec["operators"]["crossovers"], CROSSOVER_REGISTRY, rng)
            if op is None:
                continue
            child_g = op(parent.genome, other.genome, schema, rng)
            op_kind = "crossover"
            op_name = op.__name__
            parents = [parent.id, other.id]
        else:
            op = pick_op(spec["operators"]["mutations"], MUTATION_REGISTRY, rng)
            if op is None:
                continue
            child_g = op(parent.genome, schema, rng)
            op_name = op.__name__
            parents = [parent.id]

        f = evaluate(child_g, schema, tasks)
        ind = Individual(
            id=fresh_id(),
            genome=child_g,
            cell=cell_id(child_g, cell_axes),
            fitness_components=f,
            composite=composite_fitness(f),
            generation=gen,
            parents=parents,
            operator=f"{op_kind}:{op_name}",
        )
        consider(ind)

    return RunResult(spec=spec, schema=schema, population=population, elite_map=dict(elite))


def dump_run(result: RunResult, out_dir: str | Path, name: str) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lineage_path = out / f"{name}.lineage.json"
    elite_path = out / f"{name}.elite_map.json"

    lineage_path.write_text(
        json.dumps([asdict(ind) for ind in result.population], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    champions = result.champions()
    elite_dump = {
        "cells": {
            ind.cell: {
                "id": ind.id,
                "genome": ind.genome,
                "composite": ind.composite,
                "generation": ind.generation,
            }
            for ind in champions
        },
        "filled": len(champions),
    }
    elite_path.write_text(json.dumps(elite_dump, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"lineage": lineage_path, "elite_map": elite_path}
