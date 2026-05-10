"""Command-line entry point. Accepts either a `.aice` (v2) source file or
a `.ga.json` IR. For `.aice`, parses + lowers + persists `.ga.json` next to
the output before running MAP-Elites."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .schema import GeneSchema
from .map_elites import run, dump_run
from .analysis import extract_trend, find_gaps, compute_meta_fitness
from .ranking import rank_all
from .reporter import write_report
from .aice_parser import parse_aice_file
from .aipl_codegen import write_program as write_abcl


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="aice-evolution-v2 MAP-Elites runner")
    p.add_argument("input", help="path to .aice (v2) source or .ga.json IR file")
    p.add_argument("-o", "--out", default="out", help="output directory")
    p.add_argument("--abcl", action="store_true", help="also emit an AIPL orchestrator program (Phase 5)")
    p.add_argument("--no-run", action="store_true", help="skip MAP-Elites run, only emit artifacts (.ga.json/.abcl)")
    p.add_argument("--ai", action="store_true",
                   help="use LLM-backed evaluator + pairwise judge (Phase 6). "
                        "Honours ABCL_AI_PROVIDER (set to 'mock' for free tests)")
    args = p.parse_args(argv)

    in_path = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    if in_path.suffix == ".aice":
        spec = parse_aice_file(in_path)
        ga_path = out_dir / f"{spec['name']}.ga.json"
        ga_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["ga_json"] = ga_path
    else:
        ga_path = in_path
        spec = json.loads(ga_path.read_text(encoding="utf-8"))

    schema_path = Path(spec["schema_ref"])
    if not schema_path.is_absolute():
        candidates = [
            in_path.parent / schema_path,
            in_path.parent.parent / schema_path,
            Path.cwd() / schema_path,
        ]
        for c in candidates:
            if c.exists():
                schema_path = c
                break

    schema = GeneSchema.load(schema_path)

    # Phase 5/6: optionally emit the AIPL orchestrator
    if args.abcl:
        schema_raw = json.loads(schema_path.read_text(encoding="utf-8"))
        # --ai also flips use_ai=1 for the embedded reviewers in ABCL.
        if args.ai:
            spec.setdefault("evaluation", {})["use_ai"] = True
        abcl_path = write_abcl(spec, schema_raw, args.out)
        paths["abcl"] = abcl_path

    if args.no_run:
        print(f"name        : {spec['name']} (no-run)")
        print("artifacts:")
        for k, v in paths.items():
            print(f"  {k:10s}  {v}")
        return 0

    eval_fn = None
    if args.ai:
        from .ai_evaluator import evaluate_ai, composite_fitness_ai
        from .operators import set_proposer_mode
        set_proposer_mode("ai")
        reviewers = spec.get("evaluation", {}).get("reviewers", [])
        eval_fn = lambda g, sch, tasks: evaluate_ai(g, sch, tasks, reviewers)  # noqa: E731
        composite_fn = composite_fitness_ai
    else:
        composite_fn = None

    result = run(spec, schema, evaluate_fn=eval_fn, composite_fn=composite_fn)
    paths.update(dump_run(result, args.out, spec["name"]))

    trend = extract_trend(result)
    gaps = find_gaps(result, spec["search"]["cell_axes"])
    meta = compute_meta_fitness(result, trend)
    rankings = rank_all(spec, result, meta, use_ai_pairwise=args.ai)
    report_paths = write_report(args.out, spec["name"], spec, result, trend, gaps, meta, rankings)
    paths.update(report_paths)

    print(f"name        : {spec['name']}")
    print(f"individuals : {len(result.population)}")
    print(f"cells filled: {len(result.elite_map)}")
    champs = sorted(result.champions(), key=lambda i: -i.composite)
    print("top elites  :")
    for ind in champs[:5]:
        print(f"  {ind.cell}  composite={ind.composite:.3f}  (id={ind.id}, gen={ind.generation})")
    print("trend (top 3 axes):")
    for axis, v in sorted(trend.normalized().items(), key=lambda kv: -abs(kv[1]))[:3]:
        print(f"  {axis:22s}  {v:+.2f}")
    for r in rankings:
        if not r.entries:
            continue
        top = r.entries[0]
        print(f"scenario {r.scenario:18s} -> #1 id={top.individual_id} composite={top.composite:.3f} pareto={top.pareto_rank}")
    print("artifacts:")
    for k, v in paths.items():
        print(f"  {k:10s}  {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
