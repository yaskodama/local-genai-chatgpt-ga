"""Phase 9: LLM-driven proposers for new axis values and entirely new axes.

When `search.open_axes = true`, the MAP-Elites loop can call these to
extend the gene schema *during search*. Two modes:

  * deterministic mock — picks from a curated bank of speculative PL
    concepts so tests can run without an API key.
  * real LLM — uses abcl_ai.call_ai to ask the model for a novel value
    or axis, given the task context and the current schema.

Discovered (axis, value) pairs are registered into the schema in place;
later mutations can sample them like any predefined value."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional

from .schema import GeneSchema


_REPO = Path(__file__).resolve().parents[2]
_PYAIPL = _REPO / "src" / "python-aipl"
if str(_PYAIPL) not in sys.path:
    sys.path.insert(0, str(_PYAIPL))

try:
    import aipl_ai  # type: ignore
    _AI_OK = True
except ImportError:
    _AI_OK = False


# Curated bank of speculative PL concepts — values an LLM might propose
# for the standard schema axes. Mock proposer picks deterministically
# from this so tests stay reproducible.
SPECULATIVE_VALUES: dict[str, list[str]] = {
    "paradigm": [
        "Probabilistic", "LLM_Native", "Differentiable",
        "Quantum_Aware", "Gradual", "Verified_Imperative",
    ],
    "state_representation": [
        "proof_carrying", "linear_resource", "session_typed",
        "differentiable_state",
    ],
    "concurrency_model": [
        "software_transactional_memory", "verified_actors",
        "deterministic_parallelism", "session_concurrency",
    ],
    "type_safety": [
        "refinement", "verified", "self_describing", "gradual_dependent",
    ],
    "effect_handling": [
        "row_polymorphic", "modal_effects", "linear_effects",
        "verified_effects",
    ],
    "ownership_model": [
        "region_based", "fractional", "uniqueness_typed",
        "ownership_inferred",
    ],
}


# New axes a forward-looking LLM might invent (axis_name, initial_values).
SPECULATIVE_NEW_AXES: list[tuple[str, list[str]]] = [
    ("differentiable_types",   ["none", "partial", "full"]),
    ("verification_level",     ["none", "type_check", "model_check", "full_proof"]),
    ("effect_polymorphism",    ["closed", "open", "row"]),
    ("memory_safety",          ["unsafe", "checked", "proven"]),
    ("ai_native_intrinsics",   ["none", "tensor_ops", "differentiable_ops", "agent_ops"]),
]


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _strip_quotes_and_punct(s: str) -> str:
    return re.sub(r"[\s\"'`,;:.()]+", "", s).strip()


def _parse_one_token(text: str) -> str:
    """Pull the first identifier-like token from an LLM reply."""
    if not text:
        return ""
    # Try first non-whitespace word.
    m = re.search(r"[A-Za-z_][A-Za-z_0-9]*", text)
    return m.group(0) if m else _strip_quotes_and_punct(text.split()[0]) if text.split() else ""


def propose_axis_value_mock(axis: str, schema: GeneSchema, rng) -> Optional[str]:
    """Deterministic fallback: pick a speculative value not yet present."""
    bank = SPECULATIVE_VALUES.get(axis, [])
    if not bank:
        return None
    existing = set(schema.axes.get(axis, []))
    candidates = [v for v in bank if v not in existing]
    if not candidates:
        return None
    return rng.choice(candidates)


def propose_axis_value_ai(axis: str, schema: GeneSchema, task_context: str = "") -> Optional[str]:
    if not _AI_OK:
        return None
    existing = ", ".join(schema.axes.get(axis, []))
    prompt = (
        f"プログラミング言語の遺伝子軸 '{axis}' の既存値: {existing}\n"
        f"タスク文脈: {task_context}\n\n"
        "次世代言語が追加すべき新しい値を1つだけ提案してください。"
        "識別子1語のみ (snake_case か CamelCase)。説明や前置きは禁止。"
    )
    try:
        reply = aipl_ai.call_ai(prompt, system="あなたはプログラミング言語設計者です。", max_tokens=16)
    except Exception:
        return None
    token = _parse_one_token(reply)
    if not token or token in schema.axes.get(axis, []):
        return None
    return token


def propose_new_axis_mock(schema: GeneSchema, rng) -> Optional[tuple[str, list[str]]]:
    candidates = [(name, vals) for name, vals in SPECULATIVE_NEW_AXES if name not in schema.axes]
    if not candidates:
        return None
    return rng.choice(candidates)


def propose_new_axis_ai(schema: GeneSchema, task_context: str = "") -> Optional[tuple[str, list[str]]]:
    if not _AI_OK:
        return None
    existing = ", ".join(schema.axes.keys())
    prompt = (
        f"既存の遺伝子軸: {existing}\n"
        f"タスク文脈: {task_context}\n\n"
        "次世代プログラミング言語を特徴付けるかもしれない、新しい軸を1つ提案してください。\n"
        "1行目: 軸名 (snake_case)\n"
        "2行目以降: 許容値をカンマ区切りで (3〜5個、最も貧弱→最も強力の順)\n"
        "説明・前置きは禁止。"
    )
    try:
        reply = aipl_ai.call_ai(prompt, system="あなたはプログラミング言語設計者です。", max_tokens=80)
    except Exception:
        return None
    if not reply:
        return None
    lines = [ln.strip() for ln in reply.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    name = _parse_one_token(lines[0])
    if not name or name in schema.axes:
        return None
    raw_values = lines[1].replace("、", ",")
    values = [_strip_quotes_and_punct(v) for v in raw_values.split(",")]
    values = [v for v in values if v]
    if len(values) < 2:
        return None
    return name, values
