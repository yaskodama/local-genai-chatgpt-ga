"""Threading-based actor runtime for ABCL/c+.

Each actor owns a worker thread that pulls (method, args, sender) tuples
off its mailbox and dispatches them through the interpreter.  Messages
are bounced through `Scheduler.send` so the runtime can keep an
outstanding-message counter — the main thread can wait on that to know
when the system is idle and exit cleanly.
"""

import queue
import threading
from typing import Optional


class Future:
    """Single-shot result holder used by now-/future-type sends.

    The callee fulfils it via `reply(value)`; the caller blocks on
    `get()` (or polls via `done()`).  `set()` is idempotent — calling
    it twice keeps the first value.
    """

    def __init__(self):
        self._cond = threading.Condition()
        self._done = False
        self._value = None

    def set(self, value) -> None:
        with self._cond:
            if not self._done:
                self._value = value
                self._done = True
                self._cond.notify_all()

    def done(self) -> bool:
        with self._cond:
            return self._done

    def get(self, timeout: Optional[float] = None):
        with self._cond:
            if not self._done:
                self._cond.wait(timeout=timeout)
            return self._value


class Mailbox:
    def __init__(self):
        self._q: "queue.Queue" = queue.Queue()

    def put(self, msg):
        self._q.put(msg)

    def get(self, timeout=None):
        return self._q.get(timeout=timeout)

    def drain(self) -> list:
        """Pull every queued message out without blocking.  Used at
        shutdown so the persistence layer can snapshot anything we
        haven't processed yet."""
        items = []
        try:
            while True:
                items.append(self._q.get_nowait())
        except queue.Empty:
            pass
        return items


class Actor:
    """One actor = one worker thread + per-instance fields."""

    def __init__(self, name: str, cls_decl, scheduler: "Scheduler"):
        self.name = name
        self.cls = cls_decl       # ClassDecl
        self.scheduler = scheduler
        self.fields: dict = {}    # field name -> value
        self.mailbox = Mailbox()
        self._stopped = False
        # Thread is started by Scheduler after fields are initialised.
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # Lifecycle

    def start(self, run_body):
        """run_body(actor, method_name, args, sender) -> None.

        We let Scheduler hand us the dispatch hook so this module stays
        independent of the interpreter.
        """
        self._dispatch = run_body
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"actor-{self.name}")
        self._thread.start()

    def stop(self):
        self._stopped = True
        # Sentinel wakes the worker.
        self.mailbox.put(("__stop__", [], None, None, None))

    def _run(self):
        while not self._stopped:
            try:
                msg = self.mailbox.get(timeout=0.05)
            except queue.Empty:
                continue
            method_name, args, sender, msg_id, reply_future = msg
            if method_name == "__stop__":
                break
            try:
                self._dispatch(self, method_name, args, sender, reply_future)
            except Exception as e:
                # flush so actor errors surface even when stdout is
                # redirected to a file (block-buffered).
                print(f"[actor {self.name}.{method_name}] error: {e}", flush=True)
                if reply_future is not None:
                    reply_future.set(None)
            finally:
                self.scheduler.message_done()

    # ------------------------------------------------------------------
    # API used by the interpreter

    def send_method(
        self,
        method: str,
        args: list,
        sender: "Optional[Actor]" = None,
        reply_future: "Optional[Future]" = None,
    ):
        """Enqueue a message on this actor and bump the outstanding count.

        `reply_future` is set for now-/future-type sends.  When the
        callee finishes (or calls `reply(x)`), the future is fulfilled
        so the caller can unblock.
        """
        self.scheduler.message_started()
        self.mailbox.put((method, args, sender, None, reply_future))


class Scheduler:
    """Tracks the set of live actors and the global outstanding-msg count
    so the main thread can wait for quiescence."""

    def __init__(self):
        self._actors: dict = {}        # name -> Actor
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._outstanding = 0

    # ---- actor registry --------------------------------------------------

    def register(self, actor: Actor):
        with self._lock:
            self._actors[actor.name] = actor

    def get(self, name: str) -> Optional[Actor]:
        with self._lock:
            return self._actors.get(name)

    def all(self):
        with self._lock:
            return list(self._actors.values())

    # ---- outstanding-message tracking -----------------------------------

    def message_started(self):
        with self._cond:
            self._outstanding += 1

    def message_done(self):
        with self._cond:
            self._outstanding -= 1
            if self._outstanding <= 0:
                self._cond.notify_all()

    def wait_idle(self, idle_ms: int = 80, timeout_s: float = 2.0) -> bool:
        """Return True once outstanding==0 has held continuously for idle_ms,
        or False on timeout."""
        import time
        deadline = time.monotonic() + timeout_s
        idle_since = None
        while time.monotonic() < deadline:
            with self._cond:
                if self._outstanding == 0:
                    if idle_since is None:
                        idle_since = time.monotonic()
                    elif (time.monotonic() - idle_since) * 1000 >= idle_ms:
                        return True
                else:
                    idle_since = None
                self._cond.wait(timeout=0.05)
        return False

    def shutdown(self):
        for a in self.all():
            a.stop()
