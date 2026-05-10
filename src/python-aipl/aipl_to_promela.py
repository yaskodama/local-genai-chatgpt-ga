"""AIPL → Promela / SPIN exporter.

Translates an .abcl actor program (the same focused subset
aipl_modelcheck_load and aipl_to_tla accept) into a Promela (.pml)
specification, suitable for verification with SPIN.

Output:
    out_dir/<Module>.pml    Promela source (proctypes + LTL)

Run SPIN manually:
    bash aipl_spin.sh out_promela/<Module>.pml

Architecture:
    AIPL classes        →  Promela proctypes (one per class)
    Actor instances     →  numbered byte indices per class (0..N-1)
    Class fields        →  per-class state arrays  fork_held[N_FORK], etc.
                           ArrayLit fields           split into _arr + _len
                           StringLit fields          stored as byte index
    Mailboxes           →  one chan array per class, capacity QSIZE
                           message tuple: (mtype, sender, a0, a1, a2)
    Methods             →  guarded branches in proctype's main do/od loop
    LTL property        →  <> all_phils_done   (eventually all phils done)

This translator is *focused on the philosophers pattern* (Fork +
Phil with simple if-else bodies, array_push/array_get/array_len,
and integer/string fields).  General AIPL programs may need extension.
"""

from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aipl_ast import (
    Program, ClassDecl, GlobalStmt,
    VarDecl, VarNew, Assign, Send, CallStmt,
    If, Block, While,
    IntLit, FloatLit, StringLit, Var, Binop, CallExpr, ArrayLit, Neg,
)
from aipl_parser import parse_file


# ===================================================================
# Helpers

def _is_array_field(f) -> bool:
    return isinstance(f.expr, ArrayLit)


def _mtype(name: str) -> str:
    """Prefix method names so they can't collide with Promela keywords
    (`init` and `mtype` itself) or with built-in identifiers."""
    return f"m_{name}"


# ===================================================================
# Expression translation

def _t_expr(e, ctx, fields, name_to_idx, cls_var) -> str:
    cls = type(e).__name__
    if cls == "IntLit":   return str(e.val)
    if cls == "FloatLit": return str(e.val)
    if cls == "StringLit":
        # Resolve string to actor index when possible (constructor
        # args like "f0" referring to a known instance).
        if e.val in name_to_idx:
            _, idx = name_to_idx[e.val]
            return str(idx)
        return f"0 /* str:{e.val} */"
    if cls == "Var":
        if e.name == "self":   return "self_idx"
        if e.name == "sender": return "sender"
        if e.name in ctx["scope"]:
            return ctx["scope"][e.name]
        if e.name in fields:
            f = fields[e.name]
            if _is_array_field(f):
                return f"{cls_var}_{e.name}_arr"
            return f"{cls_var}_{e.name}[self_idx]"
        return e.name
    if cls == "Neg":
        return f"-({_t_expr(e.inner, ctx, fields, name_to_idx, cls_var)})"
    if cls == "Binop":
        l = _t_expr(e.lhs, ctx, fields, name_to_idx, cls_var)
        r = _t_expr(e.rhs, ctx, fields, name_to_idx, cls_var)
        op_map = {
            "==": "==", "!=": "!=", "<": "<", ">": ">",
            "<=": "<=", ">=": ">=",
            "+": "+", "-": "-", "*": "*", "/": "/",
            "&&": "&&", "||": "||",
        }
        op = op_map.get(e.op, e.op)
        return f"({l} {op} {r})"
    if cls == "CallExpr":
        if e.name == "array_len":
            arr = e.args[0]
            if isinstance(arr, Var) and arr.name in fields:
                return f"{cls_var}_{arr.name}_len[self_idx]"
            return "0"
        if e.name == "array_get":
            arr = e.args[0]
            idx = _t_expr(e.args[1], ctx, fields, name_to_idx, cls_var)
            if isinstance(arr, Var) and arr.name in fields:
                return f"{cls_var}_{arr.name}_arr[self_idx*MAX_Q + ({idx})]"
            return "0"
        args = ", ".join(_t_expr(a, ctx, fields, name_to_idx, cls_var)
                         for a in e.args)
        return f"{e.name}({args})"
    if cls == "ArrayLit":
        return "0  /* unsupported: literal array */"
    return "0"


# ===================================================================
# Statement translation

def _resolve_target(s, ctx, fields, name_to_idx, cls_var, target_class):
    """Return (target_chan_name, target_idx_expr)."""
    target_var = target_class.lower()
    if s.target == "self":   return target_var, "self_idx"
    if s.target == "sender": return target_var, "sender"
    if s.target in ctx["scope"]:
        return target_var, ctx["scope"][s.target]
    if s.target in fields:
        return target_var, f"{cls_var}_{s.target}[self_idx]"
    if s.target in name_to_idx:
        _, idx = name_to_idx[s.target]
        return target_var, str(idx)
    return target_var, "0"


def _t_stmt(s, ctx, fields, name_to_idx, cls_var, method_to_class,
            indent: str = "    ") -> list[str]:
    cls = type(s).__name__
    out: list[str] = []

    if cls == "VarDecl":
        rhs = _t_expr(s.expr, ctx, fields, name_to_idx, cls_var)
        ctx["scope"][s.name] = s.name
        out.append(f"{indent}{s.name} = {rhs};")
        return out

    if cls == "Assign":
        rhs = _t_expr(s.expr, ctx, fields, name_to_idx, cls_var)
        if s.name in fields:
            out.append(f"{indent}{cls_var}_{s.name}[self_idx] = {rhs};")
        elif s.name in ctx["scope"]:
            out.append(f"{indent}{s.name} = {rhs};")
        else:
            out.append(f"{indent}{s.name} = {rhs};  /* unknown target */")
        return out

    if cls == "Send":
        target_class = method_to_class.get(s.method, ctx["class_name"])
        target_var, idx_expr = _resolve_target(
            s, ctx, fields, name_to_idx, cls_var, target_class)
        args = [_t_expr(a, ctx, fields, name_to_idx, cls_var) for a in s.args]
        while len(args) < 3:
            args.append("0")
        out.append(
            f"{indent}mb_{target_var}[{idx_expr}] ! "
            f"{_mtype(s.method)}, self_idx, "
            f"{args[0]}, {args[1]}, {args[2]};"
        )
        return out

    if cls == "CallStmt":
        if s.name == "array_push" and len(s.args) >= 2:
            arr = s.args[0]
            val = _t_expr(s.args[1], ctx, fields, name_to_idx, cls_var)
            if isinstance(arr, Var) and arr.name in fields:
                fn = arr.name
                out.append(
                    f"{indent}{cls_var}_{fn}_arr"
                    f"[self_idx*MAX_Q + {cls_var}_{fn}_len[self_idx]] = {val};"
                )
                out.append(f"{indent}{cls_var}_{fn}_len[self_idx]++;")
            return out
        if s.name == "print":
            return out
        return out

    if cls == "If":
        cond = _t_expr(s.cond, ctx, fields, name_to_idx, cls_var)
        then_lines = _expand_block(
            s.then_body, ctx, fields, name_to_idx, cls_var,
            method_to_class, indent + "    ")
        if s.else_body is not None:
            else_lines = _expand_block(
                s.else_body, ctx, fields, name_to_idx, cls_var,
                method_to_class, indent + "    ")
        else:
            else_lines = [f"{indent}    skip;"]
        out.append(f"{indent}if")
        out.append(f"{indent}:: ({cond}) ->")
        out.extend(then_lines)
        out.append(f"{indent}:: else ->")
        out.extend(else_lines)
        out.append(f"{indent}fi;")
        return out

    if cls == "Block":
        for sub in s.stmts:
            out.extend(_t_stmt(sub, ctx, fields, name_to_idx, cls_var,
                               method_to_class, indent))
        return out

    if cls == "Return":
        return out

    if cls == "While":
        out.append(f"{indent}/* unsupported: while */ skip;")
        return out

    return out


def _expand_block(body, ctx, fields, name_to_idx, cls_var,
                  method_to_class, indent: str) -> list[str]:
    if hasattr(body, "stmts"):
        lines: list[str] = []
        for sub in body.stmts:
            lines.extend(_t_stmt(sub, ctx, fields, name_to_idx, cls_var,
                                 method_to_class, indent))
        if not lines:
            lines.append(f"{indent}skip;")
        return lines
    return _t_stmt(body, ctx, fields, name_to_idx, cls_var,
                   method_to_class, indent) or [f"{indent}skip;"]


# ===================================================================
# Locals collection (for proctype-top declarations)

def _collect_locals(stmt) -> set[str]:
    found: set[str] = set()
    def walk(s):
        cls = type(s).__name__
        if cls == "VarDecl":
            found.add(s.name)
            return
        if cls == "Block":
            for sub in s.stmts:
                walk(sub)
            return
        if cls == "If":
            walk(s.then_body)
            if s.else_body is not None:
                walk(s.else_body)
            return
        if cls == "While":
            walk(s.body)
            return
    walk(stmt)
    return found


# ===================================================================
# Module assembly

def _emit_proctype(c: ClassDecl, cls_var: str, fields: dict,
                   name_to_idx: dict, method_to_class: dict) -> str:
    cn = c.name
    lines: list[str] = []
    lines.append(f"proctype {cn}(byte self_idx) {{")
    lines.append(f"    mtype meth; byte sender; byte a0; byte a1; byte a2;")

    all_locals: set[str] = set()
    for m in c.methods:
        all_locals.update(_collect_locals(m.body))
    if all_locals:
        lines.append(f"    byte {', '.join(sorted(all_locals))};")

    lines.append(f"end_{cn}:")
    lines.append(f"    do")
    lines.append(
        f"    :: mb_{cls_var}[self_idx] ? meth, sender, a0, a1, a2 ->")
    lines.append(f"        if")
    for m in c.methods:
        lines.append(f"        :: meth == {_mtype(m.name)} ->")
        ctx = {"class_name": cn, "scope": {}}
        for i, p in enumerate(m.params):
            ctx["scope"][p] = f"a{i}"
        body_lines = _expand_block(m.body, ctx, fields, name_to_idx,
                                   cls_var, method_to_class, "            ")
        lines.extend(body_lines)
    lines.append(f"        :: else -> skip;")
    lines.append(f"        fi;")
    lines.append(f"    od;")
    lines.append(f"}}")
    return "\n".join(lines)


def emit_promela(prog: Program, name: str) -> str:
    classes = [d for d in prog.decls if isinstance(d, ClassDecl)]
    cls_by_name = {c.name: c for c in classes}

    method_to_class: dict[str, str] = {}
    for c in classes:
        for m in c.methods:
            method_to_class[m.name] = c.name

    instances_by_class: dict[str, list[tuple[str, list]]] = \
        {c.name: [] for c in classes}
    name_to_idx: dict[str, tuple[str, int]] = {}
    init_sends: list[tuple[str, str, list]] = []

    for d in prog.decls:
        if isinstance(d, GlobalStmt):
            s = d.stmt
            if isinstance(s, VarNew) and s.cls_name in cls_by_name:
                idx = len(instances_by_class[s.cls_name])
                instances_by_class[s.cls_name].append((s.name, s.args))
                name_to_idx[s.name] = (s.cls_name, idx)
                if any(m.name == "init" for m in cls_by_name[s.cls_name].methods) \
                   and s.args:
                    init_sends.append((s.name, "init", s.args))
            elif isinstance(s, Send):
                init_sends.append((s.target, s.method, s.args))

    cls_var_name = {c.name: c.name.lower() for c in classes}

    all_methods = sorted({m.name for c in classes for m in c.methods})

    out: list[str] = []
    out.append(f"// Generated by aipl_to_promela.py from {name}")
    out.append(f"// Verifies the LTL property: <> all_phils_done.")
    out.append("")
    out.append("#define MAX_Q 8")
    # Mailbox capacity per actor.  Kept tight (state space scales
    # with QSIZE^N_actors); 8 is comfortably above the max in-flight
    # count for the philosopher patterns.
    out.append("#define QSIZE 8")
    out.append("")
    for c in classes:
        N = len(instances_by_class[c.name])
        out.append(f"#define N_{c.name.upper()} {N}")
    out.append("")

    out.append(f"mtype = {{ {', '.join(_mtype(m) for m in all_methods)} }};")
    out.append("")

    for c in classes:
        v = cls_var_name[c.name]
        out.append(
            f"chan mb_{v}[N_{c.name.upper()}] = "
            f"[QSIZE] of {{mtype, byte, byte, byte, byte}};")
    out.append("")

    for c in classes:
        v = cls_var_name[c.name]
        Nm = f"N_{c.name.upper()}"
        for f in c.fields:
            if _is_array_field(f):
                out.append(f"byte {v}_{f.name}_arr[{Nm} * MAX_Q];")
                out.append(f"byte {v}_{f.name}_len[{Nm}];")
            else:
                out.append(f"byte {v}_{f.name}[{Nm}];")
    out.append("")

    for c in classes:
        v = cls_var_name[c.name]
        fields = {f.name: f for f in c.fields}
        out.append(_emit_proctype(c, v, fields, name_to_idx, method_to_class))
        out.append("")

    # init { run …; initial sends }
    out.append("init {")
    out.append("    atomic {")
    for c in classes:
        N = len(instances_by_class[c.name])
        for i in range(N):
            out.append(f"        run {c.name}({i});")
    for tgt, meth, args in init_sends:
        if tgt not in name_to_idx:
            continue
        target_cls, target_idx = name_to_idx[tgt]
        target_var = target_cls.lower()
        global_ctx = {"class_name": "", "scope": {}}
        args_p = [_t_expr(a, global_ctx, {}, name_to_idx, "") for a in args]
        while len(args_p) < 3:
            args_p.append("0")
        out.append(
            f"        mb_{target_var}[{target_idx}] ! "
            f"{_mtype(meth)}, 255, "
            f"{args_p[0]}, {args_p[1]}, {args_p[2]};"
        )
    out.append("    }")
    out.append("}")
    out.append("")

    # LTL: eventually every phil has done = 1.
    if "Phil" in cls_by_name:
        n_phil = len(instances_by_class["Phil"])
        clauses = " && ".join(f"phil_done[{i}] == 1" for i in range(n_phil))
        out.append(f"#define all_phils_done ({clauses})")
        out.append("")
        out.append("ltl progress { <> all_phils_done }")

    return "\n".join(out) + "\n"


# ===================================================================
# CLI

def main():
    ap = argparse.ArgumentParser(
        description="Export an .abcl program to Promela for SPIN")
    ap.add_argument("source")
    ap.add_argument("-o", "--out-dir", default="out_promela")
    ap.add_argument("--name", default=None,
                    help="module name (default: source basename)")
    args = ap.parse_args()

    prog = parse_file(args.source)
    name = args.name or Path(args.source).stem
    pml = emit_promela(prog, name)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pml_path = out_dir / f"{name}.pml"
    pml_path.write_text(pml)
    print(f"wrote {pml_path}")
    print()
    print("Run SPIN:")
    print(f"  bash aipl_spin.sh {pml_path}")


if __name__ == "__main__":
    main()
