# aios-claude — ABCL/c+ as an AI-OS scripting layer

[ABCL/c+](USER_MANUAL.md) is a small actor language descended from
the [ABCL/1](https://en.wikipedia.org/wiki/Actor-Based_Concurrent_Language)
family.  This project ships three wire-compatible runtimes for it
and uses the language as the scripting surface of an "AI-OS":
classes are agents, messages are prompts, and the runtime governs
token budgets, concurrency, persistence, and cross-machine
coordination.

```
+------------------+    HTTP / JSON     +-------------------+
| coordinator.abcl |  ----------------> | solver.abcl       |
| (Python)         |  <---------------- |   ai_call(...)    |
|                  |                    |   (Gemini)        |
|                  |                    +-------------------+
|                  |    HTTP / JSON     +-------------------+
|                  |  ----------------> | verifier.abcl     |
|                  |  <---------------- |   ai_call(...)    |
|                  |                    |   (Claude / GPT)  |
+------------------+                    +-------------------+
```

## Implementations

| Runtime | Source | Best for |
|---|---|---|
| OCaml ABCL/c+ | `src/*.ml`, `_build/.../repl_thread.exe` | the canonical interpreter; SDL/Xinu/Python codegen via `abcl2c`; minimal native binary |
| Browser ABCL/c+ | `src/browser-abcl/` | WebGL canvas demos in any browser |
| Python ABCL/c+ | `src/python-abcl/` | the AI-OS surface — every AI provider, every governance knob, distributed mode |

All three speak the same wire protocol: `POST /api/json/send`
(fire-and-forget) and `POST /api/json/call` (synchronous reply).
A coordinator on one runtime can drive workers on the other two
without a translation shim.

## Quick start (Python)

```sh
# 1. system Python 3.9 has the stdlib we need; install the deps
/usr/bin/python3 -m pip install --user -r src/python-abcl/requirements.txt

# 2. run a sample
/usr/bin/python3 src/python-abcl/abcl_main.py src/python-abcl/samples/Hello.abcl

# 3. or open the REPL
/usr/bin/python3 src/python-abcl/abcl_main.py
abcl> class H { method hi(n) { print("hello " + n); } }
abcl> var h = new H();
abcl> send h.hi("world");
abcl> :exit
```

To call an AI provider, set one of the keys before running:

```sh
GEMINI_API_KEY=...    src/python-abcl/abcl_main.py samples-ai/AIChainReal.abcl
ANTHROPIC_API_KEY=... src/python-abcl/abcl_main.py samples-ai/AIChainReal.abcl
OPENAI_API_KEY=...    src/python-abcl/abcl_main.py samples-ai/AIChainReal.abcl
```

`ABCL_AI_PROVIDER=mock` runs every `ai_call` against a built-in mock
so the distributed smoke and CI work without burning tokens.

## Three send types (Python)

```abcl
send target.method(args);                  // past — fire and forget
var x = now target.method(args);           // now — block, return reply
var f = future target.method(args);        // future — non-blocking
var v = await(f);                          //   ... await later
```

Replies come from the receiver via `reply(value)`.

## AI-OS governance knobs

All optional, all env-var driven:

| Variable | Effect |
|---|---|
| `ABCL_AI_PROVIDER` | `gemini` / `anthropic` / `openai` / `mock` |
| `ABCL_AI_TOKEN_BUDGET` | hard token cap; over-budget calls raise `BudgetExceeded` |
| `ABCL_AI_MAX_CONCURRENT` | semaphore on in-flight AI calls |
| `ABCL_AI_FALLBACK_MODELS` | comma-separated chain to retry on rate-limit / 5xx |
| `ABCL_AI_USAGE_FILE` | persist token / cost counters across sessions |
| `ABCL_NODE_STATE_FILE` | persist actor fields **and** undelivered mailbox messages |
| `ABCL_REMOTE_SECRET` | HMAC-SHA256 sign every remote send (X-ABCL-Sig) |
| `ABCL_PEER_DASHBOARDS` | `host:port,...` for the dashboard's cluster view |

## Distributed actors

Three nodes that cooperate via HTTP/JSON.  Provider can be
different on each.

```sh
# Terminal 1
GEMINI_API_KEY=...   /usr/bin/python3 src/python-abcl/abcl_main.py src/python-abcl/samples-remote/solver.abcl
# Terminal 2
ANTHROPIC_API_KEY=.. /usr/bin/python3 src/python-abcl/abcl_main.py src/python-abcl/samples-remote/verifier.abcl
# Terminal 3
/usr/bin/python3 src/python-abcl/abcl_main.py src/python-abcl/samples-remote/coordinator.abcl
```

Same pattern works with an OCaml worker — `web_listen(8080)` on
the OCaml side and the Python coordinator can `remote_now` into
it.  See `abclc/samples-remote/client.abcl` for the OCaml-side
view.

## Live dashboard

```sh
/usr/bin/python3 src/python-abcl/abcl_main.py --dashboard 8800 samples-ai/Budgeted.abcl
```

Open <http://127.0.0.1:8800/> for the live counters, observed
traffic table, and SSE event stream.  Set
`ABCL_PEER_DASHBOARDS=host:port,...` on the coordinator's dashboard
to fold every worker's numbers into a TOTAL row.

## Smoke tests

```sh
make smoke           # OCaml + JS + Python + 3-node mock distributed
make smoke-dynamic   # also opens the JS demos in headless Chrome
```

Latest run:

```
ABCL  : 52/52   (OCaml REPL + abcl2c + cc/SDL2)
JS    : syntax 7/7 + parse 4/4
Python: 7/7
Dist  : 8/8     (3-node distributed mock)
```

## Reference

- Language tour and grammar: [USER_MANUAL.md](USER_MANUAL.md)
- Builtin reference: [BUILTINS.md](BUILTINS.md)
- Sample index: `samples/` and `samples-ai/` and `samples-remote/`
  under `src/python-abcl/`; `abclc/*.abcl` and `abclc/ai-samples/`,
  `abclc/samples-remote/` for the OCaml side

## Related

This project descends from earlier ABCL/c+ work; the goal here is
to make the language useful as the orchestration layer of an
AI-OS — a small DSL where actors are agents, messages are prompts,
and the runtime is responsible for keeping cost, concurrency,
and reliability under control.
