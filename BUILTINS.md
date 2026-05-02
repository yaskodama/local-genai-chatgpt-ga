# ABCL/c+ Builtin Reference (Python runtime)

Every builtin available to `.abcl` programs running on the Python
runtime (`src/python-abcl/`).  All are total: filesystem and AI
calls return a sentinel value (`""`, `0`, `None`, etc.) on error
rather than raising, so `.abcl` programs can probe gracefully.

## I/O and clock

| Name | Signature | Notes |
|---|---|---|
| `print(...)` | `(any...)` → `()` | concatenates all args, line-flushed |
| `wait(ms)` | `(int)` → `()` | sleep for milliseconds |
| `sleep(s)` | `(float)` → `()` | sleep for seconds |
| `now_ms()` | `()` → `int` | wall-clock milliseconds since epoch |
| `now_s()` | `()` → `float` | wall-clock seconds since epoch |
| `random()` | `()` → `float` | uniform [0, 1) |
| `random(n)` | `(int)` → `int` | uniform [0, n) |
| `random(lo, hi)` | `(int, int)` → `int` | uniform [lo, hi) |
| `read_file(path)` | `(string)` → `string` | `""` on error |
| `write_file(path, content)` | `(string, string)` → `int` | 1 on success, 0 on failure |
| `append_file(path, content)` | `(string, string)` → `int` | 1 on success, 0 on failure |
| `file_exists(path)` | `(string)` → `int` | 1 / 0 |
| `env_get(name)` / `env_get(name, default)` | `(string [, string])` → `string` | env var lookup |

## Strings

| Name | Signature | Notes |
|---|---|---|
| `str_len(s)` | `(string)` → `int` | character count |
| `str_sub(s, start)` / `str_sub(s, start, end)` | `(string, int [, int])` → `string` | half-open `[start, end)` |
| `str_contains(haystack, needle)` | `(string, string)` → `bool` |  |
| `str_index(haystack, needle)` | `(string, string)` → `int` | -1 if not found |
| `str_lower(s)` / `str_upper(s)` | `(string)` → `string` |  |
| `str_trim(s)` | `(string)` → `string` | strips ASCII whitespace |
| `str_replace(s, old, new)` | `(string, string, string)` → `string` | replaces all occurrences |
| `str_starts_with(s, prefix)` / `str_ends_with(s, suffix)` | `(string, string)` → `bool` |  |

## Math passthroughs

`cos(x)`, `sin(x)`, `sqrt(x)`, `abs(x)`, `max(...args)`, `min(...args)`,
`int(x)`, `float(x)`, `str(x)`.

## Actor semantics

| Form | Meaning |
|---|---|
| `send t.m(args);` | past — fire-and-forget |
| `var x = now t.m(args);` | now — block until callee `reply()`s |
| `var f = future t.m(args);` | future — return placeholder; `await(f)` later |
| `var v = await(f);` | block on a future |
| `future_done(f)` → `bool` | non-blocking poll |
| `reply(value);` | callee response (sets the future on now/future, logs `[REPLY]` for past) |
| `become Class(args);` | replace the current actor's class + re-init fields |
| `self`, `sender` | special vars inside method bodies |

## AI calls

| Name | Signature |
|---|---|
| `ai_call(prompt)` | `(string)` → `string` |
| `ai_call_with_system(system, prompt)` | `(string, string)` → `string` |
| `ai_call_priority(prio, prompt)` | `(number, string)` → `string` |
| `ai_call_priority_with_system(prio, system, prompt)` | `(number, string, string)` → `string` |
| `ai_call_retry(max_attempts, prompt)` | `(int, string)` → `string` |
| `ai_call_retry_with_system(max_attempts, system, prompt)` | `(int, string, string)` → `string` |
| `ai_usage()` | `()` → `string` (one-line usage summary) |
| `ai_remaining()` | `()` → `int` (tokens left under budget; -1 if no budget) |
| `ai_cost()` | `()` → `float` (running USD) |

Provider auto-selected from `GEMINI_API_KEY` /
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `ABCL_AI_PROVIDER`
override.

## Persistence

| Name | Effect |
|---|---|
| `save_state()` | snapshot every actor's int/float/bool/string fields to `ABCL_NODE_STATE_FILE` |

The interpreter additionally auto-loads on startup and auto-saves
mailbox + fields on graceful shutdown.

## Distributed actors

| Name | Signature | Notes |
|---|---|---|
| `web_listen(port)` | `(int)` → `()` | start HTTP gateway |
| `web_expose(name, actor)` | `(string, actor)` → `()` | optional alias; locals are auto-reachable |
| `remote_call(host:port, actor, method, ...args)` | variadic | fire-and-forget POST |
| `remote_now(host:port, actor, method, ...args)` | variadic → `any` | synchronous, returns the receiver's `reply(value)` |
| `remote_future(host:port, actor, method, ...args)` | variadic → `Future` | non-blocking; `await(f)` later |
| `serve_forever()` | `()` → `()` | block; auto-applied when a gateway is up |

Wire protocol (matches OCaml `web_gateway.ml`):

```
POST /api/json/send  body: {"to":"name","method":"m","args":[...],"from":"who"}
POST /api/json/call  body: same; body returns {"ok":true,"reply":<value>}
```

`X-ABCL-Sig` header (hex SHA-256 HMAC of body) is required iff
`ABCL_REMOTE_SECRET` is set on the receiver.
