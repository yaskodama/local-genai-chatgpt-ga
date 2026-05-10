"""Mutation and crossover operators derived from the gene schema.

Phase 9 adds two LLM-directed operators that *grow* the schema during
search (only when `search.open_axes = true`):

  * `llm_proposal`  — propose a new value for a randomly-chosen axis,
                      register it on the schema, and use it.
  * `llm_new_axis`  — propose an entirely new axis with its initial
                      value list, register it, and pick a value.

Both fall back to a deterministic "speculative-value bank" so tests
run without API keys; flip via `set_proposer_mode("ai")` to use real
LLM proposals."""

from __future__ import annotations

import random
from typing import Callable, Optional

from .schema import GeneSchema
from .ai_proposer import (
    SPECULATIVE_VALUES,
    propose_axis_value_mock,
    propose_axis_value_ai,
    propose_new_axis_mock,
    propose_new_axis_ai,
)


_proposer_mode: str = "mock"   # "mock" or "ai"


def set_proposer_mode(mode: str) -> None:
    global _proposer_mode
    _proposer_mode = mode if mode in ("mock", "ai") else "mock"


def get_proposer_mode() -> str:
    return _proposer_mode


PARADIGM_CLUSTER: dict[str, dict[str, str]] = {
    "assembler": {
        "state_representation": "register_int",
        "concurrency_model": "none",
        "type_safety": "none",
        "ownership_model": "none",
        "effect_handling": "implicit",
    },
    "BASIC": {
        "state_representation": "global_num",
        "concurrency_model": "none",
        "type_safety": "low",
        "ownership_model": "none",
        "effect_handling": "implicit",
    },
    "C": {
        "state_representation": "enum_state",
        "concurrency_model": "none",
        "type_safety": "medium",
        "ownership_model": "none",
        "effect_handling": "implicit",
    },
    "Java_OOP": {
        "state_representation": "enum_state",
        "concurrency_model": "threads_locks",
        "type_safety": "high",
        "ownership_model": "gc",
        "effect_handling": "implicit",
    },
    "Functional": {
        "state_representation": "ADT",
        "concurrency_model": "none",
        "type_safety": "high",
        "ownership_model": "gc",
        "effect_handling": "monadic",
    },
    "FunctionalOOP": {
        "state_representation": "ADT",
        "concurrency_model": "structured",
        "type_safety": "high",
        "ownership_model": "gc",
        "effect_handling": "monadic",
    },
    "ParallelOOP": {
        "state_representation": "symbol_owned",
        "concurrency_model": "actor_messages",
        "type_safety": "high",
        "ownership_model": "borrow_check",
        "effect_handling": "algebraic_effects",
    },
}


def random_genome(schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    while True:
        g = {axis: rng.choice(values) for axis, values in schema.axes.items()}
        if schema.is_coherent(g):
            return g


def axis_resample(parent: dict[str, str], schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    """Pick one axis, replace its value with a random allowed value."""
    for _ in range(20):
        child = dict(parent)
        axis = rng.choice(schema.axis_names())
        choices = [v for v in schema.axes[axis] if v != parent.get(axis)]
        if not choices:
            continue
        child[axis] = rng.choice(choices)
        if schema.is_coherent(child):
            return child
    return dict(parent)


def coherent_paradigm_shift(parent: dict[str, str], schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    """Move along the paradigm axis and pull correlated axes along."""
    paradigms = schema.axes.get("paradigm", [])
    if not paradigms:
        return axis_resample(parent, schema, rng)
    current = parent.get("paradigm")
    candidates = [p for p in paradigms if p != current]
    if not candidates:
        return axis_resample(parent, schema, rng)
    for _ in range(10):
        next_p = rng.choice(candidates)
        cluster = PARADIGM_CLUSTER.get(next_p, {})
        child = dict(parent)
        child["paradigm"] = next_p
        for k, v in cluster.items():
            if k in schema.axes and rng.random() < 0.7:
                child[k] = v
        if schema.is_coherent(child):
            return child
    return axis_resample(parent, schema, rng)


def axis_uniform_crossover(a: dict[str, str], b: dict[str, str], schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    for _ in range(20):
        child = {axis: (a.get(axis) if rng.random() < 0.5 else b.get(axis)) for axis in schema.axis_names()}
        if schema.is_coherent(child):
            return child
    return dict(a)


def schema_partition_crossover(a: dict[str, str], b: dict[str, str], schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    """One-point crossover over an ordered axis list."""
    axes = schema.axis_names()
    if len(axes) < 2:
        return dict(a)
    for _ in range(20):
        cut = rng.randint(1, len(axes) - 1)
        left, right = axes[:cut], axes[cut:]
        child = {**{k: a.get(k) for k in left}, **{k: b.get(k) for k in right}}
        if schema.is_coherent(child):
            return child
    return dict(a)


MutationOp = Callable[[dict[str, str], GeneSchema, random.Random], dict[str, str]]
CrossoverOp = Callable[[dict[str, str], dict[str, str], GeneSchema, random.Random], dict[str, str]]


def llm_proposal(parent: dict[str, str], schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    """Propose a brand-new value for one of the existing axes (one that has
    an entry in SPECULATIVE_VALUES). Schema grows in place. Falls back to
    axis_resample when open_axes is off or no candidate is available."""
    axes_with_bank = [a for a in schema.axis_names() if a in SPECULATIVE_VALUES]
    if not axes_with_bank or not schema.open_axes:
        return axis_resample(parent, schema, rng)
    axis = rng.choice(axes_with_bank)
    new_value: Optional[str]
    if _proposer_mode == "ai":
        new_value = propose_axis_value_ai(axis, schema)
        if not new_value:
            new_value = propose_axis_value_mock(axis, schema, rng)
    else:
        new_value = propose_axis_value_mock(axis, schema, rng)
    if not new_value:
        return axis_resample(parent, schema, rng)
    schema.register_value(axis, new_value)
    child = dict(parent)
    child[axis] = new_value
    if not schema.is_coherent(child):
        return axis_resample(parent, schema, rng)
    return child


def llm_new_axis(parent: dict[str, str], schema: GeneSchema, rng: random.Random) -> dict[str, str]:
    """Propose an entirely new axis (with its allowed values) and pick a
    value on it for the child. Falls back to axis_resample on failure."""
    if not schema.open_axes:
        return axis_resample(parent, schema, rng)
    proposed: Optional[tuple[str, list[str]]]
    if _proposer_mode == "ai":
        proposed = propose_new_axis_ai(schema)
        if not proposed:
            proposed = propose_new_axis_mock(schema, rng)
    else:
        proposed = propose_new_axis_mock(schema, rng)
    if not proposed:
        return axis_resample(parent, schema, rng)
    name, values = proposed
    if not schema.register_axis(name, values):
        return axis_resample(parent, schema, rng)
    child = dict(parent)
    child[name] = rng.choice(values)
    if not schema.is_coherent(child):
        return axis_resample(parent, schema, rng)
    return child


MUTATION_REGISTRY: dict[str, MutationOp] = {
    "axis_resample": axis_resample,
    "coherent_paradigm_shift": coherent_paradigm_shift,
    "llm_proposal": llm_proposal,
    "llm_new_axis": llm_new_axis,
}

CROSSOVER_REGISTRY: dict[str, CrossoverOp] = {
    "uniform": axis_uniform_crossover,
    "one_point": schema_partition_crossover,
}


def pick_op(spec_list: list[dict], registry: dict, rng: random.Random):
    """Weighted choice over an op list, skipping ops not in the registry (e.g. llm_*)."""
    usable = [(s, registry[s["name"]]) for s in spec_list if s["name"] in registry and s.get("weight", 0) > 0]
    if not usable:
        return None
    total = sum(s.get("weight", 0) for s, _ in usable)
    pick = rng.uniform(0, total)
    acc = 0.0
    for s, op in usable:
        acc += s.get("weight", 0)
        if pick <= acc:
            return op
    return usable[-1][1]
