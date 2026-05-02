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
    NowCall, FutureCall,
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
        # Wait for actors to drain.
        self.scheduler.wait_idle(idle_ms=idle_ms, timeout_s=timeout_s)
        self.scheduler.shutdown()

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
        self.scheduler.register(actor)
        actor.start(self.dispatch)
        # If `init` is defined, send it the constructor args.
        if any(m.name == "init" for m in cls.methods):
            actor.send_method("init", ctor_args, sender=None)
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
    print(*[_to_str(a) for a in args], sep="")
    sys.stdout.flush()
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
    from abcl_ai import call_claude
    if not args:
        raise ValueError("ai_call(prompt): expected 1 string argument")
    return call_claude(_to_str(args[0]))


def _b_ai_call_with_system(args, frame, interp):
    from abcl_ai import call_claude
    if len(args) < 2:
        raise ValueError("ai_call_with_system(system, prompt): expected 2 string arguments")
    return call_claude(_to_str(args[1]), system=_to_str(args[0]))


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
    # AI integration (Anthropic Claude)
    "ai_call":             _b_ai_call,
    "ai_call_with_system": _b_ai_call_with_system,
}
