# Level B-2 — Phase 12 Capability Effects (AIPL implementation)

Pure-AIPL effect-set checker that mirrors `src/python-aipl/aipl_typeck.py`'s
Phase 12 rules, layered on top of Level B-1's type checker.  A
function declares its capability effects with `effects: ["fs", "ai", ...]`
in its AST decl, and the checker propagates effects through Call
chains and flags any caller whose declared set is a strict subset of
what its body actually uses.

## Effect lattice

| effect | what it covers | builtins that emit it |
| ---    | ---            | --- |
| `fs`   | filesystem    | `read_file`, `write_file`, `read_bytes`, `write_bytes`, `list_dir`, `mkdir`, `image_load`, `image_save` |
| `ai`   | AI provider call | `ai_call`, `ai_call_with_system`, `ai_call_image[…_with_system]`, `ai_call_priority[…_with_system]` |
| `net`  | network        | `web_listen`, `web_expose`, `remote_call`, `remote_now`, `remote_future` |
| `mut`  | program mutation | `compile`, `spawn`, `add_method`, `remove_method` |

`ai_call_*` is treated as `{ai, net}` — AI calls go over the wire.

## Layout

```
typeck.abcl     — Level B-1 typeck + Phase 12 effect tracking (one file)
run.sh          — concats typeck + sample, runs through host AIPL
smoke.sh        — runs all 4 samples + verifies issue counts
samples/        — clean, missing, indirect, self-consistency
out/            — captured stdout per sample
```

## What's new vs B-1

The walker (`tc_infer_expr`, `tc_check_stmt`, …) now carries an
`observed` array threaded through every Call.  When the walker sees a
Call:

- to a **builtin**: union the builtin's hard-coded effect list into `observed`.
- to a **user function**: union the callee's *declared* `effects`
  field into `observed`, plus do the existing arg-type check.

After walking each function body, `tc_check_function` computes
`eff_missing(declared, observed)` — any effect in `observed` not in
`declared` becomes an issue.

## Run

```sh
cd aipl-self-host/level-b2
bash run.sh   samples/SampleEffectClean.abcl
bash run.sh   samples/SampleEffectMissing.abcl
bash run.sh   samples/SampleEffectIndirect.abcl
bash run.sh   samples/SampleSelfConsistency.abcl

bash smoke.sh
```

## Verification (smoke.sh)

```
PASS  SampleEffectClean.abcl           issues=0
PASS  SampleEffectMissing.abcl         issues=2
PASS  SampleEffectIndirect.abcl        issues=1
PASS  SampleSelfConsistency.abcl       issues=1
Level B-2 effects samples: 4 pass / 0 fail
```

`SampleSelfConsistency` keeps the B-1 convention: 0 from the clean
self-spec + 1 from the deliberately broken sibling = 1 aggregated.

## Phase monotonicity ✓

Level B-2 *extends* B-1 without breaking any of its invariants:

| B-1 invariant                              | B-2 status |
| ---                                        | ---        |
| `tenv` shape (array of `(name, ty)` tuples) | unchanged |
| tail-first lookup wins                     | unchanged |
| per-call fresh `tenv`                      | unchanged |
| `tc_compatible` lattice                    | unchanged |
| Type rules (arity / arg / var / return)    | preserved verbatim |

Added (orthogonal axis):

- `effects: [...]` field on FunctionDecl
- `observed` array threaded through walker
- `eff_has` / `eff_add` / `eff_union` / `eff_missing` / `eff_render`
- `builtin_effects(name)` table
- `tc_check_function` post-walk completeness check

`tenv` and `observed` are siblings; neither knows about the other.
The Phase 12 layer is composed, not interleaved.

## Scope vs Level B-1 / B-3 / C

- B-1: types only.
- **B-2 (this dir)**: + capability effects.
- B-3 (next): + Phase 13 channel element-type checking.
- B-4: + Phase 14 linear / use-after-move.
- B-5: + Phase 15 owned (pub field visibility).
- C:   + parser, scheduler, mailbox, futures, I/O bridges.
