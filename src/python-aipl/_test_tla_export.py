"""Smoke test: export 4 philosophers .abcl to .tla + .cfg pairs.

Verifies that the AIPL → TLA+ exporter produces well-formed output
files for the philosophers samples.  Does NOT run TLC (TLC requires
java + tla2tools.jar; the exporter alone is portable Python)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from aipl_to_tla import emit_module
from aipl_parser import parse_file


HERE = os.path.dirname(os.path.abspath(__file__))


def _check_module(src_path: str, expected_classes: list[str],
                  expected_actions: list[str]) -> None:
    prog = parse_file(src_path)
    name = os.path.splitext(os.path.basename(src_path))[0]
    tla, cfg = emit_module(prog, name)
    assert f"---- MODULE {name} ----" in tla
    assert "EXTENDS Integers, Sequences, FiniteSets, TLC" in tla
    assert "Init ==" in tla
    assert "Spec == Init /\\ [][Next]_vars" in tla
    assert "NoDeadlock ==" in tla
    for c in expected_classes:
        assert f"{c}Set ==" in tla, f"{c}Set missing in {name}"
    for action in expected_actions:
        assert action in tla, f"{action} missing in {name}"
    assert "SPECIFICATION Spec" in cfg
    assert "INVARIANT NoDeadlock" in cfg
    assert "CHECK_DEADLOCK FALSE" in cfg


def test_philosophers_naive():
    _check_module(
        os.path.join(HERE, "samples-mc/PhilosophersNaive.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_actions=["Fork_request", "Fork_release",
                          "Phil_init", "Phil_try_eat", "Phil_granted"],
    )


def test_philosophers_ordered():
    _check_module(
        os.path.join(HERE, "samples-mc/PhilosophersOrdered.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_actions=["Fork_request", "Fork_release",
                          "Phil_init", "Phil_try_eat", "Phil_granted"],
    )


def test_philosophers5_naive():
    _check_module(
        os.path.join(HERE, "samples-mc/Philosophers5Naive.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_actions=["Fork_request", "Phil_granted"],
    )


def test_philosophers5_ordered():
    _check_module(
        os.path.join(HERE, "samples-mc/Philosophers5Ordered.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_actions=["Fork_request", "Phil_granted"],
    )


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("aipl_to_tla smoke passed")
