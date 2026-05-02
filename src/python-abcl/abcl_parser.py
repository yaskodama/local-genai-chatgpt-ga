"""Lark-based parser for ABCL/c+.

Builds the AST defined in abcl_ast.py via a Transformer.
"""

import os
from lark import Lark, Transformer, v_args

from abcl_ast import (
    Program, ClassDecl, MethodDecl, GlobalStmt,
    VarDecl, VarNew, Assign, Send, CallStmt,
    If, While, Become, Block,
    IntLit, FloatLit, StringLit, Var, Binop, Neg, New, CallExpr,
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

    def now_self(self, method, args):     return NowCall("self", str(method), list(args.children))
    def now_sender(self, method, args):   return NowCall("sender", str(method), list(args.children))
    def now_call(self, target, method, args):
        return NowCall(str(target), str(method), list(args.children))
    def future_self(self, method, args):     return FutureCall("self", str(method), list(args.children))
    def future_sender(self, method, args):   return FutureCall("sender", str(method), list(args.children))
    def future_call(self, target, method, args):
        return FutureCall(str(target), str(method), list(args.children))

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

    def var_decl_stmt(self, name, expr):
        return VarDecl(str(name), expr)

    def assign_stmt(self, name, expr):
        return Assign(str(name), expr)

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
    def field(self, name, expr):
        return VarDecl(str(name), expr)

    @v_args(inline=False)
    def params(self, names):
        return [str(n) for n in names]

    def method_decl(self, name, params, *body_stmts):
        return MethodDecl(str(name), params, Block(list(body_stmts)))

    @v_args(inline=False)
    def class_decl(self, items):
        # items: [NAME, *fields, *methods]
        name = str(items[0])
        fields, methods = [], []
        for it in items[1:]:
            if isinstance(it, MethodDecl):
                methods.append(it)
            elif isinstance(it, VarDecl):
                fields.append(it)
        return ClassDecl(name, fields, methods)

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
