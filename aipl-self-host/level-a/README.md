# Level A — Metacircular Evaluator (AIPL in AIPL)

Implementation of the Level A bootstrap target from
`aice-evolution-v2/examples/AIPLSelfHost_A_Metacircular.aice`.
Pure-AIPL `eval(ast, env)` that runs a small AIPL subset expressed as
record-tagged ASTs.

## Layout

```
metacircular.abcl    — the evaluator (functions only, no actor)
run.sh               — concats metacircular + a sample, runs through the host
samples/             — AST programs to feed the evaluator
out/                 — captured stdout per sample run
```

## Supported AST node tags

| tag        | shape                                                                |
| ---        | ---                                                                  |
| `Int`      | `{tag:"Int", val:N}`                                                 |
| `Str`      | `{tag:"Str", val:"…"}`                                               |
| `Var`      | `{tag:"Var", name:"x"}`                                              |
| `Binop`    | `{tag:"Binop", op:"+|-|*|/|==|!=|<|>|<=|>=", lhs:..., rhs:...}`      |
| `VarDecl`  | `{tag:"VarDecl", name:"x", expr:...}`                                |
| `Assign`   | `{tag:"Assign", name:"x", expr:...}`                                 |
| `Print`    | `{tag:"Print", expr:...}`                                            |
| `If`       | `{tag:"If", cond:..., then_body:[...], else_body:[...]}`             |
| `While`    | `{tag:"While", cond:..., body:[...]}`                                |
| `Call`     | `{tag:"Call", name:"fn", args:[...]}`                                |
| `Return`   | `{tag:"Return", expr:...}`                                           |

A "program" is `{funcs: [(name, {params, body})…], main: [stmt…]}`.

## Run

```sh
cd aipl-self-host/level-a
bash run.sh samples/SampleHelloMin.abcl
bash run.sh samples/SampleArith.abcl
bash run.sh samples/SampleControl.abcl
bash run.sh samples/SampleFib.abcl
```

Each invocation concatenates `metacircular.abcl` + the sample into
a tmpfile and runs it through the host's Python AIPL interpreter
with `sys.setrecursionlimit(20000)` (the metacircular eval stacks
multiple AIPL frames per host frame so the default 1000 isn't enough).

## Verification

| Sample              | Expected | Actual |
| ---                 | ---      | ---    |
| SampleHelloMin      | `5`      | `5`    |
| SampleArith         | `25`     | `25`   |
| SampleControl       | `10`     | `10`   |
| SampleFib (n=8)     | `21`     | `21`   |

## Design notes

- **Env**: array of `(name, value)` tuples; `meta_env_get` scans
  tail-first so the latest binding wins.  Fresh env per function
  call to avoid leaks (AIPL has no `array_pop`).
- **Return propagation**: `eval_stmt_list` returns a marker tuple
  `(returned?, value)` so a `Return` inside an `If` / `While` body
  unwinds all the way out to the enclosing function-body list.
- **Naming clash**: AIPL has a builtin `env_get` for environment
  variables; our user function is therefore `meta_env_get`.

## Scope (Level A vs B vs C)

- **Level A (this dir)**: parser/typeck/scheduler stay on the host.
  We only move `eval(ast, env)` into AIPL.
- **Level B**: re-implement the Phase 11–15 type / effect / linear /
  owned checkers in AIPL on top of this eval.
- **Level C**: re-implement parser, AST builder, scheduler, mailbox,
  futures, and I/O bridges in AIPL too — leaving only a ~20-line
  bootstrap loader on the host.
