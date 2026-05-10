# OCaml AIPL samples — Phase 11+ contract reference

The OCaml AIPL runtime predates Phase 11–16's typed surface (parameter
annotations, `pub` modifier, capability effects, `linear T`, transient
cast at any-boundary).  The samples in this directory therefore use
the original gradually-typed syntax.

For each OCaml sample listed below, the **typed equivalent** in current
AIPL spec lives under `src/python-aipl/samples/` (or
`src/python-aipl/samples-ai/`, `samples-remote/`).  Both implementations
share the same wire format and runtime semantics — only the surface
syntax differs.

## Mapping table

| OCaml sample (this dir)            | Python AIPL equivalent (current spec)                | Phase 11+ feature illustrated |
| ---                                | ---                                                   | --- |
| `Hello.abcl`                       | `samples/Hello.abcl`                                  | typed `var count: int`, `init(n: int)` |
| `counter.abcl`                     | `samples/Counter.abcl`                                | typed field, transient-cast clean |
| `PingPong.abcl`                    | `samples/PingPong.abcl`                               | typed `init(n: int)`, actor refs |
| `bounded_buffer.abcl`              | `samples/BoundedBuffer.abcl`                          | `pub var size: int` (Phase 15), typed init |
| `Philosophers5.abcl`               | `samples/Philosophers.abcl`                           | typed `init(my_id: int, l, r, n: int)`, `pub var meals` |
| `philosophers.abcl`                | `samples/Philosophers.abcl`                           | same |
| `Phase11_TypedCounter.abcl`        | `samples/Counter.abcl`                                | already current |
| `Phase12_EffectsLog.abcl`          | `samples/Effects.abcl`                                | `!{fs, net, ai, mut}` declarations |
| `Phase13_Channels.abcl`            | `samples/Channels.abcl`                               | `channel(N, "T")`, `channel_send`, `channel_recv` |
| `Phase14_Linear.abcl`              | `samples/Linear.abcl`                                 | `linear T` use-after-move |
| `Phase15_Owned.abcl`               | `samples/Owned.abcl`                                  | `pub` field modifier |
| `web_calc.abcl`                    | `samples-remote/server.abcl`                          | `web_listen`, `web_expose`, remote actor |
| `ai-samples/AIHello.abcl`          | `samples-ai/CooperativeNowFuture.abcl` (similar pattern) | typed AI calls |
| `ai-samples/CooperativeNowFuture.abcl` | `samples-ai/CooperativeNowFuture.abcl`            | typed AI calls + `!{ai, net}` |
| `ai-samples/RemoteCalcServer.abcl` | `samples-remote/server.abcl`                          | typed remote server |
| `ai-samples/RemoteCalcClient.abcl` | `samples-remote/client.abcl`                          | typed remote client |

## Why two implementations?

1. **OCaml**: native runtime, focused on actor scheduling and the
   shape of the program.  The HM-style inferer in `src/infer.ml` does
   simple type inference but does not parse Phase 11–16 surface syntax.
2. **Python**: research / iterating runtime where the Phase 11–16
   features (gradual typing, capability effects, CSP channels, linear
   ownership, symbol_owned, transient cast) are first implemented.

When in doubt about a sample's *intent* in current AIPL terms, read
the Python version — the OCaml version expresses the same actor
program but cannot annotate with the Phase 11+ surface.

## Running

```sh
# OCaml side
make ocaml
echo 'load Hello.abcl' >  /tmp/_run.bat
echo 'compile'          >> /tmp/_run.bat
_build/default/src/repl_thread.exe -f /tmp/_run.bat

# Python side (same program logic, typed surface)
python3 src/python-aipl/aipl_main.py src/python-aipl/samples/Hello.abcl --type-check
```

The Python form additionally accepts `--transient` to enable runtime
type checks at every annotated `any -> T` boundary (Phase 16).
