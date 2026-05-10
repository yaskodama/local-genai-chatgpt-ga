"""CLI entry point for the Python AIPL interpreter.

Usage:
    python3 abcl_main.py program.abcl [--timeout 2.0] [--idle-ms 120]
"""

import argparse
import os
import sys

# Allow running this file directly from inside src/python-abcl/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aipl_parser import parse_file
from aipl_interp import Interpreter


def main():
    ap = argparse.ArgumentParser(prog="python-abcl")
    ap.add_argument("source", nargs="?",
                    help="path to a .abcl file (omit to start an interactive REPL)")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="max seconds to wait for actors to drain (default 2.0)")
    ap.add_argument("--idle-ms", type=int, default=120,
                    help="ms of consecutive idle before exiting (default 120)")
    ap.add_argument("--ast", action="store_true",
                    help="print the parsed AST and exit")
    ap.add_argument("--type-check", action="store_true",
                    help="run the gradual type checker before executing; print "
                         "any issues to stderr (program still runs unless --strict)")
    ap.add_argument("--strict", action="store_true",
                    help="when combined with --type-check, abort on type errors")
    ap.add_argument("--transient", action="store_true",
                    help="(Phase 16) insert runtime type checks at every "
                         "annotated boundary (call args, var-decl rhs); "
                         "raise TransientCastError on any -> T mismatch")
    ap.add_argument("--dashboard", type=int, default=0, metavar="PORT",
                    help="serve a live AI-OS usage dashboard on http://127.0.0.1:PORT/")
    args = ap.parse_args()

    if args.dashboard:
        from aipl_dashboard import start as start_dashboard
        start_dashboard(args.dashboard)

    if args.source is None:
        # Interactive REPL — useful for poking at actors live or
        # exploring the language without writing a file first.
        from aipl_interp import run_repl
        run_repl()
        return

    try:
        program = parse_file(args.source)
    except Exception as e:
        print(f"[parse error] {e}", file=sys.stderr)
        sys.exit(1)

    if args.ast:
        from pprint import pprint
        pprint(program)
        return

    if args.type_check:
        from aipl_typeck import check as _typeck
        from aipl_interp import BUILTIN_SIGNATURES
        issues = _typeck(program, BUILTIN_SIGNATURES)
        if issues:
            for i in issues:
                print(i.render(), file=sys.stderr)
            print(f"[type] {len(issues)} issue(s).", file=sys.stderr)
            if args.strict:
                sys.exit(2)
        else:
            print("[type] no issues.", file=sys.stderr)

    interp = Interpreter(program, transient_checks=args.transient)
    try:
        interp.run(idle_ms=args.idle_ms, timeout_s=args.timeout)
    except KeyboardInterrupt:
        interp.scheduler.shutdown()


if __name__ == "__main__":
    main()
