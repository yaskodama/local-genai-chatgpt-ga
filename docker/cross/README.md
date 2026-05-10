# Cross-language remote-actor demo

Two AIPL runtimes (Python and OCaml) running in separate Docker
containers on a shared bridge network, dispatching `now`-style
synchronous remote calls to each other over the wire-compatible
`/api/json/call` endpoint.

## Topology

```
docker network: aipl-net
  ├─ pyserver:8080   (aipl-python:cross — exposes Counter actor)
  └─ ocserver:8080   (aipl-ocaml:cross  — exposes Calc actor)

drivers (run as one-shot containers on the same network):
  ├─ python_driver.abcl  (Python -> pyserver + ocserver)
  └─ ocaml_driver.abcl   (OCaml  -> ocserver + pyserver)
```

Both servers and both drivers use **the same wire format**
(`POST /api/json/call`, body `{"to","method","args","from"}`,
returning `{"reply": <value>}`).  No protocol shim — the OCaml
`Remote_client.remote_call` and the Python `aipl_remote.remote_call_sync`
are byte-compatible.

## Files

| Path | What |
| --- | --- |
| `Dockerfile.python`           | Python AIPL container (single stage, slim Python 3.12) |
| `Dockerfile.ocaml`            | OCaml AIPL container (multi-stage: opam build + Debian-slim runtime with libsdl2-2.0-0) |
| `ocaml_run.sh`                | Wrapper that drives `repl_thread.exe -f` so the gateway thread keeps serving after `compile` |
| `run-cross.sh`                | Orchestration script (build / up / down) — replaces `docker compose` |
| `samples/python_server.abcl`  | Python server: Counter (tick / get / add) on :8080 |
| `samples/ocaml_server.abcl`   | OCaml server: Calc (add / square / bump) on :8080 |
| `samples/python_driver.abcl`  | Python driver: 7 cross-language remote calls |
| `samples/ocaml_driver.abcl`   | OCaml driver: 5 cross-language remote calls |

## Run

Two drivers are provided.  `run-compose.sh` is the recommended path
once you have docker compose v2 installed; it honors healthchecks
and `depends_on` so drivers don't fire before the servers are ready.
`run-cross.sh` is the plain-`docker run` fallback for hosts without
the compose plugin.

```sh
# --- with docker compose v2 (recommended) ---------------------------
bash docker/cross/run-compose.sh           # build + up + drivers
bash docker/cross/run-compose.sh build     # build images only
bash docker/cross/run-compose.sh up        # start servers + run drivers
bash docker/cross/run-compose.sh down      # tear down

# --- without docker compose (plain docker run) ---------------------
bash docker/cross/run-cross.sh             # build + up + drivers
bash docker/cross/run-cross.sh down        # tear down
```

If `docker compose` is missing, install via Homebrew on macOS:
```sh
brew install docker-compose
# then add the cli plugin path to ~/.docker/config.json:
#   { "cliPluginsExtraDirs": ["/opt/homebrew/lib/docker/cli-plugins"] }
docker compose version    # should print "Docker Compose version 5.x"
```

The first build pulls the `ocaml/opam:debian-12-ocaml-5.1` base and
runs `dune build` inside the builder stage — expect ~5–10 minutes
the first time.  Subsequent builds reuse the layer cache.

## Expected output (abridged)

```text
==================== Python driver ====================
[pydriver] -> pyserver.counter.tick()       reply: 1
[pydriver] -> pyserver.counter.tick()       reply: 2
[pydriver] -> ocserver.calc.add(3, 4)       reply: 7
[pydriver] -> ocserver.calc.square(7)       reply: 49
[pydriver] -> ocserver.calc.bump(99)        reply: 100
[pydriver] -> pyserver.counter.tick()       reply: 3
[pydriver] -> ocserver.calc.add(<...>)      reply: 6

==================== OCaml driver  ====================
[ocdriver] ocserver.add(10,20)  -> 30
[ocdriver] ocserver.square(8)   -> 64
[ocdriver] pyserver.tick()      -> 4
[ocdriver] pyserver.tick()      -> 5
[ocdriver] pyserver.get()       -> 5
```

The Python driver's three `pyserver.tick()` calls bring the counter
to 3.  The OCaml driver's two more `pyserver.tick()` calls then
bring it to 5, and `pyserver.get()` confirms — so **state is shared
across the two driver containers and the Python server actor is
reached from both languages**.

## Wire-format note

Both runtimes implement:

- `POST /api/json/send` — fire-and-forget
- `POST /api/json/call` — synchronous, blocks until receiver's
  `reply(value)` is invoked, returns `{"reply": value}`

Surface syntax differs:

- Python:  `remote_now(host_port, actor, method, args...)`
- OCaml:   `now remote("host_port", "actor").method(args...)`

…but both compile down to the same HTTP POST.
