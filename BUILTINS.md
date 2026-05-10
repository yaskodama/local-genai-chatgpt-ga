# AIPL Builtin Reference (Python runtime)

**AIPL** = Actor-based Intelligent Parallel Language (formerly ABCL/c+).

Every builtin available to `.abcl` programs running on the Python
runtime (`src/python-aipl/`).  All are total: filesystem and AI
calls return a sentinel value (`""`, `0`, `None`, etc.) on error
rather than raising, so `.abcl` programs can probe gracefully.

> Internal module/file/extension names (`abcl_*.py`, `.abcl`,
> `ABCL_AI_PROVIDER`) retain the historical naming for backward compat.

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

## Array syntax (Python runtime)

Static and dynamic-sized array declarations + N-D indexed access /
assignment, in addition to the dynamic-array literals (`[1, 2, 3]`)
and `array_*` builtins:

| Form | Meaning |
|---|---|
| `var x[N];` | 1-D, N elements, default 0 |
| `var x[N] = init;` | 1-D, N copies of `init` |
| `var grid[R][C];` | 2-D, R×C cells, default 0 |
| `var grid[R][C] = init;` | 2-D, all cells = `init` |
| `var cube[A][B][C];` | 3-D (or any N) |
| `x[i]`, `grid[i][j]`, ... | element read |
| `x[i] = v;`, `grid[i][j] = v;`, ... | element write |

**Dimensions are arbitrary expressions** — variables, fields, params,
arithmetic — so dynamic sizes work:

```abcl
class Matrix {
  var rows = 4;
  var cols = 5;
  var cells[rows][cols];                   // dynamic from fields
  method poke(i, j, v) { cells[i][j] = v; }
}

var R = 3;
var pad[R][R+1] = -1;                      // dynamic from local + arith
```

Works in field declarations and local variables. See
`samples/Arrays.abcl` (1-D) and `samples/MultiDimArrays.abcl` (N-D).

## Builtin signatures via typeof (Python runtime)

`typeof(builtin_name)` returns the curated static signature; calling the
builtin and applying `typeof` to the result returns the value's
structural type. Both work identically inside actor methods, top-level
code, and user-defined functions.

```abcl
typeof(read_bytes)        → "function(path:string) -> array[int]"
typeof(image_create)      → "function(w:int, h:int, r:int, g:int, b:int [, a:int=255]) -> image"
typeof(ai_call_image)     → "function([provider,] prompt:string, image+) -> string"

typeof(image_create(8,8,0,200,100,255))   → "image(8x8, RGBA)"
typeof(image_pixel(img, 0, 0))             → "tuple(int, int, int, int)"
```

Signatures are documentation-strings (not statically checked), but
they cover I/O, image, AI-call, JSON, dynamic-class, method-patch,
distributed, and meta builtins. See
`samples/Signatures.abcl` for an end-to-end demo.

## User-defined functions (Python runtime)

```
function name(p1, p2) {
  ...
  return expr;        // synchronous return
}
```

Definable at top level **or inside a class body**. In-class functions
are visible to that class's methods unqualified, and inherit the
caller's actor context (so they can read fields and call sibling
in-class functions).

```abcl
class StatActor {
  var samples = [];

  function clamp(x, lo, hi) {            // in-class helper
    if (x < lo) { return lo; }
    if (x > hi) { return hi; }
    return x;
  }

  method add(x) { array_push(samples, x); }
  method summary() {
    var avg = clamp(sum / count, 0, 100);   // sibling helper
    reply(avg);
  }
}
```

**Trace-inferred typeof**: bare function name → `FunctionRef` value.
`typeof(f)` shows the inferred signature accumulated across observed
calls:

```abcl
function describe(x) { return typeof(x) + ":" + x; }
describe(1); describe("a"); describe(3.14);
typeof(describe)
  → "function(x:float | int | string) -> string"
```

## Tuples (組型) and Records (レコード型) (Python runtime)

### Tuples — positional, immutable, fixed-arity

| Form | Meaning |
|---|---|
| `()` | empty tuple |
| `(x,)` | 1-tuple (trailing comma required) |
| `(1, 20, "test")` | N-tuple, types can differ per slot |
| `(2, (3, 4))` | nested tuples |
| `t[i]` | positional read (works on tuples too) |

```abcl
typeof((1, 20, "test"))   → "tuple(int, int, string)"
typeof((2, (3, 4)))       → "tuple(int, tuple(int, int))"
typeof(())                → "tuple()"
typeof((42,))             → "tuple(int)"
```

Distinction from arrays: arrays are homogeneous & mutable (length is
not part of the type); tuples are positional & immutable (length and
per-slot types are part of the type).

### Records (レコード型) — named fields

| Form | Meaning |
|---|---|
| `{ k: v, k: v, ... }` | record literal (Python dict at runtime) |
| `r.field` | field read (chains: `r.a.b.c`) |
| `r.field = v;` | field write (chains too) |
| `typeof(v)` | structural type string |

`typeof` walks values recursively to surface the inferred shape:

```abcl
typeof({ name: "Alice", age: 30 })
  → "record{name:string, age:int}"
typeof({ owner: { id: 1, label: "ops" } })
  → "record{owner:record{id:int, label:string}}"
typeof([1, 2, 3])              → "array[int]"
typeof([1, "a"])               → "array[int | string]"
typeof(42)                     → "int"
typeof(actor_ref)              → "actor(ClassName)"
```

Record fields can hold anything (scalars, arrays, other records,
actors). See `samples/Records.abcl`.

## Files / images / JSON for app generation (Python runtime)

### Binary I/O

| Name | Signature | Notes |
|---|---|---|
| `read_bytes(path)` | `(string)` → `array[int]` | bytes 0-255; `[]` on error |
| `write_bytes(path, bytes)` | `(string, array[int])` → `int` | 1/0 |
| `append_bytes(path, bytes)` | `(string, array[int])` → `int` | 1/0 |

### Image read / write / pixel (Pillow-backed)

| Name | Signature | Notes |
|---|---|---|
| `image_load(path)` | `(string)` → `image` | `None` on error; converted to RGBA |
| `image_save(image, path)` | `(image, string)` → `int` | format from extension |
| `image_create(w, h, r, g, b, a=255)` | `(int, int, int, int, int [, int])` → `image` | filled RGBA image |
| `image_pixel(image, x, y)` | `(image, int, int)` → `tuple(int, int, int, int)` | (r, g, b, a) |
| `image_set_pixel(image, x, y, r, g, b, a=255)` | `(image, int, int, int, int, int [, int])` → `int` | mutates |
| `image_size(image)` | `(image)` → `tuple(int, int)` | (width, height) |

`typeof(image_load("logo.png"))` → `"image(64x64, RGBA)"`.

Image values also expose `.width` / `.height` / `.mode` via record-like
field access for direct reads inside templates.

### Path / directory helpers

`list_dir(path)`, `mkdir(path)`, `path_join(...)`, `path_basename(p)`,
`path_dirname(p)`, `is_dir(p)`, `is_file(p)`, `rm_file(p)`, `cwd()`.

### JSON

| Name | Signature |
|---|---|
| `json_parse(text)` | `(string)` → `record \| array \| scalar` |
| `json_stringify(value, indent=None)` | `(any [, int])` → `string` |

`json_stringify` accepts records, arrays, tuples (serialised as JSON
arrays), images (serialised as `{width, height, mode}`), and scalars.

```abcl
class SiteGen {
  function build_logo() {
    var img = image_create(64, 64, 0, 0, 0, 0);
    var y = 0;
    while (y < 64) do {
      var x = 0;
      while (x < 64) do {
        image_set_pixel(img, x, y, x*4, y*3, 128, 255);
        x = x + 1;
      } y = y + 1;
    }
    return img;
  }
  method generate(config) {
    mkdir("out_site");
    image_save(build_logo(), "out_site/logo.png");
    write_file("out_site/index.html", html_page(config.site_name, "..."));
    write_file("out_site/manifest.json", json_stringify(config, 2));
  }
}
```

See `samples/SiteGen.abcl` for a full HTML+CSS+image+manifest pipeline.

## Dynamic method injection / removal (Python runtime)

| Name | Signature | Notes |
|---|---|---|
| `add_method(target, source)` | `(class-name string \| actor, string)` → `int` | parse `method NAME(p) { ... }` from source and register on the target. Class-level affects all instances; actor-level overrides only that one. Returns count of methods registered (replaces same-name) |
| `remove_method(target, name)` | `(class-name string \| actor, string)` → `int` | remove method by name. Returns 1 if removed, 0 if not present |
| `methods_of(target)` | `(class-name string \| actor)` → `array[string]` | sorted list of currently-available method names (class + per-instance) |

`typeof(actor)` surfaces the method set:
`"actor(Greeter, methods=[greet, init, shout, whisper])"`.

```abcl
class Greeter {
  var label = "g1";
  method greet(n) { print("[" + label + "] hello, " + n); }
}
var g = new Greeter();
add_method("Greeter",
  "method shout(n) { print(\"[\" + label + \"] HEY!! \" + n); }");
var _ = now g.shout("Alice");        // [g1] HEY!! Alice
remove_method("Greeter", "shout");
```

Per-actor override wins over class-level on dispatch, so a single
instance can be patched without affecting siblings. See
`samples/MethodPatch.abcl`.

## Dynamic compile / spawn

| Name | Signature | Notes |
|---|---|---|
| `compile(source)` | `(string)` → `int` | parses AIPL source, registers each `class` declaration into the live class table, executes any top-level statements, returns the count of classes added/replaced |
| `spawn(name, args...)` | `(string, any...)` → `actor` | instantiates a class by string name (registered statically *or* via `compile`); calls `init(args...)` if defined; returns the new actor reference |

Together these enable factory actors that synthesise new behaviour at
runtime — e.g. receive a class spec via message, compile it, spawn an
instance, and reply with the actor reference. See
`samples/Dynamic.abcl` and `samples/DynamicWorkerPool.abcl` for working
examples.

```abcl
class Factory {
  method create(name, source) {
    compile(source);
    reply(spawn(name));
  }
}
var f = new Factory();
var greeter = now f.create("Greeter",
  "class Greeter { method hi(n) { print(\"hello \" + n); } }");
send greeter.hi("world");
```

## Default AI actor (auto-spawned)

The runtime injects `var AI = new AI();` at startup so callers can
dispatch via the standard actor protocols (`now` / `future` / `send`)
instead of the bare `ai_call_*` builtins:

```abcl
var r = now AI.ask("hello");                 // sync
var f = future AI.ask("long task");          // parallel; await(f) later
send AI.ask("fire and forget");

var img = image_load("photo.png");
var d   = now AI.see("describe this", img);  // multimodal
```

Note: `call` is reserved in AIPL (the `call f(args);` statement form),
so the methods are named `ask` for text and `see` for vision:

| Method | Purpose |
|---|---|
| `AI.ask(prompt)` / `AI.ask_p(provider, prompt)` | text |
| `AI.ask_sys(system, prompt)` / `AI.ask_sys_p(provider, system, prompt)` | text + system |
| `AI.see(prompt, image)` / `AI.see_p(provider, prompt, image)` | image |
| `AI.see_sys(system, prompt, image)` / `AI.see_sys_p(provider, system, prompt, image)` | image + system |
| `AI.usage()` / `AI.cost()` / `AI.remaining()` | monitoring |

For real parallelism (one actor processes one message at a time),
spawn extra instances: `var ai2 = new AI();`. Sample: `samples/AIActor.abcl`.

## AI calls

Every `ai_call_*` accepts an **optional provider as the first argument**.
Provider IDs:

- `1` / `"gemini"`                       — Gemini  (default)
- `2` / `"anthropic"` / `"claude"` / `"claudecode"` — Anthropic Claude
- `3` / `"openai"` / `"chatgpt"` / `"gpt"`         — OpenAI ChatGPT
- `0` / `"auto"` / omitted               — auto-select (env var / API key)

Setting `AIPL_AI_PROVIDER=mock` overrides everything (good for tests).

| Name | Signature |
|---|---|
| `ai_call([provider,] prompt)` | `([int|string,] string)` → `string` |
| `ai_call_with_system([provider,] system, prompt)` | `([provider,] string, string)` → `string` |
| `ai_call_priority([provider,] prio, prompt)` | `([provider,] number, string)` → `string` |
| `ai_call_priority_with_system([provider,] prio, system, prompt)` | → `string` |
| `ai_call_retry(max_attempts, prompt)` | `(int, string)` → `string` |
| `ai_call_retry_with_system(max_attempts, system, prompt)` | → `string` |
| **`ai_call_image([provider,] prompt, image[, image, ...])`** | multimodal — text + 1+ image inputs → text |
| **`ai_call_image_with_system([provider,] system, prompt, image[, ...])`** | same with system prompt |
| `ai_usage()` | `()` → `string` |
| `ai_remaining()` | `()` → `int` |
| `ai_cost()` | `()` → `float` |

Image inputs accept any of: an **image value** (from `image_load` /
`image_create`), an **`array[int]`** (from `read_bytes`), raw `bytes`,
or a record `{ path: "x.png" }`. MIME type is auto-sniffed from the
PNG / JPEG / GIF / WebP magic bytes.

Examples:

```abcl
// Provider switching
ai_call("hello");                            // auto / default
ai_call(1, "hello");                         // Gemini
ai_call(2, "hello");                         // Claude
ai_call(3, "hello");                         // ChatGPT
ai_call("anthropic", "hello");               // string alias

// Multimodal
var img = image_load("photo.png");
ai_call_image("describe this", img);
ai_call_image(2, "describe this", img);      // Claude vision
ai_call_image_with_system(2, "be brief", "describe", img);

// Multiple images
ai_call_image(2, "compare these", img1, img2);

// Bytes
var raw = read_bytes("photo.png");
ai_call_image(1, "what file format?", raw);
```

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
