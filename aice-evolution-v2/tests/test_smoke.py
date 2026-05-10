"""Smoke test: run MAP-Elites end-to-end on the example .ga.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.schema import GeneSchema  # type: ignore
from src.map_elites import run, dump_run  # type: ignore


def main() -> int:
    spec = json.loads((ROOT / "examples/NextLanguagePrediction.ga.json").read_text(encoding="utf-8"))
    schema = GeneSchema.load(ROOT / "schemas/programming_paradigm.schema.json")

    result = run(spec, schema)
    assert len(result.population) > 0, "no individuals produced"
    assert len(result.elite_map) > 0, "elite map empty"
    for ind in result.champions():
        assert schema.is_coherent(ind.genome), f"incoherent champion: {ind.genome}"

    paths = dump_run(result, ROOT / "out", spec["name"])
    for p in paths.values():
        assert p.exists() and p.stat().st_size > 0, f"missing artifact: {p}"

    print(f"OK  pop={len(result.population)}  cells={len(result.elite_map)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
