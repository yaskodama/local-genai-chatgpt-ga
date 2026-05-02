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
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import abcl_ai


_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>ABCL/c+ AI-OS Dashboard</title>
<style>
  body { font-family: ui-monospace, Menlo, Consolas, monospace;
         margin: 2rem; color: #ddd; background: #0e1116; }
  h1   { font-size: 1rem; color: #8af; margin-bottom: 1.5rem; }
  table { border-collapse: collapse; }
  td.k { color: #889; padding: 0.25rem 1rem 0.25rem 0; }
  td.v { color: #cde; font-weight: 600; }
  .ok  { color: #6c6; } .warn { color: #fc6; } .bad { color: #f66; }
  small { color: #667; }
</style></head><body>
<h1>ABCL/c+ AI-OS Dashboard</h1>
<table id="t"></table>
<small id="ts"></small>
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
</script></body></html>
"""


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Silence the default access log so it doesn't crowd actor output.
        return

    def do_GET(self):
        if self.path.startswith("/usage.json"):
            self._serve_json()
        elif self.path == "/" or self.path.startswith("/?"):
            self._serve_html()
        else:
            self.send_error(404, "Not Found")

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
    exits."""
    server = HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(
        target=server.serve_forever,
        name=f"abcl-dashboard-{port}",
        daemon=True,
    )
    t.start()
    print(f"[dashboard] http://127.0.0.1:{port}/")
