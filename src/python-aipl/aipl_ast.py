"""AST node classes for AIPL.

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
class IndexExpr:
    name: str             # the array variable
    idxs: List['Expr']    # one or more index expressions (a[i][j][k] etc.)


@dataclass
class ArraySized:
    """Multi-dim array constructor: var x[N][M] = init; produces this.
    Sizes are evaluated at the point of declaration so dynamic sizes
    (variables, fields, expressions) work."""
    sizes: List['Expr']
    init: Optional['Expr']    # None means "default 0"


@dataclass
class RecordLit:
    """Anonymous record literal: { k1: e1, k2: e2, ... }. Evaluates to
    a dict at runtime. Field order is preserved (Python 3.7+ dict)."""
    fields: List['tuple[str, Expr]']    # [(name, expr), ...]


@dataclass
class TupleLit:
    """Positional tuple literal: (e1, e2, e3, ...). Evaluates to a Python
    tuple at runtime (immutable, fixed-arity, positional access via [i])."""
    items: List['Expr']


@dataclass
class FunctionDecl:
    """User-defined function. Lives at top level or inside a class body
    (in which case it's callable from that class's methods unqualified)."""
    name: str
    params: List[str]
    body: 'Block'
    return_annotation: Optional[str] = None
    param_annotations: List[Optional[str]] = field(default_factory=list)
    effects: Optional[List[str]] = None   # None = not declared (gradual); [] = declared empty


@dataclass
class Return:
    expr: Optional['Expr']    # None for `return;`


@dataclass
class FieldAccess:
    """r.f or r.f.g.h — read a record field (or chain into nested records)."""
    name: str             # base variable
    attrs: List[str]      # one or more field names

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
             ArrayLit, IndexExpr, ArraySized, RecordLit, FieldAccess,
             TupleLit, NowCall, FutureCall]


# ---------- Statements ----------

@dataclass
class VarDecl:
    name: str
    expr: Expr
    type_annotation: Optional[str] = None  # gradual annotation (None = unchecked)

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
class IndexAssign:
    name: str
    idxs: List[Expr]      # one or more index expressions (a[i][j][k] = v)
    expr: Expr


@dataclass
class FieldAssign:
    """r.f = v;  or  r.f.g = v;  — assign through a chain of dict keys."""
    name: str             # base variable
    attrs: List[str]      # one or more field names (last is the leaf)
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
    return_annotation: Optional[str] = None
    param_annotations: List[Optional[str]] = field(default_factory=list)
    effects: Optional[List[str]] = None   # None = not declared (gradual); [] = declared empty

@dataclass
class ClassDecl:
    name: str
    fields: List[VarDecl]   # field initializers
    methods: List[MethodDecl]
    functions: List[FunctionDecl] = field(default_factory=list)   # in-class user functions

@dataclass
class GlobalStmt:
    stmt: Stmt

@dataclass
class Program:
    decls: List[Union[ClassDecl, FunctionDecl, GlobalStmt]]
