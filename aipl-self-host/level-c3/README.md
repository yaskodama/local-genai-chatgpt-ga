# Level C-3 — `now` / `Reply` on the AIPL-Side Scheduler

Adds synchronous send + reply slots to Level C-2's cooperative
scheduler, all in pure AIPL.

## Extensions vs C-2

| component             | C-2                  | C-3                                          |
| ---                   | ---                  | ---                                          |
| message shape         | `{meth, args}`       | `{meth, args, slot}`                         |
| scheduler             | `{actors}`           | `{actors, slots, next_slot}`                 |
| AST tags              | + `Send`             | + `Now` (expr), + `Reply` (stmt)             |
| evaluator semantics   | one-shot send        | + slot allocation + recursive scheduler drive |

## How `now` works

```
   var v = now calc.add(3, 4);   // expression
       ↓
   eval_expr_actor(Now, ...)
       ↓
   slot_id = sched_alloc_slot(sched);
   actor_enqueue(calc, {meth:"add", args:[3,4], slot: slot_id});
   while slot.filled == 0:
       sched_step(sched)         // recursive drive
   return slot.value
```

Inside `calc.add(a, b)`:

```
   reply(a + b);                  // statement
       ↓
   eval_stmt_actor(Reply, ...)
       ↓
   slot_id = lookup_name(env, fields, "__slot__");
   sched_fill_slot(sched, slot_id, a + b);
```

The current-message slot id is threaded through the env via the
special `__slot__` binding that `actor_step_one` plants when it
unpacks each message.

## Sample

```sh
cd aipl-self-host/level-c3
bash run.sh samples/SampleNow.abcl
bash smoke.sh
```

Output:

```
=== Level C-3 — SampleNow ===
7
[sched] ran 2 round(s)
[expected: 7]
PASS  SampleNow.abcl
Level C-3 scheduler samples: 1 pass / 0 fail
```

## Limits / out of scope

- **Deadlock**: if `now A.f()` causes A to internally call `now B.g()`
  which calls `now A.h()`, the recursive drive saturates at
  max_iter=200 and returns 0.  The host Python AIPL avoids this with
  a real thread-per-actor; the AIPL-side scheduler is single-thread.
- **`future` / `await` separation**: Level C-3 collapses both into
  the synchronous `now` form.  Async-style spawn-and-await would
  need pre-allocated slots returned to the caller as opaque values
  — sketchable but not implemented here.
- **Scope-bounded futures (Phase 17)**: would compose with C-3 by
  having `scope` track its own slot ids and force fill on exit.

## Bootstrap progress

| Level | role                                   | smoke |
| ---   | ---                                    | ---   |
| A     | metacircular eval                      | 4/4   |
| B-1…B-5 | Phase 11–15 typeck / effects / channels / linear / owned | 23/23 |
| C     | lexer + parser + eval                  | 3/3   |
| C-2   | actor scheduler + mailbox + Send       | 6/6   |
| **C-3** | **+ `now` / `Reply` synchronous reply** | **1/1** |
