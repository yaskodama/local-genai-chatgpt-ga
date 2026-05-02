"""CLI entry point for the Python ABCL/c+ interpreter.

Usage:
    python3 abcl_main.py program.abcl [--timeout 2.0] [--idle-ms 120]
"""

import argparse
import os
import sys

# Allow running this file directly from inside src/python-abcl/.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from abcl_parser import parse_file
from abcl_interp import Interpreter


def main():
    ap = argparse.ArgumentParser(prog="python-abcl")
    ap.add_argument("source", help="path to a .abcl file")
    ap.add_argument("--timeout", type=float, default=2.0,
                    help="max seconds to wait for actors to drain (default 2.0)")
    ap.add_argument("--idle-ms", type=int, default=120,
                    help="ms of consecutive idle before exiting (default 120)")
    ap.add_argument("--ast", action="store_true",
                    help="print the parsed AST and exit")
    args = ap.parse_args()

    try:
        program = parse_file(args.source)
    except Exception as e:
        print(f"[parse error] {e}", file=sys.stderr)
        sys.exit(1)

    if args.ast:
        from pprint import pprint
        pprint(program)
        return

    interp = Interpreter(program)
    try:
        interp.run(idle_ms=args.idle_ms, timeout_s=args.timeout)
    except KeyboardInterrupt:
        interp.scheduler.shutdown()


if __name__ == "__main__":
    main()
