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
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import abcl_ai
import abcl_events


# Web IDE: serve files from the python-abcl source tree (where this
# module lives).  Path traversal is blocked by _ide_safe_path.
_IDE_ROOT = os.path.dirname(os.path.abspath(__file__))


def _ide_safe_path(rel: str):
    """Resolve `rel` against _IDE_ROOT, returning the absolute path
    iff it stays inside the workspace and ends in `.abcl`.  None for
    anything fishy (path traversal, wrong extension, empty)."""
    if not rel:
        return None
    rel = rel.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/"):
        return None
    if not rel.endswith(".abcl"):
        return None
    full = os.path.realpath(os.path.join(_IDE_ROOT, rel))
    root = os.path.realpath(_IDE_ROOT) + os.sep
    if not (full == os.path.realpath(_IDE_ROOT) or full.startswith(root)):
        return None
    return full


# Runtime peer list — combines the static env-var seed with anyone
# who's POSTed /api/peer/register on this dashboard.
_dyn_peers_lock = threading.Lock()
_dyn_peers: set = set()


def register_peer(hostport: str) -> None:
    h = hostport.strip()
    if not h:
        return
    with _dyn_peers_lock:
        _dyn_peers.add(h)


def _peer_dashboards() -> list:
    seeds = []
    raw = os.environ.get("ABCL_PEER_DASHBOARDS", "").strip()
    if raw:
        seeds = [p.strip() for p in raw.split(",") if p.strip()]
    with _dyn_peers_lock:
        dyn = list(_dyn_peers)
    # Stable order: env seeds first, then alphabetical dynamic.
    return list(dict.fromkeys(seeds + sorted(dyn)))


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
  #peers, #topo { border-collapse: collapse; }
  #peers th, #peers td, #topo th, #topo td { padding: 0.2rem 0.8rem; text-align: right; }
  #peers th, #topo th { color: #889; font-weight: normal; border-bottom: 1px solid #223; }
  #peers td:first-child, #peers th:first-child,
  #topo td:first-child, #topo th:first-child { text-align: left; color: #aaf; }
  #topo td:nth-child(2), #topo th:nth-child(2),
  #topo td:nth-child(3), #topo th:nth-child(3) { text-align: left; }
  #peers tr.bad td { color: #f88; }
  #peers tr.total td { color: #cde; border-top: 1px solid #223; font-weight: 700; }
</style></head><body>
<h1>ABCL/c+ AI-OS Dashboard <small style="color:#667"><a style="color:#6af" href="/ide">→ Web IDE</a></small></h1>
<table id="t"></table>
<small id="ts"></small>
<h2>Cluster (this node + peers)</h2>
<table id="peers"><thead><tr>
  <th>node</th><th>calls</th><th>in</th><th>out</th><th>total</th><th>cost</th>
</tr></thead><tbody id="peers-body"></tbody></table>
<h2>Observed traffic (this node)</h2>
<svg id="graph" width="600" height="380" style="border:1px solid #223;background:#050810;display:block;margin-bottom:0.5rem"></svg>
<table id="topo"><thead><tr>
  <th>src</th><th>dst</th><th>method</th><th>count</th><th>last</th>
</tr></thead><tbody id="topo-body"></tbody></table>
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

async function refreshTopo() {
  try {
    const r = await fetch('/topology.json', { cache: 'no-store' });
    const t = await r.json();
    const tb = document.getElementById('topo-body');
    if (!t.edges.length) {
      tb.innerHTML = '<tr><td colspan="5"><small>no traffic yet</small></td></tr>';
      return;
    }
    const rows = t.edges.slice(0, 30).map(e => {
      const ago = Math.max(0, Math.round(Date.now()/1000 - e.last_ts));
      return `<tr><td>${e.src}</td><td>${e.dst}</td><td>${e.method}</td>` +
        `<td>${e.count}</td><td><small>${ago}s ago</small></td></tr>`;
    });
    tb.innerHTML = rows.join('');
  } catch (_) { /* ignore */ }
}
refreshTopo();
setInterval(refreshTopo, 2000);

async function refreshGraph() {
  let t;
  try {
    t = await (await fetch('/topology.json', { cache: 'no-store' })).json();
  } catch (_) { return; }
  const svg = document.getElementById('graph');
  const W = 600, H = 380, cx = W/2, cy = H/2, R = Math.min(W,H)/2 - 50;
  if (!t.edges.length) {
    svg.innerHTML = '<text x="20" y="30" fill="#667" font-size="12">no traffic yet</text>';
    return;
  }
  const nodes = Array.from(new Set(t.edges.flatMap(e => [e.src, e.dst])));
  const pos = {};
  nodes.forEach((n, i) => {
    const a = 2 * Math.PI * i / nodes.length - Math.PI/2;
    pos[n] = { x: cx + R*Math.cos(a), y: cy + R*Math.sin(a) };
  });
  const maxCount = Math.max(1, ...t.edges.map(e => e.count));
  let svgInner =
    '<defs><marker id="ah" viewBox="0 0 10 10" refX="14" refY="5" ' +
    'markerWidth="7" markerHeight="7" orient="auto">' +
    '<path d="M0,0 L10,5 L0,10 z" fill="#8a8"/></marker></defs>';
  // edges first so circles draw on top
  for (const e of t.edges) {
    const s = pos[e.src], d = pos[e.dst];
    if (!s || !d) continue;
    const w = 1 + 5 * (e.count / maxCount);
    svgInner += `<line x1="${s.x}" y1="${s.y}" x2="${d.x}" y2="${d.y}" ` +
                `stroke="#688" stroke-width="${w.toFixed(1)}" ` +
                `opacity="0.7" marker-end="url(#ah)"/>`;
  }
  for (const n of nodes) {
    const p = pos[n];
    svgInner += `<circle cx="${p.x}" cy="${p.y}" r="22" fill="#162a3e" stroke="#6f8" stroke-width="2"/>`;
    svgInner += `<text x="${p.x}" y="${p.y+4}" text-anchor="middle" font-size="11" fill="#cde">${n.slice(0,16)}</text>`;
  }
  svg.innerHTML = svgInner;
}
refreshGraph();
setInterval(refreshGraph, 2000);

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
        elif self.path.startswith("/topology.json"):
            self._serve_topology()
        elif self.path.startswith("/events"):
            self._serve_events()
        elif self.path.startswith("/healthz"):
            self._serve_healthz()
        elif self.path.startswith("/api/files"):
            self._serve_ide_files()
        elif self.path.startswith("/api/file?"):
            self._serve_ide_file_get()
        elif self.path == "/ide" or self.path.startswith("/ide?"):
            self._serve_ide_html()
        elif self.path == "/" or self.path.startswith("/?"):
            self._serve_html()
        else:
            self.send_error(404, "Not Found")

    # ---- IDE: list / read / write / run ----

    def _serve_ide_files(self):
        """List every .abcl file under the workspace, grouped by
        directory."""
        out = []
        for dirpath, dirnames, filenames in os.walk(_IDE_ROOT):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(("_", ".", "__"))]
            for fn in sorted(filenames):
                if not fn.endswith(".abcl"):
                    continue
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, _IDE_ROOT)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                out.append({"path": rel, "size": size})
        body = json.dumps({"files": out}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def _serve_ide_file_get(self):
        from urllib.parse import parse_qs, urlsplit
        q = parse_qs(urlsplit(self.path).query)
        rel = (q.get("path") or [""])[0]
        full = _ide_safe_path(rel)
        if full is None or not os.path.isfile(full):
            return self.send_error(404, f"file not found: {rel}")
        try:
            content = open(full).read()
        except OSError as e:
            return self.send_error(500, f"read error: {e}")
        body = json.dumps({"path": rel, "content": content}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def do_POST(self):
        if self.path.startswith("/api/peer/register"):
            self._handle_register()
        elif self.path.startswith("/api/file/save"):
            self._handle_ide_save()
        elif self.path.startswith("/api/run"):
            self._handle_ide_run()
        else:
            self.send_error(404, "Not Found")

    def _read_json_body(self) -> "dict | None":
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        try:
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError):
            self.send_error(400, "bad json")
            return None
        if not isinstance(data, dict):
            self.send_error(400, "json body must be an object")
            return None
        return data

    def _handle_ide_save(self):
        data = self._read_json_body()
        if data is None:
            return
        rel = str(data.get("path", ""))
        content = str(data.get("content", ""))
        full = _ide_safe_path(rel)
        if full is None:
            return self.send_error(400, "invalid path")
        try:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)
        except OSError as e:
            return self.send_error(500, f"write error: {e}")
        body = json.dumps({"ok": True, "path": rel,
                           "size": len(content)}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def _handle_ide_run(self):
        """Run a .abcl program through abcl_main.py and return the
        captured stdout+stderr.  Bounded to ABCL_IDE_RUN_TIMEOUT
        seconds (default 8) so a runaway sample can't tie up the
        dashboard."""
        data = self._read_json_body()
        if data is None:
            return
        rel = str(data.get("path", ""))
        full = _ide_safe_path(rel)
        if full is None or not os.path.isfile(full):
            return self.send_error(404, f"file not found: {rel}")
        try:
            timeout = float(os.environ.get("ABCL_IDE_RUN_TIMEOUT", "8"))
        except ValueError:
            timeout = 8.0
        cmd = [sys.executable, os.path.join(_IDE_ROOT, "abcl_main.py"),
               "--timeout", str(timeout), full]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout + 4, cwd=_IDE_ROOT)
            out = (r.stdout or "") + (r.stderr or "")
            ok = (r.returncode == 0)
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "") + (e.stderr or "") + "\n[ide] run timed out"
            if isinstance(out, bytes):
                out = out.decode("utf-8", errors="replace")
            ok = False
        body = json.dumps({"ok": ok, "output": out}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def _serve_healthz(self):
        body = json.dumps({
            "status": "ok",
            "subscribers": abcl_events.subscriber_count(),
        }).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    def _serve_topology(self):
        edges = abcl_events.topology_snapshot()
        edges.sort(key=lambda e: -e["count"])
        body = json.dumps({"edges": edges}).encode("utf-8")
        self._send_bytes(200, "application/json", body)

    # (do_POST is defined earlier with the IDE routes — peer
    #  registration is handled there too.)

    def _handle_register(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        try:
            payload = json.loads(body) if body else {}
        except (json.JSONDecodeError, ValueError) as e:
            return self.send_error(400, f"bad json: {e}")
        host = str(payload.get("host", "")).strip()
        port = payload.get("port")
        if not host or not isinstance(port, int):
            return self.send_error(400, "host (str) and port (int) required")
        register_peer(f"{host}:{port}")
        body_resp = json.dumps({"ok": True, "peers": _peer_dashboards()}).encode("utf-8")
        self._send_bytes(200, "application/json", body_resp)

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

    def _serve_ide_html(self):
        body = _IDE_HTML.encode("utf-8")
        self._send_bytes(200, "text/html; charset=utf-8", body)

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


_IDE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>ABCL/c+ Web IDE</title>
<style>
  html, body { margin: 0; padding: 0; height: 100%;
               font-family: ui-monospace, Menlo, Consolas, monospace;
               color: #ddd; background: #0e1116; }
  header { padding: 0.6rem 1rem; background: #11161e; border-bottom: 1px solid #223;
           display: flex; align-items: center; gap: 1rem; }
  header h1 { font-size: 0.95rem; color: #8af; margin: 0; }
  header a { color: #6af; text-decoration: none; font-size: 0.85rem; }
  #wrap { display: grid; grid-template-columns: 220px 1fr; height: calc(100% - 41px); }
  #files { background: #11161e; border-right: 1px solid #223; padding: 0.5rem 0;
           overflow-y: auto; font-size: 0.78rem; }
  .group  { color: #6a8; padding: 0.4rem 0.7rem 0.2rem; }
  .file   { padding: 0.18rem 0.7rem; cursor: pointer; color: #cde; }
  .file:hover { background: #1a2332; }
  .file.active { background: #1f2c3e; color: #fff; }
  #right { display: grid; grid-template-rows: 1fr 36px 38% ; min-height: 0; }
  #editor { width: 100%; height: 100%; box-sizing: border-box;
            background: #050810; color: #cde; border: 0; outline: 0;
            padding: 0.6rem 0.8rem; resize: none; font: 0.82rem ui-monospace, Menlo, monospace;
            tab-size: 2; }
  #bar { background: #11161e; border-top: 1px solid #223; border-bottom: 1px solid #223;
         display: flex; align-items: center; gap: 0.5rem; padding: 0 0.7rem;
         font-size: 0.78rem; color: #889; }
  #bar button { background: #1c2a3e; color: #cde; border: 1px solid #335;
                padding: 0.18rem 0.7rem; cursor: pointer;
                font: inherit; }
  #bar button:hover { background: #28395a; }
  #bar .right { margin-left: auto; }
  #out { background: #050810; color: #aab; padding: 0.6rem 0.8rem;
         font-size: 0.78rem; white-space: pre-wrap; overflow-y: auto;
         border-top: 1px solid #223; }
  .err { color: #f88; }
  .ok  { color: #6f8; }
</style></head>
<body>
<header>
  <h1>ABCL/c+ Web IDE</h1>
  <a href="/">← dashboard</a>
  <span id="path" style="color:#667;font-size:0.78rem"></span>
</header>
<div id="wrap">
  <nav id="files"><div style="color:#667;padding:0.5rem 0.7rem">loading…</div></nav>
  <section id="right">
    <textarea id="editor" spellcheck="false" placeholder="Pick a file on the left or type a fresh program here."></textarea>
    <div id="bar">
      <button id="save">Save</button>
      <button id="run">Run</button>
      <button id="fmt">Format</button>
      <span id="status" class="right"></span>
    </div>
    <pre id="out">(output will appear here)</pre>
  </section>
</div>
<script>
let currentPath = null;
const E = (id) => document.getElementById(id);

async function loadList() {
  const r = await fetch('/api/files', { cache: 'no-store' });
  const d = await r.json();
  const groups = {};
  for (const f of d.files) {
    const dir = f.path.includes('/') ? f.path.split('/').slice(0, -1).join('/') : '(root)';
    (groups[dir] = groups[dir] || []).push(f);
  }
  const html = Object.keys(groups).sort().map(dir => {
    const files = groups[dir]
      .map(f => `<div class="file" data-p="${f.path}">${f.path.split('/').pop()}</div>`)
      .join('');
    return `<div class="group">${dir}</div>${files}`;
  }).join('');
  E('files').innerHTML = html;
  for (const el of document.querySelectorAll('.file')) {
    el.addEventListener('click', () => openFile(el.dataset.p));
  }
}

async function openFile(p) {
  const r = await fetch('/api/file?path=' + encodeURIComponent(p), { cache: 'no-store' });
  if (!r.ok) { setStatus('open failed: ' + r.status, 'err'); return; }
  const d = await r.json();
  currentPath = p;
  E('editor').value = d.content;
  E('path').textContent = p;
  for (const el of document.querySelectorAll('.file')) el.classList.toggle('active', el.dataset.p === p);
  setStatus('opened (' + d.content.length + ' bytes)', 'ok');
}

function setStatus(msg, cls) {
  const s = E('status');
  s.textContent = msg;
  s.className = 'right ' + (cls || '');
  if (cls) setTimeout(() => { if (s.textContent === msg) s.textContent = ''; }, 3500);
}

async function save() {
  if (!currentPath) { setStatus('no file open', 'err'); return; }
  const r = await fetch('/api/file/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ path: currentPath, content: E('editor').value }),
  });
  if (r.ok) setStatus('saved', 'ok'); else setStatus('save failed: ' + r.status, 'err');
}

async function run() {
  if (!currentPath) { setStatus('no file open', 'err'); return; }
  await save();
  E('out').textContent = 'running…';
  const r = await fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ path: currentPath }),
  });
  const d = await r.json();
  E('out').textContent = d.output || '(no output)';
  setStatus(d.ok ? 'done' : 'failed', d.ok ? 'ok' : 'err');
}

async function fmt() {
  // Lightweight client-side reformat — just normalises blank lines.
  // The real formatter is abcl_fmt.py; expose later via /api/fmt.
  const t = E('editor').value;
  E('editor').value = t.replace(/\\n{3,}/g, '\\n\\n').replace(/[ \\t]+$/gm, '');
  setStatus('whitespace tidied (full fmt via abcl_fmt CLI)', 'ok');
}

E('save').addEventListener('click', save);
E('run').addEventListener('click', run);
E('fmt').addEventListener('click', fmt);

// Cmd-S / Ctrl-S to save, Cmd-Enter to run.
document.addEventListener('keydown', (e) => {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key === 's') { e.preventDefault(); save(); }
  if (mod && e.key === 'Enter') { e.preventDefault(); run(); }
});

loadList();
</script>
</body></html>
"""


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
