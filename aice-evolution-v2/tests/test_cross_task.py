"""Phase 7: cross-task aggregation tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.cross_task import aggregate, write_report  # type: ignore


def test_aggregation_finds_universal_axes() -> None:
    rk_paths = sorted((ROOT / "out").glob("*.ranking.json"))
    # Phase 7 example .aice files have already been run by the smoke harness
    # (or by `python -m src.batch ...`); we expect at least 4 of them present.
    expected = {"NextLanguagePrediction", "WebServiceEvolution",
                "DataPipelineEvolution", "CompilerEvolution"}
    available = {p.stem.replace(".ranking", "") for p in rk_paths}
    missing = expected - available
    assert not missing, f"smoke prereq missing: {missing}. Run `python -m src.batch examples/*.aice` first."

    chosen = [p for p in rk_paths if p.stem.replace(".ranking", "") in expected]
    result = aggregate(chosen)

    # Each run contributes a non-empty top_individual_ids set
    for r in result.runs:
        assert len(r.top_individual_ids) > 0, f"no top candidates in {r.name}"

    # Every axis should have stats present and finite
    for s in result.axis_stats:
        assert len(s.values) == len(result.runs)
        assert s.std >= 0.0
        assert 0.0 <= s.sign_agreement <= 1.0

    # At least one axis should be universal (sign-agreement >= threshold).
    universal = [s for s in result.axis_stats
                 if s.sign_agreement >= result.universal_threshold and abs(s.mean) > 0.05]
    assert len(universal) >= 1, "no axis reached cross-task universality"

    # Consensus genome covers all schema axes seen in the runs
    assert "type_safety" in result.consensus_genome
    assert "paradigm" in result.consensus_genome


def test_report_emission() -> None:
    rk_paths = sorted((ROOT / "out").glob("*.ranking.json"))
    expected = {"NextLanguagePrediction", "WebServiceEvolution",
                "DataPipelineEvolution", "CompilerEvolution"}
    chosen = [p for p in rk_paths if p.stem.replace(".ranking", "") in expected]
    result = aggregate(chosen)
    paths = write_report(result, ROOT / "out", "cross_task")
    for k, v in paths.items():
        assert v.exists() and v.stat().st_size > 0, f"missing artifact {k}: {v}"
    md = paths["cross_report"].read_text(encoding="utf-8")
    assert "Universal direction" in md
    assert "Consensus genome" in md


if __name__ == "__main__":
    test_aggregation_finds_universal_axes()
    test_report_emission()
    print("OK  cross-task tests")
