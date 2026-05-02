"""Distributed actor communication for the Python ABCL/c+ runtime.

Wire-compatible with the OCaml runtime's web_gateway.ml so a Python
program can send to actors hosted by an OCaml process and vice versa
without any protocol shim.

Endpoints exposed by start_gateway():
  GET  /                  -> tiny HTML banner
  POST /api/json/send     -> body {"to","method","args","from"}
                             route to a locally-exposed actor
                             (matches src/web_gateway.ml exactly)
  GET  /api/exposed       -> JSON list of exposed actor names

Send side: remote_send(hostport, to, method, args, from) does a
single fire-and-forget POST.  No reply correlation yet — the
receiver can talk back via its own remote_send if it knows the
sender's address.
"""

import hashlib
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


# ---------------------------------------------------------------------------
# HMAC authentication.  Optional — when ABCL_REMOTE_SECRET is set on
# both sides, every POST carries an X-ABCL-Sig header (hex SHA-256
# HMAC of the request body) and the receiver rejects requests whose
# signature doesn't match.

def _shared_secret() -> bytes:
    return os.environ.get("ABCL_REMOTE_SECRET", "").encode("utf-8")


def _sign(body: bytes) -> str:
    return hmac.new(_shared_secret(), body, hashlib.sha256).hexdigest()


def _verify(body: bytes, sig: str) -> bool:
    if not sig:
        return False
    try:
        return hmac.compare_digest(_sign(body), sig)
    except Exception:
        return False


# Registry of actors that should accept remote messages.
_exposed_lock = threading.Lock()
_exposed_actors: dict = {}

# Optional fallback that finds an actor by its variable name in the
# running interpreter's globals — installed by Interpreter.run() so
# any locally-spawned actor is reachable by name from a remote send,
# matching OCaml's "actor_exists" behaviour.  Keeps web_expose
# optional, used only when you want to alias an actor under a
# different public name.
_actor_lookup = None


def set_actor_lookup(callback) -> None:
    """callback(name: str) -> Optional[Actor]"""
    global _actor_lookup
    _actor_lookup = callback


# Track whether a gateway is running so the interpreter knows not to
# auto-shutdown when actors go idle.
_gateway_lock = threading.Lock()
_gateway_count = 0


def _normalize(name: str) -> str:
    """OCaml's web_expose strips a leading slash so `/foo` and `foo`
    register under the same key.  Mirror that on every lookup so
    incoming traffic from an OCaml-style sender lands the same way."""
    n = (name or "").strip()
    if n.startswith("/"):
        n = n[1:]
    return n


def expose(name: str, actor) -> None:
    """Register an actor under a public name.  Subsequent POSTs
    targeting that name from any client (Python or OCaml) are
    delivered to the actor's mailbox."""
    with _exposed_lock:
        _exposed_actors[_normalize(name)] = actor


def find_actor(name: str):
    """Resolve a remote `to` field to a local Actor.  Tries the
    explicit expose() table first (alias names), then the
    interpreter's globals (any local var that holds an actor)."""
    n = _normalize(name)
    with _exposed_lock:
        a = _exposed_actors.get(n)
    if a is not None:
        return a
    if _actor_lookup is not None:
        try:
            return _actor_lookup(n)
        except Exception:
            return None
    return None


def list_exposed_names() -> list:
    with _exposed_lock:
        return list(_exposed_actors.keys())


def is_gateway_running() -> bool:
    with _gateway_lock:
        return _gateway_count > 0


# ---------------------------------------------------------------------------
# HTTP server

class _Handler(BaseHTTPRequestHandler):
    # Silence the default access log so it doesn't crowd actor output.
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._serve_index()
        elif self.path.startswith("/api/exposed"):
            self._serve_exposed()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self.path.startswith("/api/json/send"):
            self._handle_send()
        elif self.path.startswith("/api/json/call"):
            self._handle_call()
        else:
            self.send_error(404, "Not Found")

    def _send_bytes(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_index(self):
        names = list_exposed_names()
        rows = "".join(f"<li>{n}</li>" for n in names) or "<li><em>(none)</em></li>"
        body = (
            "<!doctype html><meta charset=utf-8>"
            "<style>body{font-family:ui-monospace,Menlo,monospace;margin:2rem;color:#cde;background:#0e1116}"
            "h1{font-size:1rem;color:#8af}li{color:#cde}</style>"
            "<h1>ABCL/c+ Python gateway</h1>"
            "<p>Exposed actors:</p><ul>" + rows + "</ul>"
            "<p><small>Wire-compat with OCaml web_gateway: "
            "<code>POST /api/json/send</code></small></p>"
        ).encode("utf-8")
        self._send_bytes(200, "text/html; charset=utf-8", body)

    def _serve_exposed(self):
        body = json.dumps({"exposed": list_exposed_names()}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def _read_authed_body(self):
        """Read POST body bytes; if ABCL_REMOTE_SECRET is set, also
        verify the X-ABCL-Sig HMAC.  Returns (str body, ok)."""
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        if _shared_secret():
            sig = self.headers.get("X-ABCL-Sig", "")
            if not _verify(raw, sig):
                self.send_error(401, "invalid or missing X-ABCL-Sig")
                return "", False
        return raw.decode("utf-8"), True

    def _handle_send(self):
        body, ok = self._read_authed_body()
        if not ok:
            return
        try:
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            return self.send_error(400, f"bad json: {e}")
        if not isinstance(payload, dict):
            return self.send_error(400, "json body must be an object")

        to_name = str(payload.get("to", ""))
        method = str(payload.get("method", ""))
        args = payload.get("args", []) or []
        if not isinstance(args, list):
            return self.send_error(400, "args must be an array")
        from_name = str(payload.get("from", ""))

        actor = find_actor(to_name)
        if actor is None:
            print(f"[gateway] unknown actor: {to_name!r} (from={from_name})")
            return self.send_error(404, f"no exposed actor: {to_name}")

        # Print so a server-side .abcl program shows traffic in its
        # log without explicit handler instrumentation.
        print(f"[gateway] -> {to_name}.{method}({args}) from={from_name!r}")

        try:
            actor.send_method(method, list(args), sender=None)
        except Exception as e:
            return self.send_error(500, f"dispatch failed: {e}")

        body_ok = b'{"ok":true}'
        self._send_bytes(200, "application/json", body_ok)

    def _handle_call(self):
        """Synchronous remote call: dispatch with a Future and block
        the HTTP response until the actor's reply() arrives (or the
        method returns without one — then reply is null).  Wire shape:

          POST /api/json/call
          body: {"to":"name","method":"m","args":[...],"from":"who"}
          resp 200 application/json: {"ok": true, "reply": <value>}

        Optional `?timeout_ms=N` query (default 30 000)."""
        body, ok = self._read_authed_body()
        if not ok:
            return
        try:
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            return self.send_error(400, f"bad json: {e}")
        if not isinstance(payload, dict):
            return self.send_error(400, "json body must be an object")

        to_name = str(payload.get("to", ""))
        method = str(payload.get("method", ""))
        args = payload.get("args", []) or []
        if not isinstance(args, list):
            return self.send_error(400, "args must be an array")
        from_name = str(payload.get("from", ""))

        timeout_ms = 30_000
        if "?" in self.path:
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(self.path).query)
            if q.get("timeout_ms"):
                try:
                    timeout_ms = int(q["timeout_ms"][0])
                except ValueError:
                    pass

        actor = find_actor(to_name)
        if actor is None:
            return self.send_error(404, f"no exposed actor: {to_name}")

        from abcl_runtime import Future
        fut = Future()
        print(f"[gateway] (call) -> {to_name}.{method}({args}) from={from_name!r}")
        try:
            actor.send_method(method, list(args), sender=None, reply_future=fut)
        except Exception as e:
            return self.send_error(500, f"dispatch failed: {e}")

        value = fut.get(timeout=timeout_ms / 1000.0)
        body_resp = json.dumps({"ok": True, "reply": value}).encode("utf-8")
        self._send_bytes(200, "application/json", body_resp)


def start_gateway(port: int, *, host: str = "0.0.0.0") -> None:
    """Start the HTTP gateway on a daemon thread.  Returns once the
    listen socket is bound.  Multiple calls are allowed (each binds a
    separate port); is_gateway_running() goes True after the first."""
    server = HTTPServer((host, port), _Handler)
    global _gateway_count
    with _gateway_lock:
        _gateway_count += 1
    t = threading.Thread(
        target=server.serve_forever,
        name=f"abcl-gateway-{port}",
        daemon=True,
    )
    t.start()
    print(f"[gateway] listening on http://{host}:{port}/")


# ---------------------------------------------------------------------------
# Client side

def _make_signed_request(url: str, payload: bytes) -> "urllib.request.Request":
    headers = {"Content-Type": "application/json"}
    if _shared_secret():
        headers["X-ABCL-Sig"] = _sign(payload)
    return urllib.request.Request(url, data=payload, method="POST", headers=headers)


def remote_send(hostport: str, to_actor: str, method: str,
                args: list, from_name: str = "") -> None:
    """Fire-and-forget remote send.  Matches the OCaml
    Remote_client.remote_send wire format."""
    url = f"http://{hostport}/api/json/send"
    payload = json.dumps({
        "to":     to_actor,
        "method": method,
        "args":   list(args),
        "from":   from_name,
    }).encode("utf-8")
    req = _make_signed_request(url, payload)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        print(f"[remote_send] {hostport}/{to_actor}.{method} HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"[remote_send] {hostport}/{to_actor}.{method} failed: {e.reason}")


def remote_call_sync(hostport: str, to_actor: str, method: str,
                     args: list, from_name: str = "",
                     timeout_s: float = 30.0):
    """Synchronous remote call: blocks until the receiver's actor
    method calls reply(value) (or returns without one — then None).
    Returns the JSON-decoded reply value."""
    url = f"http://{hostport}/api/json/call?timeout_ms={int(timeout_s * 1000)}"
    payload = json.dumps({
        "to":     to_actor,
        "method": method,
        "args":   list(args),
        "from":   from_name,
    }).encode("utf-8")
    req = _make_signed_request(url, payload)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s + 5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("reply")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"remote_call {hostport}/{to_actor}.{method} HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"remote_call {hostport}/{to_actor}.{method} failed: {e.reason}")
