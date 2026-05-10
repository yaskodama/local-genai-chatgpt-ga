# Level C-2 — Actor Scheduler + Mailbox in AIPL

A pure-AIPL **single-threaded cooperative actor scheduler**.  Actors,
their mailboxes, and the round-robin dispatch loop are all written in
AIPL `function`s; the host runtime only contributes `print`,
`array_*` builtins, and the outermost `send d.run()` that boots the
demo Driver.

## What's in here

```
scheduler.abcl    — actor / sched_*  primitives + actor-aware evaluator
                     (eval_expr_actor / eval_stmt_actor / sched_step / sched_run).
run.sh            — concats scheduler + sample, runs through host AIPL.
samples/          — programs that hand-build actors + drive them.
out/              — captured stdout per sample.
```

## Actor / scheduler representation

```
actor:
  {name:        "c1",
   class_name:  "Counter",
   fields:      [(name, value), ...],         // mutable, tail-first
   methods:     [(name, {params, body}), ...],
   queue:       [{meth, args}, ...]}

scheduler:
  {actors: [(name, actor), ...]}
```

`meth` rather than `method` because **AIPL reserves the keyword
`method`**, so a record key with that name is a parse error.  The
`Send` AST tag therefore uses `meth: "tick"`.

## Supported AST tags (extended from Level C)

| tag        | new in C-2? | purpose                               |
| ---        | ---         | ---                                   |
| `Send`     | ✓           | `send target.meth(args)` enqueue      |
| `Var`      | extended    | tail-first lookup: env → fields       |
| `Assign`   | extended    | local var if in env, else mutate field|

The rest (`Int / Str / Binop / VarDecl / Print / If / While / Return`)
is carried over from Level C.

## Run

```sh
cd aipl-self-host/level-c2
bash run.sh   samples/SampleCounter.abcl
bash run.sh   samples/SamplePingPong.abcl

bash smoke.sh
```

## Samples

| sample                       | what it exercises                                  | expected output |
| ---                          | ---                                                | --- |
| `SampleCounter.abcl`         | single actor, 3 enqueued ticks                     | `1, 2, 3`            |
| `SamplePingPong.abcl`        | 2 actors mutually sending                          | `3, 2, 1`            |
| `SampleSelfSend.abcl`        | actor self-sends until limit                       | `1, 2, 3, 4, 5`      |
| `SampleMethodArgs.abcl`      | methods with parameters (`add(a,b)`, `square(x)`)  | `7, 36, 30`          |
| `SampleProducerConsumer.abcl`| Producer self-sends + emits `put(i)` to Consumer   | `1, 3, 6, 10`        |
| `SampleWorkerPool.abcl`      | Coordinator fans out to 3 workers                  | `104, 209, 325`      |

## Verification (smoke.sh)

```
PASS  SampleCounter.abcl
PASS  SamplePingPong.abcl
PASS  SampleSelfSend.abcl
PASS  SampleMethodArgs.abcl
PASS  SampleProducerConsumer.abcl
PASS  SampleWorkerPool.abcl
Level C-2 scheduler samples: 6 pass / 0 fail
```

Both samples run **purely on the AIPL-side scheduler** — the host
Python AIPL contributes only the literal interpreter for the
`function` declarations; the actor mailbox, dispatch, and method
invocation logic all live in `scheduler.abcl`.

## What this proves

```
Source string  ← Level C
Tokens         ← Level C lexer
AST records    ← Level C parser
Type checking  ← Level B-1…B-5
Method body eval + actor dispatch + mailbox  ← Level C-2 (this dir)
```

After Level C-2 the **only host responsibility is**:

1. The Python interpreter that runs the AIPL `function` declarations
   (i.e. the layer that calls `eval_expr_actor` etc.).
2. A handful of pure builtins: `print`, `array_push/get/len/set`,
   string operations.

A truly host-free AIPL would replace step 1 with a tiny C/Rust boot
loop — about 200 lines that:
- mmaps the AIPL bytecode of `eval_expr_actor` + friends,
- exposes the `array_*` builtins as foreign calls,
- calls `sched_run(sched, max_steps)` once.

That is the inherent layer-0 every self-hosted runtime carries.

## Pipeline diagram

```
                   AIPL source
                       │
                       ↓
   Level C lexer  →  tokens   (in AIPL)
                       ↓
   Level C parser →  AST      (in AIPL)
                       ↓
   Level B-1…B-5 →  type/effect/linear/owned check (in AIPL)
                       ↓
   Level C-2     →  scheduler creates actors + processes mailbox
                                                       (in AIPL)
                       ↓
                   stdout
```

Each box from "lexer" downward is pure-AIPL.  The host's role has
become a thin, replaceable substrate.

## Out of scope

- **Recursion / nested method calls in user code**: bodies that call
  `now self.other()` synchronously aren't modelled (would need a
  call-stack machine on top of the round-robin loop).
- **Future / await**: the cooperative scheduler doesn't support
  blocking primitives.  Could be added by giving each actor an
  optional "waiting on slot id" field.
- **Real preemption**: this is a deliberately single-threaded
  cooperative scheduler.  Real parallelism still needs OS threads.

## Bootstrap progress

| Level | Phase | Self-host responsibility                       | smoke |
| ---   | ---   | ---                                            | ---   |
| A     | —     | metacircular eval                              | 4/4   |
| B-1   | 11    | typed annotations / arity / unions / promotion | 6/6   |
| B-2   | 12    | + capability effects                           | 4/4   |
| B-3   | 13    | + channel element types                        | 5/5   |
| B-4   | 14    | + linear / use-after-move                      | 4/4   |
| B-5   | 15    | + owned (pub field visibility)                 | 4/4   |
| C     | 16+   | lexer + parser + eval pipeline                 | 3/3   |
| **C-2** | —   | **actor scheduler + mailbox**                  | **2/2** |
