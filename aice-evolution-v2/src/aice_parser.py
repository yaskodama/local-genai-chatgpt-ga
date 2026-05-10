"""Parser for .aice v2: tokenizer + recursive-descent parser + lowering to
the .ga.json IR structure used by Phase 2/3."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# --------------------------------------------------------------------------
# Tokenizer
# --------------------------------------------------------------------------

@dataclass
class Token:
    kind: str
    value: Any
    line: int


_PUNCT = set("{}[]=;,")


def tokenize(src: str) -> list[Token]:
    tokens: list[Token] = []
    i, line = 0, 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        # line comment
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        # block comment
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            i += 2
            while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                if src[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue
        # punctuation
        if c in _PUNCT:
            tokens.append(Token("PUNCT", c, line))
            i += 1
            continue
        # string
        if c == '"':
            j = i + 1
            buf = []
            while j < n and src[j] != '"':
                if src[j] == "\\" and j + 1 < n:
                    esc = src[j + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\"}.get(esc, esc))
                    j += 2
                else:
                    if src[j] == "\n":
                        line += 1
                    buf.append(src[j])
                    j += 1
            if j >= n:
                raise SyntaxError(f"unterminated string at line {line}")
            tokens.append(Token("STRING", "".join(buf), line))
            i = j + 1
            continue
        # number
        m = re.match(r"-?\d+(?:\.\d+)?", src[i:])
        if m and (c.isdigit() or (c == "-" and i + 1 < n and src[i + 1].isdigit())):
            text = m.group(0)
            value: Any = float(text) if "." in text else int(text)
            tokens.append(Token("NUMBER", value, line))
            i += len(text)
            continue
        # identifier / keyword
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", src[i:])
        if m:
            text = m.group(0)
            if text == "true":
                tokens.append(Token("BOOL", True, line))
            elif text == "false":
                tokens.append(Token("BOOL", False, line))
            else:
                tokens.append(Token("IDENT", text, line))
            i += len(text)
            continue
        raise SyntaxError(f"unexpected char {c!r} at line {line}")
    return tokens


# --------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------

@dataclass
class Assignment:
    key: str
    value: Any
    line: int = 0


@dataclass
class Block:
    kind: str          # the leading IDENT, e.g. "search", "task", "reviewer"
    name: str | None   # second IDENT for named blocks, else None
    decls: list[Any] = field(default_factory=list)
    line: int = 0


@dataclass
class AiceFile:
    name: str
    decls: list[Any]


# --------------------------------------------------------------------------
# Parser
# --------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.t = tokens
        self.p = 0

    def _peek(self, offset: int = 0) -> Token | None:
        i = self.p + offset
        return self.t[i] if i < len(self.t) else None

    def _eat(self, kind: str, value: Any | None = None) -> Token:
        tok = self._peek()
        if tok is None or tok.kind != kind or (value is not None and tok.value != value):
            got = "EOF" if tok is None else f"{tok.kind} {tok.value!r}"
            want = kind if value is None else f"{kind} {value!r}"
            raise SyntaxError(f"expected {want}, got {got} at line {getattr(tok, 'line', '?')}")
        self.p += 1
        return tok

    def parse(self) -> AiceFile:
        self._eat("IDENT", "aice")
        name = self._eat("IDENT").value
        self._eat("PUNCT", "{")
        decls = self._parse_decls()
        self._eat("PUNCT", "}")
        return AiceFile(name=name, decls=decls)

    def _parse_decls(self) -> list[Any]:
        decls: list[Any] = []
        while True:
            tok = self._peek()
            if tok is None or (tok.kind == "PUNCT" and tok.value == "}"):
                return decls
            decls.append(self._parse_decl())

    def _parse_decl(self) -> Any:
        tok = self._eat("IDENT")
        nxt = self._peek()
        if nxt is None:
            raise SyntaxError(f"unexpected EOF after {tok.value!r}")
        if nxt.kind == "PUNCT" and nxt.value == "=":
            self._eat("PUNCT", "=")
            value = self._parse_value()
            self._eat("PUNCT", ";")
            return Assignment(key=tok.value, value=value, line=tok.line)
        if nxt.kind == "PUNCT" and nxt.value == "{":
            self._eat("PUNCT", "{")
            sub = self._parse_decls()
            self._eat("PUNCT", "}")
            return Block(kind=tok.value, name=None, decls=sub, line=tok.line)
        if nxt.kind == "IDENT":
            name = self._eat("IDENT").value
            self._eat("PUNCT", "{")
            sub = self._parse_decls()
            self._eat("PUNCT", "}")
            return Block(kind=tok.value, name=name, decls=sub, line=tok.line)
        raise SyntaxError(f"unexpected {nxt.kind} {nxt.value!r} after {tok.value!r} at line {tok.line}")

    def _parse_value(self) -> Any:
        tok = self._peek()
        if tok is None:
            raise SyntaxError("expected value, got EOF")
        if tok.kind in ("STRING", "NUMBER", "BOOL"):
            self.p += 1
            return tok.value
        if tok.kind == "IDENT":
            # bare identifier as value (e.g. for axis lists)
            self.p += 1
            return tok.value
        if tok.kind == "PUNCT" and tok.value == "[":
            return self._parse_list()
        raise SyntaxError(f"unexpected token {tok.kind} {tok.value!r} at line {tok.line}")

    def _parse_list(self) -> list[Any]:
        self._eat("PUNCT", "[")
        out: list[Any] = []
        while True:
            tok = self._peek()
            if tok and tok.kind == "PUNCT" and tok.value == "]":
                self._eat("PUNCT", "]")
                return out
            out.append(self._parse_value())
            tok = self._peek()
            if tok and tok.kind == "PUNCT" and tok.value == ",":
                self._eat("PUNCT", ",")
                continue
            self._eat("PUNCT", "]")
            return out


def parse(src: str) -> AiceFile:
    return Parser(tokenize(src)).parse()


# --------------------------------------------------------------------------
# Lowering: AST -> .ga.json dict
# --------------------------------------------------------------------------

def default_operators(open_axes: bool) -> dict[str, list[dict[str, Any]]]:
    """Return mutation/crossover defaults. When `open_axes` is true, the
    Phase 9 LLM-directed proposers get non-zero weight so the search
    actually invokes them; otherwise they are zero-weighted (skipped)."""
    if open_axes:
        mutations = [
            {"name": "axis_resample",           "kind": "single_axis",           "weight": 0.45},
            {"name": "coherent_paradigm_shift", "kind": "multi_axis_correlated", "weight": 0.25},
            {"name": "llm_proposal",            "kind": "llm_directed",          "weight": 0.25},
            {"name": "llm_new_axis",            "kind": "llm_directed",          "weight": 0.05},
        ]
    else:
        mutations = [
            {"name": "axis_resample",           "kind": "single_axis",           "weight": 0.5},
            {"name": "coherent_paradigm_shift", "kind": "multi_axis_correlated", "weight": 0.3},
            {"name": "llm_proposal",            "kind": "llm_directed",          "weight": 0.0},
            {"name": "llm_new_axis",            "kind": "llm_directed",          "weight": 0.0},
        ]
    return {
        "mutations": mutations,
        "crossovers": [
            {"name": "uniform",   "kind": "axis_uniform",     "weight": 0.5},
            {"name": "one_point", "kind": "schema_partition", "weight": 0.5},
            {"name": "llm_merge", "kind": "llm_directed",     "weight": 0.0},
        ],
    }


# Backward-compat shim — older callers expect a dict, not a function.
DEFAULT_OPERATORS = default_operators(open_axes=False)

DEFAULT_SCENARIO_WEIGHTS: dict[str, dict[str, float]] = {
    "conservative":    {"trend_alignment": 0.45, "cross_task_generality": 0.20, "implementability": 0.15, "evolvability": 0.10, "frontier_coverage": 0.05, "novelty": 0.05},
    "innovative":      {"novelty": 0.35, "frontier_coverage": 0.30, "evolvability": 0.15, "trend_alignment": 0.05, "cross_task_generality": 0.10, "implementability": 0.05},
    "general_purpose": {"cross_task_generality": 0.40, "implementability": 0.20, "trend_alignment": 0.15, "evolvability": 0.10, "frontier_coverage": 0.10, "novelty": 0.05},
}


def _decls_to_dict(decls: list[Any]) -> dict[str, Any]:
    """Treat a flat list of Assignments as a dict (last writer wins)."""
    out: dict[str, Any] = {}
    for d in decls:
        if isinstance(d, Assignment):
            out[d.key] = d.value
    return out


def _split_csv(value: Any) -> list[str]:
    """Accept either a list or a comma-separated string."""
    if isinstance(value, list):
        return [str(v).strip() for v in value]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    raise TypeError(f"cannot interpret {value!r} as a list of axes")


def lower(ast: AiceFile) -> dict[str, Any]:
    top_assigns = _decls_to_dict([d for d in ast.decls if isinstance(d, Assignment)])
    top_blocks = [d for d in ast.decls if isinstance(d, Block)]

    out: dict[str, Any] = {
        "name": ast.name,
        "task": top_assigns.get("task", ""),
        "schema_ref": top_assigns.get("gene_schema", ""),
    }

    # search
    search_block = next((b for b in top_blocks if b.kind == "search"), None)
    search = _decls_to_dict(search_block.decls) if search_block else {}
    out["search"] = {
        "algorithm": search.get("algorithm", "map_elites"),
        "cell_axes": _split_csv(search.get("cell_axes", "paradigm")),
        "generations": int(search.get("generations", 30)),
        "seed_count": int(search.get("seed_count", 8)),
        "open_axes": bool(search.get("open_axes", False)),
        "rng_seed": int(search.get("rng_seed", 42)),
    }

    # operators (use defaults if absent — varies with open_axes)
    ops_block = next((b for b in top_blocks if b.kind == "operators"), None)
    if ops_block is None:
        out["operators"] = default_operators(open_axes=out["search"]["open_axes"])
    else:
        # nested blocks inside operators: mutations { ... } / crossovers { ... }
        ops: dict[str, list[dict[str, Any]]] = {"mutations": [], "crossovers": []}
        for inner in ops_block.decls:
            if isinstance(inner, Block) and inner.kind in ops:
                for op in inner.decls:
                    if isinstance(op, Block):
                        op_dict = _decls_to_dict(op.decls)
                        op_dict["name"] = op.name or op_dict.get("name", "")
                        ops[inner.kind].append(op_dict)
        # fall back to defaults if any side empty
        if not ops["mutations"]:
            ops["mutations"] = default_operators(open_axes=out["search"]["open_axes"])["mutations"]
        if not ops["crossovers"]:
            ops["crossovers"] = default_operators(open_axes=out["search"]["open_axes"])["crossovers"]
        out["operators"] = ops

    # evaluation_tasks
    eval_block = next((b for b in top_blocks if b.kind == "evaluation_tasks"), None)
    tasks: list[str] = []
    if eval_block is not None:
        for inner in eval_block.decls:
            if isinstance(inner, Block) and inner.kind == "task" and inner.name:
                tasks.append(inner.name)
    # reviewers
    rev_block = next((b for b in top_blocks if b.kind == "reviewers"), None)
    reviewers: list[dict[str, Any]] = []
    if rev_block is not None:
        for inner in rev_block.decls:
            if isinstance(inner, Block) and inner.kind == "reviewer" and inner.name:
                rd = _decls_to_dict(inner.decls)
                reviewers.append({
                    "name": inner.name,
                    "persona": rd.get("persona", ""),
                    "weight": float(rd.get("weight", 1.0 / max(1, len(rev_block.decls)))),
                })
    out["evaluation"] = {
        "tasks": tasks,
        "evaluator": top_assigns.get("evaluator", "mock_v1"),
        "reviewers": reviewers,
    }

    # meta_fitness
    mf_block = next((b for b in top_blocks if b.kind == "meta_fitness"), None)
    out["meta_fitness"] = _decls_to_dict(mf_block.decls) if mf_block else {}

    # ranking
    rk_block = next((b for b in top_blocks if b.kind == "ranking"), None)
    rk_top = _decls_to_dict(rk_block.decls) if rk_block else {}
    scenarios = rk_top.get("scenarios", list(DEFAULT_SCENARIO_WEIGHTS.keys()))
    if isinstance(scenarios, str):
        scenarios = _split_csv(scenarios)
    sw_block = None
    if rk_block is not None:
        sw_block = next((b for b in rk_block.decls if isinstance(b, Block) and b.kind == "scenario_weights"), None)
    if sw_block is not None:
        scenario_weights: dict[str, dict[str, float]] = {}
        for inner in sw_block.decls:
            if isinstance(inner, Block) and inner.name:
                scenario_weights[inner.name] = _decls_to_dict(inner.decls)
    else:
        scenario_weights = {s: DEFAULT_SCENARIO_WEIGHTS.get(s, {}) for s in scenarios}
    out["ranking"] = {
        "strategy": rk_top.get("strategy", "pareto_then_pairwise"),
        "scenarios": scenarios,
        "scenario_weights": scenario_weights,
        "top_k": int(rk_top.get("top_k", 3)),
    }

    return out


def parse_aice_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    src = p.read_text(encoding="utf-8")
    ast = parse(src)
    spec = lower(ast)
    # If schema_ref is relative, leave it relative — CLI resolves it.
    return spec


def aice_to_ga_json(in_path: str | Path, out_path: str | Path) -> dict[str, Any]:
    spec = parse_aice_file(in_path)
    Path(out_path).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return spec
