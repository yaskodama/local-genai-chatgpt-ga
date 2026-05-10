"""Phase 5: smoke-test the AIPL codegen output (parse-only).

We verify the generated `.abcl` contains the expected actor classes
and bootstrap statements. Running it through the AIPL runtime is
covered by a manual command in the README — that takes ~30s and
needs the Python AIPL runtime alongside this directory."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.aice_parser import parse_aice_file  # type: ignore
from src.aipl_codegen import write_program  # type: ignore


def test_codegen_emits_expected_classes() -> None:
    spec = parse_aice_file(ROOT / "examples/NextLanguagePrediction.aice")
    schema_path = ROOT / "schemas/programming_paradigm.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    target = write_program(spec, schema, ROOT / "out")
    assert target.exists(), f"missing generated abcl: {target}"
    src = target.read_text(encoding="utf-8")

    for required_class in ("Util", "Generator", "Reviewer", "Evaluator", "EliteMap", "Lineage", "TaskProfiles", "Worker", "Coordinator"):
        assert f"class {required_class}" in src, f"missing class {required_class}"

    # Bootstrap calls
    assert "var util = new Util();" in src
    assert "var coord = new Coordinator(" in src
    assert "send coord.run();" in src

    # Spec embedded
    assert "paradigm=ParallelOOP" in src       # task profile literal
    assert "seed_count = " in src

    # No self-call deadlocks (the Phase 5 fix)
    assert "now self." not in src, "found re-entrant `now self.X()` (deadlock)"


if __name__ == "__main__":
    test_codegen_emits_expected_classes()
    print("OK  codegen tests")
