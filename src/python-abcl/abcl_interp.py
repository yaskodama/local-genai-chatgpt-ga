"""Tree-walking interpreter for ABCL/c+ Python implementation.

Top-level statements run on the main thread.  Each `new C(...)` spawns
an actor, which has its own worker thread and processes incoming
messages via Interpreter.dispatch().
"""

import math
import sys
import threading
import time
from typing import Optional

from abcl_ast import (
    Program, ClassDecl, MethodDecl, GlobalStmt,
    VarDecl, VarNew, Assign, Send, CallStmt,
    If, While, Become, Block,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, New, CallExpr,
    ArrayLit, NowCall, FutureCall,
)
from abcl_runtime import Actor, Future, Scheduler


class Frame:
    """Lexical frame: locals chain back to a parent frame."""
    def __init__(
        self,
        actor: Optional[Actor],
        sender: Optional[Actor],
        parent: "Optional[Frame]" = None,
        reply_future: Optional[Future] = None,
    ):
        self.actor = actor
        self.sender = sender
        self.locals = {}
        self.parent = parent
        # reply_future is set on the *top* frame of a now-/future-type
        # message dispatch; nested blocks reach it via parent chain.
        self.reply_future = reply_future

    def get_reply_future(self) -> Optional[Future]:
        f = self
        while f is not None:
            if f.reply_future is not None:
                return f.reply_future
            f = f.parent
        return None

    def find_local_frame(self, name):
        f = self
        while f is not None:
            if name in f.locals:
                return f
            f = f.parent
        return None

    def lookup(self, name, globals_):
        if name == "self":   return self.actor
        if name == "sender": return self.sender
        f = self.find_local_frame(name)
        if f is not None:
            return f.locals[name]
        if self.actor is not None and name in self.actor.fields:
            return self.actor.fields[name]
        if name in globals_:
            return globals_[name]
        raise NameError(f"unbound variable: {name}")

    def assign(self, name, value, globals_):
        f = self.find_local_frame(name)
        if f is not None:
            f.locals[name] = value
            return
        if self.actor is not None and name in self.actor.fields:
            self.actor.fields[name] = value
            return
        if name in globals_:
            globals_[name] = value
            return
        # No declaration found — create as local in current frame
        # (matches the OCaml behaviour for fresh names).
        self.locals[name] = value


class ReturnSignal(Exception):
    pass


class Interpreter:
    def __init__(self, program: Program):
        self.program = program
        self.classes: dict = {}      # name -> ClassDecl
        self.globals: dict = {}      # global name -> value (typically actor refs)
        self.scheduler = Scheduler()
        self._global_lock = threading.Lock()
        self._actor_counter = 0
        # Optional persisted-fields + pending-mailbox snapshot loaded
        # once at startup; replay happens per-actor during spawn.
        try:
            from abcl_state import load_snapshot, load_pending
            self._state_snapshot = load_snapshot()
            self._pending_snapshot = load_pending()
        except Exception:
            self._state_snapshot = {}
            self._pending_snapshot = {}
        for d in program.decls:
            if isinstance(d, ClassDecl):
                self.classes[d.name] = d

    # ------------------------------------------------------------------
    # Entry point

    def run(self, idle_ms: int = 120, timeout_s: float = 2.0):
        # Top-level runs in a synthetic frame with no actor.
        frame = Frame(actor=None, sender=None)
        for d in self.program.decls:
            if isinstance(d, GlobalStmt):
                self.exec_stmt(d.stmt, frame)
        # Make every globally-scoped actor reachable by name to remote
        # senders, matching OCaml's "actor_exists" behaviour.
        try:
            from abcl_remote import set_actor_lookup
            def _lookup(name):
                v = self.globals.get(name)
                return v if isinstance(v, Actor) else None
            set_actor_lookup(_lookup)
        except Exception:
            pass

        # If a remote gateway was started during top-level execution,
        # stay alive until the user interrupts — auto-idle would shut
        # the listener down right after binding the port.
        try:
            from abcl_remote import is_gateway_running
        except Exception:
            is_gateway_running = lambda: False  # noqa: E731
        if is_gateway_running():
            print("[interp] gateway running — Ctrl-C to stop")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            self.scheduler.wait_idle(idle_ms=idle_ms, timeout_s=timeout_s)
        # Persist actor fields + any undelivered mailbox messages
        # before shutdown so a graceful restart can pick up where
        # we left off.  No-op when ABCL_NODE_STATE_FILE is unset.
        try:
            self._save_state_with_pending()
        except Exception as e:
            print(f"[state] save on exit failed: {e}", flush=True)
        self.scheduler.shutdown()

    def _save_state_with_pending(self) -> None:
        try:
            from abcl_state import save_snapshot
        except Exception:
            return
        actors_fields = []
        pending = []
        with self._global_lock:
            globs = list(self.globals.items())
        for name, val in globs:
            if isinstance(val, Actor):
                actors_fields.append((name, dict(val.fields)))
                drained = val.mailbox.drain()
                msgs = []
                for tup in drained:
                    if not isinstance(tup, tuple) or len(tup) < 2:
                        continue
                    method = tup[0]
                    args = tup[1] if len(tup) > 1 else []
                    if method == "__stop__":
                        continue
                    if not isinstance(args, list):
                        continue
                    if not all(isinstance(a, (int, float, bool, str)) or a is None for a in args):
                        # Skip messages whose args we can't safely
                        # round-trip through JSON.
                        continue
                    msgs.append({"method": method, "args": args})
                if msgs:
                    pending.append((name, msgs))
        save_snapshot(actors_fields, pending=pending)

    # ------------------------------------------------------------------
    # Actor lifecycle

    def _fresh_actor_name(self, cls_name: str) -> str:
        with self._global_lock:
            self._actor_counter += 1
            return f"_anon_{cls_name}_{self._actor_counter}"

    def spawn_actor(self, cls_name: str, ctor_args: list, var_name: Optional[str] = None) -> Actor:
        cls = self.classes.get(cls_name)
        if cls is None:
            raise NameError(f"unknown class: {cls_name}")
        name = var_name or self._fresh_actor_name(cls_name)
        actor = Actor(name=name, cls_decl=cls, scheduler=self.scheduler)
        # Initialise fields by evaluating each field initializer in a
        # frame that has access to the actor (so referring to other
        # fields works) but no sender.
        init_frame = Frame(actor=actor, sender=None)
        for f in cls.fields:
            actor.fields[f.name] = self.eval_expr(f.expr, init_frame)
        # Overwrite with persisted values if a snapshot is present.
        # Only int/float/string/bool fields are persisted; everything
        # else (e.g. Actor references) is left at its default.
        snap = self._state_snapshot.get(name)
        if isinstance(snap, dict):
            for k, v in snap.items():
                if k in actor.fields and isinstance(v, (int, float, bool, str)):
                    actor.fields[k] = v
        self.scheduler.register(actor)
        actor.start(self.dispatch)
        # If `init` is defined, send it the constructor args.
        if any(m.name == "init" for m in cls.methods):
            actor.send_method("init", ctor_args, sender=None)
        # Replay any messages that were pending for this actor at the
        # previous shutdown.
        replay = self._pending_snapshot.pop(name, None)
        if isinstance(replay, list):
            for msg in replay:
                m_method = msg.get("method") if isinstance(msg, dict) else None
                m_args   = msg.get("args", []) if isinstance(msg, dict) else []
                if isinstance(m_method, str) and isinstance(m_args, list):
                    actor.send_method(m_method, list(m_args), sender=None)
        return actor

    def dispatch(
        self,
        actor: Actor,
        method_name: str,
        args: list,
        sender: Optional[Actor],
        reply_future: Optional[Future] = None,
    ):
        method = next((m for m in actor.cls.methods if m.name == method_name), None)
        if method is None:
            if reply_future is not None:
                reply_future.set(None)
            return  # silently ignore unknown method
        if len(args) != len(method.params):
            print(f"[arity] {actor.name}.{method_name}: expected {len(method.params)}, got {len(args)}")
            if reply_future is not None:
                reply_future.set(None)
            return
        frame = Frame(actor=actor, sender=sender, reply_future=reply_future)
        for p, v in zip(method.params, args):
            frame.locals[p] = v
        self.exec_block(method.body, frame)
        # If the method never called reply(), unblock any waiter with None.
        if reply_future is not None:
            reply_future.set(None)

    # ------------------------------------------------------------------
    # Execution

    def exec_block(self, block: Block, parent: Frame):
        # Each block introduces a nested scope.
        frame = Frame(actor=parent.actor, sender=parent.sender, parent=parent)
        for s in block.stmts:
            self.exec_stmt(s, frame)

    def exec_stmt(self, s, frame: Frame):
        kind = type(s)
        if kind is VarDecl:
            v = self.eval_expr(s.expr, frame)
            frame.locals[s.name] = v
        elif kind is VarNew:
            actor = self.spawn_actor(s.cls_name, [self.eval_expr(a, frame) for a in s.args], var_name=s.name)
            with self._global_lock:
                self.globals[s.name] = actor
        elif kind is Assign:
            v = self.eval_expr(s.expr, frame)
            frame.assign(s.name, v, self.globals)
        elif kind is Send:
            self._do_send(s.target, s.method, s.args, frame)
        elif kind is CallStmt:
            self._call_builtin(s.name, [self.eval_expr(a, frame) for a in s.args], frame)
        elif kind is If:
            cond = self.eval_expr(s.cond, frame)
            if _truthy(cond):
                self.exec_stmt(s.then_body, frame)
            elif s.else_body is not None:
                self.exec_stmt(s.else_body, frame)
        elif kind is While:
            while _truthy(self.eval_expr(s.cond, frame)):
                self.exec_stmt(s.body, frame)
        elif kind is Become:
            self._do_become(s.cls_name, [self.eval_expr(a, frame) for a in s.args], frame)
        elif kind is Block:
            self.exec_block(s, frame)
        else:
            raise RuntimeError(f"unknown stmt: {s!r}")

    def _resolve_actor(self, target_name: str, frame: Frame) -> Optional[Actor]:
        if target_name == "self":
            return frame.actor
        if target_name == "sender":
            return frame.sender
        f = frame.find_local_frame(target_name)
        if f is not None and isinstance(f.locals[target_name], Actor):
            return f.locals[target_name]
        if frame.actor is not None and target_name in frame.actor.fields \
           and isinstance(frame.actor.fields[target_name], Actor):
            return frame.actor.fields[target_name]
        with self._global_lock:
            v = self.globals.get(target_name)
        return v if isinstance(v, Actor) else None

    def _do_send(self, target_name: str, method: str, raw_args: list, frame: Frame):
        args = [self.eval_expr(a, frame) for a in raw_args]
        tgt = self._resolve_actor(target_name, frame)
        if tgt is None:
            print(f"[send] {target_name}.{method}(): no such actor")
            return
        tgt.send_method(method, args, sender=frame.actor)

    def _do_become(self, cls_name: str, args: list, frame: Frame):
        actor = frame.actor
        if actor is None:
            print("[become] outside an actor body — ignored")
            return
        new_cls = self.classes.get(cls_name)
        if new_cls is None:
            print(f"[become] unknown class: {cls_name}")
            return
        actor.cls = new_cls
        actor.fields = {}
        init_frame = Frame(actor=actor, sender=None)
        for f in new_cls.fields:
            actor.fields[f.name] = self.eval_expr(f.expr, init_frame)
        if any(m.name == "init" for m in new_cls.methods):
            actor.send_method("init", args, sender=None)

    # ------------------------------------------------------------------
    # Expression evaluation

    def eval_expr(self, e, frame: Frame):
        kind = type(e)
        if kind is IntLit:    return e.val
        if kind is FloatLit:  return e.val
        if kind is StringLit: return e.val
        if kind is Var:       return frame.lookup(e.name, self.globals)
        if kind is Neg:       return -self.eval_expr(e.inner, frame)
        if kind is Binop:
            l = self.eval_expr(e.lhs, frame)
            r = self.eval_expr(e.rhs, frame)
            return _apply_binop(e.op, l, r)
        if kind is New:
            args = [self.eval_expr(a, frame) for a in e.args]
            return self.spawn_actor(e.cls_name, args)
        if kind is CallExpr:
            args = [self.eval_expr(a, frame) for a in e.args]
            return self._call_builtin(e.name, args, frame, returning=True)
        if kind is ArrayLit:
            return [self.eval_expr(x, frame) for x in e.items]
        if kind is NowCall:
            return self._do_now_send(e.target, e.method, e.args, frame)
        if kind is FutureCall:
            return self._do_future_send(e.target, e.method, e.args, frame)
        raise RuntimeError(f"unknown expr: {e!r}")

    def _do_now_send(self, target_name: str, method: str, raw_args: list, frame: Frame):
        tgt = self._resolve_actor(target_name, frame)
        if tgt is None:
            print(f"[now] {target_name}.{method}(): no such actor")
            return None
        args = [self.eval_expr(a, frame) for a in raw_args]
        fut = Future()
        tgt.send_method(method, args, sender=frame.actor, reply_future=fut)
        return fut.get()

    def _do_future_send(self, target_name: str, method: str, raw_args: list, frame: Frame):
        tgt = self._resolve_actor(target_name, frame)
        if tgt is None:
            print(f"[future] {target_name}.{method}(): no such actor")
            return None
        args = [self.eval_expr(a, frame) for a in raw_args]
        fut = Future()
        tgt.send_method(method, args, sender=frame.actor, reply_future=fut)
        return fut

    # ------------------------------------------------------------------
    # Builtins

    def _call_builtin(self, name: str, args: list, frame: Frame, returning: bool = False):
        fn = _BUILTINS.get(name)
        if fn is None:
            if returning:
                raise NameError(f"unknown function: {name}")
            print(f"[call] unknown builtin: {name}")
            return None
        return fn(args, frame, self)


# ----------------------------------------------------------------------
# Helpers

def _truthy(v) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v != ""
    return v is not None


def _apply_binop(op: str, l, r):
    if op == "+":
        if isinstance(l, str) or isinstance(r, str):
            return _to_str(l) + _to_str(r)
        return l + r
    if op == "-": return l - r
    if op == "*": return l * r
    if op == "/":
        if isinstance(l, int) and isinstance(r, int) and r != 0:
            return l / r if (l % r) else l // r
        return l / r
    if op == "==": return l == r
    if op == "!=": return l != r
    if op == "<":  return l < r
    if op == ">":  return l > r
    if op == "<=": return l <= r
    if op == ">=": return l >= r
    raise RuntimeError(f"unknown op: {op}")


def _to_str(v):
    if isinstance(v, float):
        # Match OCaml's printing of whole floats (e.g. "5.")
        if v.is_integer():
            return f"{int(v)}."
        return str(v)
    if isinstance(v, Actor):
        return f"<actor {v.name}>"
    return str(v)


# ----------------------------------------------------------------------
# Built-in functions
#
# Each builtin: fn(args, frame, interp) -> return value (or None)

def _b_print(args, frame, interp):
    print(*[_to_str(a) for a in args], sep="", flush=True)
    return None

def _b_reply(args, frame, interp):
    """ABCL reply(x).

    For now-/future-type sends, fulfils the caller's Future so it can
    unblock with `x` as the value.  For plain past-type sends (no
    reply_future on the frame chain), prints [REPLY] x as before so
    debugging output stays visible.
    """
    val = args[0] if args else None
    fut = frame.get_reply_future()
    if fut is not None:
        fut.set(val)
        return None
    print(f"[REPLY] {_to_str(val)}")
    sys.stdout.flush()
    return None


def _b_await(args, frame, interp):
    """await(f): block until the future is fulfilled and return its value."""
    if not args:
        return None
    f = args[0]
    if isinstance(f, Future):
        return f.get()
    # Allow await on a plain value as a no-op for ergonomic chaining
    return f


def _b_future_done(args, frame, interp):
    if not args:
        return False
    f = args[0]
    return f.done() if isinstance(f, Future) else True

def _b_wait(args, frame, interp):
    ms = int(args[0]) if args else 0
    time.sleep(ms / 1000.0)
    return None

def _b_sleep(args, frame, interp):
    s = float(args[0]) if args else 0.0
    time.sleep(s)
    return None

def _b_now_ms(args, frame, interp):
    return int(time.time() * 1000)

def _b_str(args, frame, interp):
    return _to_str(args[0]) if args else ""

def _b_int(args, frame, interp):
    return int(args[0]) if args else 0

def _b_float(args, frame, interp):
    return float(args[0]) if args else 0.0

def _b_random(args, frame, interp):
    import random
    if len(args) == 0:
        return random.random()
    if len(args) == 1:
        return random.randint(0, int(args[0]) - 1)
    return random.randint(int(args[0]), int(args[1]) - 1)


def _b_ai_call(args, frame, interp):
    from abcl_ai import call_ai
    if not args:
        raise ValueError("ai_call(prompt): expected 1 string argument")
    return call_ai(_to_str(args[0]))


def _b_ai_call_with_system(args, frame, interp):
    from abcl_ai import call_ai
    if len(args) < 2:
        raise ValueError("ai_call_with_system(system, prompt): expected 2 string arguments")
    return call_ai(_to_str(args[1]), system=_to_str(args[0]))


def _b_ai_call_priority(args, frame, interp):
    """ai_call_priority(prio, prompt) — lower prio served first when
    ABCL_AI_MAX_CONCURRENT is set and the gate is full."""
    from abcl_ai import call_ai
    if len(args) < 2:
        raise ValueError("ai_call_priority(prio, prompt): expected 2 arguments")
    return call_ai(_to_str(args[1]), priority=float(args[0]))


def _b_ai_call_priority_with_system(args, frame, interp):
    from abcl_ai import call_ai
    if len(args) < 3:
        raise ValueError(
            "ai_call_priority_with_system(prio, system, prompt): expected 3 arguments")
    return call_ai(
        _to_str(args[2]),
        system=_to_str(args[1]),
        priority=float(args[0]),
    )


def _b_ai_usage(args, frame, interp):
    """Returns a one-line usage summary string."""
    from abcl_ai import get_usage
    u = get_usage()
    return (f"calls={u['calls']} in={u['input_tokens']} "
            f"out={u['output_tokens']} total={u['total_tokens']} "
            f"cost=${u['cost_usd']:.6f}")


def _b_ai_remaining(args, frame, interp):
    """Tokens still allowed by ABCL_AI_TOKEN_BUDGET; -1 if no budget."""
    from abcl_ai import get_remaining
    return get_remaining()


def _b_ai_cost(args, frame, interp):
    """Returns running cost in USD as a float."""
    from abcl_ai import get_cost_usd
    return get_cost_usd()


def _ai_retry_loop(max_attempts: int, do_call):
    """Common retry loop used by ai_call_retry / ai_call_retry_with_system."""
    import random as _rand
    from abcl_ai import _is_retryable
    last_exc = None
    for i in range(max(1, max_attempts)):
        try:
            return do_call()
        except Exception as e:
            last_exc = e
            if i == max_attempts - 1 or not _is_retryable(e):
                raise
            delay = (0.5 * (2 ** i)) + _rand.uniform(0, 0.25)
            print(f"[ai_retry] attempt {i+1}/{max_attempts} "
                  f"failed ({type(e).__name__}); retry in {delay:.2f}s",
                  flush=True)
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc


def _b_ai_call_retry(args, frame, interp):
    """ai_call_retry(max_attempts, prompt) — retry on rate-limit /
    transient errors with exponential backoff."""
    from abcl_ai import call_ai
    if len(args) < 2:
        raise ValueError("ai_call_retry(max_attempts, prompt)")
    max_attempts = int(args[0])
    prompt = _to_str(args[1])
    return _ai_retry_loop(max_attempts, lambda: call_ai(prompt))


def _b_ai_call_retry_with_system(args, frame, interp):
    """ai_call_retry_with_system(max_attempts, system, prompt)"""
    from abcl_ai import call_ai
    if len(args) < 3:
        raise ValueError("ai_call_retry_with_system(max_attempts, system, prompt)")
    max_attempts = int(args[0])
    system = _to_str(args[1])
    prompt = _to_str(args[2])
    return _ai_retry_loop(max_attempts, lambda: call_ai(prompt, system=system))


# ---------------------------------------------------------------------------
# Distributed actor builtins.

def _b_web_listen(args, frame, interp):
    from abcl_remote import start_gateway
    if not args:
        raise ValueError("web_listen(port): expected 1 int argument")
    start_gateway(int(args[0]))
    return None


def _b_web_expose(args, frame, interp):
    """web_expose(name, actor) — register `actor` under `name` so any
    remote `POST /api/json/send` with that to-field is delivered to its
    mailbox."""
    from abcl_remote import expose
    if len(args) < 2:
        raise ValueError("web_expose(name, actor): expected 2 arguments")
    name = _to_str(args[0])
    actor_arg = args[1]
    if not isinstance(actor_arg, Actor):
        raise ValueError("web_expose: second arg must be an actor reference")
    expose(name, actor_arg)
    print(f"[expose] {name} -> {actor_arg.name}")
    return None


def _b_remote_call(args, frame, interp):
    """remote_call(hostport, actor_name, method, ...args) — fire-and-forget
    POST to a remote ABCL/c+ runtime (Python or OCaml).  Wire format
    matches OCaml src/web_gateway.ml."""
    from abcl_remote import remote_send
    if len(args) < 3:
        raise ValueError("remote_call(hostport, actor, method, ...args)")
    hostport = _to_str(args[0])
    to_actor = _to_str(args[1])
    method = _to_str(args[2])
    rest = list(args[3:])
    sender_name = frame.actor.name if frame.actor is not None else "main"
    remote_send(hostport, to_actor, method, rest, from_name=sender_name)
    return None


def _b_remote_now(args, frame, interp):
    """remote_now(hostport, actor, method, ...args) — synchronous,
    returns the receiver's reply(value).  Goes through Python's
    /api/json/call endpoint; not supported by an OCaml peer (yet)."""
    from abcl_remote import remote_call_sync
    if len(args) < 3:
        raise ValueError("remote_now(hostport, actor, method, ...args)")
    hostport = _to_str(args[0])
    to_actor = _to_str(args[1])
    method = _to_str(args[2])
    rest = list(args[3:])
    sender_name = frame.actor.name if frame.actor is not None else "main"
    return remote_call_sync(hostport, to_actor, method, rest, from_name=sender_name)


def _b_remote_future(args, frame, interp):
    """remote_future(hostport, actor, method, ...args) — like
    remote_now but returns a Future immediately.  await(f) to get
    the reply.  Lets the caller fan out parallel synchronous remote
    calls without spinning up an explicit thread per call."""
    from abcl_remote import remote_call_sync
    from abcl_runtime import Future
    if len(args) < 3:
        raise ValueError("remote_future(hostport, actor, method, ...args)")
    hostport = _to_str(args[0])
    to_actor = _to_str(args[1])
    method = _to_str(args[2])
    rest = list(args[3:])
    sender_name = frame.actor.name if frame.actor is not None else "main"
    fut = Future()
    def _runner():
        try:
            v = remote_call_sync(hostport, to_actor, method, rest, from_name=sender_name)
            fut.set(v)
        except Exception as e:
            print(f"[remote_future] error: {e}")
            fut.set(None)
    threading.Thread(target=_runner, daemon=True).start()
    return fut


def _b_serve_forever(args, frame, interp):
    """Block the current thread.  Useful at the end of a server-style
    .abcl program after web_listen / web_expose so the process keeps
    accepting incoming messages."""
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return None


def _b_register_with(args, frame, interp):
    """register_with(coordinator_dashboard_host:port, my_host, my_port)
    — announce this node to a coordinator's dashboard so it appears
    in the peer aggregation view without an env-var rebuild."""
    if len(args) < 3:
        raise ValueError(
            "register_with(coord_hostport, my_host, my_port)")
    coord = _to_str(args[0])
    my_host = _to_str(args[1])
    my_port = int(args[2])
    import json as _json
    import urllib.request as _u
    import urllib.error as _ue
    payload = _json.dumps({"host": my_host, "port": my_port}).encode("utf-8")
    req = _u.Request(f"http://{coord}/api/peer/register",
                     data=payload, method="POST",
                     headers={"Content-Type": "application/json"})
    try:
        with _u.urlopen(req, timeout=2) as resp:
            return resp.read().decode("utf-8")
    except (_ue.URLError, _ue.HTTPError) as e:
        return f"error: {e}"


def _b_inspect(args, frame, interp):
    """inspect(actor) -> multi-line string with name + class + fields."""
    if not args:
        return ""
    a = args[0]
    if not isinstance(a, Actor):
        return f"<not-an-actor: {type(a).__name__}>"
    lines = [f"{a.name} : {a.cls.name}"]
    for k, v in a.fields.items():
        lines.append(f"  {k} = {_to_str(v)}")
    return "\n".join(lines)


def _b_actors(args, frame, interp):
    """actors() -> array of every locally-registered actor name."""
    return [a.name for a in interp.scheduler.all()]


def _b_inspect_all(args, frame, interp):
    """inspect_all() -> dump of every actor's name, class, and fields."""
    return "\n".join(_b_inspect([a], frame, interp)
                     for a in interp.scheduler.all())


def _b_save_state(args, frame, interp):
    """Persist every actor's int/float/string/bool fields to
    ABCL_NODE_STATE_FILE (no-op if the env var is unset).  Reloaded
    automatically on the next interpreter start."""
    try:
        from abcl_state import save_snapshot
    except Exception:
        return None
    actors = []
    with interp._global_lock:
        for name, val in list(interp.globals.items()):
            if isinstance(val, Actor):
                actors.append((name, dict(val.fields)))
    save_snapshot(actors)
    return None


# ---------------------------------------------------------------------------
# Standard library (string + I/O + misc).  Keep these synchronous and
# total — anything that can hit the filesystem returns "" / False on
# error rather than raising, so an .abcl program can probe gracefully.

def _b_str_len(args, frame, interp):
    return len(_to_str(args[0])) if args else 0

def _b_str_sub(args, frame, interp):
    """str_sub(s, start) or str_sub(s, start, end_exclusive)."""
    if not args:
        return ""
    s = _to_str(args[0])
    if len(args) == 1:
        return s
    start = int(args[1])
    if len(args) >= 3:
        return s[start:int(args[2])]
    return s[start:]

def _b_str_contains(args, frame, interp):
    if len(args) < 2:
        return False
    return _to_str(args[1]) in _to_str(args[0])

def _b_str_index(args, frame, interp):
    """str_index(haystack, needle) -> int (or -1)."""
    if len(args) < 2:
        return -1
    return _to_str(args[0]).find(_to_str(args[1]))

def _b_str_lower(args, frame, interp):
    return _to_str(args[0]).lower() if args else ""

def _b_str_upper(args, frame, interp):
    return _to_str(args[0]).upper() if args else ""

def _b_str_trim(args, frame, interp):
    return _to_str(args[0]).strip() if args else ""

def _b_str_replace(args, frame, interp):
    if len(args) < 3:
        return _to_str(args[0]) if args else ""
    return _to_str(args[0]).replace(_to_str(args[1]), _to_str(args[2]))

def _b_str_starts_with(args, frame, interp):
    if len(args) < 2:
        return False
    return _to_str(args[0]).startswith(_to_str(args[1]))

def _b_str_ends_with(args, frame, interp):
    if len(args) < 2:
        return False
    return _to_str(args[0]).endswith(_to_str(args[1]))

def _b_read_file(args, frame, interp):
    if not args:
        return ""
    try:
        with open(_to_str(args[0])) as f:
            return f.read()
    except OSError:
        return ""

def _b_write_file(args, frame, interp):
    """write_file(path, content) -> 1 on success, 0 on failure."""
    if len(args) < 2:
        return 0
    try:
        with open(_to_str(args[0]), "w") as f:
            f.write(_to_str(args[1]))
        return 1
    except OSError:
        return 0

def _b_append_file(args, frame, interp):
    if len(args) < 2:
        return 0
    try:
        with open(_to_str(args[0]), "a") as f:
            f.write(_to_str(args[1]))
        return 1
    except OSError:
        return 0

def _b_file_exists(args, frame, interp):
    import os.path
    return 1 if (args and os.path.exists(_to_str(args[0]))) else 0

def _b_env_get(args, frame, interp):
    import os as _os
    if not args:
        return ""
    default = _to_str(args[1]) if len(args) >= 2 else ""
    return _os.environ.get(_to_str(args[0]), default)

def _b_now_s(args, frame, interp):
    """Wall-clock seconds since epoch as a float."""
    return time.time()


# ---- Arrays ----------------------------------------------------------------

def _b_array_len(args, frame, interp):
    if not args:
        return 0
    a = args[0]
    return len(a) if isinstance(a, list) else 0

def _b_array_get(args, frame, interp):
    if len(args) < 2:
        return None
    a = args[0]
    i = int(args[1])
    if not isinstance(a, list) or i < 0 or i >= len(a):
        return None
    return a[i]

def _b_array_set(args, frame, interp):
    if len(args) < 3:
        return None
    a = args[0]
    i = int(args[1])
    v = args[2]
    if isinstance(a, list) and 0 <= i < len(a):
        a[i] = v
    return v

def _b_array_push(args, frame, interp):
    if len(args) < 2:
        return None
    a = args[0]
    if isinstance(a, list):
        a.append(args[1])
    return None

def _b_array_concat(args, frame, interp):
    if len(args) < 2:
        return list(args[0]) if args and isinstance(args[0], list) else []
    a, b = args[0], args[1]
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    return []

def _b_array_join(args, frame, interp):
    if not args:
        return ""
    a = args[0]
    sep = _to_str(args[1]) if len(args) >= 2 else ","
    if isinstance(a, list):
        return sep.join(_to_str(x) for x in a)
    return _to_str(a)


def run_repl() -> None:
    """Interactive REPL.  Each accepted line/block is parsed as a
    standalone program; class declarations are merged into the
    interpreter's class table and top-level statements run against
    the running globals.  Lines are buffered until the parser
    accepts them, so multi-line class definitions just work.

    Special commands:
        :exit / :quit   leave
        :show           print known classes + globals
        :clear          discard pending buffered input
        :help           show command list
    """
    from abcl_ast import Program as _Program, ClassDecl as _ClassDecl
    from abcl_parser import parse as _parse

    interp = Interpreter(_Program(decls=[]))
    # Hook actor lookup so an interactive web_listen still routes
    # incoming traffic to actors typed at the REPL.
    try:
        from abcl_remote import set_actor_lookup
        def _lookup(name):
            v = interp.globals.get(name)
            return v if isinstance(v, Actor) else None
        set_actor_lookup(_lookup)
    except Exception:
        pass

    print("ABCL/c+ Python REPL — :help for commands, Ctrl-D / :exit to quit",
          flush=True)
    buf = []

    def prompt() -> str:
        return "abcl> " if not buf else "....> "

    def _braces_balanced(s: str) -> bool:
        depth = 0
        in_str = False
        escape = False
        for c in s:
            if escape:
                escape = False
                continue
            if in_str:
                if c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
        return depth <= 0

    while True:
        try:
            line = input(prompt())
        except (EOFError, KeyboardInterrupt):
            print()
            break

        stripped = line.strip()
        if stripped in (":exit", ":quit"):
            break
        if stripped == ":help":
            print(":exit / :quit  leave the REPL")
            print(":show          list known classes and globals")
            print(":clear         discard pending buffered input")
            print("Otherwise type any .abcl statement; multi-line input is")
            print("buffered until the parser accepts it.")
            continue
        if stripped == ":show":
            print(f"classes: {sorted(interp.classes.keys())}")
            print(f"globals: {sorted(interp.globals.keys())}")
            continue
        if stripped == ":clear":
            buf = []
            continue
        if not stripped:
            continue

        buf.append(line)
        src = "\n".join(buf)
        try:
            program = _parse(src)
        except Exception as e:
            # Heuristic: keep buffering until the brace count is
            # balanced AND the line looks terminal — that's when a
            # real syntax error becomes worth reporting.
            terminal = stripped.endswith(";") or stripped.endswith("}")
            if terminal and _braces_balanced(src):
                print(f"[parse error] {e}", flush=True)
                buf = []
            continue

        buf = []
        frame = Frame(actor=None, sender=None)
        for d in program.decls:
            try:
                if isinstance(d, _ClassDecl):
                    interp.classes[d.name] = d
                    print(f"[defined] class {d.name}", flush=True)
                else:
                    interp.exec_stmt(d.stmt, frame)
            except Exception as e:
                print(f"[error] {e}", flush=True)
                break

    # Let any in-flight messages finish before shutting down so the
    # actor thread's print() output isn't lost on exit.
    interp.scheduler.wait_idle(idle_ms=80, timeout_s=2.0)
    interp.scheduler.shutdown()


_BUILTINS = {
    "print":   _b_print,
    "println": _b_print,
    "reply":   _b_reply,
    "wait":    _b_wait,
    "sleep":   _b_sleep,
    "now_ms":  _b_now_ms,
    "str":     _b_str,
    "int":     _b_int,
    "float":   _b_float,
    "random":  _b_random,
    # math passthroughs (mostly no-ops without SDL)
    "cos":     lambda a, f, i: math.cos(a[0]),
    "sin":     lambda a, f, i: math.sin(a[0]),
    "sqrt":    lambda a, f, i: math.sqrt(a[0]),
    "abs":     lambda a, f, i: abs(a[0]),
    "max":     lambda a, f, i: max(a),
    "min":     lambda a, f, i: min(a),
    # Future / synchronisation
    "await":       _b_await,
    "future_done": _b_future_done,
    # AI integration (provider auto-selected by env var)
    "ai_call":                       _b_ai_call,
    "ai_call_with_system":           _b_ai_call_with_system,
    "ai_call_priority":              _b_ai_call_priority,
    "ai_call_priority_with_system":  _b_ai_call_priority_with_system,
    "ai_call_retry":                 _b_ai_call_retry,
    "ai_call_retry_with_system":     _b_ai_call_retry_with_system,
    "ai_usage":                      _b_ai_usage,
    "ai_remaining":                  _b_ai_remaining,
    "ai_cost":                       _b_ai_cost,
    # Distributed actors (wire-compat with OCaml web_gateway.ml)
    "web_listen":                    _b_web_listen,
    "web_expose":                    _b_web_expose,
    "remote_call":                   _b_remote_call,
    "remote_now":                    _b_remote_now,
    "remote_future":                 _b_remote_future,
    "serve_forever":                 _b_serve_forever,
    "register_with":                 _b_register_with,
    # Per-node persistent state
    "save_state":                    _b_save_state,
    # Introspection
    "inspect":                       _b_inspect,
    "inspect_all":                   _b_inspect_all,
    "actors":                        _b_actors,
    # ---- stdlib: strings ----
    "str_len":                       _b_str_len,
    "str_sub":                       _b_str_sub,
    "str_contains":                  _b_str_contains,
    "str_index":                     _b_str_index,
    "str_lower":                     _b_str_lower,
    "str_upper":                     _b_str_upper,
    "str_trim":                      _b_str_trim,
    "str_replace":                   _b_str_replace,
    "str_starts_with":               _b_str_starts_with,
    "str_ends_with":                 _b_str_ends_with,
    # ---- stdlib: I/O + env + clock ----
    "read_file":                     _b_read_file,
    "write_file":                    _b_write_file,
    "append_file":                   _b_append_file,
    "file_exists":                   _b_file_exists,
    "env_get":                       _b_env_get,
    "now_s":                         _b_now_s,
    # ---- arrays ----
    "array_len":                     _b_array_len,
    "array_get":                     _b_array_get,
    "array_set":                     _b_array_set,
    "array_push":                    _b_array_push,
    "array_concat":                  _b_array_concat,
    "array_join":                    _b_array_join,
}
