# Level B-1 — Phase 11 Type Checker (AIPL implementation)

Pure-AIPL type checker that mirrors the rules from
`src/python-aipl/aipl_typeck.py` (Phase 11): annotated function
parameters, annotated var-decls, union types, return-type checking,
arity matching.  Sits one rung above Level A's metacircular
evaluator: same record-tagged AST shape, same `(name, value)`
tail-first env idiom, but with one new dimension — types as strings.

## Layout

```
typeck.abcl     — the type checker (functions only, no actor)
run.sh          — concats typeck + a sample, runs through host AIPL
smoke.sh        — runs all 6 samples + verifies expected issue counts
samples/        — typed AST programs (clean + 4 violation kinds + self-consistency)
out/            — captured stdout per sample
```

## AST shape (extended from Level A)

```
Param         {name: "x", type: "int" | "any" | ...}
FunctionDecl  {name, params: [Param], return_type, body: [stmt]}
VarDecl       {tag:"VarDecl", name, type, expr}     // `type` may be "any"
Assign        {tag:"Assign", name, expr}
Print         {tag:"Print", expr}
Return        {tag:"Return", expr}
If            {tag:"If", cond, then_body, else_body}
While         {tag:"While", cond, body}
Call          {tag:"Call", name, args: [expr]}
Var/Int/Str/Binop      same as Level A
```

A program is `{fns: [FunctionDecl], main: [stmt]}`.

## What the checker enforces

| Rule                                            | Sample that exercises it     |
| ---                                             | ---                          |
| arity match at call site                        | `SampleArityViolation`       |
| arg type vs declared param type (`tc_compatible`) | `SampleTypeViolation`      |
| var-decl initializer vs annotation              | `SampleTypeViolation`        |
| return expr vs declared return type             | `SampleReturnViolation`      |
| union types `T1 | T2 | …`                       | `SampleUnion`                |
| `any` wildcard accepts everything               | (used implicitly throughout) |
| numeric promotion `int → float`                 | (used by `SampleUnion`)      |
| typeck applied to itself                         | `SampleSelfConsistency`      |

## Run

```sh
cd aipl-self-host/level-b
bash run.sh   samples/SampleClean.abcl
bash run.sh   samples/SampleArityViolation.abcl
bash run.sh   samples/SampleTypeViolation.abcl
bash run.sh   samples/SampleReturnViolation.abcl
bash run.sh   samples/SampleUnion.abcl
bash run.sh   samples/SampleSelfConsistency.abcl

# all six at once + count check
bash smoke.sh
```

## Verification (smoke.sh)

```
PASS  SampleClean.abcl                 issues=0
PASS  SampleArityViolation.abcl        issues=2
PASS  SampleTypeViolation.abcl         issues=2
PASS  SampleReturnViolation.abcl       issues=1
PASS  SampleUnion.abcl                 issues=1
PASS  SampleSelfConsistency.abcl       issues=1
Level B-1 typeck samples: 6 pass / 0 fail
```

`SampleSelfConsistency` reports `issues=1` because the sample combines
two checks:

1. The typeck's own function signatures (`tc_compatible`, `tc_infer_expr`,
   `tc_check_stmt`, `tc_check_stmt_list`, `tc_check_function`,
   `tc_check_program`) are encoded as a typeck-AST and fed back into
   `tc_check_program(self_spec)`. Result: **0 issues** — the typeck
   accepts its own surface as type-coherent.
2. A deliberately broken caller is then fed in (calls
   `tc_compatible(99, "string")` — int instead of string).
   Result: **1 issue** — the typeck flags it as expected.

The smoke runner sums both (0 + 1 = 1) so a single
`issues=` summary line stays comparable across the suite.

## Design notes

- **Reuse of Level A idioms**: the env shape (`array of (name, value)
  tuples`, tail-first scan), the per-call fresh env trick, and the
  marker-tuple dance for non-local control flow all carry over —
  here `tenv` instead of `env`, and the marker tuple isn't needed
  because the type checker doesn't need to model early-exit Returns.
- **String-encoded types**: matches the host Python checker's
  `_compatible(expected, actual)` — no separate AST for types,
  just `"int"`, `"float"`, `"int | string"`, etc.  Container
  types (`array[T]`, `tuple(...)`, `record{...}`) are out of
  scope for B-1; they need a richer parser and would be the next
  half-step (B-1.5 or B-2).
- **No `str_split` builtin**, so `str_split_on(s, sep)` is hand-rolled
  with `str_sub` + `str_len`.

## Phase monotonicity hook

Level B-2 (Phase 12 effects) extends this checker by:
1. adding an `effects: ["fs", "ai", ...]` field on `FunctionDecl`,
2. propagating each `Call`'s callee effects into the caller's set,
3. flagging callers that declare a strict subset of what they use.

The `tenv` becomes a pair `(type_env, effect_set)` — the existing
Phase 11 path is reused unchanged.

## Scope vs Levels A and C

- Level A: only `eval(ast, env)` is in AIPL.
- **Level B-1 (this dir)**: + Phase 11 type checker is in AIPL.
- Level B-2…B-5: + Phase 12 effects, 13 channels, 14 linear, 15 owned.
- Level C: + parser, scheduler, mailbox, futures, I/O bridges.
