"""Smoke test: export 4 philosophers .abcl to .pml files.

Verifies that the AIPL → Promela exporter produces well-formed
output for the philosophers samples.  Does NOT run SPIN itself
(SPIN is a separate brew install; the exporter is portable Python).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from aipl_to_promela import emit_promela
from aipl_parser import parse_file


HERE = os.path.dirname(os.path.abspath(__file__))


def _check_pml(src_path: str, expected_classes: list[str],
               expected_methods: list[str]) -> None:
    prog = parse_file(src_path)
    name = os.path.splitext(os.path.basename(src_path))[0]
    pml = emit_promela(prog, name)

    assert "mtype = {" in pml
    assert "init {" in pml
    assert "atomic {" in pml
    for c in expected_classes:
        assert f"proctype {c}" in pml, f"{c} proctype missing"
        assert f"chan mb_{c.lower()}" in pml, f"{c} mailbox missing"
    for m in expected_methods:
        assert f"meth == m_{m}" in pml, f"m_{m} dispatch missing"
    assert "ltl progress { <> all_phils_done }" in pml, "LTL clause missing"
    assert "all_phils_done" in pml


def test_philosophers_naive():
    _check_pml(
        os.path.join(HERE, "samples-mc/PhilosophersNaive.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_methods=["request", "release", "init", "try_eat", "granted"],
    )


def test_philosophers_ordered():
    _check_pml(
        os.path.join(HERE, "samples-mc/PhilosophersOrdered.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_methods=["request", "release", "init", "try_eat", "granted"],
    )


def test_philosophers5_naive():
    _check_pml(
        os.path.join(HERE, "samples-mc/Philosophers5Naive.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_methods=["request", "granted"],
    )


def test_philosophers5_ordered():
    _check_pml(
        os.path.join(HERE, "samples-mc/Philosophers5Ordered.abcl"),
        expected_classes=["Fork", "Phil"],
        expected_methods=["request", "granted"],
    )


if __name__ == "__main__":
    for nm, fn in list(globals().items()):
        if nm.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {nm}")
    print("aipl_to_promela smoke passed")
