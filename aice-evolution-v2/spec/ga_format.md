# `.ga.json` Intermediate Representation

The canonical file every other component negotiates with. Produced by
the `.aice` v2 parser, consumed by the MAP-Elites runner, the
analysis/ranking pipeline, and (Phase 5+) the AIPL code generator.

## Top-level shape

```json
{
  "name": "NextLanguagePrediction",
  "task": "...",
  "schema": { ... resolved gene schema ... },
  "cells": [ ... cell descriptors derived from cell_axes ... ],
  "operators": { "mutations": [...], "crossovers": [...] },
  "evaluation": { "tasks": [...], "reviewers": [...] },
  "search": { "algorithm": "map_elites", "generations": 30, "seed_count": 8, "open_axes": true },
  "meta_fitness": { "trend_alignment": 0.20, ... },
  "ranking": { "strategy": "pareto_then_pairwise", "scenarios": [...], "top_k": 3 }
}
```

## `schema` block

Resolved form of `gene_schema`. Every axis is enumerated. `open_axes`
allows the runner to add new (axis, value) pairs at runtime; if they
appear, they are written back into the schema in the produced lineage
file so subsequent runs can build on them.

```json
"schema": {
  "axes": {
    "paradigm":            ["assembler","BASIC","C","Java_OOP","Functional","FunctionalOOP","ParallelOOP"],
    "concurrency_model":   ["none","threads_locks","actor_messages","csp_channels","structured"],
    "type_safety":         ["none","low","medium","high","dependent"],
    "state_representation":["register_int","global_num","enum_state","ADT","symbol_owned"],
    "effect_handling":     ["implicit","monadic","algebraic_effects","capability"],
    "ownership_model":     ["none","gc","rc","borrow_check","linear"]
  },
  "coherence": [
    "paradigm=Functional => state_representation in [ADT,symbol_owned]",
    "paradigm=ParallelOOP => concurrency_model != none"
  ],
  "open_axes": true
}
```

## `cells` block

Derived from `search.cell_axes`. Each cell is a unique tuple of values
on the chosen axes. Axes not in `cell_axes` are *free*: the genome
varies inside the cell, but only one champion per cell survives.

```json
"cells": [
  {"id": "C0",  "descriptor": {"paradigm": "assembler",   "concurrency_model": "none",            "type_safety": "none"}},
  {"id": "C1",  "descriptor": {"paradigm": "BASIC",       "concurrency_model": "none",            "type_safety": "low"}},
  ...
]
```

## `operators` block

Fully derivable from the schema; included verbatim so the runner is
self-describing.

```json
"operators": {
  "mutations": [
    {"name": "axis_resample",           "kind": "single_axis",            "weight": 0.5},
    {"name": "coherent_paradigm_shift", "kind": "multi_axis_correlated",  "weight": 0.3},
    {"name": "llm_proposal",            "kind": "llm_directed",           "weight": 0.2}
  ],
  "crossovers": [
    {"name": "uniform",   "kind": "axis_uniform",     "weight": 0.5},
    {"name": "one_point", "kind": "schema_partition", "weight": 0.3},
    {"name": "llm_merge", "kind": "llm_directed",     "weight": 0.2}
  ]
}
```

## Sidecar artifacts produced by the runner

| File | Content |
|---|---|
| `<name>.lineage.json` | every individual: id, parent(s), genome, fitness, generation, cell |
| `<name>.elite_map.json` | snapshot of the final cell -> champion table |
| `<name>.ranking.json` | per-scenario Pareto layers and pairwise win-rates |
| `<name>.report.md` | human-readable summary; trend vector, gaps, ranked candidates |
