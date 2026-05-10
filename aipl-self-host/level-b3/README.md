# Level B-3 — Phase 13 Channel Element-Type Checker (AIPL)

Pure-AIPL extension of Level B-2 that recognises the channel
builtins (`channel`, `channel_send`, `channel_recv`, `channel_try_recv`,
`channel_close`, `channel_size`) and tracks their element type.

## What's new vs B-2

```aipl
function channel_elem_type(ty: string) {
  // strip "channel[" prefix and "]" suffix
}
```

Special-case branches in `tc_infer_expr`:

| Call site                | inferred type       | extra check                   |
| ---                      | ---                 | ---                           |
| `channel(N, "T")`        | `channel[T]`        | (none)                        |
| `channel(N)`             | `channel[any]`      | (none)                        |
| `channel_send(ch, v)`    | `int`               | `v` ~ channel's `T`           |
| `channel_recv(ch)`       | `T`                 | (consumes for var-decl check) |
| `channel_try_recv(ch)`   | `tuple(int, T)`     |                               |
| `channel_close(ch)`      | `int`               |                               |
| `channel_size(ch)`       | `int`               |                               |

The walker uses Level B-2's `tc_compatible` lattice unchanged, so
unions / `any` / numeric promotion are inherited.

## Phase monotonicity

| Invariant                           | B-3 status |
| ---                                 | ---        |
| Level A's eval shape                | unchanged  |
| Level B-1's `tenv` + tail-first     | unchanged  |
| Level B-1's per-call fresh env      | unchanged  |
| Level B-1's `tc_compatible` lattice | unchanged  |
| Level B-2's effect tracking         | unchanged  |
| Level B-2's `builtin_effects` table | unchanged  |

The channel rules are added at one specific site (Call branch in
`tc_infer_expr`) — sibling-orthogonal to the effect-set walker.

## Run

```sh
cd aipl-self-host/level-b3
bash run.sh   samples/SampleChannelClean.abcl
bash run.sh   samples/SampleChannelSendMismatch.abcl
bash run.sh   samples/SampleChannelRecvMismatch.abcl
bash run.sh   samples/SampleChannelTryRecv.abcl
bash run.sh   samples/SampleSelfConsistency.abcl

bash smoke.sh
```

## Verification (smoke.sh)

```
PASS  SampleChannelClean.abcl          issues=0
PASS  SampleChannelSendMismatch.abcl   issues=1
PASS  SampleChannelRecvMismatch.abcl   issues=1
PASS  SampleChannelTryRecv.abcl        issues=0
PASS  SampleSelfConsistency.abcl       issues=1
Level B-3 channel samples: 5 pass / 0 fail
```

## Diagnostic strings (representative)

```
channel_send: element type mismatch (channel expects int, got string)
var `n` initializer mismatch (expected int, got string)        ← from recv
```

## Out of scope (deferred)

- **Capacity tracking**: `.ga.json` records capacity; the static
  checker doesn't yet flag a `channel_send` past a hard `cap=0`
  unbuffered channel without a matching receiver.  That needs flow
  analysis, not just types.
- **Multi-element-type unions** (`channel[int | string]`):
  representable in the type string but not yet exercised by samples.
- **`select`**: AIPL's runtime `select` (Phase 13b) isn't tracked
  here; the AST shape isn't yet fixed in the bootstrap.

## Scope vs other Levels

- B-2: + capability effects.
- **B-3 (this dir)**: + channel element-type checking.
- B-4 (next): + linear / use-after-move (Phase 14).
- B-5: + owned (Phase 15 `pub` field visibility).
- C: + parser, scheduler, mailbox, futures, I/O bridges.
