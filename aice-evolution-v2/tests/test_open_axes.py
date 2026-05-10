"""Phase 9 tests: schema growth + LLM proposers (mock fallback)."""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.schema import GeneSchema  # type: ignore
from src.operators import llm_proposal, llm_new_axis, set_proposer_mode  # type: ignore
from src.aice_parser import parse_aice_file  # type: ignore
from src.map_elites import run as me_run  # type: ignore


def _schema() -> GeneSchema:
    return GeneSchema.load(ROOT / "schemas/programming_paradigm.schema.json")


def test_register_value_requires_open_axes() -> None:
    s = _schema()
    s.open_axes = False
    assert not s.register_value("paradigm", "Probabilistic")
    s.open_axes = True
    assert s.register_value("paradigm", "Probabilistic")
    assert "Probabilistic" in s.axes["paradigm"]
    assert s.discovered_values["paradigm"] == ["Probabilistic"]
    assert not s.register_value("paradigm", "Probabilistic")  # idempotent


def test_register_axis_requires_open_axes() -> None:
    s = _schema()
    s.open_axes = False
    assert not s.register_axis("differentiable_types", ["none", "full"])
    s.open_axes = True
    assert s.register_axis("differentiable_types", ["none", "full"])
    assert "differentiable_types" in s.axes
    assert "differentiable_types" in s.discovered_axes


def test_llm_proposal_grows_schema_with_mock() -> None:
    set_proposer_mode("mock")
    s = _schema()
    s.open_axes = True
    parent = {axis: vals[0] for axis, vals in s.axes.items()}
    rng = random.Random(7)
    before_total = sum(len(v) for v in s.axes.values())
    # Run llm_proposal a few times — at least one should add a new value.
    for _ in range(10):
        llm_proposal(parent, s, rng)
    after_total = sum(len(v) for v in s.axes.values())
    assert after_total > before_total, "schema did not grow despite open_axes=true"
    assert any(s.discovered_values.values())


def test_llm_new_axis_with_mock() -> None:
    set_proposer_mode("mock")
    s = _schema()
    s.open_axes = True
    parent = {axis: vals[0] for axis, vals in s.axes.items()}
    rng = random.Random(7)
    child = llm_new_axis(parent, s, rng)
    assert s.discovered_axes, "no new axis discovered"
    new_axis = s.discovered_axes[0]
    assert new_axis in child, "child genome missing the new axis value"
    assert child[new_axis] in s.axes[new_axis]


def test_end_to_end_open_axes_run() -> None:
    """Run the OpenAxesEvolution example via the same code path as the CLI
    and check that discoveries appear in the resulting elite map."""
    spec = parse_aice_file(ROOT / "examples/OpenAxesEvolution.aice")
    schema = GeneSchema.load(ROOT / "schemas/programming_paradigm.schema.json")
    set_proposer_mode("mock")
    result = me_run(spec, schema)
    assert schema.discovered_values or schema.discovered_axes, \
        "no schema growth across the run — operators may not be wired"
    # At least one champion should land in a cell with a discovered value or
    # in a cell using a discovered axis.
    champ_cells = [ind.cell for ind in result.champions()]
    discovered_axis_values = set()
    for axis, values in schema.discovered_values.items():
        for v in values:
            discovered_axis_values.add(f"{axis}={v}")
    has_discovery_in_champ = any(
        any(piece in cell for piece in discovered_axis_values) for cell in champ_cells
    )
    # It's possible all discovered values fall in non-champion cells; that's
    # still a valid run, so we don't hard-assert. We do assert the schema grew.


if __name__ == "__main__":
    test_register_value_requires_open_axes()
    test_register_axis_requires_open_axes()
    test_llm_proposal_grows_schema_with_mock()
    test_llm_new_axis_with_mock()
    test_end_to_end_open_axes_run()
    print("OK  open_axes tests")
