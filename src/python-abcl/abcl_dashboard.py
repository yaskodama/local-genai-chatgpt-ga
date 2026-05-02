"""Tiny HTTP dashboard for AI-OS counters.

Serves two endpoints from a daemon thread (stdlib only):

    GET /              — auto-refreshing HTML page
    GET /usage.json    — current counters as JSON

Started from abcl_main.py via the --dashboard PORT flag.  The runtime
keeps running normally; the server reads the counters via
abcl_ai.get_usage() / get_remaining().  The page itself polls
/usage.json every second and renders without any external assets.
"""

import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import abcl_ai
import abcl_events


def _peer_dashboards() -> list:
    raw = os.environ.get("ABCL_PEER_DASHBOARDS", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


# Tiny per-key cache so a noisy page-refresh doesn't hammer peers.
_peer_cache_lock = threading.Lock()
_peer_cache: dict = {}        # hostport -> (timestamp, payload_dict | None)
PEER_CACHE_TTL_S = 0.8


def _fetch_peer_usage(hostport: str) -> "dict | None":
    now = time.monotonic()
    with _peer_cache_lock:
        cached = _peer_cache.get(hostport)
        if cached is not None and (now - cached[0]) < PEER_CACHE_TTL_S:
            return cached[1]
    payload = None
    url = f"http://{hostport}/usage.json"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError):
        payload = None
    with _peer_cache_lock:
        _peer_cache[hostport] = (now, payload)
    return payload


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>ABCL/c+ AI-OS Dashboard</title>
<style>
  body { font-family: ui-monospace, Menlo, Consolas, monospace;
         margin: 2rem; color: #ddd; background: #0e1116; }
  h1   { font-size: 1rem; color: #8af; margin: 0 0 1rem; }
  h2   { font-size: 0.85rem; color: #6a8; margin: 1.25rem 0 0.4rem; }
  table { border-collapse: collapse; }
  td.k { color: #889; padding: 0.2rem 1rem 0.2rem 0; }
  td.v { color: #cde; font-weight: 600; }
  small { color: #667; }
  #events {
    background: #050810; padding: 0.6rem 0.8rem; max-height: 320px;
    overflow-y: auto; border: 1px solid #223;
    font-size: 0.78rem; line-height: 1.4; }
  .ev { color: #aab; }
  .ev .k { color: #fc6; margin-right: 0.5rem; }
  .ev .ai_call { color: #8df; }
  .ev .remote_in { color: #6f8; }
  .ev .remote_out { color: #f9a; }
  #peers { border-collapse: collapse; }
  #peers th, #peers td { padding: 0.2rem 0.8rem; text-align: right; }
  #peers th { color: #889; font-weight: normal; border-bottom: 1px solid #223; }
  #peers td:first-child, #peers th:first-child { text-align: left; color: #aaf; }
  #peers tr.bad td { color: #f88; }
  #peers tr.total td { color: #cde; border-top: 1px solid #223; font-weight: 700; }
</style></head><body>
<h1>ABCL/c+ AI-OS Dashboard</h1>
<table id="t"></table>
<small id="ts"></small>
<h2>Cluster (this node + peers)</h2>
<table id="peers"><thead><tr>
  <th>node</th><th>calls</th><th>in</th><th>out</th><th>total</th><th>cost</th>
</tr></thead><tbody id="peers-body"></tbody></table>
<h2>Live events</h2>
<div id="events"></div>
<script>
async function refresh() {
  try {
    const r = await fetch('/usage.json', { cache: 'no-store' });
    const u = await r.json();
    const rows = [
      ['calls',           u.calls],
      ['input tokens',    u.input_tokens.toLocaleString()],
      ['output tokens',   u.output_tokens.toLocaleString()],
      ['total tokens',    u.total_tokens.toLocaleString()],
      ['cost (USD)',      '$' + u.cost_usd.toFixed(6)],
      ['budget',          u.budget > 0 ? u.budget.toLocaleString() : '(unlimited)'],
      ['remaining',       u.remaining < 0 ? '(unlimited)' : u.remaining.toLocaleString()],
    ];
    document.getElementById('t').innerHTML = rows
      .map(([k, v]) => `<tr><td class=k>${k}</td><td class=v>${v}</td></tr>`)
      .join('');
    document.getElementById('ts').textContent =
      'last update: ' + new Date().toLocaleTimeString();
  } catch (e) {
    document.getElementById('ts').textContent = 'error: ' + e;
  }
}
refresh();
setInterval(refresh, 1000);

async function refreshPeers() {
  try {
    const r = await fetch('/aggregate.json', { cache: 'no-store' });
    const a = await r.json();
    const tb = document.getElementById('peers-body');
    const fmt = (n) => (typeof n === 'number') ? n.toLocaleString() : '-';
    const lines = [];
    for (const n of a.nodes) {
      const u = n.usage || {};
      const cls = n.ok ? '' : 'bad';
      lines.push(`<tr class="${cls}"><td>${n.name}${n.ok ? '' : ' (offline)'}</td>` +
        `<td>${fmt(u.calls)}</td><td>${fmt(u.input_tokens)}</td>` +
        `<td>${fmt(u.output_tokens)}</td><td>${fmt(u.total_tokens)}</td>` +
        `<td>${u.cost_usd != null ? '$' + u.cost_usd.toFixed(6) : '-'}</td></tr>`);
    }
    const A = a.aggregate;
    lines.push(`<tr class="total"><td>TOTAL</td><td>${fmt(A.calls)}</td>` +
      `<td>${fmt(A.input_tokens)}</td><td>${fmt(A.output_tokens)}</td>` +
      `<td>${fmt(A.total_tokens)}</td><td>$${A.cost_usd.toFixed(6)}</td></tr>`);
    tb.innerHTML = lines.join('');
  } catch (e) { /* ignore — peer offline */ }
}
refreshPeers();
setInterval(refreshPeers, 2000);

const events = document.getElementById('events');
function appendEvent(evt) {
  const t = new Date(evt.ts * 1000).toLocaleTimeString();
  const detail = Object.entries(evt)
    .filter(([k]) => k !== 'ts' && k !== 'kind')
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(' ');
  const div = document.createElement('div');
  div.className = 'ev';
  div.innerHTML = `<span class="k ${evt.kind}">${t}  ${evt.kind}</span> ${detail}`;
  events.appendChild(div);
  while (events.childNodes.length > 200) events.removeChild(events.firstChild);
  events.scrollTop = events.scrollHeight;
}
const es = new EventSource('/events');
es.onmessage = (m) => { try { appendEvent(JSON.parse(m.data)); } catch (_) {} };
es.onerror   = () => { /* auto-reconnect */ };
</script></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence the default access log so it doesn't crowd actor output.
        return

    def _send_bytes(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/usage.json"):
            self._serve_json()
        elif self.path.startswith("/aggregate.json"):
            self._serve_aggregate()
        elif self.path.startswith("/events"):
            self._serve_events()
        elif self.path == "/" or self.path.startswith("/?"):
            self._serve_html()
        else:
            self.send_error(404, "Not Found")

    def _serve_aggregate(self):
        peers = _peer_dashboards()
        nodes = []
        # Self first
        local = abcl_ai.get_usage()
        try:
            local_budget = abcl_ai._get_budget()  # type: ignore[attr-defined]
        except Exception:
            local_budget = 0
        local["budget"]    = local_budget
        local["remaining"] = abcl_ai.get_remaining()
        nodes.append({"name": "self", "ok": True, "usage": local})
        # Peers
        for hp in peers:
            payload = _fetch_peer_usage(hp)
            nodes.append({"name": hp, "ok": payload is not None,
                          "usage": payload or {}})
        # Aggregate the truthy ones
        keys = ("calls", "input_tokens", "output_tokens", "total_tokens")
        agg = {k: 0 for k in keys}
        agg["cost_usd"] = 0.0
        for n in nodes:
            u = n.get("usage", {}) or {}
            for k in keys:
                v = u.get(k, 0)
                if isinstance(v, int):
                    agg[k] += v
            c = u.get("cost_usd", 0)
            if isinstance(c, (int, float)):
                agg["cost_usd"] += float(c)
        body = json.dumps({"nodes": nodes, "aggregate": agg}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def _serve_events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        q = abcl_events.subscribe()
        try:
            while True:
                try:
                    evt = q.get(timeout=15)
                except queue.Empty:
                    # Heartbeat so proxies don't drop the connection.
                    try:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    continue
                try:
                    body = ("data: " + json.dumps(evt) + "\n\n").encode("utf-8")
                    self.wfile.write(body)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
        finally:
            abcl_events.unsubscribe(q)

    def _serve_html(self):
        body = _HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_json(self):
        usage = abcl_ai.get_usage()
        # Augment with budget info — useful for the page header.
        budget = 0
        try:
            budget = abcl_ai._get_budget()  # type: ignore[attr-defined]
        except Exception:
            pass
        usage["budget"] = budget
        usage["remaining"] = abcl_ai.get_remaining()
        body = json.dumps(usage).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def start(port: int) -> None:
    """Start the dashboard server on a daemon thread.  Returns once
    the listen socket is bound; the thread runs until the program
    exits.  Threading server so an open SSE connection on /events
    doesn't block /usage.json polling."""
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(
        target=server.serve_forever,
        name=f"abcl-dashboard-{port}",
        daemon=True,
    )
    t.start()
    print(f"[dashboard] http://127.0.0.1:{port}/")
