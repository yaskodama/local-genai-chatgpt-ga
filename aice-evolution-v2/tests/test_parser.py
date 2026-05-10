"""Unit tests for the .aice v2 parser + lowering."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.aice_parser import parse, lower, parse_aice_file  # type: ignore


SAMPLE = """
aice DemoSpec {
  dialect = "aice_evolution_v2";
  task = "demo task";
  gene_schema = "schemas/programming_paradigm.schema.json";

  evaluation_tasks {
    task TrafficLight  { spec = "x"; }
    task BankAccount   { spec = "y"; }
  }

  search {
    algorithm   = "map_elites";
    cell_axes   = "paradigm, concurrency_model";
    generations = 12;
    seed_count  = 4;
    open_axes   = true;
  }

  meta_fitness {
    trend_alignment = 0.30;
    novelty         = 0.20;
  }

  ranking {
    strategy  = "pareto_then_pairwise";
    scenarios = ["conservative", "innovative"];
    top_k     = 2;
  }

  reviewers {
    reviewer Plausibility { persona = "P"; }
    reviewer Coherence    { persona = "C"; }
  }
}
"""


def test_parse_round_trip() -> None:
    ast = parse(SAMPLE)
    assert ast.name == "DemoSpec"
    spec = lower(ast)

    assert spec["name"] == "DemoSpec"
    assert spec["task"] == "demo task"
    assert spec["schema_ref"].endswith("programming_paradigm.schema.json")

    assert spec["search"]["cell_axes"] == ["paradigm", "concurrency_model"]
    assert spec["search"]["generations"] == 12
    assert spec["search"]["seed_count"] == 4
    assert spec["search"]["open_axes"] is True

    assert spec["evaluation"]["tasks"] == ["TrafficLight", "BankAccount"]
    rev_names = [r["name"] for r in spec["evaluation"]["reviewers"]]
    assert rev_names == ["Plausibility", "Coherence"]

    assert spec["meta_fitness"]["trend_alignment"] == 0.30
    assert spec["meta_fitness"]["novelty"] == 0.20

    assert spec["ranking"]["scenarios"] == ["conservative", "innovative"]
    assert spec["ranking"]["top_k"] == 2
    # default scenario_weights filled in
    assert "conservative" in spec["ranking"]["scenario_weights"]
    assert "innovative" in spec["ranking"]["scenario_weights"]

    # default operators filled in
    assert any(m["name"] == "axis_resample" for m in spec["operators"]["mutations"])
    assert any(c["name"] == "uniform" for c in spec["operators"]["crossovers"])


def test_real_example_file() -> None:
    spec = parse_aice_file(ROOT / "examples/NextLanguagePrediction.aice")
    assert spec["name"] == "NextLanguagePrediction"
    assert spec["search"]["cell_axes"] == ["paradigm", "concurrency_model", "type_safety"]
    assert spec["evaluation"]["tasks"] == ["TrafficLight", "BankAccount", "Philosophers"]
    rev_names = [r["name"] for r in spec["evaluation"]["reviewers"]]
    assert rev_names == ["Plausibility", "Coherence", "Implementability"]


if __name__ == "__main__":
    test_parse_round_trip()
    test_real_example_file()
    print("OK  parser tests")
