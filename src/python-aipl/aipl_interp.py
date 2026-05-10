"""Tree-walking interpreter for AIPL Python implementation.

Top-level statements run on the main thread.  Each `new C(...)` spawns
an actor, which has its own worker thread and processes incoming
messages via Interpreter.dispatch().
"""

import io
import math
import sys
import threading
import time
from typing import Optional

from aipl_ast import (
    Program, ClassDecl, MethodDecl, FunctionDecl, GlobalStmt,
    VarDecl, VarNew, Assign, IndexAssign, FieldAssign, Send, CallStmt,
    If, While, Become, Block, Return,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, New, CallExpr,
    ArrayLit, IndexExpr, ArraySized, RecordLit, FieldAccess, TupleLit,
    NowCall, FutureCall,
)
from aipl_runtime import Actor, Future, Scheduler


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
    """Raised by `return expr;` inside a user-defined function. Caught by
    the function-call dispatcher to materialise the return value."""
    def __init__(self, value=None):
        super().__init__()
        self.value = value


class FunctionRef:
    """A first-class handle for a user-defined function. Returned by Var
    lookup when the name resolves to a function, and accepted by typeof.
    Records observed call signatures so typeof can surface a trace-based
    type after the function has been called at least once."""
    def __init__(self, decl: 'FunctionDecl', class_owner_name: str = "<top>"):
        self.decl = decl
        self.owner = class_owner_name
        # List of (param_types_tuple, return_type) observations.
        self.observations: list[tuple[tuple, str]] = []

    def record(self, args, ret_value) -> None:
        param_t = tuple(_infer_type(a) for a in args)
        ret_t = _infer_type(ret_value)
        sig = (param_t, ret_t)
        # Keep the list short — repeats add no information.
        if sig not in self.observations:
            self.observations.append(sig)

    def signature(self) -> str:
        # Pull static annotations off the FunctionDecl when available.
        anns = getattr(self.decl, "param_annotations", None) or [None] * len(self.decl.params)
        ret_anno = getattr(self.decl, "return_annotation", None)
        n = len(self.decl.params)
        per_slot_types: list[set[str]] = [set() for _ in range(n)]
        ret_types: set[str] = set()
        # Seed from static annotations.
        for i, a in enumerate(anns):
            if a:
                per_slot_types[i].add(a)
        if ret_anno:
            ret_types.add(ret_anno)
        # Refine with traced observations.
        for ptypes, rtype in self.observations:
            for i, t in enumerate(ptypes[:n]):
                per_slot_types[i].add(t)
            ret_types.add(rtype)
        slot_strs = []
        for name, types in zip(self.decl.params, per_slot_types):
            ts = " | ".join(sorted(types)) if types else "?"
            slot_strs.append(f"{name}:{ts}")
        ret_str = " | ".join(sorted(ret_types)) if ret_types else "?"
        return f"function({', '.join(slot_strs)}) -> {ret_str}"


class BuiltinRef:
    """First-class handle for a runtime builtin. Var lookup of a builtin
    name returns one of these so `typeof(name)` surfaces a signature."""
    def __init__(self, name: str):
        self.name = name

    def signature(self) -> str:
        return BUILTIN_SIGNATURES.get(
            self.name, f"function {self.name}(...) -> any"
        )


# Curated static signatures for builtins. Used by typeof on a BuiltinRef.
# `[provider]` denotes an optional first arg; `+` after a param means
# variadic (one-or-more); `=value` is a default. These are documentation
# strings, not strictly machine-checkable.
BUILTIN_SIGNATURES: "dict[str, str]" = {
    # I/O — text
    "print":          "function(args:any+) -> unit",
    "println":        "function(args:any+) -> unit",
    "read_file":      "function(path:string) -> string",
    "write_file":     "function(path:string, content:string) -> int",
    "append_file":    "function(path:string, content:string) -> int",
    "file_exists":    "function(path:string) -> int",
    "env_get":        "function(name:string [, default:string]) -> string",
    # I/O — binary
    "read_bytes":     "function(path:string) -> array[int]",
    "write_bytes":    "function(path:string, bytes:array[int]) -> int",
    "append_bytes":   "function(path:string, bytes:array[int]) -> int",
    # Filesystem / paths
    "list_dir":       "function(path:string) -> array[string]",
    "is_dir":         "function(path:string) -> int",
    "is_file":        "function(path:string) -> int",
    "mkdir":          "function(path:string) -> int",
    "rm_file":        "function(path:string) -> int",
    "path_join":      "function(parts:string+) -> string",
    "path_basename":  "function(path:string) -> string",
    "path_dirname":   "function(path:string) -> string",
    "basename":       "function(path:string) -> string",
    "dirname":        "function(path:string) -> string",
    "cwd":            "function() -> string",
    # Time / random
    "now_ms":         "function() -> int",
    "now_s":          "function() -> float",
    "wait":           "function(ms:int) -> unit",
    "sleep":          "function(seconds:float) -> unit",
    "random":         "function([n:int [, hi:int]]) -> int | float",
    # Strings
    "str":            "function(any) -> string",
    "str_len":        "function(s:string) -> int",
    "str_sub":        "function(s:string, start:int [, end:int]) -> string",
    "str_contains":   "function(s:string, needle:string) -> bool",
    "str_index":      "function(s:string, needle:string) -> int",
    "str_lower":      "function(s:string) -> string",
    "str_upper":      "function(s:string) -> string",
    "str_trim":       "function(s:string) -> string",
    "str_replace":    "function(s:string, old:string, new:string) -> string",
    "str_starts_with":"function(s:string, prefix:string) -> bool",
    "str_ends_with":  "function(s:string, suffix:string) -> bool",
    # Math
    "cos":            "function(x:float) -> float",
    "sin":            "function(x:float) -> float",
    "sqrt":           "function(x:float) -> float",
    "abs":            "function(x:int|float) -> int|float",
    "max":            "function(int|float+) -> int|float",
    "min":            "function(int|float+) -> int|float",
    # Arrays
    "array_len":      "function(arr:array|tuple) -> int",
    "array_get":      "function(arr:array|tuple, i:int) -> any",
    "array_set":      "function(arr:array, i:int, v:any) -> any",
    "array_push":     "function(arr:array, v:any) -> unit",
    "array_concat":   "function(a:array, b:array) -> array",
    "array_join":     "function(arr:array[string], sep:string) -> string",
    # Actor / future
    "reply":          "function(value:any) -> unit",
    "await":          "function(f:future) -> any",
    "future_done":    "function(f:future) -> bool",
    "become":         "function(class_name:string [, args+]) -> unit",   # (also a stmt)
    # Classes / functions / typeof — meta
    "typeof":         "function(value:any) -> string",
    "type_check":     "function() -> array[string]",
    "compile":        "function(source:string) -> int",
    "spawn":          "function(class_name:string [, args+]) -> actor",
    "add_method":     "function(target:string|actor, source:string) -> int",
    "remove_method":  "function(target:string|actor, name:string) -> int",
    "methods_of":     "function(target:string|actor) -> array[string]",
    "actors":         "function() -> array[string]",
    "inspect":        "function(actor) -> record",
    "inspect_all":    "function() -> array[record]",
    # AI calls — provider override + multimodal
    "ai_call":                       "function([provider:int|string,] prompt:string) -> string",
    "ai_call_with_system":           "function([provider,] system:string, prompt:string) -> string",
    "ai_call_priority":              "function([provider,] prio:float, prompt:string) -> string",
    "ai_call_priority_with_system":  "function([provider,] prio:float, system:string, prompt:string) -> string",
    "ai_call_retry":                 "function(max_attempts:int, prompt:string) -> string",
    "ai_call_retry_with_system":     "function(max_attempts:int, system:string, prompt:string) -> string",
    "ai_call_image":                 "function([provider,] prompt:string, image+) -> string",
    "ai_call_image_with_system":     "function([provider,] system:string, prompt:string, image+) -> string",
    "ai_stream":                     "function(prompt:string) -> string",
    "ai_stream_with_system":         "function(system:string, prompt:string) -> string",
    "ai_usage":                      "function() -> string",
    "ai_remaining":                  "function() -> int",
    "ai_cost":                       "function() -> float",
    # CSP-style channels (Phase 13)
    "channel":           "function(capacity:int [, element_type:string]) -> channel",
    "channel_send":      "function(ch:channel, value:any) -> int",
    "channel_recv":      "function(ch:channel [, timeout_ms:int]) -> any",
    "channel_try_recv":  "function(ch:channel) -> tuple(bool, any)",
    "channel_close":     "function(ch:channel) -> int",
    "channel_size":      "function(ch:channel) -> int",
    "select_recv":       "function(chs:array[channel] [, timeout_ms:int]) -> tuple(int, any)",
    # Image ops (Pillow-backed)
    "image_load":      "function(path:string) -> image",
    "image_save":      "function(image, path:string) -> int",
    "image_create":    "function(w:int, h:int, r:int, g:int, b:int [, a:int=255]) -> image",
    "image_pixel":     "function(image, x:int, y:int) -> tuple(int, int, int, int)",
    "image_set_pixel": "function(image, x:int, y:int, r:int, g:int, b:int [, a:int=255]) -> int",
    "image_size":      "function(image) -> tuple(int, int)",
    # JSON
    "json_parse":      "function(text:string) -> any",
    "json_stringify":  "function(value:any [, indent:int]) -> string",
    # Distributed
    "web_listen":      "function(port:int) -> unit",
    "web_expose":      "function(name:string, actor) -> unit",
    "remote_call":     "function(host_port:string, actor:string, method:string, args+) -> unit",
    "remote_now":      "function(host_port:string, actor:string, method:string, args+) -> any",
    "remote_future":   "function(host_port:string, actor:string, method:string, args+) -> future",
    "serve_forever":   "function() -> unit",
    "save_state":      "function() -> unit",
}


_AI_ACTOR_PREAMBLE = """
// Auto-spawned global AI actor. Wraps the ai_call_* builtins so callers
// can use the actor send / now / future protocols uniformly:
//   var r = now AI.ask("hello");
//   var f = future AI.ask_p(2, "long question");
//   var ans = await(f);
//
// (`call` is a reserved keyword in AIPL — used for `call f(args);`
// statement syntax — so the AI methods are named `ask`/`see` instead.)
class AI {
  // Text — auto provider.
  method ask(prompt) {
    reply(ai_call(prompt));
  }
  // Text — explicit provider (1=Gemini, 2=Anthropic, 3=OpenAI).
  method ask_p(provider, prompt) {
    reply(ai_call(provider, prompt));
  }
  // Text + system prompt.
  method ask_sys(system, prompt) {
    reply(ai_call_with_system(system, prompt));
  }
  method ask_sys_p(provider, system, prompt) {
    reply(ai_call_with_system(provider, system, prompt));
  }
  // Image input (multimodal).
  method see(prompt, image) {
    reply(ai_call_image(prompt, image));
  }
  method see_p(provider, prompt, image) {
    reply(ai_call_image(provider, prompt, image));
  }
  method see_sys(system, prompt, image) {
    reply(ai_call_image_with_system(system, prompt, image));
  }
  method see_sys_p(provider, system, prompt, image) {
    reply(ai_call_image_with_system(provider, system, prompt, image));
  }
  // Monitoring.
  method usage()     { reply(ai_usage()); }
  method cost()      { reply(ai_cost()); }
  method remaining() { reply(ai_remaining()); }
}

var AI = new AI();
"""


class Interpreter:
    def __init__(self, program: Program):
        self.program = program
        self.classes: dict = {}      # name -> ClassDecl
        self.functions: dict = {}    # name -> FunctionDecl  (top-level user functions)
        self.globals: dict = {}      # global name -> value (typically actor refs)
        self._function_refs: dict = {}   # id(FunctionDecl) -> FunctionRef (for typeof)
        self.scheduler = Scheduler()
        self._global_lock = threading.Lock()
        self._actor_counter = 0
        # Optional persisted-fields + pending-mailbox snapshot loaded
        # once at startup; replay happens per-actor during spawn.
        try:
            from aipl_state import load_snapshot, load_pending
            self._state_snapshot = load_snapshot()
            self._pending_snapshot = load_pending()
        except Exception:
            self._state_snapshot = {}
            self._pending_snapshot = {}
        # Inject the default AI actor preamble (auto-spawn at run() time
        # via _preamble_globals; class registration happens here so user
        # code can reference AI methods at parse time).
        self._preamble_globals: list = []
        try:
            from aipl_parser import parse as _parse_aipl_src
            preamble = _parse_aipl_src(_AI_ACTOR_PREAMBLE)
            for d in preamble.decls:
                if isinstance(d, ClassDecl) and d.name not in (program_classes := {
                    pc.name for pc in program.decls if isinstance(pc, ClassDecl)
                }):
                    self.classes[d.name] = d
                elif isinstance(d, FunctionDecl) and d.name not in (program_functions := {
                    pf.name for pf in program.decls if isinstance(pf, FunctionDecl)
                }):
                    self.functions[d.name] = d
                elif isinstance(d, GlobalStmt):
                    self._preamble_globals.append(d.stmt)
        except Exception as e:
            print(f"[AI preamble] parse error: {e}", flush=True)
        # User decls win on name conflicts (these come AFTER the preamble).
        for d in program.decls:
            if isinstance(d, ClassDecl):
                self.classes[d.name] = d
            elif isinstance(d, FunctionDecl):
                self.functions[d.name] = d

    # ------------------------------------------------------------------
    # Entry point

    def run(self, idle_ms: int = 120, timeout_s: float = 2.0):
        # Top-level runs in a synthetic frame with no actor.
        frame = Frame(actor=None, sender=None)
        # Spawn default actors (AI, etc.) before user code runs so the
        # global symbols are reachable from the user's first statement.
        # User code that defines its own `AI` will overwrite this.
        for stmt in getattr(self, "_preamble_globals", []):
            try:
                self.exec_stmt(stmt, frame)
            except Exception as e:
                print(f"[AI preamble exec] {e}", flush=True)
        for d in self.program.decls:
            if isinstance(d, GlobalStmt):
                self.exec_stmt(d.stmt, frame)
        # Make every globally-scoped actor reachable by name to remote
        # senders, matching OCaml's "actor_exists" behaviour.
        try:
            from aipl_remote import set_actor_lookup
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
            from aipl_remote import is_gateway_running
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
            from aipl_state import save_snapshot
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
        # Per-actor instance methods (added via add_method on a specific actor)
        # win over class-level methods so a single instance can be patched
        # without affecting siblings.
        method = None
        inst_methods = getattr(actor, "_instance_methods", None)
        if inst_methods and method_name in inst_methods:
            method = inst_methods[method_name]
        if method is None:
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
        try:
            self.exec_block(method.body, frame)
        except ReturnSignal as r:
            # `return value;` inside a method behaves like reply(value).
            if reply_future is not None:
                reply_future.set(r.value)
                reply_future = None    # don't override below with None
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
        elif kind is IndexAssign:
            arr = frame.lookup(s.name, self.globals)
            v = self.eval_expr(s.expr, frame)
            # Walk all but the last index to descend; assign at the leaf.
            try:
                for ix in s.idxs[:-1]:
                    idx = self.eval_expr(ix, frame)
                    arr = arr[int(idx)]
                final = int(self.eval_expr(s.idxs[-1], frame))
                arr[final] = v
            except (IndexError, TypeError, ValueError) as e:
                print(f"[index_assign] {s.name}[...] failed: {e}", flush=True)
        elif kind is FieldAssign:
            rec = frame.lookup(s.name, self.globals)
            v = self.eval_expr(s.expr, frame)
            try:
                # Walk all but the last attr; assign at the leaf.
                for a in s.attrs[:-1]:
                    rec = rec[a]
                rec[s.attrs[-1]] = v
            except (KeyError, TypeError) as e:
                print(f"[field_assign] {s.name}.{'.'.join(s.attrs)} failed: {e}",
                      flush=True)
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
        elif kind is Return:
            v = self.eval_expr(s.expr, frame) if s.expr is not None else None
            raise ReturnSignal(v)
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
        if kind is Var:
            # Standard lookup, but if the name resolves to a user function
            # (top-level or in-class) and isn't shadowed locally, return a
            # FunctionRef so typeof / printing surface a function value.
            try:
                return frame.lookup(e.name, self.globals)
            except (NameError, KeyError):
                pass
            if frame.actor is not None and frame.actor.cls is not None:
                for fd in getattr(frame.actor.cls, "functions", []):
                    if fd.name == e.name:
                        return self._function_refs.setdefault(id(fd), FunctionRef(fd, frame.actor.cls.name))
            fd = self.functions.get(e.name)
            if fd is not None:
                return self._function_refs.setdefault(id(fd), FunctionRef(fd))
            # Fall through to runtime builtins so `typeof(read_bytes)` etc.
            # surface the static signature.
            if e.name in _BUILTINS:
                return BuiltinRef(e.name)
            return frame.lookup(e.name, self.globals)   # re-raise default error
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
        if kind is IndexExpr:
            arr = frame.lookup(e.name, self.globals)
            try:
                for ix in e.idxs:
                    idx = self.eval_expr(ix, frame)
                    arr = arr[int(idx)]
                return arr
            except (IndexError, TypeError, ValueError):
                return None
        if kind is ArraySized:
            sizes = [int(self.eval_expr(s, frame)) for s in e.sizes]
            init_value = self.eval_expr(e.init, frame) if e.init is not None else 0
            return _build_nested_array(sizes, init_value)
        if kind is RecordLit:
            return {k: self.eval_expr(v, frame) for k, v in e.fields}
        if kind is TupleLit:
            return tuple(self.eval_expr(it, frame) for it in e.items)
        if kind is FieldAccess:
            rec = frame.lookup(e.name, self.globals)
            try:
                for a in e.attrs:
                    rec = rec[a]
                return rec
            except (KeyError, TypeError):
                return None
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
        # Resolution order: builtins -> in-class user functions (if in actor
        # context) -> top-level user functions.
        fn = _BUILTINS.get(name)
        if fn is not None:
            return fn(args, frame, self)
        # In-class function (visible inside that actor's methods, unqualified).
        # In-class functions inherit the caller's actor context so they can
        # see fields and call sibling in-class functions unqualified.
        if frame.actor is not None and frame.actor.cls is not None:
            for f in getattr(frame.actor.cls, "functions", []):
                if f.name == name:
                    return self._call_user_function(f, args, inherit_actor=frame.actor)
        # Top-level user function (no actor context).
        f = self.functions.get(name)
        if f is not None:
            return self._call_user_function(f, args, inherit_actor=None)
        if returning:
            raise NameError(f"unknown function: {name}")
        print(f"[call] unknown builtin: {name}")
        return None

    def _call_user_function(self, decl, args, inherit_actor=None):
        """Invoke a user-defined function. If `inherit_actor` is set, the
        function's frame sees that actor's fields and in-class siblings; this
        is used for in-class function calls. Top-level functions get None."""
        f = Frame(actor=inherit_actor, sender=None)
        for i, p in enumerate(decl.params):
            f.locals[p] = args[i] if i < len(args) else None
        try:
            self.exec_block(decl.body, f)
        except ReturnSignal as r:
            v = r.value
            self._record_function_call(decl, args, v)
            return v
        # Fell off end without explicit return.
        self._record_function_call(decl, args, None)
        return None

    def _record_function_call(self, decl, args, ret_value):
        """Update the FunctionRef trace for typeof inference."""
        # Build a stable per-decl FunctionRef cache so multiple Var lookups
        # share the same observation history.
        ref = self._function_refs.setdefault(id(decl), FunctionRef(decl))
        ref.record(args, ret_value)


# ----------------------------------------------------------------------
# Helpers

def _build_nested_array(sizes: list, init_value):
    """Recursively build an N-D array from its size list. Each cell holds
    the same `init_value` (cheap to share for scalars; for lists the user
    gets shared references — usually intentional for matrix initialisers
    where the inner dim was meant to be its own dimension)."""
    if not sizes:
        return init_value
    n = max(0, int(sizes[0]))
    if len(sizes) == 1:
        return [init_value for _ in range(n)]
    return [_build_nested_array(sizes[1:], init_value) for _ in range(n)]


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
        v = f.get()
        # If this future was created via aios_future, record the call into
        # any active protocol / session now that we know the reply value.
        meta = getattr(f, "_aios_meta", None)
        if meta is not None:
            from aipl_aios import record_observation
            alias, method, call_args = meta
            record_observation(alias, method, call_args, v)
        return v
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


_PROVIDER_TOKENS = {"gemini", "anthropic", "claude", "claudecode", "claude-code",
                    "openai", "chatgpt", "gpt", "mock", "auto"}


def _split_provider(args):
    """Many AIPL ai_call_* builtins now accept an optional provider as the
    very first argument (int 1..3 or string 'gemini'/'anthropic'/'openai').
    Strip it off and return (provider_or_None, remaining_args)."""
    if not args:
        return None, args
    a0 = args[0]
    if isinstance(a0, bool):
        return None, args
    if isinstance(a0, int):
        if a0 in (0, 1, 2, 3):
            return ({0: None, 1: 1, 2: 2, 3: 3}[a0], list(args[1:]))
        return None, args
    if isinstance(a0, str) and len(args) >= 2:
        if a0.strip().lower() in _PROVIDER_TOKENS:
            return (a0, list(args[1:]))
    return None, args


def _resolve_images(args, key="images"):
    """Pull image-like values (`_AiplImage` or array[int] from read_bytes
    or a record with 'path'/'bytes') from the *trailing* args. We treat
    args after the prompt as image inputs."""
    out = []
    for a in args:
        if isinstance(a, _AiplImage):
            buf = io.BytesIO()
            a._pil.save(buf, format="PNG")
            out.append({"_pil_bytes": buf.getvalue(), "mime_type": "image/png"})
        elif isinstance(a, (bytes, bytearray)):
            out.append(bytes(a))
        elif isinstance(a, list) and a and all(isinstance(x, int) and 0 <= x <= 255 for x in a):
            out.append(bytes(a))
        elif isinstance(a, dict) and "path" in a:
            out.append({"path": a["path"], "mime_type": a.get("mime_type")})
    return out


def _b_ai_call(args, frame, interp):
    """ai_call([provider,] prompt) — string in, string out. provider
    optional: int 1=gemini 2=anthropic 3=openai or matching string."""
    from aipl_ai import call_ai, _resolve_provider
    provider, rest = _split_provider(args)
    if not rest:
        raise ValueError("ai_call([provider,] prompt): missing prompt")
    return call_ai(_to_str(rest[0]),
                   provider_override=_resolve_provider(provider))


def _b_ai_call_with_system(args, frame, interp):
    """ai_call_with_system([provider,] system, prompt)"""
    from aipl_ai import call_ai, _resolve_provider
    provider, rest = _split_provider(args)
    if len(rest) < 2:
        raise ValueError("ai_call_with_system([provider,] system, prompt)")
    return call_ai(_to_str(rest[1]),
                   system=_to_str(rest[0]),
                   provider_override=_resolve_provider(provider))


def _b_ai_call_priority(args, frame, interp):
    """ai_call_priority([provider,] prio, prompt)"""
    from aipl_ai import call_ai, _resolve_provider
    provider, rest = _split_provider(args)
    if len(rest) < 2:
        raise ValueError("ai_call_priority([provider,] prio, prompt)")
    return call_ai(_to_str(rest[1]),
                   priority=float(rest[0]),
                   provider_override=_resolve_provider(provider))


def _b_ai_call_priority_with_system(args, frame, interp):
    """ai_call_priority_with_system([provider,] prio, system, prompt)"""
    from aipl_ai import call_ai, _resolve_provider
    provider, rest = _split_provider(args)
    if len(rest) < 3:
        raise ValueError(
            "ai_call_priority_with_system([provider,] prio, system, prompt)")
    return call_ai(_to_str(rest[2]),
                   system=_to_str(rest[1]),
                   priority=float(rest[0]),
                   provider_override=_resolve_provider(provider))


def _b_ai_call_image(args, frame, interp):
    """ai_call_image([provider,] prompt, image[, image, ...]) — multimodal.
    Each image can be:
      - an image value (returned by image_load / image_create)
      - an array[int] of bytes (e.g. read_bytes('photo.png'))
      - a record { path: 'p', mime_type: 'image/png' (optional) }
    Output is text."""
    from aipl_ai import call_ai, _resolve_provider
    provider, rest = _split_provider(args)
    if len(rest) < 2:
        raise ValueError("ai_call_image([provider,] prompt, image[, ...])")
    prompt = _to_str(rest[0])
    imgs = _resolve_images(rest[1:])
    return call_ai(prompt, provider_override=_resolve_provider(provider), images=imgs)


def _b_ai_call_image_with_system(args, frame, interp):
    """ai_call_image_with_system([provider,] system, prompt, image[, ...])"""
    from aipl_ai import call_ai, _resolve_provider
    provider, rest = _split_provider(args)
    if len(rest) < 3:
        raise ValueError(
            "ai_call_image_with_system([provider,] system, prompt, image[, ...])")
    system = _to_str(rest[0])
    prompt = _to_str(rest[1])
    imgs = _resolve_images(rest[2:])
    return call_ai(prompt, system=system,
                   provider_override=_resolve_provider(provider),
                   images=imgs)


def _b_ai_usage(args, frame, interp):
    """Returns a one-line usage summary string."""
    from aipl_ai import get_usage
    u = get_usage()
    return (f"calls={u['calls']} in={u['input_tokens']} "
            f"out={u['output_tokens']} total={u['total_tokens']} "
            f"cost=${u['cost_usd']:.6f}")


def _b_ai_remaining(args, frame, interp):
    """Tokens still allowed by ABCL_AI_TOKEN_BUDGET; -1 if no budget."""
    from aipl_ai import get_remaining
    return get_remaining()


def _b_ai_cost(args, frame, interp):
    """Returns running cost in USD as a float."""
    from aipl_ai import get_cost_usd
    return get_cost_usd()


def _b_ai_stream(args, frame, interp):
    """ai_stream(prompt, actor, chunk_method) — start a streaming AI
    response on a background thread.  Each chunk of text is delivered
    as `send actor.chunk_method(chunk)`.  When the stream finishes a
    final marker is sent: `actor.chunk_method("__done__")` (or
    "__error__: ..." on failure)."""
    if len(args) < 3:
        raise ValueError("ai_stream(prompt, actor, chunk_method)")
    prompt = _to_str(args[0])
    actor = args[1]
    method = _to_str(args[2])
    if not isinstance(actor, Actor):
        raise ValueError("ai_stream: 2nd arg must be an actor reference")

    def _runner():
        try:
            from aipl_ai import stream_ai
            for chunk in stream_ai(prompt):
                actor.send_method(method, [chunk], sender=None)
            actor.send_method(method, ["__done__"], sender=None)
        except Exception as e:
            actor.send_method(method, [f"__error__: {e}"], sender=None)

    threading.Thread(target=_runner, daemon=True).start()
    return None


def _b_ai_stream_with_system(args, frame, interp):
    """ai_stream_with_system(system, prompt, actor, chunk_method)."""
    if len(args) < 4:
        raise ValueError("ai_stream_with_system(system, prompt, actor, method)")
    system = _to_str(args[0])
    prompt = _to_str(args[1])
    actor = args[2]
    method = _to_str(args[3])
    if not isinstance(actor, Actor):
        raise ValueError("ai_stream_with_system: 3rd arg must be an actor reference")

    def _runner():
        try:
            from aipl_ai import stream_ai
            for chunk in stream_ai(prompt, system=system):
                actor.send_method(method, [chunk], sender=None)
            actor.send_method(method, ["__done__"], sender=None)
        except Exception as e:
            actor.send_method(method, [f"__error__: {e}"], sender=None)

    threading.Thread(target=_runner, daemon=True).start()
    return None


def _ai_retry_loop(max_attempts: int, do_call):
    """Common retry loop used by ai_call_retry / ai_call_retry_with_system."""
    import random as _rand
    from aipl_ai import _is_retryable
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
    from aipl_ai import call_ai
    if len(args) < 2:
        raise ValueError("ai_call_retry(max_attempts, prompt)")
    max_attempts = int(args[0])
    prompt = _to_str(args[1])
    return _ai_retry_loop(max_attempts, lambda: call_ai(prompt))


def _b_ai_call_retry_with_system(args, frame, interp):
    """ai_call_retry_with_system(max_attempts, system, prompt)"""
    from aipl_ai import call_ai
    if len(args) < 3:
        raise ValueError("ai_call_retry_with_system(max_attempts, system, prompt)")
    max_attempts = int(args[0])
    system = _to_str(args[1])
    prompt = _to_str(args[2])
    return _ai_retry_loop(max_attempts, lambda: call_ai(prompt, system=system))


# ---------------------------------------------------------------------------
# Distributed actor builtins.

def _b_web_listen(args, frame, interp):
    from aipl_remote import start_gateway
    if not args:
        raise ValueError("web_listen(port): expected 1 int argument")
    start_gateway(int(args[0]))
    return None


def _b_web_expose(args, frame, interp):
    """web_expose(name, actor) — register `actor` under `name` so any
    remote `POST /api/json/send` with that to-field is delivered to its
    mailbox."""
    from aipl_remote import expose
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
    POST to a remote AIPL runtime (Python or OCaml).  Wire format
    matches OCaml src/web_gateway.ml."""
    from aipl_remote import remote_send
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
    from aipl_remote import remote_call_sync
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
    from aipl_remote import remote_call_sync
    from aipl_runtime import Future
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


# =====================================================================
# AIOS coordination + protocol traces + typed session protocols.
# Implemented in abcl_aios.py; we just expose the entry points as
# language-level builtins.
# =====================================================================

def _b_aios_register_service(args, frame, interp):
    from aipl_aios import aios_register_service
    if len(args) != 2:
        raise ValueError("aios_register_service(alias, actor)")
    aios_register_service(_to_str(args[0]), _to_str(args[1]))
    return None


def _b_aios_emit(args, frame, interp):
    from aipl_aios import aios_emit
    if len(args) != 1:
        raise ValueError("aios_emit(msg)")
    aios_emit(_to_str(args[0]))
    return None


def _b_aios_services(args, frame, interp):
    from aipl_aios import aios_services_list
    items = aios_services_list()
    return "[" + ", ".join(f"{a}={n}" for (a, n) in items) + "]"


def _b_aios_events(args, frame, interp):
    from aipl_aios import aios_events_list
    return "\n".join(aios_events_list())


def _aios_dispatch(alias_or_actor, method, args, frame, interp):
    """Resolve alias -> actor, send the method synchronously, return Future."""
    from aipl_aios import aios_resolve
    name = aios_resolve(_to_str(alias_or_actor))
    tgt = interp._resolve_actor(name, frame)
    if tgt is None:
        raise RuntimeError(f"aios: actor not found for alias {alias_or_actor!r}")
    fut = Future()
    tgt.send_method(method, args, sender=frame.actor, reply_future=fut)
    return fut


def _b_aios_now(args, frame, interp):
    """aios_now(alias, method, ...args) — sync: send to actor by alias,
    wait for reply, then auto-observe against all active protocols and
    sessions. Returns the reply value."""
    from aipl_aios import record_observation
    if len(args) < 2:
        raise ValueError("aios_now(alias, method, ...args)")
    alias = _to_str(args[0])
    method = _to_str(args[1])
    rest = list(args[2:])
    fut = _aios_dispatch(alias, method, rest, frame, interp)
    reply = fut.get()
    record_observation(alias, method, rest, reply)
    return reply


def _b_aios_future(args, frame, interp):
    """aios_future(alias, method, ...args) — async: send to actor by alias,
    return a Future immediately. The await() builtin will auto-observe the
    call against active protocols/sessions when the reply arrives."""
    if len(args) < 2:
        raise ValueError("aios_future(alias, method, ...args)")
    alias = _to_str(args[0])
    method = _to_str(args[1])
    rest = list(args[2:])
    fut = _aios_dispatch(alias, method, rest, frame, interp)
    # Tag the future so the await() builtin can run record_observation
    # at completion time.
    setattr(fut, "_aios_meta", (alias, method, rest))
    return fut


# ---- protocol_* (order-only traces) ----

def _b_protocol_define(args, frame, interp):
    from aipl_aios import protocol_define
    if len(args) != 2:
        raise ValueError("protocol_define(name, spec)")
    protocol_define(_to_str(args[0]), _to_str(args[1]))
    return None


def _b_protocol_start(args, frame, interp):
    from aipl_aios import protocol_start
    if len(args) != 1:
        raise ValueError("protocol_start(name)")
    return protocol_start(_to_str(args[0]))


def _b_protocol_state(args, frame, interp):
    from aipl_aios import protocol_state
    if len(args) != 1:
        raise ValueError("protocol_state(sid)")
    return protocol_state(_to_str(args[0]))


def _b_protocol_end(args, frame, interp):
    from aipl_aios import protocol_end
    if len(args) != 1:
        raise ValueError("protocol_end(sid)")
    protocol_end(_to_str(args[0]))
    return None


def _b_protocol_events(args, frame, interp):
    from aipl_aios import protocol_events_list
    return "\n".join(protocol_events_list())


# ---- session_* (typed sessions, separate from regular type inference) ----

def _b_session_define(args, frame, interp):
    from aipl_aios import session_define
    if len(args) != 2:
        raise ValueError("session_define(name, spec)")
    session_define(_to_str(args[0]), _to_str(args[1]))
    return None


def _b_session_start(args, frame, interp):
    from aipl_aios import session_start
    if len(args) != 1:
        raise ValueError("session_start(name)")
    return session_start(_to_str(args[0]))


def _b_session_state(args, frame, interp):
    from aipl_aios import session_state
    if len(args) != 1:
        raise ValueError("session_state(sid)")
    return session_state(_to_str(args[0]))


def _b_session_end(args, frame, interp):
    from aipl_aios import session_end
    if len(args) != 1:
        raise ValueError("session_end(sid)")
    session_end(_to_str(args[0]))
    return None


def _b_session_events(args, frame, interp):
    from aipl_aios import session_events_list
    return "\n".join(session_events_list())


def _b_session_check(args, frame, interp):
    """Manual hook for tests / user code that wants to assert a call."""
    from aipl_aios import session_check
    if len(args) < 4:
        raise ValueError("session_check(sid, actor, method, args_array, reply)")
    sid = _to_str(args[0])
    actor = _to_str(args[1])
    method = _to_str(args[2])
    arg_list = args[3] if isinstance(args[3], list) else [args[3]]
    reply = args[4] if len(args) >= 5 else None
    return session_check(sid, actor, method, arg_list, reply)


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
        from aipl_state import save_snapshot
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


# ---------------------------------------------------------------------------
# Binary I/O — for non-text content (images, archives, AI-OS dumps).
#
#   read_bytes(path)             -> array of int 0..255 (empty on error)
#   write_bytes(path, bytes)     -> 1 / 0
#   append_bytes(path, bytes)    -> 1 / 0

def _b_read_bytes(args, frame, interp):
    if not args:
        return []
    try:
        with open(_to_str(args[0]), "rb") as f:
            return list(f.read())
    except OSError:
        return []


def _b_write_bytes(args, frame, interp):
    if len(args) < 2:
        return 0
    data = args[1]
    if not isinstance(data, (list, tuple, bytes, bytearray)):
        return 0
    try:
        payload = bytes(data) if not isinstance(data, (bytes, bytearray)) else data
        with open(_to_str(args[0]), "wb") as f:
            f.write(payload)
        return 1
    except (OSError, ValueError, TypeError):
        return 0


def _b_append_bytes(args, frame, interp):
    if len(args) < 2:
        return 0
    data = args[1]
    if not isinstance(data, (list, tuple, bytes, bytearray)):
        return 0
    try:
        payload = bytes(data) if not isinstance(data, (bytes, bytearray)) else data
        with open(_to_str(args[0]), "ab") as f:
            f.write(payload)
        return 1
    except (OSError, ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Phase 13 — CSP-style channels.
#
#   var ch = channel(capacity);             // capacity 0 = unbounded
#   var ch = channel(capacity, "int");      // typed (advisory)
#   channel_send(ch, value);                // blocks if full
#   var v = channel_recv(ch);               // blocks if empty
#   var pair = channel_try_recv(ch);        // tuple(ok, value)
#   channel_close(ch);
#   var pick = select_recv([ch1, ch2], 100); // tuple(idx, value); idx=-1 timeout
#
# Channels are passed by reference between actors; producers and
# consumers can be on different actor threads. Each channel is backed
# by a thread-safe queue.Queue, so `channel_send` and `channel_recv`
# coordinate cleanly with the existing `now`/`future`/`await` model.

class _AiplChannel:
    """Bounded synchronous channel. Capacity 0 = unbounded (Python's
    queue.Queue(maxsize=0) interprets that as no upper limit). Element
    type is advisory — used by typeof and (later) by the static checker."""
    _counter = 0

    def __init__(self, capacity: int = 0, element_type: Optional[str] = None):
        import queue as _q
        self.capacity = max(0, int(capacity))
        self.element_type = element_type or "any"
        self.q = _q.Queue(maxsize=self.capacity)
        self.closed = False
        type(self)._counter += 1
        self.id = type(self)._counter

    def send(self, v) -> bool:
        if self.closed:
            return False
        self.q.put(v)
        return True

    def recv(self, timeout: Optional[float] = None):
        import queue as _q
        try:
            return self.q.get(timeout=timeout)
        except _q.Empty:
            return None

    def try_recv(self):
        import queue as _q
        try:
            return (True, self.q.get_nowait())
        except _q.Empty:
            return (False, None)

    def __repr__(self):
        return f"<channel#{self.id} cap={self.capacity} type={self.element_type}>"


def _b_channel(args, frame, interp):
    capacity = int(args[0]) if args else 0
    element_type = _to_str(args[1]) if len(args) > 1 else None
    return _AiplChannel(capacity, element_type)


def _b_channel_send(args, frame, interp):
    if len(args) < 2 or not isinstance(args[0], _AiplChannel):
        return 0
    return 1 if args[0].send(args[1]) else 0


def _b_channel_recv(args, frame, interp):
    if not args or not isinstance(args[0], _AiplChannel):
        return None
    timeout = float(args[1]) / 1000.0 if len(args) > 1 else None
    return args[0].recv(timeout=timeout)


def _b_channel_try_recv(args, frame, interp):
    if not args or not isinstance(args[0], _AiplChannel):
        return (False, None)
    return args[0].try_recv()


def _b_channel_close(args, frame, interp):
    if not args or not isinstance(args[0], _AiplChannel):
        return 0
    args[0].closed = True
    return 1


def _b_channel_size(args, frame, interp):
    if not args or not isinstance(args[0], _AiplChannel):
        return 0
    return args[0].q.qsize()


def _b_select_recv(args, frame, interp):
    """select_recv(channels, timeout_ms=None) — wait for the first ready
    channel and return (idx, value). On timeout returns (-1, None)."""
    import time as _time
    if not args or not isinstance(args[0], list):
        return (-1, None)
    chs = args[0]
    timeout_ms = int(args[1]) if len(args) > 1 else None
    deadline = (_time.monotonic() + timeout_ms / 1000.0) if timeout_ms is not None else None
    while True:
        for i, ch in enumerate(chs):
            if not isinstance(ch, _AiplChannel):
                continue
            ok, v = ch.try_recv()
            if ok:
                return (i, v)
        if deadline is not None and _time.monotonic() >= deadline:
            return (-1, None)
        _time.sleep(0.001)


# ---------------------------------------------------------------------------
# Image I/O — wraps Pillow. Images are exposed as a small record-like
# wrapper carrying width/height/mode + the underlying PIL image.

class _AiplImage(dict):
    """Image value: behaves like a record (.width / .height / .mode visible
    via field access) but carries a PIL image as ._pil for native ops.
    typeof reports `image(WxH, MODE)`."""
    def __init__(self, pil_img):
        super().__init__()
        self["width"] = pil_img.width
        self["height"] = pil_img.height
        self["mode"] = pil_img.mode
        self._pil = pil_img

    def _refresh(self):
        self["width"] = self._pil.width
        self["height"] = self._pil.height
        self["mode"] = self._pil.mode


def _b_image_load(args, frame, interp):
    if not args:
        return None
    try:
        from PIL import Image as _PILImage
        img = _PILImage.open(_to_str(args[0])).convert("RGBA")
        return _AiplImage(img)
    except Exception as e:
        print(f"[image_load] {e}", flush=True)
        return None


def _b_image_save(args, frame, interp):
    if len(args) < 2:
        return 0
    img, path = args[0], _to_str(args[1])
    if not isinstance(img, _AiplImage):
        return 0
    try:
        img._pil.save(path)
        return 1
    except Exception as e:
        print(f"[image_save] {e}", flush=True)
        return 0


def _b_image_create(args, frame, interp):
    """image_create(w, h, r, g, b, a=255) -> new RGBA image filled with the
    given color. Defaults to opaque white."""
    if len(args) < 2:
        return None
    try:
        from PIL import Image as _PILImage
        w, h = int(args[0]), int(args[1])
        r = int(args[2]) if len(args) > 2 else 255
        g = int(args[3]) if len(args) > 3 else 255
        b = int(args[4]) if len(args) > 4 else 255
        a = int(args[5]) if len(args) > 5 else 255
        img = _PILImage.new("RGBA", (w, h), (r, g, b, a))
        return _AiplImage(img)
    except Exception as e:
        print(f"[image_create] {e}", flush=True)
        return None


def _b_image_pixel(args, frame, interp):
    if len(args) < 3:
        return (0, 0, 0, 0)
    img = args[0]
    if not isinstance(img, _AiplImage):
        return (0, 0, 0, 0)
    try:
        x, y = int(args[1]), int(args[2])
        return tuple(img._pil.getpixel((x, y)))
    except Exception:
        return (0, 0, 0, 0)


def _b_image_set_pixel(args, frame, interp):
    """image_set_pixel(image, x, y, r, g, b, a=255). Mutates the image."""
    if len(args) < 6:
        return 0
    img = args[0]
    if not isinstance(img, _AiplImage):
        return 0
    try:
        x, y = int(args[1]), int(args[2])
        r, g, b = int(args[3]), int(args[4]), int(args[5])
        a = int(args[6]) if len(args) > 6 else 255
        img._pil.putpixel((x, y), (r, g, b, a))
        return 1
    except Exception as e:
        print(f"[image_set_pixel] {e}", flush=True)
        return 0


def _b_image_size(args, frame, interp):
    if not args or not isinstance(args[0], _AiplImage):
        return (0, 0)
    return (args[0]["width"], args[0]["height"])


# ---------------------------------------------------------------------------
# Filesystem & path helpers — useful for app/website generation.

def _b_list_dir(args, frame, interp):
    import os
    if not args:
        return []
    try:
        return sorted(os.listdir(_to_str(args[0])))
    except OSError:
        return []


def _b_mkdir(args, frame, interp):
    """mkdir(path) — create dirs recursively. Returns 1 if exists/created, 0 on error."""
    import os
    if not args:
        return 0
    try:
        os.makedirs(_to_str(args[0]), exist_ok=True)
        return 1
    except OSError:
        return 0


def _b_path_join(args, frame, interp):
    import os.path
    parts = [_to_str(a) for a in args]
    return os.path.join(*parts) if parts else ""


def _b_path_basename(args, frame, interp):
    import os.path
    return os.path.basename(_to_str(args[0])) if args else ""


def _b_path_dirname(args, frame, interp):
    import os.path
    return os.path.dirname(_to_str(args[0])) if args else ""


# ---------------------------------------------------------------------------
# JSON — convenient for app config / generated data.

def _b_json_parse(args, frame, interp):
    import json as _json
    if not args:
        return None
    try:
        return _json.loads(_to_str(args[0]))
    except Exception:
        return None


def _b_json_stringify(args, frame, interp):
    import json as _json
    if not args:
        return ""
    indent = int(args[1]) if len(args) > 1 else None
    try:
        # tuples → lists for JSON; image wrappers serialise as record-ish.
        return _json.dumps(_to_jsonable(args[0]), ensure_ascii=False, indent=indent)
    except Exception:
        return ""


def _to_jsonable(v):
    if isinstance(v, _AiplImage):
        return {"width": v["width"], "height": v["height"], "mode": v["mode"]}
    if isinstance(v, tuple):
        return [_to_jsonable(x) for x in v]
    if isinstance(v, list):
        return [_to_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _to_jsonable(x) for k, x in v.items()}
    return v

def _b_env_get(args, frame, interp):
    import os as _os
    if not args:
        return ""
    default = _to_str(args[1]) if len(args) >= 2 else ""
    return _os.environ.get(_to_str(args[0]), default)

def _b_now_s(args, frame, interp):
    """Wall-clock seconds since epoch as a float."""
    return time.time()


# ---- Filesystem ------------------------------------------------------------
# All total: bad paths return [] / "" / 0 instead of raising.

def _b_list_dir(args, frame, interp):
    import os as _os
    if not args:
        return []
    try:
        return sorted(_os.listdir(_to_str(args[0])))
    except OSError:
        return []

def _b_is_dir(args, frame, interp):
    import os.path as _op
    return 1 if (args and _op.isdir(_to_str(args[0]))) else 0

def _b_is_file(args, frame, interp):
    import os.path as _op
    return 1 if (args and _op.isfile(_to_str(args[0]))) else 0

def _b_mkdir(args, frame, interp):
    """mkdir(path) — creates the directory + parents.  Returns 1 / 0."""
    import os as _os
    if not args:
        return 0
    try:
        _os.makedirs(_to_str(args[0]), exist_ok=True)
        return 1
    except OSError:
        return 0

def _b_rm_file(args, frame, interp):
    """rm_file(path) — removes a regular file.  Refuses directories."""
    import os as _os
    import os.path as _op
    if not args:
        return 0
    p = _to_str(args[0])
    if _op.isdir(p):
        return 0
    try:
        _os.remove(p)
        return 1
    except OSError:
        return 0

def _b_path_join(args, frame, interp):
    import os.path as _op
    return _op.join(*[_to_str(a) for a in args]) if args else ""

def _b_basename(args, frame, interp):
    import os.path as _op
    return _op.basename(_to_str(args[0])) if args else ""

def _b_dirname(args, frame, interp):
    import os.path as _op
    return _op.dirname(_to_str(args[0])) if args else ""

def _b_cwd(args, frame, interp):
    import os as _os
    try:
        return _os.getcwd()
    except OSError:
        return ""


# ---- Arrays ----------------------------------------------------------------

def _b_array_len(args, frame, interp):
    if not args:
        return 0
    a = args[0]
    return len(a) if isinstance(a, (list, tuple)) else 0

def _b_array_get(args, frame, interp):
    if len(args) < 2:
        return None
    a = args[0]
    i = int(args[1])
    if not isinstance(a, (list, tuple)) or i < 0 or i >= len(a):
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
    from aipl_ast import Program as _Program, ClassDecl as _ClassDecl
    from aipl_parser import parse as _parse

    interp = Interpreter(_Program(decls=[]))
    # Hook actor lookup so an interactive web_listen still routes
    # incoming traffic to actors typed at the REPL.
    try:
        from aipl_remote import set_actor_lookup
        def _lookup(name):
            v = interp.globals.get(name)
            return v if isinstance(v, Actor) else None
        set_actor_lookup(_lookup)
    except Exception:
        pass

    print("AIPL Python REPL — :help for commands, Ctrl-D / :exit to quit",
          flush=True)
    buf = []
    # Persist locals across REPL inputs so `var a = ...` stays bound on
    # the next line.
    _persistent_frame = Frame(actor=None, sender=None)

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
        for d in program.decls:
            try:
                if isinstance(d, _ClassDecl):
                    interp.classes[d.name] = d
                    print(f"[defined] class {d.name}", flush=True)
                else:
                    interp.exec_stmt(d.stmt, _persistent_frame)
            except Exception as e:
                print(f"[error] {e}", flush=True)
                break

    # Let any in-flight messages finish before shutting down so the
    # actor thread's print() output isn't lost on exit.
    interp.scheduler.wait_idle(idle_ms=80, timeout_s=2.0)
    interp.scheduler.shutdown()


# ---------------------------------------------------------------------------
# Dynamic compile / spawn — runtime extensions for self-modifying programs.
#
#   var n = compile("class Foo { method hi() { print(\"hi\"); } }");
#       -> parses the source, registers each `class` declaration into the
#          interpreter's class table, and returns the number of classes
#          newly added (or updated). Top-level statements in the source
#          are executed in a fresh top-level frame, so `var x = new Foo();`
#          inside the compiled string also works.
#
#   var a = spawn("Foo", arg1, arg2);
#       -> instantiates a previously-compiled (or statically-defined) class
#          by string name, calling `init(arg1, arg2)` if defined. Returns
#          the new actor reference, ready to receive messages via send/now/
#          future.
#
# Together these enable factory actors that synthesise new behaviour at
# runtime — typically by receiving a class spec or AI-generated source
# via a message and instantiating it on demand.

def _b_add_method(args, frame, interp):
    """add_method(target, source) — inject method(s) into a class or actor.

    target: a class name string (class-level injection, all instances see it)
            or an actor reference (per-instance override).
    source: a string with one or more `method NAME(params) { ... }` decls.

    Returns the number of methods registered (0 on parse error or unknown
    target). Existing methods with the same name are replaced."""
    if len(args) < 2:
        return 0
    target, source = args[0], args[1]
    if not isinstance(source, str):
        return 0
    # Wrap in a synthetic class so the existing parser accepts it.
    wrapped = f"class _AipllPatchTmp_ {{ {source} }}"
    try:
        from aipl_parser import parse as _parse
        prog = _parse(wrapped)
    except Exception as e:
        print(f"[add_method] parse error: {e}", flush=True)
        return 0
    new_methods = []
    for d in prog.decls:
        if isinstance(d, ClassDecl):
            new_methods.extend(d.methods)
    if not new_methods:
        return 0
    if isinstance(target, str):
        cls = interp.classes.get(target)
        if cls is None:
            print(f"[add_method] unknown class: {target}", flush=True)
            return 0
        for m in new_methods:
            existing = next((i for i, x in enumerate(cls.methods) if x.name == m.name), None)
            if existing is not None:
                cls.methods[existing] = m
            else:
                cls.methods.append(m)
        return len(new_methods)
    if isinstance(target, Actor):
        if not hasattr(target, "_instance_methods"):
            target._instance_methods = {}
        for m in new_methods:
            target._instance_methods[m.name] = m
        return len(new_methods)
    print("[add_method] target must be a class-name string or an actor", flush=True)
    return 0


def _b_remove_method(args, frame, interp):
    """remove_method(target, name) — return the number of methods removed."""
    if len(args) < 2:
        return 0
    target, name = args[0], args[1]
    if not isinstance(name, str):
        return 0
    if isinstance(target, str):
        cls = interp.classes.get(target)
        if cls is None:
            return 0
        before = len(cls.methods)
        cls.methods = [m for m in cls.methods if m.name != name]
        return before - len(cls.methods)
    if isinstance(target, Actor):
        n = 0
        if hasattr(target, "_instance_methods") and name in target._instance_methods:
            del target._instance_methods[name]
            n += 1
        return n
    return 0


def _b_methods_of(args, frame, interp):
    """methods_of(target) -> sorted array of method names. For an actor this
    is the union of class methods + per-instance overrides."""
    if not args:
        return []
    target = args[0]
    if isinstance(target, str):
        cls = interp.classes.get(target)
        if cls is None:
            return []
        return sorted({m.name for m in cls.methods})
    if isinstance(target, Actor):
        names = {m.name for m in target.cls.methods}
        inst = getattr(target, "_instance_methods", None)
        if inst:
            names |= set(inst.keys())
        return sorted(names)
    return []


def _b_type_check(args, frame, interp):
    """type_check() — run the static type checker on the loaded program
    and return an array of issue strings. Empty array means clean."""
    try:
        from aipl_typeck import check as _check
        issues = _check(interp.program, BUILTIN_SIGNATURES)
        return [i.render() for i in issues]
    except Exception as e:
        return [f"[type] checker error: {e}"]


def _b_typeof(args, frame, interp) -> str:
    """Structural type inference. For records, descend recursively to
    surface the shape; for arrays, sample one element if uniform."""
    if not args:
        return "unit"
    return _infer_type(args[0])


def _infer_type(v) -> str:
    if v is None:
        return "unit"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "string"
    if isinstance(v, _AiplChannel):
        cap = "∞" if v.capacity == 0 else str(v.capacity)
        return f"channel[{v.element_type}, cap={cap}]"
    if isinstance(v, _AiplImage):
        # Image is a dict subclass — must check before plain dict.
        return f"image({v['width']}x{v['height']}, {v['mode']})"
    if isinstance(v, dict):
        # Anonymous record. Order is preserved (Python 3.7+ dicts).
        parts = [f"{k}:{_infer_type(val)}" for k, val in v.items()]
        return "record{" + ", ".join(parts) + "}"
    if isinstance(v, tuple):
        # Tuple (組型): positional types, length is part of the type.
        parts = [_infer_type(x) for x in v]
        return "tuple(" + ", ".join(parts) + ")"
    if isinstance(v, list):
        if not v:
            return "array[unit]"
        elem_types = {_infer_type(x) for x in v}
        if len(elem_types) == 1:
            return f"array[{next(iter(elem_types))}]"
        # Mixed: report multiset.
        return "array[" + " | ".join(sorted(elem_types)) + "]"
    if isinstance(v, Actor):
        cls_name = getattr(v.cls, "name", "?")
        # Surface the method set so trace tooling can see runtime injections.
        names = {m.name for m in v.cls.methods}
        inst = getattr(v, "_instance_methods", None)
        if inst:
            names |= set(inst.keys())
        if names:
            method_list = ", ".join(sorted(names))
            return f"actor({cls_name}, methods=[{method_list}])"
        return f"actor({cls_name})"
    if isinstance(v, FunctionRef):
        return v.signature()
    if isinstance(v, BuiltinRef):
        return v.signature()
    if isinstance(v, Future):
        return "future"
    if isinstance(v, _AiplImage):
        return f"image({v['width']}x{v['height']}, {v['mode']})"
    if isinstance(v, (bytes, bytearray)):
        return f"bytes({len(v)})"
    return type(v).__name__


def _b_compile(args, frame, interp):
    if not args or not isinstance(args[0], str):
        return 0
    source = args[0]
    try:
        from aipl_parser import parse as _parse_aipl
        sub_program = _parse_aipl(source)
    except Exception as e:
        print(f"[compile] parse error: {e}", flush=True)
        return 0
    added = 0
    for d in sub_program.decls:
        if isinstance(d, ClassDecl):
            interp.classes[d.name] = d
            added += 1
    # Execute any top-level statements from the compiled source so users
    # can ship `var x = new Foo();` in the same string. Errors don't abort
    # the whole compile — they're reported and the count of registered
    # classes is still returned.
    top_frame = Frame(actor=None, sender=None)
    for d in sub_program.decls:
        if isinstance(d, GlobalStmt):
            try:
                interp.exec_stmt(d.stmt, top_frame)
            except Exception as e:
                print(f"[compile] top-level exec error: {e}", flush=True)
    return added


def _b_spawn(args, frame, interp):
    if not args or not isinstance(args[0], str):
        return None
    cls_name = args[0]
    ctor_args = list(args[1:])
    try:
        return interp.spawn_actor(cls_name, ctor_args)
    except NameError as e:
        print(f"[spawn] {e}", flush=True)
        return None


_BUILTINS = {
    "print":   _b_print,
    "println": _b_print,
    "reply":   _b_reply,
    "wait":    _b_wait,
    # Dynamic class registration + actor instantiation by string name.
    "compile": _b_compile,
    "spawn":   _b_spawn,
    # Structural type inference (records, arrays, scalars, actors).
    "typeof":  _b_typeof,
    # Phase 11 — gradual static type checker.
    "type_check": _b_type_check,
    # Dynamic method injection / removal / inspection.
    "add_method":    _b_add_method,
    "remove_method": _b_remove_method,
    "methods_of":    _b_methods_of,
    # Binary I/O.
    "read_bytes":    _b_read_bytes,
    "write_bytes":   _b_write_bytes,
    "append_bytes":  _b_append_bytes,
    # CSP-style channels (Phase 13).
    "channel":           _b_channel,
    "channel_send":      _b_channel_send,
    "channel_recv":      _b_channel_recv,
    "channel_try_recv":  _b_channel_try_recv,
    "channel_close":     _b_channel_close,
    "channel_size":      _b_channel_size,
    "select_recv":       _b_select_recv,
    # Image read / write / pixel ops (Pillow-backed).
    "image_load":      _b_image_load,
    "image_save":      _b_image_save,
    "image_create":    _b_image_create,
    "image_pixel":     _b_image_pixel,
    "image_set_pixel": _b_image_set_pixel,
    "image_size":      _b_image_size,
    # Directory / path helpers (list_dir/mkdir/path_join already in the
    # filesystem block below; just add the new aliases here).
    "path_basename": _b_path_basename,
    "path_dirname":  _b_path_dirname,
    # JSON.
    "json_parse":     _b_json_parse,
    "json_stringify": _b_json_stringify,
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
    "ai_call_image":                 _b_ai_call_image,
    "ai_call_image_with_system":     _b_ai_call_image_with_system,
    "ai_call_retry":                 _b_ai_call_retry,
    "ai_call_retry_with_system":     _b_ai_call_retry_with_system,
    "ai_stream":                     _b_ai_stream,
    "ai_stream_with_system":         _b_ai_stream_with_system,
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
    # ---- filesystem ----
    "list_dir":                      _b_list_dir,
    "is_dir":                        _b_is_dir,
    "is_file":                       _b_is_file,
    "mkdir":                         _b_mkdir,
    "rm_file":                       _b_rm_file,
    "path_join":                     _b_path_join,
    "basename":                      _b_basename,
    "dirname":                       _b_dirname,
    "cwd":                           _b_cwd,
    # ---- arrays ----
    "array_len":                     _b_array_len,
    "array_get":                     _b_array_get,
    "array_set":                     _b_array_set,
    "array_push":                    _b_array_push,
    "array_concat":                  _b_array_concat,
    "array_join":                    _b_array_join,
    # ---- AIOS coordination ----
    "aios_register_service":         _b_aios_register_service,
    "aios_emit":                     _b_aios_emit,
    "aios_services":                 _b_aios_services,
    "aios_events":                   _b_aios_events,
    "aios_now":                      _b_aios_now,
    "aios_future":                   _b_aios_future,
    # ---- Protocol traces (order-only) ----
    "protocol_define":               _b_protocol_define,
    "protocol_start":                _b_protocol_start,
    "protocol_state":                _b_protocol_state,
    "protocol_end":                  _b_protocol_end,
    "protocol_events":               _b_protocol_events,
    # ---- Typed session protocols (separate from regular type inference) ----
    "session_define":                _b_session_define,
    "session_start":                 _b_session_start,
    "session_state":                 _b_session_state,
    "session_end":                   _b_session_end,
    "session_events":                _b_session_events,
    "session_check":                 _b_session_check,
}
