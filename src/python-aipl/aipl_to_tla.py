"""AIPL → TLA+ exporter.

Translates an .abcl actor program (the same focused subset
aipl_modelcheck_load accepts) into a TLA+ MODULE + cfg file pair
that TLC can model-check.  Output:

    out_dir/<Module>.tla    the TLA+ specification
    out_dir/<Module>.cfg    the TLC config (CONSTANTS, SPECIFICATION,
                            INVARIANT NoDeadlock)

Run TLC manually:
    java -jar tla2tools.jar out_dir/<Module>.tla -config out_dir/<Module>.cfg

Architecture:
    AIPL classes  → TLA+ records, one per class
    Actor instances (top-level `var x = new C(...)`) →
       TLA+ CONSTANT set per class
    AIPL fields   → fields on the per-class record
    Methods       → action predicates conditioning on (actor, msg.meth)
    Mailboxes     → mailboxes[a] : Seq of message records

This translator is *focused on the philosophers pattern* (Fork +
Phil with simple if-else bodies and array_push/array_get/array_len).
General AIPL programs may need extension.
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aipl_ast import (
    Program, ClassDecl, MethodDecl, GlobalStmt,
    VarDecl, VarNew, Assign, FieldAssign, Send, CallStmt,
    If, While, Block, Return,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, CallExpr, ArrayLit,
)
from aipl_parser import parse_file


# ===================================================================
# Helpers

def _qstr(s: str) -> str:
    """TLA+ string literal."""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _is_str_const(e) -> bool:
    return isinstance(e, StringLit)


def _classify_field(init_expr) -> str:
    """Heuristic: infer a TLA+ comment annotating the field type."""
    if isinstance(init_expr, IntLit):    return "Int"
    if isinstance(init_expr, FloatLit):  return "Real"
    if isinstance(init_expr, StringLit): return "STRING"
    if isinstance(init_expr, ArrayLit):  return "Seq"
    return "ANY"


# ===================================================================
# Expression translation

def _t_expr(e, scope: dict[str, str]) -> str:
    """Translate an AIPL expression to TLA+.  `scope` maps each name
    to the TLA+ accessor expression that yields its value (e.g. a
    field becomes 'forks[self].held', a param becomes the bare name)."""
    cls = type(e).__name__
    if cls == "IntLit":   return str(e.val)
    if cls == "FloatLit": return str(e.val)
    if cls == "StringLit": return _qstr(e.val)
    if cls == "Var":
        if e.name == "self":   return "self"
        if e.name == "sender": return "sender"
        # Parameter / field / local — must be in scope.
        if e.name in scope:    return scope[e.name]
        return e.name
    if cls == "Neg":
        return f"(-({_t_expr(e.inner, scope)}))"
    if cls == "Binop":
        l = _t_expr(e.lhs, scope)
        r = _t_expr(e.rhs, scope)
        op_map = {
            "+": "+", "-": "-", "*": "*", "/": "\\div",
            "==": "=", "!=": "/=",
            "<": "<", ">": ">", "<=": "<=", ">=": ">=",
        }
        op = op_map.get(e.op, e.op)
        return f"({l} {op} {r})"
    if cls == "CallExpr":
        if e.name == "array_len":
            return f"Len({_t_expr(e.args[0], scope)})"
        if e.name == "array_get":
            # TLA+ Sequences are 1-indexed; AIPL is 0-indexed.
            return f"({_t_expr(e.args[0], scope)})[{_t_expr(e.args[1], scope)} + 1]"
        if e.name == "array_empty":
            return "<<>>"
        # Unknown function — emit as-is for human inspection.
        args = ", ".join(_t_expr(a, scope) for a in e.args)
        return f"{e.name}({args})"
    if cls == "ArrayLit":
        items = ", ".join(_t_expr(a, scope) for a in e.items)
        return f"<<{items}>>"
    return "0"


# ===================================================================
# Statement translation

class _MethodCtx:
    """Mutable accumulator while walking a method body."""
    def __init__(self, class_name: str, var_name: str, all_class_vars: list[str]):
        self.class_name = class_name
        self.var_name = var_name           # TLA+ variable for this class
        self.all_class_vars = all_class_vars
        self.field_updates: list[str] = []   # ![<self>].<field> = <expr>
        self.queue_appends: list[tuple[str, str]] = []  # (field, value)
        self.sends: list[str] = []           # mailbox append exprs
        self.lets: list[tuple[str, str]] = []  # local LET bindings
        self.scope: dict[str, str] = {}      # name -> TLA+ accessor


def _walk_path(stmts: list, ctx: _MethodCtx, fields: dict[str, str]) -> str:
    """Walk a sequence of stmts, *flattening* any If into a top-level
    IF-THEN-ELSE whose branches are themselves complete action bodies.

    This avoids the duplicate-prime problem where both the outer
    accumulator AND the inner branch try to set forks'/mailboxes' in
    the same conjunction."""
    if not isinstance(stmts, list):
        stmts = [stmts]

    for i, s in enumerate(stmts):
        cls = type(s).__name__
        if cls == "Block":
            return _walk_path(list(s.stmts) + stmts[i + 1:], ctx, fields)
        if cls == "If":
            # Build cond first.
            sc = _scope_with_fields(ctx.scope, fields, ctx)
            cond = _t_expr(s.cond, sc)

            then_body = list(s.then_body.stmts) if hasattr(s.then_body, "stmts") \
                        else [s.then_body]
            else_body = []
            if s.else_body is not None:
                else_body = list(s.else_body.stmts) if hasattr(s.else_body, "stmts") \
                            else [s.else_body]

            tail = stmts[i + 1:]
            then_action = _walk_path(then_body + tail, _clone_ctx(ctx), fields)
            else_action = _walk_path(else_body + tail, _clone_ctx(ctx), fields)
            return f"IF {cond}\n  THEN {then_action}\n  ELSE {else_action}"
        # Non-If: accumulate its effects via _t_stmt.
        _t_stmt(s, ctx, fields)

    other_cv = [v for v in ctx.all_class_vars if v != ctx.var_name]
    return _emit_action_body(ctx, fields, [], other_cv)


def _clone_ctx(ctx: _MethodCtx) -> _MethodCtx:
    new = _MethodCtx(ctx.class_name, ctx.var_name, ctx.all_class_vars)
    new.field_updates = list(ctx.field_updates)
    new.queue_appends = list(ctx.queue_appends)
    new.sends = list(ctx.sends)
    new.scope = dict(ctx.scope)
    return new


def _t_stmt(s, ctx: _MethodCtx, fields: dict[str, str]) -> list[str]:
    """Translate a single non-control-flow statement.  Returns no
    conjunct fragments for normal stmts (effects accumulate on ctx);
    returns a list with one IF-THEN-ELSE fragment for `If` stmts.
    Used by `_walk_path` only when it hits a stand-alone leaf stmt."""
    cls = type(s).__name__

    if cls == "VarDecl":
        # Inline-substitute: subsequent references to s.name expand
        # to the TLA+ expression directly.  Since AIPL VarDecl in a
        # method body is a one-shot binding, this avoids the need to
        # wrap the whole action in LET … IN.
        rhs = _t_expr(s.expr, _scope_with_fields(ctx.scope, fields, ctx))
        ctx.scope[s.name] = f"({rhs})"
        return []

    if cls == "Assign":
        rhs = _t_expr(s.expr, _scope_with_fields(ctx.scope, fields, ctx))
        if s.name in fields:
            ctx.field_updates.append(f"![self].{s.name} = {rhs}")
            return []
        else:
            # Local rebind: re-bind the substitution.
            ctx.scope[s.name] = f"({rhs})"
            return []

    if cls == "Send":
        if s.target == "self":
            target = "self"
        elif s.target == "sender":
            target = "sender"
        elif s.target in ctx.scope:
            target = ctx.scope[s.target]
        elif s.target in fields:
            target = f"{ctx.var_name}[self].{s.target}"
        else:
            target = _qstr(s.target)   # literal actor name
        args_tla = ", ".join(_t_expr(a, _scope_with_fields(ctx.scope, fields, ctx))
                             for a in s.args)
        msg = (f'[meth |-> {_qstr(s.method)}, '
               f'sender |-> self, '
               f'args |-> <<{args_tla}>>]')
        ctx.sends.append((target, msg))
        return []

    if cls == "CallStmt":
        # array_push(field, value)   → field' .= Append(@, value)
        if s.name == "array_push" and len(s.args) >= 2:
            arr = s.args[0]
            val = s.args[1]
            if isinstance(arr, Var) and arr.name in fields:
                v_tla = _t_expr(val, _scope_with_fields(ctx.scope, fields, ctx))
                ctx.queue_appends.append((arr.name, v_tla))
            return []
        return []

    if cls == "If":
        sc = _scope_with_fields(ctx.scope, fields, ctx)
        cond = _t_expr(s.cond, sc)
        then_action = _emit_branch(s.then_body, ctx, fields)
        else_action = _emit_branch(s.else_body, ctx, fields) if s.else_body else "TRUE"
        # We return a single conjunct that is the IF-THEN-ELSE.
        return [f"IF {cond}\n  THEN {then_action}\n  ELSE {else_action}"]

    if cls == "Block":
        out = []
        for sub in s.stmts:
            out.extend(_t_stmt(sub, ctx, fields))
        return out

    if cls == "Return":
        return []

    if cls == "While":
        # Skip (no while in our philosophers sample).
        return ["TRUE  \\* unsupported: while"]

    return []


def _emit_branch(body, parent_ctx: _MethodCtx, fields: dict[str, str]) -> str:
    """Translate a statement (or Block) inside an if/else branch.
    Each branch is rendered as its own conjunctive snapshot of
    field updates and sends."""
    ctx = _MethodCtx(parent_ctx.class_name, parent_ctx.var_name,
                     parent_ctx.all_class_vars)
    ctx.scope = dict(parent_ctx.scope)
    extra_conjuncts = _t_stmt(body, ctx, fields)
    return _emit_action_body(ctx, fields, extra_conjuncts,
                              other_class_vars=[v for v in parent_ctx.all_class_vars
                                                if v != parent_ctx.var_name])


def _emit_action_body(ctx: _MethodCtx, fields: dict[str, str],
                      extra_conjuncts: list[str],
                      other_class_vars: list[str]) -> str:
    """Combine field updates + queue_appends + sends + extra into a
    single TLA+ expression."""
    parts = []

    # 1) Field updates on this class's variable.
    field_clauses = list(ctx.field_updates)
    for fname, val in ctx.queue_appends:
        # In TLA+ EXCEPT, `@` inside `![self].fname = expr` refers
        # to the OLD value of forks[self].fname.  We must NOT add
        # another `.fname`.
        field_clauses.append(f"![self].{fname} = Append(@, {val})")
    if field_clauses:
        clauses = ", ".join(field_clauses)
        parts.append(f"{ctx.var_name}' = [{ctx.var_name} EXCEPT {clauses}]")
    else:
        parts.append(f"UNCHANGED <<{ctx.var_name}>>")

    # 2) Other class vars unchanged (in this branch).
    if other_class_vars:
        parts.append(f"UNCHANGED <<{', '.join(other_class_vars)}>>")

    # 3) Mailbox transitions: pop head from `self`'s mailbox; append
    # sends.  Multiple appends to the same target must be coalesced
    # into one EXCEPT update (TLA+ keeps only the LAST clause for a
    # given key).  We build a per-target expression chain.
    target_expr: dict[str, str] = {"self": "Tail(mailboxes[self])"}
    for tgt, msg in ctx.sends:
        # Initialise the chain with the source expression for this
        # target — either Tail(...) (if target is `self`) or the raw
        # mailbox lookup (otherwise).
        if tgt not in target_expr:
            if tgt == "self":
                target_expr[tgt] = "Tail(mailboxes[self])"
            else:
                target_expr[tgt] = f"mailboxes[{tgt}]"
        target_expr[tgt] = f"Append({target_expr[tgt]}, {msg})"
    mailbox_excepts = [f"![{k}] = {v}" for k, v in target_expr.items()]
    parts.append("mailboxes' = [mailboxes EXCEPT " + ", ".join(mailbox_excepts) + "]")

    # 4) Extra conjuncts (typically the result of a nested IF-block,
    # but we're calling this as a leaf — should be empty in practice).
    parts.extend(extra_conjuncts)

    body = " /\\ ".join(f"({p})" for p in parts)
    return body


def _scope_with_fields(scope: dict[str, str], fields: dict[str, str],
                       ctx: _MethodCtx) -> dict[str, str]:
    """Augment scope so a bare reference to a field name resolves
    to its TLA+ accessor (e.g. `held` → `forks[self].held`)."""
    out = dict(scope)
    for f in fields:
        if f not in out:
            out[f] = f"{ctx.var_name}[self].{f}"
    return out


# ===================================================================
# TLA+ MODULE assembly

def _module_for_class(cls: ClassDecl, var_name: str,
                      all_class_vars: list[str]) -> tuple[str, str]:
    """Return (action_definitions_text, init_default_record_text).

    For each method m, emit an action predicate of the form

       <Class>_<method>(self, sender, <params>) ==
         /\\ ...

    Plus a record of default field values used by Init.
    """
    fields: dict[str, str] = {}
    field_init_text = []
    for st in cls.fields:
        if hasattr(st, "name") and hasattr(st, "expr"):
            fields[st.name] = _classify_field(st.expr)
            init_val = _t_expr(st.expr, {})
            field_init_text.append(f"{st.name} |-> {init_val}")

    actions = []
    for m in cls.methods:
        ctx = _MethodCtx(cls.name, var_name, all_class_vars)
        for p in m.params:
            ctx.scope[p] = p
        body_str = _walk_path(list(m.body.stmts), ctx, fields)
        params = ", ".join(["self", "sender"] + list(m.params))
        actions.append(
            f"\\* {cls.name}.{m.name}\n"
            f"{cls.name}_{m.name}({params}) ==\n  "
            + body_str + "\n"
        )

    init_record = "[" + ", ".join(field_init_text) + "]"
    return "\n".join(actions), init_record


def emit_module(prog: Program, module_name: str) -> tuple[str, str]:
    """Emit (tla_text, cfg_text) for the program."""
    classes = [d for d in prog.decls if isinstance(d, ClassDecl)]
    cls_by_name = {c.name: c for c in classes}

    # Find top-level VarNew declarations to determine each class's
    # instance set + initial-mailbox sends.
    instances_by_class: dict[str, list[tuple[str, list]]] = {c.name: [] for c in classes}
    init_sends: list[tuple[str, str, list]] = []   # (target, method, args_lits)

    for d in prog.decls:
        if isinstance(d, GlobalStmt):
            s = d.stmt
            if isinstance(s, VarNew) and s.cls_name in cls_by_name:
                ctor_args = [(_t_expr(a, {})) for a in s.args]
                instances_by_class[s.cls_name].append((s.name, ctor_args))
                # Auto-init: if class has init method, queue it.
                cls = cls_by_name[s.cls_name]
                if any(m.name == "init" for m in cls.methods) and ctor_args:
                    init_sends.append((s.name, "init", ctor_args))
            elif isinstance(s, Send):
                args = [_t_expr(a, {}) for a in s.args]
                init_sends.append((s.target, s.method, args))

    # Class variable names: lowercase pluralised class name (Fork → forks).
    cls_var = {c.name: c.name.lower() + "s" for c in classes}
    all_class_vars = list(cls_var.values())

    # Emit action definitions and default field records.
    action_chunks = []
    init_default = {}
    for c in classes:
        actions, init_rec = _module_for_class(c, cls_var[c.name], all_class_vars)
        action_chunks.append(actions)
        init_default[c.name] = init_rec

    # Instance sets — names as TLA+ string constants.
    instance_set_lines = []
    for cname, insts in instances_by_class.items():
        if not insts:
            continue
        names = ", ".join(_qstr(n) for n, _ in insts)
        instance_set_lines.append(f"{cname}Set == {{{names}}}")

    # All actor names.
    instance_set_lines.append(
        "Actors == " + " \\union ".join(f"{c}Set" for c in cls_by_name) +
        ("" if cls_by_name else "{}")
    )

    # Initial actor records (class-vars).
    init_class_vars = []
    for c in classes:
        cname = c.name
        var = cls_var[cname]
        init_class_vars.append(
            f"{var} = [a \\in {cname}Set |-> {init_default[cname]}]"
        )

    init_class_conj = " /\\ ".join(init_class_vars) if init_class_vars else "TRUE"

    # Initial mailboxes.
    if init_sends:
        msg_records = []
        for tgt, meth, args in init_sends:
            args_tla = ", ".join(args)
            msg_records.append(
                f'[a |-> {_qstr(tgt)}, '
                f'msg |-> [meth |-> {_qstr(meth)}, '
                f'sender |-> {_qstr("__main__")}, '
                f'args |-> <<{args_tla}>>]]'
            )
        init_mailbox_lines = (
            "/\\ mailboxes = [a \\in Actors |-> <<>>]\n"
            "/\\ mailboxes' = mailboxes  \\* placeholder\n"
            "\\* initial sends queued explicitly:\n"
            + "\n".join(f"\\*   {m}" for m in msg_records)
        )
    else:
        init_mailbox_lines = "/\\ mailboxes = [a \\in Actors |-> <<>>]"

    # We need to render initial sends as concrete mailbox state at
    # Init time (not a primed transition).  Build it explicitly.
    by_target_init_msgs: dict[str, list[str]] = {}
    for tgt, meth, args in init_sends:
        args_tla = ", ".join(args)
        msg = (f'[meth |-> {_qstr(meth)}, '
               f'sender |-> {_qstr("__main__")}, '
               f'args |-> <<{args_tla}>>]')
        by_target_init_msgs.setdefault(tgt, []).append(msg)

    init_mailbox_clauses = []
    for actor_name, msgs in by_target_init_msgs.items():
        init_mailbox_clauses.append(
            f'{_qstr(actor_name)} :> <<{", ".join(msgs)}>>'
        )

    if init_mailbox_clauses:
        # TLC's @@ is left-biased: keys in the LEFT operand override
        # the right.  Put the explicit sends on the left so they win
        # over the default empty-sequence map.
        init_mb_expr = (
            "(" + " @@ ".join(init_mailbox_clauses) + ")"
            " @@ [a \\in Actors |-> <<>>]"
        )
    else:
        init_mb_expr = "[a \\in Actors |-> <<>>]"

    # Step / Next / NoDeadlock.
    # For each (class, method) pair, dispatch on (a in ClassSet) and
    # (msg.meth = "method").
    dispatch_branches = []
    for c in classes:
        for m in c.methods:
            params_after_seed = m.params
            cond = (f'a \\in {c.name}Set /\\ msg.meth = {_qstr(m.name)}'
                    + (f' /\\ Len(msg.args) = {len(params_after_seed)}'
                       if params_after_seed else ''))
            if params_after_seed:
                # TLA+ LET: each binding is a separate `name == expr`
                # clause separated by spaces (no /\), terminated by IN.
                let_bindings = "\n             ".join(
                    f"{p} == msg.args[{i+1}]"
                    for i, p in enumerate(params_after_seed)
                )
                call_args = ", ".join(["a", "msg.sender"] + list(params_after_seed))
                dispatch_branches.append(
                    f"       \\/ ( {cond}\n"
                    f"            /\\ LET {let_bindings}\n"
                    f"               IN  {c.name}_{m.name}({call_args}) )"
                )
            else:
                call_args = ", ".join(["a", "msg.sender"])
                dispatch_branches.append(
                    f"       \\/ ( {cond}\n"
                    f"            /\\ {c.name}_{m.name}({call_args}) )"
                )

    dispatch = "\n".join(dispatch_branches) if dispatch_branches else "       \\/ FALSE"

    tla = f"""---- MODULE {module_name} ----
EXTENDS Integers, Sequences, FiniteSets, TLC

\\* Actor instance sets (constants from the .abcl)
{chr(10).join(instance_set_lines)}

VARIABLES {", ".join(all_class_vars)}, mailboxes
vars == <<{", ".join(all_class_vars)}, mailboxes>>

\\* ===== Per-method actions =====

{chr(10).join(action_chunks)}

\\* ===== Step / Next =====

StepActor(a) ==
  /\\ Len(mailboxes[a]) > 0
  /\\ LET msg == Head(mailboxes[a])
     IN ( \\/ FALSE
{dispatch}
        )

Next == \\E a \\in Actors : StepActor(a)

\\* ===== Initial state =====

Init ==
  /\\ {init_class_conj}
  /\\ mailboxes = {init_mb_expr}

Spec == Init /\\ [][Next]_vars

\\* ===== Properties =====

\\* Some Phil's done flag is 0 — used by NoDeadlock to distinguish
\\* normal halt from a true stuck state.  Adapt this predicate per
\\* program.
HasUnfinishedPhil == \\E p \\in PhilSet : phils[p].done = 0

NoDeadlock ==
  ~ ((\\A a \\in Actors : Len(mailboxes[a]) = 0) /\\ HasUnfinishedPhil)

====
"""

    # CHECK_DEADLOCK FALSE: TLC's built-in deadlock detection treats
    # any state where Next is disabled as a deadlock — but in our
    # programs that includes the *natural halt* where every Phil has
    # done = 1.  We rely on the explicit NoDeadlock INVARIANT instead.
    cfg = f"""SPECIFICATION Spec
INVARIANT NoDeadlock
CHECK_DEADLOCK FALSE
"""
    return tla, cfg


# ===================================================================
# CLI

def main():
    ap = argparse.ArgumentParser(description="Export an .abcl program to TLA+ for TLC")
    ap.add_argument("source")
    ap.add_argument("-o", "--out-dir", default="out_tla")
    ap.add_argument("--name", default=None,
                    help="module name (default: source basename)")
    args = ap.parse_args()

    prog = parse_file(args.source)
    name = args.name or Path(args.source).stem
    tla, cfg = emit_module(prog, name)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tla_path = out_dir / f"{name}.tla"
    cfg_path = out_dir / f"{name}.cfg"
    tla_path.write_text(tla)
    cfg_path.write_text(cfg)
    print(f"wrote {tla_path}")
    print(f"wrote {cfg_path}")
    print()
    print("Run TLC (download tla2tools.jar from "
          "https://github.com/tlaplus/tlaplus/releases):")
    print(f"  java -jar tla2tools.jar -config {cfg_path} {tla_path}")


if __name__ == "__main__":
    main()
