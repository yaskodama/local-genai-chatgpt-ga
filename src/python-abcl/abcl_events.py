"""In-process event broker for the AI-OS dashboard.

Threads inside the runtime call publish(kind, data); SSE consumers
attached to the dashboard's /events endpoint each get a private
queue and receive every published event.  Bounded to 1 024 events
per subscriber; an overrun drops the *new* event so the slow
subscriber doesn't back up the publisher.

Currently published kinds:
  ai_call     — ai_call() resolved (model + token counts + cost)
  remote_in   — gateway received a /api/json/(send|call)
  remote_out  — local code called remote_send / remote_call_sync
"""

import queue
import threading
import time
from typing import Optional


class _Broker:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: list = []

    def subscribe(self) -> "queue.Queue":
        q: "queue.Queue" = queue.Queue(maxsize=1024)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q) -> None:
        with self._lock:
            try:
                self._subs.remove(q)
            except ValueError:
                pass

    def publish(self, evt: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(evt)
            except queue.Full:
                # Slow subscriber — drop this event for them, keep
                # the publisher fast.
                pass

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)


_broker = _Broker()


# ---------------------------------------------------------------------------
# Topology view: who has been talking to whom?  Each remote_in /
# remote_out event ticks an edge counter; the dashboard renders
# the resulting graph as a table.

_topo_lock = threading.Lock()
_topo_edges: dict = {}  # (src, dst, method) -> {"count": N, "last": ts}


def _record_edge(src: str, dst: str, method: str) -> None:
    key = (src, dst, method)
    with _topo_lock:
        e = _topo_edges.get(key)
        if e is None:
            _topo_edges[key] = {"count": 1, "last": time.time()}
        else:
            e["count"] += 1
            e["last"] = time.time()


def topology_snapshot() -> list:
    with _topo_lock:
        return [
            {"src": k[0], "dst": k[1], "method": k[2],
             "count": v["count"], "last_ts": v["last"]}
            for k, v in _topo_edges.items()
        ]


def publish(kind: str, **data) -> None:
    """Fan-out one event to every live subscriber."""
    evt = {"ts": time.time(), "kind": kind, **data}
    _broker.publish(evt)
    # Side-effect: keep an edge count for the dashboard.
    if kind == "remote_in":
        src = data.get("from_") or data.get("from") or "?"
        dst = data.get("to", "?")
        _record_edge(str(src), str(dst), str(data.get("method", "?")))
    elif kind == "remote_out":
        src = "self"
        dst = f'{data.get("host", "?")}/{data.get("to", "?")}'
        _record_edge(src, dst, str(data.get("method", "?")))


def subscribe():
    return _broker.subscribe()


def unsubscribe(q) -> None:
    _broker.unsubscribe(q)


def subscriber_count() -> int:
    return _broker.subscriber_count()
