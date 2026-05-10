"""Phase 11 — gradual static type checker for AIPL.

Walks the parsed Program before execution and reports type-mismatches:

  * `var x: int = "hi";`            → flagged (literal string vs int)
  * `function f(a: int) -> int { return "x"; }` → flagged (string vs int)
  * `f("a", "b")` where f expects `(int, int)` → flagged
  * `now actor.method(wrong_type)` validates against the class's method sig
  * `read_file(42)` validates against the builtin signature
  * arity mismatches on user functions and builtins
  * unannotated code is treated as `any` and never flagged (gradual)

Phase 11b extends 11 with: call-site arg-type validation everywhere
(CallExpr / NowCall / FutureCall / Send / CallStmt / VarNew constructor),
better signature parsing for variadic (`+`) and optional (`[..,]`) params,
and method-return-type inference for `now obj.method(...)`."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_TYPEVAR_RE = re.compile(r"\b[A-Z]\b")    # single uppercase letter token


# Phase 12 — capability-based effect system. Each builtin produces zero or
# more side-effect categories. Functions/methods declare their effect set
# via `!{eff1, eff2}`; the static checker propagates effects through call
# chains and flags shortfalls (declared less than required).
BUILTIN_EFFECTS: "dict[str, set]" = {
    # filesystem
    "read_file":    {"fs"},
    "write_file":   {"fs"},
    "append_file":  {"fs"},
    "file_exists":  {"fs"},
    "read_bytes":   {"fs"},
    "write_bytes":  {"fs"},
    "append_bytes": {"fs"},
    "list_dir":     {"fs"},
    "is_dir":       {"fs"},
    "is_file":      {"fs"},
    "mkdir":        {"fs"},
    "rm_file":      {"fs"},
    "image_load":   {"fs"},
    "image_save":   {"fs"},
    # AI / network (LLM calls go over the wire)
    "ai_call":                       {"ai", "net"},
    "ai_call_with_system":           {"ai", "net"},
    "ai_call_priority":              {"ai", "net"},
    "ai_call_priority_with_system":  {"ai", "net"},
    "ai_call_retry":                 {"ai", "net"},
    "ai_call_retry_with_system":     {"ai", "net"},
    "ai_call_image":                 {"ai", "net"},
    "ai_call_image_with_system":     {"ai", "net"},
    "ai_stream":                     {"ai", "net"},
    "ai_stream_with_system":         {"ai", "net"},
    # network only
    "web_listen":     {"net"},
    "web_expose":     {"net"},
    "remote_call":    {"net"},
    "remote_now":     {"net"},
    "remote_future":  {"net"},
    "serve_forever":  {"net"},
    # program mutation (compile / patch / spawn)
    "compile":        {"mut"},
    "spawn":          {"mut"},
    "add_method":     {"mut"},
    "remove_method":  {"mut"},
    "save_state":     {"fs"},
    # Pure: print (output is always allowed for diagnostics), str_*, math,
    # array_*, typeof, methods_of, json_parse / json_stringify, time, etc.
    # Anything not in this dict is considered effect-free.
}


def _typevars_in(t: str) -> set:
    return set(_TYPEVAR_RE.findall(t))


def _substitute(t: str, bindings: dict) -> str:
    """Replace each type variable (\b[A-Z]\b) in `t` with its binding."""
    if not bindings:
        return t
    def _sub(m):
        return bindings.get(m.group(0), m.group(0))
    return _TYPEVAR_RE.sub(_sub, t)

from aipl_ast import (
    Program, ClassDecl, MethodDecl, FunctionDecl, GlobalStmt,
    VarDecl, VarNew, Assign, IndexAssign, FieldAssign, Send, CallStmt,
    If, While, Become, Block, Return,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, New, CallExpr,
    ArrayLit, IndexExpr, ArraySized, RecordLit, FieldAccess, TupleLit,
    NowCall, FutureCall,
)


@dataclass
class TypeIssue:
    where: str
    message: str
    expected: Optional[str] = None
    actual: Optional[str] = None

    def render(self) -> str:
        if self.expected and self.actual:
            return f"[type] {self.where}: {self.message}  (expected {self.expected}, got {self.actual})"
        return f"[type] {self.where}: {self.message}"


# ---------------------------------------------------------------------------
# Signature parsing — Phase 11b distinguishes static / variadic / optional.

@dataclass
class ParamSpec:
    name: str
    type: str
    variadic: bool = False    # trailing `+` (zero-or-more of this type)
    optional: bool = False    # leading `[..,]` first arg


def _split_top(text: str) -> list:
    """Split on top-level commas, respecting nested brackets/parens/braces."""
    parts: list = []
    depth, buf = 0, ""
    for c in text:
        if c in "[({":   depth += 1
        elif c in "])}": depth -= 1
        if c == "," and depth == 0:
            parts.append(buf.strip()); buf = ""
        else:
            buf += c
    if buf.strip():
        parts.append(buf.strip())
    return parts


def _parse_signature(sig: str) -> Optional[list]:
    """Return list[ParamSpec] for `function(...) -> R`. None if malformed."""
    open_p = sig.find("(")
    close_p = sig.rfind(") ->")
    if open_p < 0 or close_p < 0:
        return None
    inside = sig[open_p + 1:close_p].strip()
    if not inside:
        return []
    # Strip a leading "[provider:T,]" or similar optional-first marker:
    # we model it as ParamSpec(optional=True) but otherwise unconstrained.
    optional_first: Optional[ParamSpec] = None
    s = inside
    if s.startswith("["):
        end = s.find("]")
        if end > 0:
            chunk = s[1:end].rstrip(",").strip()
            if ":" in chunk:
                n, _, t = chunk.partition(":")
                optional_first = ParamSpec(n.strip(), t.strip(), optional=True)
            else:
                optional_first = ParamSpec(chunk.strip(), "any", optional=True)
            s = s[end + 1:].lstrip(", ")
    out: list = []
    if optional_first:
        out.append(optional_first)
    for p in _split_top(s):
        is_var = p.endswith("+")
        body = p[:-1] if is_var else p
        if ":" in body:
            n, _, t = body.partition(":")
            out.append(ParamSpec(n.strip(), t.strip(), variadic=is_var))
        else:
            out.append(ParamSpec(body.strip(), "any", variadic=is_var))
    return out


def _return_of(sig: str) -> str:
    arrow = sig.rfind("->")
    return sig[arrow + 2:].strip() if arrow >= 0 else "any"


# ---------------------------------------------------------------------------
# Type compatibility. Gradual: `any` matches anything.

def _stmt_terminates(s) -> bool:
    """Return True if this statement always transfers control out of the
    enclosing function (i.e. ends in `return`). Used by Phase 14 branch
    analysis: branches that terminate don't influence post-if moved state."""
    if isinstance(s, Return):
        return True
    if isinstance(s, Block):
        return any(_stmt_terminates(x) for x in s.stmts)
    if isinstance(s, If):
        if s.else_body is None:
            return False
        return _stmt_terminates(s.then_body) and _stmt_terminates(s.else_body)
    return False


def _strip_linear(t: str) -> tuple:
    """Strip a leading `linear ` modifier and return (is_linear, base_type)."""
    if t.startswith("linear "):
        return True, t[len("linear "):].strip()
    return False, t


def _compatible(expected: str, actual: str) -> bool:
    # Phase 14: linearity is a separate dimension from element type.
    # Strip both sides so `linear int` matches `int` for compat purposes.
    _, expected = _strip_linear(expected)
    _, actual = _strip_linear(actual)
    if expected == "any" or actual == "any":
        return True
    if expected == actual:
        return True
    # Union forms: split on `|` and check intersection.
    if "|" in expected:
        es = {e.strip() for e in expected.split("|")}
        if "any" in es:    return True
        return any(_compatible(e, actual) for e in es)
    if "|" in actual:
        ais = {a.strip() for a in actual.split("|")}
        return any(_compatible(expected, a) for a in ais)
    if expected == "float" and actual == "int":
        return True
    # Bare container types match any specialization.
    if expected == "array" and actual.startswith("array["):    return True
    if expected == "tuple" and actual.startswith("tuple("):    return True
    if expected == "record" and actual.startswith("record{"):  return True
    if expected == "actor" and actual.startswith("actor("):    return True
    if actual == "array" and expected.startswith("array["):    return True
    if actual == "tuple" and expected.startswith("tuple("):    return True
    if actual == "record" and expected.startswith("record{"):  return True
    if actual == "actor" and expected.startswith("actor("):    return True
    # Container-aware compatibility.
    if expected.startswith("array[") and actual.startswith("array["):
        ei = expected[len("array["):-1]
        ai = actual[len("array["):-1]
        # Phase 11e: split off length suffix when present and require
        # exact match if both sides specify one.
        e_parts = _split_top(ei)
        a_parts = _split_top(ai)
        e_elem = e_parts[0] if e_parts else "any"
        a_elem = a_parts[0] if a_parts else "any"
        if not _compatible(e_elem, a_elem):
            return False
        if len(e_parts) >= 2 and len(a_parts) >= 2:
            # Both annotated with length; require equality.
            try:
                return int(e_parts[1]) == int(a_parts[1])
            except (TypeError, ValueError):
                return True
        return True
    if expected.startswith("tuple(") and actual.startswith("tuple("):
        ei = expected[len("tuple("):-1]
        ai = actual[len("tuple("):-1]
        ep = _split_top(ei)
        ap = _split_top(ai)
        if len(ep) != len(ap):
            return False
        return all(_compatible(e, a) for e, a in zip(ep, ap))
    if expected.startswith("record{") and actual.startswith("record{"):
        # subtype: actual must have at least the same keys w/ compat types.
        ef = _record_fields(expected)
        af = _record_fields(actual)
        for k, et in ef.items():
            if k not in af or not _compatible(et, af[k]):
                return False
        return True
    return False


def _subtract_type(union: str, removed: str) -> str:
    """Remove `removed` from a `T1 | T2 | ...` union, returning a narrowed
    type. Returns "never" when nothing is left, or the unchanged union
    when `removed` isn't a member."""
    if "|" not in union:
        return "never" if union.strip() == removed.strip() else union
    parts = [p.strip() for p in union.split("|")]
    survivors = [p for p in parts if p != removed.strip()]
    if not survivors:
        return "never"
    if len(survivors) == 1:
        return survivors[0]
    return " | ".join(survivors)


def _record_fields(rec: str) -> dict:
    if not (rec.startswith("record{") and rec.endswith("}")):
        return {}
    body = rec[len("record{"):-1]
    out: dict = {}
    for p in _split_top(body):
        if ":" in p:
            k, _, v = p.partition(":")
            out[k.strip()] = v.strip()
    return out


def _unify(pattern: str, actual: str, bindings: dict) -> bool:
    """Best-effort structural unification. `pattern` may contain type
    variables. Returns True if `actual` is consistent with `pattern`
    under the bindings (mutating bindings as needed). False on mismatch."""
    if pattern in bindings:
        return _compatible(bindings[pattern], actual)
    if pattern in _typevars_in(pattern) and len(pattern) == 1:
        bindings[pattern] = actual
        return True
    # Both arrays — unify on element type only (ignore length suffix).
    if pattern.startswith("array[") and actual.startswith("array["):
        ip = pattern[len("array["):-1]
        ia = actual[len("array["):-1]
        ip_parts = _split_top(ip)
        ia_parts = _split_top(ia)
        ip_elem = ip_parts[0] if ip_parts else ip
        ia_elem = ia_parts[0] if ia_parts else ia
        return _unify(ip_elem, ia_elem, bindings)
    if pattern.startswith("tuple(") and actual.startswith("tuple("):
        ip = pattern[len("tuple("):-1]
        ia = actual[len("tuple("):-1]
        pp = _split_top(ip); aa = _split_top(ia)
        if len(pp) != len(aa):
            return False
        return all(_unify(x, y, bindings) for x, y in zip(pp, aa))
    # Substitute current bindings into the pattern and fall back to compat.
    return _compatible(_substitute(pattern, bindings), actual)


# ---------------------------------------------------------------------------
# Walker — full call-site validation lives here in Phase 11b.

class TypeChecker:
    def __init__(self, program: Program, builtin_signatures: dict):
        self.program = program
        self.builtin_sigs = dict(builtin_signatures)
        self.fn_sigs: dict = {}
        self.classes_by_name: dict = {}
        self.issues: list[TypeIssue] = []
        # Phase 12: declared effects per user function/method (key matches
        # fn_sigs) and observed effects (filled during walk).
        self.fn_decl_effects: "dict[str, set]" = {}
        self.fn_observed_effects: "dict[str, set]" = {}
        self._current_observed_key: Optional[str] = None
        # Phase 14: linear / affine ownership tracking. `_moved` is the
        # set of var names that have been consumed in the current scope.
        self._moved: set = set()

    # ----- signatures ---------------------------------------------------
    def _build_user_sigs(self):
        for d in self.program.decls:
            if isinstance(d, FunctionDecl):
                self.fn_sigs[d.name] = self._sig_for(d)
                if d.effects is not None:
                    self.fn_decl_effects[d.name] = set(d.effects)
            elif isinstance(d, ClassDecl):
                self.classes_by_name[d.name] = d
                for m in d.methods:
                    key = f"{d.name}.{m.name}"
                    self.fn_sigs[key] = self._sig_for(m)
                    if m.effects is not None:
                        self.fn_decl_effects[key] = set(m.effects)
                for f in d.functions:
                    key = f"{d.name}.{f.name}"
                    self.fn_sigs[key] = self._sig_for(f)
                    if f.effects is not None:
                        self.fn_decl_effects[key] = set(f.effects)
                    self.fn_sigs.setdefault(f.name, self._sig_for(f))
                    if f.effects is not None:
                        self.fn_decl_effects.setdefault(f.name, set(f.effects))

    @staticmethod
    def _sig_for(decl) -> str:
        params = []
        for name, ann in zip(decl.params, decl.param_annotations or []):
            params.append(f"{name}:{ann or 'any'}")
        ret = decl.return_annotation or "any"
        return f"function({', '.join(params)}) -> {ret}"

    # ----- top-level driver --------------------------------------------
    def check(self) -> list[TypeIssue]:
        self._build_user_sigs()
        for d in self.program.decls:
            if isinstance(d, FunctionDecl):
                self._check_function(d, where=f"function {d.name}",
                                     observed_key=d.name)
            elif isinstance(d, ClassDecl):
                for f in d.fields:
                    if f.type_annotation:
                        actual = self._infer(f.expr, env={})
                        if not _compatible(f.type_annotation, actual):
                            self._issue(f"field {d.name}.{f.name}",
                                        "field initializer mismatch",
                                        f.type_annotation, actual)
                for m in d.methods:
                    self._check_function(m, where=f"method {d.name}.{m.name}",
                                         observed_key=f"{d.name}.{m.name}")
                for fn in d.functions:
                    self._check_function(fn, where=f"function {d.name}.{fn.name}",
                                         observed_key=f"{d.name}.{fn.name}")
            elif isinstance(d, GlobalStmt):
                self._check_stmt(d.stmt, env={}, where="global")
        # Phase 12: compare declared vs observed effects per user function.
        self._check_effect_declarations()
        return self.issues

    def _check_function(self, fn, where: str, observed_key: Optional[str] = None):
        prev_key = self._current_observed_key
        prev_moved = self._moved
        if observed_key is not None:
            self._current_observed_key = observed_key
            self.fn_observed_effects.setdefault(observed_key, set())
        # Phase 14: each function has its own moved set, isolated from caller.
        self._moved = set()
        env = {p: (a or "any") for p, a in zip(fn.params, fn.param_annotations or [])}
        # Seed in-class methods/functions with the actor's field types so
        # `field = expr;` and `field` reads inside method bodies type-check
        # against the field's annotation (Phase 11d/11e benefit).
        cls_name = self._owning_class(where)
        if cls_name:
            cls = self.classes_by_name.get(cls_name)
            if cls is not None:
                for f in cls.fields:
                    if f.name in env:
                        continue   # parameter shadows field
                    if f.type_annotation:
                        env[f.name] = f.type_annotation
                    else:
                        env[f.name] = self._infer(f.expr, {}, where=where)
        self._check_block(fn.body, env, fn.return_annotation, where)
        self._current_observed_key = prev_key
        self._moved = prev_moved

    @staticmethod
    def _owning_class(where: str) -> Optional[str]:
        # `where` is like "method Demo.run" or "function Demo.helper".
        for prefix in ("method ", "function "):
            if where.startswith(prefix):
                rest = where[len(prefix):]
                if "." in rest:
                    return rest.split(".")[0]
        return None

    def _check_block(self, blk: Block, env: dict, ret_ann: Optional[str], where: str):
        for s in blk.stmts:
            self._check_stmt(s, env, where, ret_ann)

    # ----- statement walker --------------------------------------------
    def _check_stmt(self, s, env: dict, where: str, ret_ann: Optional[str] = None):
        kind = type(s)
        if kind is VarDecl:
            actual = self._infer(s.expr, env, where=where)
            if s.type_annotation and not _compatible(s.type_annotation, actual):
                self._issue(where, f"`var {s.name}` initializer mismatch",
                            s.type_annotation, actual)
            env[s.name] = s.type_annotation or actual
        elif kind is VarNew:
            env[s.name] = f"actor({s.cls_name})"
            self._check_constructor(s.cls_name, s.args, env, where)
        elif kind is Assign:
            actual = self._infer(s.expr, env, where=where)
            expected = env.get(s.name, "any")
            if expected != "any" and not _compatible(expected, actual):
                self._issue(where, f"`{s.name} = ...` mismatch", expected, actual)
            # Phase 14: rebinding clears the moved state — the name now
            # refers to a fresh value.
            self._moved.discard(s.name)
        elif kind is If:
            self._infer(s.cond, env, where=where)
            # Phase 11d: flow-sensitive narrowing via typeof(x) == "T" guards.
            then_env, else_env = self._narrow(s.cond, env)
            # Phase 14: branch the moved set so each arm sees a fresh
            # consumption record; merge afterwards. Branches that always
            # `return` don't contribute to the post-if moved set since
            # control never reaches code below.
            saved_moved = set(self._moved)
            self._check_stmt(s.then_body, then_env, where, ret_ann)
            then_moved = self._moved
            then_terminates = _stmt_terminates(s.then_body)
            self._moved = saved_moved
            else_moved = saved_moved
            else_terminates = False
            if s.else_body is not None:
                self._check_stmt(s.else_body, else_env, where, ret_ann)
                else_moved = self._moved
                else_terminates = _stmt_terminates(s.else_body)
            # If a branch always returns, the *other* branch (or the
            # pre-if state) governs the post-if moved set.
            if then_terminates and else_terminates:
                self._moved = saved_moved   # unreachable below
            elif then_terminates:
                self._moved = else_moved
            elif else_terminates:
                self._moved = then_moved
            else:
                self._moved = then_moved | else_moved
        elif kind is While:
            self._infer(s.cond, env, where=where)
            self._check_stmt(s.body, env, where, ret_ann)
        elif kind is Block:
            self._check_block(s, env, ret_ann, where)
        elif kind is Return:
            if s.expr is not None:
                actual = self._infer(s.expr, env, where=where)
                if ret_ann and not _compatible(ret_ann, actual):
                    self._issue(where, "return type mismatch", ret_ann, actual)
        elif kind is CallStmt:
            self._validate_call(s.name, s.args, env, where, kind_label="function")
        elif kind is Send:
            self._validate_method_call(s.target, s.method, s.args, env, where,
                                       call_form="send")
        elif kind is IndexAssign:
            self._infer(s.expr, env, where=where)
            for ix in s.idxs:
                self._infer(ix, env, where=where)
        elif kind is FieldAssign:
            # Phase 15: external write to actor fields is forbidden, even
            # for `pub` fields. Records remain mutable. Self-fields inside
            # methods are bare-Var assigns (caught by Assign branch above)
            # so this only fires for `obj.field = ...` with obj an actor.
            base_t = env.get(s.name, "any")
            if base_t.startswith("actor(") and base_t.endswith(")"):
                cls_name = base_t[len("actor("):-1].split(",")[0].strip()
                self._issue(where,
                    f"external write to `{s.name}.{'.'.join(s.attrs)}` "
                    f"on actor({cls_name}) is not allowed — use a method "
                    f"(Phase 15: symbol_owned enforcement)")
            self._infer(s.expr, env, where=where)
        elif kind is Become:
            self._check_constructor(s.cls_name, s.args, env, where)

    # ----- constructor / method dispatch -------------------------------
    def _check_constructor(self, cls_name: str, args: list, env: dict, where: str):
        cls = self.classes_by_name.get(cls_name)
        if cls is None:
            return
        init_m = next((m for m in cls.methods if m.name == "init"), None)
        if init_m is None:
            return
        sig = self._sig_for(init_m)
        self._validate_with_sig(f"new {cls_name}", sig, args, env, where)

    def _validate_method_call(self, target: str, method: str, args: list,
                              env: dict, where: str, call_form: str = "now") -> Optional[dict]:
        actor_t = env.get(target, "any") if target not in ("self", "sender") else "any"
        cls_name = None
        if actor_t.startswith("actor(") and actor_t.endswith(")"):
            cls_name = actor_t[len("actor("):-1].split(",")[0].strip()
        if cls_name is None:
            return None
        key = f"{cls_name}.{method}"
        sig = self.fn_sigs.get(key)
        if sig is None:
            return None
        # Phase 12: a method call inherits the method's declared effects.
        self._observe_effects_from(key)
        return self._validate_with_sig(f"{call_form} {target}.{method}", sig, args, env, where)

    def _validate_call(self, name: str, args: list, env: dict, where: str,
                       kind_label: str = "function") -> Optional[dict]:
        sig = self.builtin_sigs.get(name) or self.fn_sigs.get(name)
        # Phase 12: accumulate observed effects from each callee.
        self._observe_effects_from(name)
        if sig is None:
            return None
        return self._validate_with_sig(f"{kind_label} `{name}`", sig, args, env, where)

    def _observe_effects_from(self, callee: str):
        if self._current_observed_key is None:
            return
        bucket = self.fn_observed_effects.setdefault(self._current_observed_key, set())
        if callee in BUILTIN_EFFECTS:
            bucket |= BUILTIN_EFFECTS[callee]
        # User function calls: pull declared effects (or recompute later).
        if callee in self.fn_decl_effects:
            bucket |= self.fn_decl_effects[callee]
            # Also fold in already-observed for callees we've already walked.
            bucket |= self.fn_observed_effects.get(callee, set())

    def _validate_with_sig(self, label: str, sig: str, args: list,
                           env: dict, where: str) -> Optional[dict]:
        """Validate args against a signature. Returns the type-variable
        bindings (for generic substitution) so callers can apply them
        to the return type. Returns None on signature-parse failure."""
        specs = _parse_signature(sig)
        if specs is None:
            return None
        bindings: dict = {}
        # Strip optional first when its arity matches (caller passed extra arg).
        opt_first = specs[0] if specs and specs[0].optional else None
        non_opt = specs[1:] if opt_first else specs[:]
        # Detect variadic on the LAST non-optional param.
        if non_opt and non_opt[-1].variadic:
            v_param = non_opt[-1]
            required = non_opt[:-1]
            min_args = len(required)
            if opt_first and len(args) >= min_args + 1:
                self._check_arg(args[0], opt_first, env, where, label, bindings)
                self._check_required(args[1:], required, env, where, label, bindings)
                for a in args[1 + len(required):]:
                    self._check_arg(a, v_param, env, where, label, bindings)
            else:
                if len(args) < min_args:
                    self._issue(where, f"call to {label}: too few args (need >= {min_args}, got {len(args)})")
                    return bindings
                self._check_required(args[:len(required)], required, env, where, label, bindings)
                for a in args[len(required):]:
                    self._check_arg(a, v_param, env, where, label, bindings)
            return bindings
        # Non-variadic.
        n_required = len(non_opt)
        valid_arities = {n_required}
        if opt_first:
            valid_arities.add(n_required + 1)
        if len(args) not in valid_arities:
            self._issue(where, f"call to {label}: arity {len(args)} vs declared {sorted(valid_arities)}")
            return bindings
        offset = 0
        if opt_first and len(args) == n_required + 1:
            self._check_arg(args[0], opt_first, env, where, label, bindings)
            offset = 1
        self._check_required(args[offset:], non_opt, env, where, label, bindings)
        return bindings

    def _check_required(self, args: list, specs: list, env: dict,
                        where: str, label: str, bindings: dict):
        for spec, arg in zip(specs, args):
            self._check_arg(arg, spec, env, where, label, bindings)

    def _check_arg(self, arg, spec: ParamSpec, env: dict,
                   where: str, label: str, bindings: dict):
        actual = self._infer(arg, env, where=where)
        # Phase 14: if the parameter is `linear T` and the argument is a
        # plain variable reference, the variable is consumed (moved into
        # the callee). We mark it on the way out so subsequent uses error.
        is_linear_param, _ = _strip_linear(spec.type)
        if is_linear_param and isinstance(arg, Var):
            self._moved.add(arg.name)
        # If the param type contains a type-variable (e.g. T), bind/check it
        # against the actual type rather than failing on `T` not matching.
        tvars = _typevars_in(spec.type)
        if tvars:
            # Try to bind each variable. If the param type is exactly a
            # variable (e.g. `T`), bind directly. Otherwise we attempt a
            # structural unification: "array[T]" vs "array[int]" → T = int.
            if spec.type in tvars:
                # Pure type-var slot.
                tvar = spec.type
                if tvar in bindings:
                    if not _compatible(bindings[tvar], actual):
                        self._issue(where,
                            f"call to {label} arg `{spec.name}`: "
                            f"type-var `{tvar}` already bound to {bindings[tvar]}, got {actual}")
                else:
                    bindings[tvar] = actual
                return
            # Structural unify: substitute one var at a time when the shape
            # matches, else fall back to checking compatibility after a best-
            # effort substitution.
            unified = _unify(spec.type, actual, bindings)
            if not unified:
                self._issue(where, f"call to {label} arg `{spec.name}` mismatch",
                            spec.type, actual)
            return
        if not _compatible(spec.type, actual):
            self._issue(where, f"call to {label} arg `{spec.name}` mismatch",
                        spec.type, actual)

    # ----- expression-type inference (Phase 11b strengthens this) -------
    def _infer(self, e, env: dict, where: str = "") -> str:
        kind = type(e)
        if kind is IntLit:    return "int"
        if kind is FloatLit:  return "float"
        if kind is StringLit: return "string"
        if kind is Var:
            t = env.get(e.name, "any")
            # Phase 14: read of a moved (consumed) linear variable is a use-
            # after-move error. We surface it once per offending name.
            if e.name in self._moved:
                self._issue(where,
                            f"use of moved linear variable `{e.name}`")
            return t
        if kind is Neg:
            return self._infer(e.inner, env, where=where)
        if kind is Binop:
            l = self._infer(e.lhs, env, where=where)
            r = self._infer(e.rhs, env, where=where)
            if e.op == "+":
                if "string" in (l, r):    return "string"
                if "float" in (l, r):     return "float"
                if l == "int" == r:        return "int"
                return "any"
            if e.op in ("-", "*", "/"):
                if "float" in (l, r):     return "float"
                if l == "int" == r:        return "int"
                return "any"
            if e.op in ("==", "!=", "<", "<=", ">", ">="):
                return "bool"
            return "any"
        if kind is ArrayLit:
            n = len(e.items)
            if n == 0:
                return "array[unit, 0]"
            inner = {self._infer(x, env, where=where) for x in e.items}
            elem = next(iter(inner)) if len(inner) == 1 else " | ".join(sorted(inner))
            # Phase 11e: tag with literal length so dependent-type checks fire.
            return f"array[{elem}, {n}]"
        if kind is TupleLit:
            return "tuple(" + ", ".join(self._infer(x, env, where=where) for x in e.items) + ")"
        if kind is RecordLit:
            return "record{" + ", ".join(
                f"{k}:{self._infer(v, env, where=where)}" for k, v in e.fields
            ) + "}"
        if kind is New:
            self._check_constructor(e.cls_name, e.args, env, where)
            return f"actor({e.cls_name})"
        if kind is CallExpr:
            # Validate args and get return type, applying any generic substitution.
            sig = self.builtin_sigs.get(e.name) or self.fn_sigs.get(e.name)
            bindings = self._validate_call(e.name, e.args, env, where) or {}
            if sig is None:
                return "any"
            return _substitute(_return_of(sig), bindings)
        if kind is IndexExpr:
            base = env.get(e.name, "any")
            if base.startswith("array[") and base.endswith("]"):
                inner = base[len("array["):-1]
                parts = _split_top(inner)
                elem_t = parts[0] if parts else "any"
                # Phase 11e: literal-index out-of-bound check when length known.
                if len(parts) >= 2 and len(e.idxs) == 1:
                    idx = e.idxs[0]
                    if isinstance(idx, IntLit):
                        try:
                            length = int(parts[1])
                            if idx.val < 0 or idx.val >= length:
                                self._issue(where,
                                    f"index {idx.val} out of bounds for `{e.name}: array[..., {length}]`")
                        except (TypeError, ValueError):
                            pass
                return elem_t
            return "any"
        if kind is FieldAccess:
            cur = env.get(e.name, "any")
            base_name = e.name
            for attr in e.attrs:
                cur = self._field_type(cur, attr, where=where, base_name=base_name)
                if cur == "any":
                    break
                base_name = base_name + "." + attr
            return cur
        if kind is ArraySized:
            init = self._infer(e.init, env, where=where) if e.init is not None else "int"
            return ("array[" * len(e.sizes)) + init + ("]" * len(e.sizes))
        if kind is NowCall:
            self._validate_method_call(e.target, e.method, e.args, env, where,
                                       call_form="now")
            return self._method_return(e.target, e.method, env)
        if kind is FutureCall:
            self._validate_method_call(e.target, e.method, e.args, env, where,
                                       call_form="future")
            return "future"
        return "any"

    def _method_return(self, target: str, method: str, env: dict) -> str:
        if target in ("self", "sender"):
            return "any"
        actor_t = env.get(target, "any")
        if not (actor_t.startswith("actor(") and actor_t.endswith(")")):
            return "any"
        cls_name = actor_t[len("actor("):-1].split(",")[0].strip()
        sig = self.fn_sigs.get(f"{cls_name}.{method}")
        return _return_of(sig) if sig else "any"

    def _field_type(self, rec: str, field: str, where: str = "",
                    base_name: str = "") -> str:
        # First try record annotation.
        if rec.startswith("record{") and rec.endswith("}"):
            return _record_fields(rec).get(field, "any")
        # Then actor field declared type — Phase 15: external read of a
        # private actor field is flagged. Inside the actor's own methods,
        # bare `field` is a Var lookup (not FieldAccess), so this only
        # fires for `obj.field` with `obj` an actor reference.
        if rec.startswith("actor(") and rec.endswith(")"):
            cls_name = rec[len("actor("):-1].split(",")[0].strip()
            cls = self.classes_by_name.get(cls_name)
            if cls is not None:
                for f in cls.fields:
                    if f.name == field:
                        if not f.is_public:
                            self._issue(where,
                                f"private field `{base_name}.{field}` "
                                f"of actor({cls_name}) — annotate with `pub` "
                                f"or call a method instead")
                        return f.type_annotation or "any"
        return "any"

    def _issue(self, where: str, message: str,
               expected: Optional[str] = None, actual: Optional[str] = None):
        self.issues.append(TypeIssue(where, message, expected, actual))

    # ----- Phase 12: declared vs observed effect set --------------------
    def _check_effect_declarations(self):
        """Compare each user function/method's declared effects with what
        the body actually does. Iterate to a fixed point so that effects
        propagate through indirect call chains."""
        # Closure: keep recomputing observed effects until stable.
        for _ in range(8):
            changed = False
            for key, observed in list(self.fn_observed_effects.items()):
                # For each callee that's also a user function, fold in its
                # currently-observed effects.
                for callee, _eff in BUILTIN_EFFECTS.items():
                    pass  # builtins already counted at observe time
                # Walk the body? — too expensive; rely on the pass we did.
                # Just inflate via fn_decl_effects of any user funcs we
                # reference, picked up at observation time.
            if not changed:
                break
        for key, observed in self.fn_observed_effects.items():
            # Gradual: only check when the user explicitly declared a set.
            if key not in self.fn_decl_effects:
                continue
            declared = self.fn_decl_effects[key]
            missing = observed - declared
            if missing:
                kind = "method" if "." in key else "function"
                self._issue(f"{kind} {key}",
                            f"effect set incomplete — declared {{{', '.join(sorted(declared)) or '∅'}}} "
                            f"but uses {{{', '.join(sorted(observed))}}}; "
                            f"missing: {{{', '.join(sorted(missing))}}}")

    # ----- Phase 11d: flow-sensitive narrowing -------------------------
    def _narrow(self, cond, env: dict) -> tuple[dict, dict]:
        """Inspect an `if` condition for `typeof(x) == "T"` shape and return
        (then_env, else_env) with x narrowed accordingly. Falls back to
        unchanged copies of env when the pattern doesn't match."""
        then_env = dict(env)
        else_env = dict(env)
        if not isinstance(cond, Binop):
            return then_env, else_env
        if cond.op not in ("==", "!="):
            return then_env, else_env
        # Look for typeof(x) on either side, and a string literal on the other.
        var_name, type_str = self._typeof_guard_pieces(cond.lhs, cond.rhs)
        if var_name is None:
            var_name, type_str = self._typeof_guard_pieces(cond.rhs, cond.lhs)
        if var_name is None or type_str is None:
            return then_env, else_env
        current = env.get(var_name, "any")
        narrowed_to = type_str
        narrowed_else = _subtract_type(current, type_str)
        if cond.op == "==":
            then_env[var_name] = narrowed_to
            else_env[var_name] = narrowed_else
        else:   # !=
            then_env[var_name] = narrowed_else
            else_env[var_name] = narrowed_to
        return then_env, else_env

    @staticmethod
    def _typeof_guard_pieces(maybe_call, maybe_str):
        """Return (var_name, type_string) if `maybe_call` is `typeof(NAME)`
        and `maybe_str` is a string literal."""
        if not isinstance(maybe_call, CallExpr):
            return (None, None)
        if maybe_call.name != "typeof" or len(maybe_call.args) != 1:
            return (None, None)
        arg = maybe_call.args[0]
        if not isinstance(arg, Var):
            return (None, None)
        if not isinstance(maybe_str, StringLit):
            return (None, None)
        return (arg.name, maybe_str.val)


def check(program: Program, builtin_signatures: dict) -> list[TypeIssue]:
    return TypeChecker(program, builtin_signatures).check()
