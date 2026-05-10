# aipl_modelcheck — Bounded Model Checker for AIPL Actor Programs

Pure-Python state-space exploration tool that detects deadlocks and
checks safety / progress properties of AIPL-style actor systems.
Uses bounded LTL (G, F, ¬, ∧, ∨) over the reachable state set.

## Why

AIPL programs interleave message-passing across actors.  Some
schedules can deadlock (the dining-philosophers being the textbook
example).  Static type/effect/linear/owned checks (Phase 11–15)
guarantee local soundness but say nothing about global *liveness* /
*deadlock-freedom*.  The model checker fills that gap by exhausting
all schedules up to a depth bound and reporting any state where
every actor is permanently blocked.

## Files

```
aipl_modelcheck.py          core: World / MCActor / LTL / ModelChecker
modelcheck/philosophers.py  dining-philosophers model + CLI
modelcheck/ltl_examples.py  φ1 (safety) + φ2 (progress) demo
modelcheck/README.md        this file
```

## API

```python
from aipl_modelcheck import World, MCActor, ModelChecker, LTL

class Fork(MCActor):
    def __init__(self, fid):
        self.fid = fid
        self.held = None
        self.queue = ()
    def request(self, world, sender):
        if self.held is None:
            self.held = sender
            world.send(sender, "granted", sender=self.name)
        else:
            self.queue = self.queue + (sender,)
    def release(self, world, sender):
        if self.queue:
            nxt, *rest = self.queue
            self.queue = tuple(rest)
            self.held = nxt
            world.send(nxt, "granted", sender=self.name)
        else:
            self.held = None

# … plus Philosopher class with try_eat / granted methods …

def init():
    w = World()
    for i in range(3): w.add(f"f{i}", Fork(i))
    for i in range(3): w.add(f"p{i}", Philosopher(i, ...))
    for i in range(3): w.send(f"p{i}", "try_eat", sender=f"p{i}")
    return w

mc = ModelChecker(init, depth=2000)
result = mc.check_deadlock_free(is_terminal=lambda s: ...)
print(result.render())

# Or LTL:
formula = LTL.Globally(LTL.Not(LTL.Atom(my_predicate)))
mc.check(formula)
```

## Run the philosophers demo

```sh
cd src/python-aipl

# Naive (deadlock-prone) vs Ordered (deadlock-free), 3 philosophers:
python3 modelcheck/philosophers.py --N 3 --meals 1

# 5 philosophers — slower but tractable:
python3 modelcheck/philosophers.py --N 5 --meals 1 --depth 5000
```

## Verified results

```text
=== naive N=5 meals=1 ===
[modelcheck] verdict: VIOLATION
  states explored : 50236
  max depth       : 35
  deadlock states : 1
  counter-example trace:
      0  depth=  1  step: p0
      ...
     19  depth= 20  step: f0     ← dead-end state reached

=== ordered N=5 meals=1 ===
[modelcheck] verdict: OK
  states explored : 46662
  max depth       : 35
  deadlock states : 0
```

LTL examples (3 philosophers):

```text
=== naive   (deadlock-prone) ===
  ✗  φ1: G ¬all_hungry_holding_lo (safety)
  ✓  φ2: F all_done                (progress)

=== ordered (deadlock-free) ===
  ✓  φ1: G ¬all_hungry_holding_lo (safety)
  ✓  φ2: F all_done                (progress)
```

The naive variant violates safety (a state where all 3 philosophers
hold their low fork while still hungry IS reachable) but the bounded
checker still finds *some* schedule where everyone finishes — that's
why φ2 reads ✓ on naive.  This is the textbook distinction between
"a deadlock is possible" (safety violation) and "the program can
make progress on some schedule" (existential liveness).

## Architecture

```
┌─────────────────────────────────┐
│  init() -> World                │   user-supplied
│  fork0=Fork(0); phil0=...       │
│  send phil0.try_eat;            │
└─────────────────┬───────────────┘
                  │
                  ↓
┌─────────────────────────────────┐
│  ModelChecker.reachable()       │   BFS over interleavings
│  visited[sig]= (state, depth)   │   parent links for trace recon
└─────────────────┬───────────────┘
                  │
       ┌──────────┴──────────┐
       ↓                     ↓
 check_deadlock_free()   check(LTL formula)
 (safety + counter ex.)  (G/F/¬/∧/∨ on reachable)
```

State signature = sorted tuple of (actor_name, repr(actor)) ⊗
sorted tuple of (actor_name, mailbox).  Two states with identical
fields and identical pending mailboxes are treated as the same node
(visited-set pruning); deepcopy is used per step so methods can
mutate freely.

## Loading `.abcl` files directly

`aipl_modelcheck_load.py` parses an AIPL source file with the
existing `aipl_parser`, walks the resulting AST, and dynamically
synthesises an `MCActor` subclass per `class` declaration.  The
top-level `var x = new C(args);` and `send target.method(args);`
statements build the initial `World`.

```sh
# Detect deadlock in a 2-lock acquire-in-opposite-order pattern:
python3 aipl_modelcheck_load.py samples-mc/TwoLockDeadlock.abcl --depth 500

# Verify the ordered fix is deadlock-free:
python3 aipl_modelcheck_load.py samples-mc/TwoLockOrdered.abcl --depth 500
```

For accurate deadlock vs normal-halt classification, supply a
program-aware `is_terminal` predicate from Python:

```python
from aipl_modelcheck_load import load_program
from aipl_modelcheck    import ModelChecker

def all_phils_done(state):
    return all(a._fields.get("done", 0) == 1
               for a in state.actors.values()
               if hasattr(a, "_fields") and "done" in a._fields)

init, _ = load_program("samples-mc/TwoLockDeadlock.abcl")
mc = ModelChecker(init, depth=500)
res = mc.check_deadlock_free(is_terminal=all_phils_done)
print(res.render())
```

### AIPL subset accepted by the loader

| feature                          | supported? |
| ---                              | --- |
| `class C { var f = init; method m(p) { ... } }` | ✓ |
| `var x = new C(args);` (top-level)               | ✓ |
| `send target.method(args);` / `send self.m()`    | ✓ |
| `if (cond) ... else ...` / `while (c) do { ... }`| ✓ |
| `+ - * /  ==  != < > <= >=`                      | ✓ |
| `array_push / get / len / empty`, `str_eq`        | ✓ |
| `print(...)`                                     | no-op (output unobserved) |
| `now / future / await / become`                  | ✗ (out of scope for safety) |
| `compile / spawn / add_method`                   | ✗ |
| Records / tuples / typed annotations             | partially ignored |
| AI / file / image builtins                       | ✗ |

The subset is intentionally narrower than the full runtime: the
goal is *deadlock detection over the actor message-passing graph*,
not full program execution.

## Limitations

- **Bounded**: BFS terminates at `depth` or visited-set saturation.
  Unbounded-state systems (e.g. counter that grows without limit)
  give incomplete results.
- **No abstract domains**: every actor field is concrete.  Symmetry
  reduction / partial-order reduction are future work.
- **LTL-lite**: only G / F / ¬ / ∧ / ∨ over Atoms.  X (next), U
  (until), R (release) need the full bounded-LTL evaluator.
- **Hand-modelled**: actors must currently be hand-written Python
  subclasses of MCActor.  An AIPL-AST-to-MCActor translator is
  obvious future work — the AST shape we already use in self-host
  Levels A–C-3 is most of the way there.

## Bigger picture

```
┌────────────────────────────────────────────────────┐
│  Phase 11–15 (static)                              │
│  type / effect / channel / linear / owned checks   │
│  → local soundness                                 │
└──────────────────────────────────────────────────┬─┘
                                                   │
                                                   │   composes with
                                                   ↓
┌────────────────────────────────────────────────────┐
│  Phase 16 (transient cast)                         │
│  → dynamic soundness at any-boundary               │
└──────────────────────────────────────────────────┬─┘
                                                   │
                                                   ↓
┌────────────────────────────────────────────────────┐
│  aipl_modelcheck (bounded LTL, this dir)           │
│  → global safety / deadlock-freedom under bound K  │
└────────────────────────────────────────────────────┘
```

The model checker sits one rung above the type system: where the
checkers prove "this single function is internally type-coherent",
the model checker proves "this multi-actor system has no schedule
that ends in a stuck configuration".  Together they form a layered
verification stack that's orthogonal to the LLM-driven prediction
infrastructure (`aice-evolution-v2`).
