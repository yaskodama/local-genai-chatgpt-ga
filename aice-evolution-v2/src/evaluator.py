"""Mock evaluator: deterministic fitness scores so the algorithm is testable
without LLM access. Replaced by real ai_call-backed reviewers in Phase 6."""

from __future__ import annotations

from .schema import GeneSchema


# Per-task ideal genome fragments. The mock score is the fraction of axes
# in the task profile that the genome matches, plus a small smoothness bonus
# for ordinal axes (closeness on the ordinal scale, not just exact match).
TASK_PROFILES: dict[str, dict[str, str]] = {
    # original (concurrency / state-machine) tasks
    "TrafficLight": {
        "paradigm": "ParallelOOP",
        "state_representation": "symbol_owned",
        "concurrency_model": "actor_messages",
        "type_safety": "high",
    },
    "BankAccount": {
        "paradigm": "Java_OOP",
        "state_representation": "enum_state",
        "concurrency_model": "threads_locks",
        "type_safety": "high",
        "ownership_model": "gc",
    },
    "Philosophers": {
        "paradigm": "ParallelOOP",
        "concurrency_model": "actor_messages",
        "ownership_model": "borrow_check",
        "type_safety": "high",
    },
    # Phase 7 additions: more diverse problem domains
    "WebService": {  # REST endpoint, request/response, effect handling
        "paradigm": "FunctionalOOP",
        "concurrency_model": "structured",
        "type_safety": "high",
        "effect_handling": "algebraic_effects",
        "ownership_model": "gc",
    },
    "DataPipeline": {  # streaming transform, ADTs, pure stages
        "paradigm": "Functional",
        "state_representation": "ADT",
        "concurrency_model": "csp_channels",
        "type_safety": "high",
        "effect_handling": "monadic",
    },
    "Compiler": {  # AST transform, dependent-ish types, no concurrency
        "paradigm": "Functional",
        "state_representation": "ADT",
        "concurrency_model": "none",
        "type_safety": "dependent",
        "ownership_model": "gc",
    },
}

# Reviewer-style sub-fitness components. Each is a property of the genome
# alone; the per-task suitability is a separate dimension.
REVIEWER_WEIGHTS: dict[str, dict[str, float]] = {
    "Plausibility": {"paradigm_match": 0.5, "task_fit": 0.5},
    "Coherence": {"coherence_pass": 1.0},
    "Implementability": {"impl_score": 1.0},
}


def _ordinal_distance(schema: GeneSchema, axis: str, a: str, b: str) -> float:
    ia = schema.ordinal_index(axis, a)
    ib = schema.ordinal_index(axis, b)
    if ia is None or ib is None:
        return 1.0 if a != b else 0.0
    span = max(1, len(schema.ordinal_axes[axis]) - 1)
    return abs(ia - ib) / span


def task_fit(genome: dict[str, str], task: str, schema: GeneSchema) -> float:
    profile = TASK_PROFILES.get(task)
    if not profile:
        return 0.5
    matched = 0.0
    for axis, want in profile.items():
        got = genome.get(axis)
        if got == want:
            matched += 1.0
        elif axis in schema.ordinal_axes:
            matched += max(0.0, 1.0 - _ordinal_distance(schema, axis, got, want))
    return matched / len(profile)


def implementability(genome: dict[str, str], schema: GeneSchema) -> float:
    """Higher type_safety + reasonable concurrency = easier to verify; but
    pushing every axis to the maximum is implausible (engineering cost)."""
    score = 0.6
    ts = schema.ordinal_index("type_safety", genome.get("type_safety", "none")) or 0
    score += 0.05 * ts
    cm = schema.ordinal_index("concurrency_model", genome.get("concurrency_model", "none")) or 0
    score += 0.04 * cm
    if genome.get("type_safety") == "dependent":
        score -= 0.10
    if genome.get("ownership_model") == "linear":
        score -= 0.05
    return max(0.0, min(1.0, score))


def coherence_score(genome: dict[str, str], schema: GeneSchema) -> float:
    return 1.0 if schema.is_coherent(genome) else 0.0


def evaluate(genome: dict[str, str], schema: GeneSchema, tasks: list[str]) -> dict[str, float]:
    """Returns per-task fitness plus the reviewer dimensions used by Phase 3
    meta-fitness aggregation."""
    per_task = {f"task::{t}": task_fit(genome, t, schema) for t in tasks}
    impl = implementability(genome, schema)
    coh = coherence_score(genome, schema)
    cross_task = sum(per_task.values()) / max(1, len(per_task))
    paradigm_match = max(per_task.values()) if per_task else 0.0
    return {
        **per_task,
        "implementability": impl,
        "coherence": coh,
        "cross_task_generality": cross_task,
        "paradigm_match": paradigm_match,
    }


def composite_fitness(scores: dict[str, float]) -> float:
    """Single scalar used by MAP-Elites to compare two genomes within the
    same cell. Meta-fitness ranking in Phase 3 is separate."""
    return (
        0.40 * scores.get("cross_task_generality", 0.0)
        + 0.25 * scores.get("paradigm_match", 0.0)
        + 0.20 * scores.get("implementability", 0.0)
        + 0.15 * scores.get("coherence", 0.0)
    )
