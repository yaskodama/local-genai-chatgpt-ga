"""LTL (Linear Temporal Logic) examples on top of aipl_modelcheck.

Demonstrates G (always) and F (eventually) over the bounded reachable
set of the dining-philosophers system.

Properties checked on each variant:

  φ1  (safety):  G ¬all_hungry_and_holding_lo
                 — never reach a state where every philosopher
                 holds its low fork while still hungry.

  φ2  (progress under bound): F all_done
                 — eventually every philosopher reaches `done`.
                 (This is bounded so it under-approximates real
                 liveness; it tells us "some schedule exists" not
                 "every schedule terminates".)

Run:
  python3 modelcheck/ltl_examples.py
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aipl_modelcheck import ModelChecker, LTL  # noqa: E402
from modelcheck.philosophers import (              # noqa: E402
    init_naive, init_ordered, Philosopher
)


# ---------- atomic predicates ------------------------------------------

def all_hungry_holding_lo(state) -> bool:
    """All philosophers in state `hungry` and holding their low fork."""
    phils = [a for a in state.actors.values()
             if isinstance(a, Philosopher)]
    if not phils:
        return False
    return all(p.state == "hungry" and p.got_lo for p in phils)


def all_done(state) -> bool:
    phils = [a for a in state.actors.values()
             if isinstance(a, Philosopher)]
    return bool(phils) and all(p.state == "done" for p in phils)


# ---------- LTL formulas ----------------------------------------------

# G ¬(全員 hungry かつ lo を持っている)
phi1_safety = LTL.Globally(
    LTL.Not(LTL.Atom(all_hungry_holding_lo, name="all_hungry_holding_lo"))
)

# F all_done
phi2_progress = LTL.Eventually(
    LTL.Atom(all_done, name="all_done")
)


# ---------- driver ----------------------------------------------------

def report(label: str, init_fn, formulas):
    print(f"=== {label} ===")
    mc = ModelChecker(init_fn, depth=2000)
    for name, formula in formulas:
        r = mc.check(formula)
        verdict = "✓" if r.ok else "✗"
        print(f"  {verdict}  {name}    "
              f"({r.states_explored} states, max depth {r.max_depth_reached})")
    print()


def main():
    formulas = [
        ("φ1: G ¬all_hungry_holding_lo (safety)", phi1_safety),
        ("φ2: F all_done                (progress)", phi2_progress),
    ]
    print("LTL bounded-model-check on dining philosophers (N=3, meals=1)\n")
    report("naive   (deadlock-prone)", init_naive(3, 1), formulas)
    report("ordered (deadlock-free)",  init_ordered(3, 1), formulas)


if __name__ == "__main__":
    main()
