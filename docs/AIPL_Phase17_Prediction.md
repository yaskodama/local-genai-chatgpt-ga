# AIPL Phase 17 — Next-Generation Language Prediction

**Date**: 2026-05-10
**GA spec**: `aice-evolution-v2/examples/AIPLPostC2_NextGen.aice`
**Seed state**: AIPL Phase 11–16 + self-host Levels A〜C-2 (all 36/36 smoke tests passing)
**RNG seed**: `1717`, **generations**: 50, **seed_count**: 14, **open_axes**: true

## TL;DR

The MAP-Elites trend over 50 generations of cross-task evaluation
(verified concurrency / AI self-modification / distributed CRDT /
real-time bounds / session-typed protocols / self-evolution)
converges on a single dominant direction:

```
concurrency_model       +0.50    ← strongest pull
type_safety             +0.25
ownership_model         +0.25
```

The GA recommends **Phase 17 should be structured concurrency** —
moving AIPL's concurrency axis from `actor_messages` / `csp_channels`
(Phase 9 + 13) up to `structured`, the next ordinal step the
schema already enumerates.

## Top 5 elites

| rank | composite | gen | genome (compact) |
| ---  | ---       | --- | --- |
| 1 | 0.657 | 25 | FunctionalOOP / ADT / **structured** / high / monadic / none |
| 2 | 0.657 | 41 | FunctionalOOP / ADT / **structured** / high / implicit / borrow_check |
| 3 | 0.657 | 43 | FunctionalOOP / symbol_owned / **structured** / high / monadic / none |
| 4 | 0.649 | 27 | BASIC / global_num / actor_messages / high / implicit / gc |
| 5 | 0.649 | 49 | BASIC / **session_typed** / actor_messages / high / implicit / gc |

The top 3 share `concurrency_model=structured` + `type_safety=high`.
Rank 5 carries a **novel axis value** (`state_representation=session_typed`)
that the GA proposed via `open_axes=true`.

## Frequency among the 61 elite cells

| axis              | top values (count)                                                |
| ---               | ---                                                               |
| paradigm          | BASIC (24), ParallelOOP (11), Quantum_Aware (5), C (7)            |
| state_representation | symbol_owned (16), global_num (14), ADT (13), **session_typed (1)** |
| concurrency_model | threads_locks (19), none (16), **structured (12)**, csp_channels (6), **STM (1)** |
| type_safety       | high (19), medium (18), dependent (9)                             |
| effect_handling   | implicit (34), algebraic_effects (10), capability (6), **verified_effects (1)** |
| ownership_model   | none (28), gc (17), borrow_check (8), linear (7), rc (1)          |

## Novel axes / values proposed by `open_axes`

The `--open_axes=true` proposers (LLM-directed mutation operators)
suggested four values not in the original schema:

| axis              | new value                       | rationale (from reviewer personas) |
| ---               | ---                             | --- |
| `concurrency_model` | `software_transactional_memory` | STM as a sibling to `csp_channels` |
| `effect_handling`   | `verified_effects`              | effects with formally proven bounds |
| `state_representation` | `session_typed`              | session types as a state dimension |
| `paradigm`          | `Quantum_Aware`                 | quantum-bit-aware computation       |

## Phase 17 recommendation

### Primary: Phase 17 = `concurrency_model = structured`

Structured concurrency is **the** universal direction. AIPL already
has actor messages (Phase 9 baseline) and CSP channels (Phase 13);
the next step is **scoped task hierarchies** with automatic
cancellation and deterministic shutdown.

What this would look like in AIPL:

```
class Coordinator {
  method run() {
    // structured scope: all spawned tasks join (or are cancelled)
    // before run() returns.
    scope {
      var f1 = spawn worker_a();
      var f2 = spawn worker_b();
      // any failure here cancels the other; the scope only exits
      // once both complete.
      var v = await(f1) + await(f2);
      return v;
    }
  }
}
```

Static rules to add:

- a `scope { ... }` block delimits a task hierarchy
- `spawn` inside scope must not escape the scope
- on early `return` / panic, all in-flight tasks are cancelled
- the static checker proves no spawned future outlives its scope

This composes cleanly with Phase 11–16:

- Phase 11 types: `linear future[T]` becomes well-defined (the
  scope guarantees consumption)
- Phase 12 effects: `!{spawn}` effect category is a natural addition
- Phase 13 channels: scope-bounded channels close automatically
- Phase 14 linear: future handles already linear-friendly
- Phase 15 owned: actor scope = ownership scope

### Secondary candidates (Phase 18+)

| candidate                    | rationale | implementation cost |
| ---                          | ---       | --- |
| `state_representation = session_typed` | typed multi-step protocols (auth → request → ack → close) | medium — new AST tag + protocol type checker |
| `effect_handling = verified_effects`   | formally prove effect bounds (e.g. `!{fs}` calls ≤ 5 per request) | high — needs proof obligations |
| `concurrency_model = software_transactional_memory` | retry-based atomic state | medium — runtime support + commit log |
| `paradigm = Quantum_Aware`             | qubit-aware data types | speculative; out of near-term scope |

## Comparison with Phase 9's prediction

Phase 9 (the original 2026-04 prediction, before any of Phase 11–16
existed) produced 5 universal axes — all now implemented:

| Phase 9 axis                       | implementation phase | Self-host Level |
| ---                                | ---                  | --- |
| type_safety = high/dependent       | Phase 11             | B-1 |
| effect_handling = capability       | Phase 12             | B-2 |
| concurrency_model = csp_channels   | Phase 13             | B-3 |
| ownership_model = linear           | Phase 14             | B-4 |
| state_representation = symbol_owned| Phase 15             | B-5 |

Phase 17's prediction is qualitatively different:

- **Phase 9** gave us 5 axes simultaneously (a "next-gen language"
  package).
- **Phase 17** gives us a **single dominant axis** (concurrency =
  structured).  The other dimensions have already saturated;
  there's no comparable consensus on a second axis to advance.

That single-axis convergence is *itself* a signal: AIPL post-Level
C-2 is approaching the local optimum of this cell space.  Further
progress likely requires either (a) the new open_axes values to
mature into recognized dimensions (session types, verified effects)
or (b) a new schema entirely — e.g. axes around AI-native primitives
or distributed-first design.

## Artifacts

| file | content |
| ---  | --- |
| `aice-evolution-v2/examples/AIPLPostC2_NextGen.aice`        | input spec |
| `aice-evolution-v2/out/postC2/AIPLPostC2_NextGen.ga.json`   | lowered GA spec |
| `aice-evolution-v2/out/postC2/AIPLPostC2_NextGen.lineage.json` | per-individual record |
| `aice-evolution-v2/out/postC2/AIPLPostC2_NextGen.elite_map.json` | 61 elite cells |
| `aice-evolution-v2/out/postC2/AIPLPostC2_NextGen.report.md` | auto report |
| `aice-evolution-v2/viz/postC2.html`                          | Chart.js dashboard |
| `aice-evolution-v2/viz/postC2_tree.html`                     | SVG lineage tree |

## Reproduce

```sh
cd aice-evolution-v2
ABCL_AI_PROVIDER=mock /usr/bin/python3 -m src.cli \
  examples/AIPLPostC2_NextGen.aice -o out/postC2

/usr/bin/python3 -m src.viz_generations \
  out/postC2/AIPLPostC2_NextGen.lineage.json viz/postC2.html
/usr/bin/python3 -m src.viz_lineage_tree \
  out/postC2/AIPLPostC2_NextGen.lineage.json viz/postC2_tree.html
```

Deterministic via `rng_seed: 1717`.  No API key needed under
`ABCL_AI_PROVIDER=mock`.
