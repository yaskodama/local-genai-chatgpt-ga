# Level B-4 — Phase 14 Linear / Use-After-Move (AIPL)

Pure-AIPL extension of Level B-3 that detects **use-after-move** on
`linear T` values.  Linearity is encoded as a string prefix on the
type ("linear int") and "movedness" is encoded as a tenv-side prefix
("&lt;moved&gt; linear int").  The walker scans for `Var` lookups whose
tenv binding starts with `<moved> ` and emits a diagnostic.

## Encoding (no separate `moved` set)

```
declared:    fh -> "linear int"
after consume: fh -> "<moved> linear int"   (newer binding, tail-first wins)
after rebind: fh -> "linear int"             (Assign re-pushes original)
```

This avoids the AIPL-array-pop-less limitation and reuses the
existing tenv shape — Level B-1's tail-first lookup naturally
implements the rebind-clears-moved semantics.

## What's enforced

| Rule                                                          | Sample                  |
| ---                                                           | ---                     |
| use-after-move on `Var`                                       | `SampleUseAfterMove`    |
| double-consume                                                | `SampleDoubleConsume`   |
| rebind clears moved status                                    | `SampleLinearClean`     |
| typeck applied to itself + double-consume violation example   | `SampleSelfConsistency` |

The walker calls `tenv_set(tenv, name, mark_moved(at))` on a Call's
linear-typed parameter when its argument is a bare `Var`.  Only
bare-Var args are tracked; chained expressions (e.g. passing the
result of another Call) are out of scope for B-4.

## Phase monotonicity

| B-3 invariant                       | B-4 status |
| ---                                 | ---        |
| `tenv` shape (array of (name,ty))   | unchanged  |
| tail-first lookup                   | unchanged (rebind reuses this) |
| per-call fresh tenv                 | unchanged |
| `tc_compatible` lattice             | extended only at the boundary (linearity + moved are stripped before comparing) |
| effect-set walker                   | unchanged |
| channel rules                       | unchanged |

The only new walker logic is:
1. one extra branch in `Var` (check `is_moved`)
2. one extra branch in `Call` (mark moved when `linear T` param + Var arg)
3. trivial passthrough updates for Assign / VarDecl

The signature of `tc_infer_expr` etc. is identical to B-3.

## Run

```sh
cd aipl-self-host/level-b4
bash run.sh   samples/SampleLinearClean.abcl
bash run.sh   samples/SampleUseAfterMove.abcl
bash run.sh   samples/SampleDoubleConsume.abcl
bash run.sh   samples/SampleSelfConsistency.abcl

bash smoke.sh
```

## Verification (smoke.sh)

```
PASS  SampleLinearClean.abcl           issues=0
PASS  SampleUseAfterMove.abcl          issues=1
PASS  SampleDoubleConsume.abcl         issues=1
PASS  SampleSelfConsistency.abcl       issues=1
Level B-4 linear samples: 4 pass / 0 fail
```

## Out of scope (deferred)

- **Control-flow refinement**: the host typeck (Phase 14) is precise
  about If branches that end in `return` — the moved set in the post-if
  position only inherits from non-returning branches.  B-4 walks both
  branches without that refinement, so a complex control-flow test
  could give a false positive.
- **Linear values in record/array fields**: a `linear int` stored as a
  record field is treated as the field's declared type (no recursive
  linearity tracking).
- **Linear consumed via crossover assignments** (e.g.
  `var a = b; consume(a);`) — only direct Var args are watched.

## Scope vs other Levels

- B-3: + channel element types.
- **B-4 (this dir)**: + linear / use-after-move.
- B-5 (next): + owned (Phase 15 `pub` field visibility).
- C: + parser, scheduler, mailbox, futures, I/O bridges.
