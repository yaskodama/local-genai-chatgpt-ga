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


def publish(kind: str, **data) -> None:
    """Fan-out one event to every live subscriber."""
    evt = {"ts": time.time(), "kind": kind, **data}
    _broker.publish(evt)


def subscribe():
    return _broker.subscribe()


def unsubscribe(q) -> None:
    _broker.unsubscribe(q)


def subscriber_count() -> int:
    return _broker.subscriber_count()
