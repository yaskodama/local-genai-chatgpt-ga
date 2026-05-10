"""Phase 6 tests: parse_score, AI evaluator wiring, AIPL codegen ai mode.

All tests run with ABCL_AI_PROVIDER=mock so no API key is required."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("ABCL_AI_PROVIDER", "mock")

from src.ai_evaluator import parse_score, evaluate_ai  # type: ignore
from src.aice_parser import parse_aice_file  # type: ignore
from src.aipl_codegen import write_program  # type: ignore
from src.schema import GeneSchema  # type: ignore


def test_parse_score_basic() -> None:
    assert parse_score("0.7") == 0.7
    assert parse_score("0.5") == 0.5
    assert parse_score("1.0") == 1.0
    assert parse_score("0") == 0.0
    assert abs(parse_score("Score: 0.42 (good)") - 0.42) < 1e-9
    assert parse_score("75") == 0.75       # tolerate percent
    assert parse_score("garbage no number") == 0.5
    assert parse_score("") == 0.5
    assert parse_score("-0.3") == 0.0
    assert parse_score("1.5") == 1.0       # clamp


def test_evaluate_ai_with_mock_provider() -> None:
    schema = GeneSchema.load(ROOT / "schemas/programming_paradigm.schema.json")
    spec = parse_aice_file(ROOT / "examples/NextLanguagePrediction.aice")
    genome = {
        "paradigm": "ParallelOOP",
        "state_representation": "symbol_owned",
        "concurrency_model": "actor_messages",
        "type_safety": "high",
        "effect_handling": "algebraic_effects",
        "ownership_model": "borrow_check",
    }
    scores = evaluate_ai(genome, schema, spec["evaluation"]["tasks"], spec["evaluation"]["reviewers"])
    # Mock LLM returns canned text with no number → parse_score falls back
    # to 0.5. That's the expected, deterministic test signal.
    for k, v in scores.items():
        if k.startswith("task::") or k in ("cross_task_generality", "paradigm_match"):
            assert 0.0 <= v <= 1.0, f"{k}={v} out of [0,1]"
    assert "task::TrafficLight" in scores


def test_codegen_ai_mode_flag() -> None:
    spec = parse_aice_file(ROOT / "examples/NextLanguagePrediction.aice")
    spec.setdefault("evaluation", {})["use_ai"] = True
    schema = json.loads((ROOT / "schemas/programming_paradigm.schema.json").read_text(encoding="utf-8"))
    target = write_program(spec, schema, ROOT / "out")
    src = target.read_text(encoding="utf-8")
    # Reviewer constructors should have the third arg = 1 in AI mode.
    assert "new Reviewer(" in src
    assert ", 1, " in src, "use_ai=1 not propagated to Reviewer constructor"
    # parse_score / DigitOps must be present.
    assert "method parse_score" in src
    assert "class DigitOps" in src
    assert "ai_call_with_system" in src


if __name__ == "__main__":
    test_parse_score_basic()
    test_evaluate_ai_with_mock_provider()
    test_codegen_ai_mode_flag()
    print("OK  ai/codegen tests")
