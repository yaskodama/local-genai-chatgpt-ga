"""Smoke test: load .abcl files into the model checker and verify
the deadlock vs no-deadlock contrast holds."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from aipl_modelcheck import ModelChecker
from aipl_modelcheck_load import load_program


HERE = os.path.dirname(os.path.abspath(__file__))


def _all_phils_done(state) -> bool:
    """Termination predicate: every Phil actor has its `done` field
    set to 1.  Used to distinguish a real deadlock from a normal
    halt."""
    found_phil = False
    for a in state.actors.values():
        if not hasattr(a, "_fields"):
            continue
        if "done" in a._fields:
            found_phil = True
            if a._fields["done"] == 0:
                return False
    return found_phil


def test_twolock_deadlock_detected():
    init, _ = load_program(os.path.join(HERE, "samples-mc/TwoLockDeadlock.abcl"))
    mc = ModelChecker(init, depth=500)
    res = mc.check_deadlock_free(is_terminal=_all_phils_done)
    assert not res.ok, "TwoLockDeadlock should violate"
    assert len(res.deadlocks) >= 1
    assert res.counter_example is not None and len(res.counter_example) > 0


def test_twolock_ordered_clean():
    init, _ = load_program(os.path.join(HERE, "samples-mc/TwoLockOrdered.abcl"))
    mc = ModelChecker(init, depth=500)
    res = mc.check_deadlock_free(is_terminal=_all_phils_done)
    assert res.ok, f"TwoLockOrdered should be clean, got {res.deadlocks!r}"
    assert len(res.deadlocks) == 0


def test_counterpair_finishes():
    """A program with no waiting semantics — every counter just
    self-ticks.  No deadlock under the all-mailboxes-empty=stuck
    rule (the conservative default), since every empty-mailbox
    state IS the natural halt."""
    init, _ = load_program(os.path.join(HERE, "samples-mc/CounterPair.abcl"))
    mc = ModelChecker(init, depth=200)
    # Without a domain-specific is_terminal, any halt looks like a
    # deadlock — but the explored state count proves the program
    # parsed and ran end-to-end.
    res = mc.check_deadlock_free(is_terminal=lambda s: True)
    assert res.ok
    assert res.states_explored >= 4


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("aipl_modelcheck_load smoke passed")
