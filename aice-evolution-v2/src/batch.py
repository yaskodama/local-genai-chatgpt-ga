"""Phase 7 batch runner: run multiple .aice files end-to-end, then
aggregate trend vectors across them via cross_task.aggregate()."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .cli import main as cli_main
from .cross_task import aggregate, write_report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="aice-evolution-v2 cross-task batch runner")
    p.add_argument("inputs", nargs="+", help="paths to .aice (v2) source files")
    p.add_argument("-o", "--out", default="out", help="output directory")
    p.add_argument("--name", default="cross_task", help="aggregation report name")
    p.add_argument("--ai", action="store_true", help="propagate --ai to each run")
    p.add_argument("--abcl", action="store_true", help="propagate --abcl to each run")
    p.add_argument("--no-aggregate", action="store_true", help="run each .aice but skip aggregation")
    args = p.parse_args(argv)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    ranking_paths: list[Path] = []
    for inp in args.inputs:
        sub_argv = [inp, "-o", str(out)]
        if args.ai:
            sub_argv.append("--ai")
        if args.abcl:
            sub_argv.append("--abcl")
        print(f"\n=== batch: running {inp} ===")
        rc = cli_main(sub_argv)
        if rc != 0:
            print(f"!! {inp} returned {rc}, aborting batch")
            return rc
        # ranking.json was emitted as <name>.ranking.json in `out`.
        # We discover it by matching the .aice basename's `aice <Name>` —
        # cli_main already emitted a `<Name>.ranking.json`. List by mtime.
        candidates = sorted(out.glob("*.ranking.json"), key=lambda p: -p.stat().st_mtime)
        if not candidates:
            print(f"!! no ranking.json produced for {inp}")
            return 1
        ranking_paths.append(candidates[0])
        print(f"   -> {candidates[0].name}")

    # Deduplicate while preserving order (a single .aice run can replace another's
    # ranking.json by mtime; but each .aice has a distinct `<Name>` so files differ).
    seen: set[Path] = set()
    deduped: list[Path] = []
    for p in ranking_paths:
        if p in seen:
            continue
        seen.add(p)
        deduped.append(p)

    if args.no_aggregate or len(deduped) < 2:
        print(f"\n[batch] {len(deduped)} run(s) completed; aggregation skipped.")
        return 0

    print(f"\n=== batch: aggregating {len(deduped)} runs ===")
    result = aggregate(deduped)
    paths = write_report(result, out, args.name)

    universal = [s for s in result.axis_stats if s.sign_agreement >= result.universal_threshold and abs(s.mean) > 0.05]
    print(f"runs        : {[r.name for r in result.runs]}")
    print(f"universal   : {[s.axis for s in universal]}")
    print(f"axis stability (top 5):")
    for s in result.axis_stats[:5]:
        print(f"  {s.axis:22s}  mean={s.mean:+.2f}  std={s.std:.2f}  agree={s.sign_agreement:.0%}")
    print("artifacts:")
    for k, v in paths.items():
        print(f"  {k:13s}  {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
