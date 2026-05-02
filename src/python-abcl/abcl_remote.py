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

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional


# Registry of actors that should accept remote messages.
_exposed_lock = threading.Lock()
_exposed_actors: dict = {}

# Track whether a gateway is running so the interpreter knows not to
# auto-shutdown when actors go idle.
_gateway_lock = threading.Lock()
_gateway_count = 0


def expose(name: str, actor) -> None:
    """Register an actor under a public name.  Subsequent POSTs
    targeting that name from any client (Python or OCaml) are
    delivered to the actor's mailbox."""
    with _exposed_lock:
        _exposed_actors[name] = actor


def get_exposed(name: str):
    with _exposed_lock:
        return _exposed_actors.get(name)


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

    def _handle_send(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
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

        actor = get_exposed(to_name)
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
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        print(f"[remote_send] {hostport}/{to_actor}.{method} HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"[remote_send] {hostport}/{to_actor}.{method} failed: {e.reason}")
