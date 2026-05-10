"""Load an .abcl program into the bounded model checker.

The runtime AIPL is too large to model-check in full; this loader
covers a *focused subset* sufficient for actor-deadlock analysis:

  Statements: VarDecl, Assign, If, While, Send (named target)
              Block, Return.
  Expressions: IntLit, StringLit, Var, Binop (+ - * / == != < > <= >=)
              CallExpr to a small builtin set:
                  array_push(a, v)   array_get(a, i)   array_len(a)
                  array_empty()      str_eq(a, b)      print(...) (no-op)

Out of scope (silently ignored or treated as no-ops): Now, Future,
Await, Become, FieldAccess, ai_call_*, image_*, file_*.

Top-level globals build the initial World:
  var name = new ClassName(args);    -> world.add(name, ClassName(...))
  send target.method(args);           -> world.send(target, method, *args)

Run:
  python3 aipl_modelcheck_load.py samples-mc/Philosophers.abcl
"""

from __future__ import annotations
import argparse
import os
import sys
from copy import deepcopy
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aipl_ast import (
    ClassDecl, MethodDecl, GlobalStmt,
    VarDecl, VarNew, Assign, IndexAssign, FieldAssign, Send, CallStmt,
    If, While, Block, Return,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, CallExpr, ArrayLit,
)
from aipl_parser import parse_file
from aipl_modelcheck import World, MCActor, ModelChecker


# ===================================================================
# Mini-evaluator over the AIPL subset
# ===================================================================

class _Stop(Exception):
    """Carries a Return value out of a method body."""
    def __init__(self, value): self.value = value


def _eval_expr(e, env: dict, fields: dict, sender: str | None) -> Any:
    cls = type(e).__name__
    if cls == "IntLit":   return e.val
    if cls == "FloatLit": return e.val
    if cls == "StringLit":return e.val
    if cls == "Var":
        if e.name == "sender":
            return sender if sender is not None else ""
        if e.name == "self":
            return "<self>"
        if e.name in env:    return env[e.name]
        if e.name in fields: return fields[e.name]
        return 0
    if cls == "Neg":
        return -_eval_expr(e.inner, env, fields, sender)
    if cls == "Binop":
        l = _eval_expr(e.lhs, env, fields, sender)
        r = _eval_expr(e.rhs, env, fields, sender)
        return _apply_binop(e.op, l, r)
    if cls == "CallExpr":
        return _eval_builtin(e.name, [_eval_expr(a, env, fields, sender) for a in e.args])
    if cls == "ArrayLit":
        return [_eval_expr(a, env, fields, sender) for a in e.items]
    # Unsupported expression — return 0 silently.
    return 0


def _apply_binop(op: str, a: Any, b: Any) -> Any:
    if op == "+":
        if isinstance(a, str) or isinstance(b, str):
            return str(a) + str(b)
        return a + b
    if op == "-":  return a - b
    if op == "*":  return a * b
    if op == "/":
        if b == 0: return 0
        return a // b if isinstance(a, int) and isinstance(b, int) else a / b
    if op == "==": return 1 if a == b else 0
    if op == "!=": return 1 if a != b else 0
    if op == "<":  return 1 if a <  b else 0
    if op == ">":  return 1 if a >  b else 0
    if op == "<=": return 1 if a <= b else 0
    if op == ">=": return 1 if a >= b else 0
    return 0


def _eval_builtin(name: str, args: list) -> Any:
    if name == "array_push":
        if len(args) >= 2:
            args[0].append(args[1])
        return 0
    if name == "array_get":
        if len(args) >= 2 and 0 <= args[1] < len(args[0]):
            return args[0][args[1]]
        return 0
    if name == "array_len":
        return len(args[0]) if args else 0
    if name == "array_empty":
        return []
    if name == "str_eq":
        return 1 if args[0] == args[1] else 0
    if name == "print":
        # silent in model-check (output is not observed)
        return 0
    return 0


def _exec_stmt(s, env: dict, fields: dict, world: "World",
               sender: str | None, self_name: str) -> None:
    cls = type(s).__name__
    if cls == "VarDecl":
        env[s.name] = _eval_expr(s.expr, env, fields, sender)
        return
    if cls == "Assign":
        v = _eval_expr(s.expr, env, fields, sender)
        if s.name in env:
            env[s.name] = v
        else:
            fields[s.name] = v
        return
    if cls == "If":
        if _eval_expr(s.cond, env, fields, sender):
            _exec_stmt(s.then_body, env, fields, world, sender, self_name)
        elif s.else_body is not None:
            _exec_stmt(s.else_body, env, fields, world, sender, self_name)
        return
    if cls == "While":
        guard = 0
        while _eval_expr(s.cond, env, fields, sender):
            guard += 1
            if guard > 1000:
                break  # paranoia — runaway loop in model-check eval
            _exec_stmt(s.body, env, fields, world, sender, self_name)
        return
    if cls == "Block":
        for sub in s.stmts:
            _exec_stmt(sub, env, fields, world, sender, self_name)
        return
    if cls == "Send":
        target = _resolve_target(s.target, env, fields, sender, self_name)
        args = [_eval_expr(a, env, fields, sender) for a in s.args]
        if target:
            world.send(target, s.method, *args, sender=self_name)
        return
    if cls == "CallStmt":
        # builtin / no-op for our subset
        _eval_builtin(s.name, [_eval_expr(a, env, fields, sender) for a in s.args])
        return
    if cls == "Return":
        v = _eval_expr(s.expr, env, fields, sender) if s.expr is not None else None
        raise _Stop(v)
    if cls == "VarNew":
        # nested `var x = new C(...)` inside a method — out of scope.
        return
    # Unknown stmt: silently ignore.


def _resolve_target(name: str, env: dict, fields: dict,
                    sender: str | None, self_name: str) -> str:
    if name == "self":
        return self_name
    if name == "sender":
        return sender if sender is not None else ""
    # Look up in env first, then fields (typical AIPL `var partner = X;`).
    if name in env:
        v = env[name]
        return v if isinstance(v, str) else name
    if name in fields:
        v = fields[name]
        return v if isinstance(v, str) else name
    return name      # treat as actor name literal


# ===================================================================
# Class -> MCActor subclass
# ===================================================================

def _make_actor_class(class_decl: ClassDecl, parser_globals=None):
    """Build a Python subclass of MCActor whose methods dispatch into
    the AIPL method bodies via the mini-evaluator above."""

    class _Loaded(MCActor):
        _src_class = class_decl
        # Pre-compute a list of (field_name, init_expr) so __init__
        # can replay the field initializers.
        _field_inits = [
            (st.name, st.expr) for st in class_decl.fields
            if hasattr(st, "name") and hasattr(st, "expr")
        ]
        _methods = {m.name: m for m in class_decl.methods}

        def __init__(self, *ctor_args):
            # Initialize fields by evaluating their init exprs.
            fields = {}
            for fname, expr in self._field_inits:
                fields[fname] = _eval_expr(expr, {}, fields, None)
            self.__dict__["_fields"] = fields
            # If the class has an `init` method, call it lazily on
            # first message dispatch (matches AIPL's runtime behavior
            # of auto-`init`).  Caller can also drive init manually
            # via world.send(name, "init", *args).
            self.__dict__["_pending_init_args"] = list(ctor_args)

        def __getattr__(self, item):
            # Dynamic method dispatch — install a method that walks
            # the AIPL body when accessed.
            if item.startswith("_"):
                raise AttributeError(item)
            m = type(self)._methods.get(item)
            if m is None:
                raise AttributeError(item)

            def _dispatch(world, sender, *args):
                env = {p: a for p, a in zip(m.params, args)}
                try:
                    _exec_stmt(m.body, env, self._fields, world,
                               sender, self.name)
                except _Stop:
                    pass
            return _dispatch

        def __repr__(self):
            cn = type(self)._src_class.name
            items = sorted((k, v) for k, v in self._fields.items())
            body = ", ".join(f"{k}={v!r}" for k, v in items)
            return f"{cn}({body})"

    _Loaded.__name__ = class_decl.name
    return _Loaded


# ===================================================================
# Entry point — load an .abcl program into a (World init, classes).
# ===================================================================

def load_program(abcl_path: str):
    """Parse `abcl_path` and return (init_fn, classes_dict).

    The returned init_fn builds the initial World by replaying
    top-level VarNew + Send statements.  classes_dict maps class
    name to the dynamically-built MCActor subclass."""
    prog = parse_file(abcl_path)

    classes = {}
    for d in prog.decls:
        if isinstance(d, ClassDecl):
            classes[d.name] = _make_actor_class(d)

    # Top-level statements in order: VarNew (creates an actor) /
    # Send (enqueues an initial message).  Other statements are
    # ignored.
    top_stmts = [d.stmt for d in prog.decls if isinstance(d, GlobalStmt)]

    def init():
        w = World()
        # Snapshot built actors here so we can run `init` via world.send
        # only AFTER all actors are added.
        pending_init = []
        for s in top_stmts:
            if isinstance(s, VarNew):
                cls = classes.get(s.cls_name)
                if cls is None:
                    continue
                ctor_args = [_eval_const(a) for a in s.args]
                actor = cls(*ctor_args)
                w.add(s.name, actor)
                # If the class has an `init` method, queue it now.
                if "init" in cls._methods and ctor_args:
                    w.send(s.name, "init", *ctor_args, sender=s.name)
                pending_init.append(s.name)
            elif isinstance(s, Send):
                args = [_eval_const(a) for a in s.args]
                # `target` may be the literal name of an actor we just
                # added; AIPL also treats top-level vars holding actor
                # references the same way.
                w.send(s.target, s.method, *args, sender="<main>")
        return w
    return init, classes


def _eval_const(expr) -> Any:
    """Top-level args have to be literal constants (Int/Str/etc).
    We evaluate them with empty env/fields."""
    return _eval_expr(expr, {}, {}, None)


# ===================================================================
# CLI

def main():
    ap = argparse.ArgumentParser(description="Load an .abcl program and model-check it")
    ap.add_argument("source")
    ap.add_argument("--depth", type=int, default=2000)
    ap.add_argument("--check", choices=["deadlock"], default="deadlock",
                    help="property to check")
    args = ap.parse_args()

    init, classes = load_program(args.source)
    print(f"[load] classes: {sorted(classes.keys())}")
    mc = ModelChecker(init, depth=args.depth)
    if args.check == "deadlock":
        # Without a per-program is_terminal, we conservatively
        # treat any "all mailboxes empty" as a deadlock signal.
        # User can supply a more specific predicate by importing
        # this module from Python.
        res = mc.check_deadlock_free(is_terminal=lambda s: False)
        print(res.render())
        sys.exit(0 if res.ok else 1)


if __name__ == "__main__":
    main()
