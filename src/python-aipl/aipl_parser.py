"""Lark-based parser for AIPL.

Builds the AST defined in abcl_ast.py via a Transformer.
"""

import os
from typing import Optional
from lark import Lark, Transformer, v_args

from aipl_ast import (
    Program, ClassDecl, MethodDecl, FunctionDecl, GlobalStmt,
    VarDecl, VarNew, Assign, IndexAssign, FieldAssign, Send, CallStmt,
    If, While, Become, Block, Return,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, New, CallExpr,
    ArrayLit, IndexExpr, ArraySized, RecordLit, FieldAccess, TupleLit,
    NowCall, FutureCall,
)


_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "grammar.lark")
with open(_GRAMMAR_PATH) as f:
    _GRAMMAR = f.read()

_parser = Lark(_GRAMMAR, parser="lalr", propagate_positions=False)


@v_args(inline=True)
class _Builder(Transformer):
    # ---- atoms / expressions ----
    def int_lit(self, tok):     return IntLit(int(tok))
    def float_lit(self, tok):   return FloatLit(float(tok))
    def string_lit(self, tok):
        s = str(tok)[1:-1]      # strip surrounding quotes
        return StringLit(bytes(s, "utf-8").decode("unicode_escape"))
    def self_var(self):         return Var("self")
    def sender_var(self):       return Var("sender")
    def var_expr(self, name):   return Var(str(name))
    def neg(self, inner):       return Neg(inner)
    def new_expr(self, name, args):     return New(str(name), list(args.children))
    def call_expr(self, name, args):    return CallExpr(str(name), list(args.children))

    def array_lit(self, args):
        return ArrayLit(list(args.children))

    def now_self(self, method, args):     return NowCall("self", str(method), list(args.children))
    def now_sender(self, method, args):   return NowCall("sender", str(method), list(args.children))
    def now_call(self, target, method, args):
        return NowCall(str(target), str(method), list(args.children))
    def future_self(self, method, args):     return FutureCall("self", str(method), list(args.children))
    def future_sender(self, method, args):   return FutureCall("sender", str(method), list(args.children))
    def future_call(self, target, method, args):
        return FutureCall(str(target), str(method), list(args.children))

    def await_expr(self, e):
        # `await x` desugars to the existing `await(x)` builtin call.
        return CallExpr("await", [e])

    @v_args(inline=False)
    def args(self, items):
        return _ArgList(items)

    # rel/add/mul flatten left-associative chains
    @v_args(inline=False)
    def rel_expr(self, items):  return _flatten_binop(items)
    @v_args(inline=False)
    def add_expr(self, items):  return _flatten_binop(items)
    @v_args(inline=False)
    def mul_expr(self, items):  return _flatten_binop(items)
    def rel_op(self, tok):      return str(tok)
    def add_op(self, tok):      return str(tok)
    def mul_op(self, tok):      return str(tok)

    # ---- statements ----
    def var_new_stmt(self, *parts):
        # parts may be (name, cls, args) or with leading kw token; lark drops
        # literal terminals so the leading "var"/"float"/"int" is gone.
        name, cls, args = parts[0], parts[1], parts[2]
        return VarNew(str(name), str(cls), list(args.children))

    @v_args(inline=False)
    def var_decl_stmt(self, items):
        # items: [NAME, type_anno?, expr]
        name = str(items[0])
        if len(items) == 3:
            return VarDecl(name, items[2], type_annotation=str(items[1]))
        return VarDecl(name, items[1])

    @v_args(inline=False)
    def dim_list(self, items):
        # items is the list of `expr` AST nodes between the brackets.
        return list(items)

    def var_array_decl(self, name, dims):
        # `var x[N1][N2]...;` — sizes evaluated at declaration time.
        return VarDecl(str(name), ArraySized(dims, None))

    def var_array_decl_init(self, name, dims, init_expr):
        return VarDecl(str(name), ArraySized(dims, init_expr))

    def assign_stmt(self, name, expr):
        return Assign(str(name), expr)

    def index_assign(self, name, dims, expr):
        return IndexAssign(str(name), dims, expr)

    def index_expr(self, name, dims):
        return IndexExpr(str(name), dims)

    @v_args(inline=False)
    def field_assign(self, items):
        # items: [NAME (base), NAME (attr1), NAME (attr2), ..., expr]
        base = str(items[0])
        attrs = [str(t) for t in items[1:-1]]
        expr = items[-1]
        return FieldAssign(base, attrs, expr)

    @v_args(inline=False)
    def field_access(self, items):
        # items: [NAME (base), NAME (attr1), ...]
        base = str(items[0])
        attrs = [str(t) for t in items[1:]]
        return FieldAccess(base, attrs)

    # ---- record literals ----
    @v_args(inline=False)
    def record_fields(self, items):
        # items is the list of (name, expr) tuples produced by record_field.
        return list(items)

    def record_field(self, name, expr):
        return (str(name), expr)

    def record_lit(self, fields):
        # `fields` is the list returned by record_fields.
        return RecordLit(list(fields))

    def record_empty(self):
        return RecordLit([])

    # ---- tuple literals (組型) ----
    def tuple_empty(self):
        return TupleLit([])

    def tuple_one(self, item):
        return TupleLit([item])

    @v_args(inline=False)
    def tuple_many(self, items):
        return TupleLit(list(items))

    def send_self(self, method, args):
        return Send("self", str(method), list(args.children))

    def send_sender(self, method, args):
        return Send("sender", str(method), list(args.children))

    def send_named(self, target, method, args):
        return Send(str(target), str(method), list(args.children))

    def call_stmt(self, name, args):
        return CallStmt(str(name), list(args.children))

    def if_stmt(self, *parts):
        cond = parts[0]
        then_body = parts[1]
        else_body = parts[2] if len(parts) >= 3 else None
        return If(cond, then_body, else_body)

    def while_stmt(self, cond, body):
        return While(cond, body)

    def become_stmt(self, cls, args):
        return Become(str(cls), list(args.children))

    @v_args(inline=False)
    def block(self, stmts):
        return Block(list(stmts))

    # ---- class / method / params ----
    @v_args(inline=False)
    def field(self, items):
        # items: [NAME, type_anno?, expr]
        name = str(items[0])
        if len(items) == 3:
            return VarDecl(name, items[2], type_annotation=str(items[1]))
        return VarDecl(name, items[1])

    @v_args(inline=False)
    def field_pub(self, items):
        # Same shape as `field` but the surrounding production already
        # ensured `pub` was present.
        name = str(items[0])
        if len(items) == 3:
            return VarDecl(name, items[2], type_annotation=str(items[1]), is_public=True)
        return VarDecl(name, items[1], is_public=True)

    def field_array(self, name, dims):
        return VarDecl(str(name), ArraySized(dims, None))

    def field_array_pub(self, name, dims):
        return VarDecl(str(name), ArraySized(dims, None), is_public=True)

    def field_array_init(self, name, dims, init_expr):
        return VarDecl(str(name), ArraySized(dims, init_expr))

    def field_array_init_pub(self, name, dims, init_expr):
        return VarDecl(str(name), ArraySized(dims, init_expr), is_public=True)

    @v_args(inline=False)
    def params(self, items):
        # Each `item` is already a plain str (from `param`).
        return [s for s in items]

    @v_args(inline=False)
    def param(self, items):
        # items: [NAME] or [NAME, type_anno_value]. We return a tuple so
        # the method/function builders can pull out param + annotation.
        if len(items) == 2:
            return (str(items[0]), str(items[1]))
        return (str(items[0]), None)

    # ---- type expressions: build string representations matching _infer_type ----
    @v_args(inline=False)
    def type_anno(self, items):
        # items: [type_expr_string]
        return items[0]

    @v_args(inline=False)
    def return_anno(self, items):
        return items[0]

    @v_args(inline=False)
    def effect_anno(self, items):
        # items: list of NAME tokens (effect identifiers).
        return [str(t) for t in items]

    @v_args(inline=False)
    def type_atom(self, items):
        return str(items[0])

    @v_args(inline=False)
    def type_atom_kw(self, items):
        return str(items[0])

    @v_args(inline=False)
    def type_atom_kw_pass(self, items):
        return str(items[0])

    @v_args(inline=False)
    def type_param(self, items):
        # NAME "[" type_expr ("," type_expr)* "]"
        head = str(items[0])
        params = ", ".join(str(t) for t in items[1:])
        return f"{head}[{params}]"

    @v_args(inline=False)
    def type_param_kw(self, items):
        head = str(items[0])
        params = ", ".join(str(t) for t in items[1:])
        return f"{head}[{params}]"

    @v_args(inline=False)
    def type_tuple(self, items):
        return "tuple(" + ", ".join(str(t) for t in items) + ")"

    @v_args(inline=False)
    def type_record(self, items):
        return "record{" + ", ".join(str(t) for t in items) + "}"

    def type_record_field(self, name, ty):
        return f"{str(name)}:{str(ty)}"

    @v_args(inline=False)
    def type_union(self, items):
        return " | ".join(str(t) for t in items)

    @v_args(inline=False)
    def type_int_arg(self, items):
        # An INT literal used as a type parameter (e.g. array[int, 3]).
        return str(items[0])

    @v_args(inline=False)
    def type_linear(self, items):
        # `linear T` modifier (Phase 14). Stored as "linear T" string.
        return "linear " + str(items[0])

    @v_args(inline=False)
    def method_decl(self, items):
        # items: [NAME, params, return_anno?, effect_anno?, *body_stmts]
        name = str(items[0])
        params_raw = items[1]
        idx = 2
        ret_anno: Optional[str] = None
        effects: Optional[list] = None
        if idx < len(items) and isinstance(items[idx], str):
            ret_anno = items[idx]; idx += 1
        if idx < len(items) and isinstance(items[idx], list):
            effects = items[idx]; idx += 1
        body_stmts = items[idx:]
        param_names = [p[0] for p in params_raw]
        param_annos = [p[1] for p in params_raw]
        return MethodDecl(name, param_names, Block(list(body_stmts)),
                          return_annotation=ret_anno,
                          param_annotations=param_annos,
                          effects=effects)

    @v_args(inline=False)
    def function_decl(self, items):
        name = str(items[0])
        params_raw = items[1]
        idx = 2
        ret_anno: Optional[str] = None
        effects: Optional[list] = None
        if idx < len(items) and isinstance(items[idx], str):
            ret_anno = items[idx]; idx += 1
        if idx < len(items) and isinstance(items[idx], list):
            effects = items[idx]; idx += 1
        body_stmts = items[idx:]
        param_names = [p[0] for p in params_raw]
        param_annos = [p[1] for p in params_raw]
        return FunctionDecl(name, param_names, Block(list(body_stmts)),
                            return_annotation=ret_anno,
                            param_annotations=param_annos,
                            effects=effects)

    def return_value(self, expr):
        return Return(expr)

    def return_unit(self):
        return Return(None)

    @v_args(inline=False)
    def class_decl(self, items):
        # items: [NAME, *fields, *methods, *functions]
        name = str(items[0])
        fields, methods, functions = [], [], []
        for it in items[1:]:
            if isinstance(it, MethodDecl):
                methods.append(it)
            elif isinstance(it, FunctionDecl):
                functions.append(it)
            elif isinstance(it, VarDecl):
                fields.append(it)
        return ClassDecl(name, fields, methods, functions)

    def global_stmt(self, s):
        return GlobalStmt(s)

    @v_args(inline=False)
    def start(self, decls):
        return Program(list(decls))


class _ArgList:
    """Lightweight container so transformer rules can pass arg arrays around."""
    def __init__(self, children):
        self.children = list(children)


def _flatten_binop(items):
    # items is [expr, op, expr, op, expr, ...] for chained ops
    if len(items) == 1:
        return items[0]
    cur = items[0]
    i = 1
    while i < len(items):
        op = items[i]
        rhs = items[i + 1]
        cur = Binop(op, cur, rhs)
        i += 2
    return cur


def parse(source: str) -> Program:
    tree = _parser.parse(source)
    return _Builder().transform(tree)


def parse_file(path: str) -> Program:
    with open(path) as f:
        return parse(f.read())
