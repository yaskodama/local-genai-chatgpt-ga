"""Smoke test: aipl_modelcheck.

Verifies that:
  - naive philosophers report a deadlock (1 state, counter-example trace)
  - ordered philosophers report 0 deadlocks
  - LTL φ1 (safety) is violated on naive, satisfied on ordered
  - LTL φ2 (progress) is satisfied on both (under bounded semantics)
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from aipl_modelcheck import ModelChecker, LTL
from modelcheck.philosophers import (
    init_naive, init_ordered, all_done as termination_pred,
)
from modelcheck.ltl_examples import (
    phi1_safety, phi2_progress,
)


def test_naive_3_has_deadlock():
    mc = ModelChecker(init_naive(3, 1), depth=1000)
    res = mc.check_deadlock_free(is_terminal=termination_pred)
    assert not res.ok, "naive should have at least 1 deadlock"
    assert len(res.deadlocks) >= 1
    assert res.counter_example is not None
    assert len(res.counter_example) > 0


def test_ordered_3_no_deadlock():
    mc = ModelChecker(init_ordered(3, 1), depth=1000)
    res = mc.check_deadlock_free(is_terminal=termination_pred)
    assert res.ok, f"ordered should be deadlock-free, got {res.deadlocks}"
    assert len(res.deadlocks) == 0


def test_naive_3_violates_safety():
    mc = ModelChecker(init_naive(3, 1), depth=1000)
    res = mc.check(phi1_safety)
    assert not res.ok, "naive should violate G ¬all_hungry_holding_lo"


def test_ordered_3_satisfies_safety():
    mc = ModelChecker(init_ordered(3, 1), depth=1000)
    res = mc.check(phi1_safety)
    assert res.ok, "ordered should satisfy G ¬all_hungry_holding_lo"


def test_both_satisfy_progress_under_bound():
    for label, init in [("naive", init_naive(3, 1)),
                        ("ordered", init_ordered(3, 1))]:
        mc = ModelChecker(init, depth=1000)
        res = mc.check(phi2_progress)
        assert res.ok, f"{label} should satisfy F all_done under bound"


def test_naive_5_finds_deadlock():
    mc = ModelChecker(init_naive(5, 1), depth=2000)
    res = mc.check_deadlock_free(is_terminal=termination_pred)
    assert not res.ok, "naive 5 should have a deadlock"
    assert len(res.deadlocks) >= 1


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("aipl_modelcheck smoke passed")
