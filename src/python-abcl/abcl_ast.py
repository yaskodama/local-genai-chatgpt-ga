"""AST node classes for ABCL/c+.

Plain dataclasses; the interpreter walks these directly.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Union


# ---------- Expressions ----------

@dataclass
class IntLit:
    val: int

@dataclass
class FloatLit:
    val: float

@dataclass
class StringLit:
    val: str

@dataclass
class Var:
    name: str  # 'self' / 'sender' are spelled out as Var('self') etc.

@dataclass
class Binop:
    op: str
    lhs: 'Expr'
    rhs: 'Expr'

@dataclass
class Neg:
    inner: 'Expr'

@dataclass
class New:
    cls_name: str
    args: List['Expr']

@dataclass
class CallExpr:
    name: str
    args: List['Expr']

@dataclass
class ArrayLit:
    items: List['Expr']

@dataclass
class NowCall:
    """Synchronous send: caller blocks until receiver replies."""
    target: str   # 'self' / 'sender' / a variable name
    method: str
    args: List['Expr']

@dataclass
class FutureCall:
    """Asynchronous send returning a Future; await(f) to retrieve value."""
    target: str
    method: str
    args: List['Expr']


Expr = Union[IntLit, FloatLit, StringLit, Var, Binop, Neg, New, CallExpr,
             ArrayLit, NowCall, FutureCall]


# ---------- Statements ----------

@dataclass
class VarDecl:
    name: str
    expr: Expr

@dataclass
class VarNew:
    name: str
    cls_name: str
    args: List[Expr]

@dataclass
class Assign:
    name: str
    expr: Expr

@dataclass
class Send:
    target: str   # variable name (or 'self' / 'sender')
    method: str
    args: List[Expr]

@dataclass
class CallStmt:
    name: str
    args: List[Expr]

@dataclass
class If:
    cond: Expr
    then_body: 'Stmt'
    else_body: Optional['Stmt']

@dataclass
class While:
    cond: Expr
    body: 'Stmt'

@dataclass
class Become:
    cls_name: str
    args: List[Expr]

@dataclass
class Block:
    stmts: List['Stmt']


Stmt = Union[
    VarDecl, VarNew, Assign, Send, CallStmt,
    If, While, Become, Block,
]


# ---------- Top level ----------

@dataclass
class MethodDecl:
    name: str
    params: List[str]
    body: Block

@dataclass
class ClassDecl:
    name: str
    fields: List[VarDecl]   # field initializers
    methods: List[MethodDecl]

@dataclass
class GlobalStmt:
    stmt: Stmt

@dataclass
class Program:
    decls: List[Union[ClassDecl, GlobalStmt]]
