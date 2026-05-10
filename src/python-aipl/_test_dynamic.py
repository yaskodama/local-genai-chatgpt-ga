"""Smoke test for the AIPL `compile()` and `spawn()` builtins.

Runs the two sample .abcl programs under the python-aipl runtime and
asserts the expected output appears, so the new dynamic-class machinery
doesn't regress."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent

# Use the mock provider so this test runs without API keys.
ENV = {**os.environ, "AIPL_AI_PROVIDER": "mock"}


def _run(sample: str) -> str:
    result = subprocess.run(
        [sys.executable, "aipl_main.py", f"samples/{sample}"],
        cwd=THIS,
        env=ENV,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{sample} exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout


def test_dynamic_basic() -> None:
    out = _run("Dynamic.abcl")
    # Greeter compiled and used three times
    assert "[factory] compiled 1 class(es) for 'Greeter'" in out
    assert "[Greeter#1] hello, Alice" in out
    assert "[Greeter#2] hello, Bob" in out
    assert "[Greeter#3] hello, Carol" in out
    # Counter compiled separately, ticks 1..3
    assert "[factory] compiled 1 class(es) for 'Counter'" in out
    assert "[Counter] tick -> n=1" in out
    assert "[Counter] tick -> n=3" in out
    assert "[Counter] final n=3" in out
    # A second Greeter actor has independent state (count starts at 1).
    assert "[Greeter#1] hello, Dave" in out
    # The original Greeter actor still has its own count (#4 for Eve).
    assert "[Greeter#4] hello, Eve" in out
    print("OK  Dynamic.abcl")


def test_dynamic_worker_pool() -> None:
    out = _run("DynamicWorkerPool.abcl")
    # 3 workers spawned (ids 0..2), 5 jobs run, sum = 4+9+25+49+121 = 208.
    for w in ("[worker 0]", "[worker 1]", "[worker 2]"):
        assert w in out, f"missing worker output: {w}"
    for sq in ("square(2) = 4", "square(3) = 9", "square(5) = 25",
               "square(7) = 49", "square(11) = 121"):
        assert sq in out, f"missing computation: {sq}"
    assert "[manager] sum of squares = 208" in out
    assert "=== final result: 208 ===" in out
    print("OK  DynamicWorkerPool.abcl")


if __name__ == "__main__":
    test_dynamic_basic()
    test_dynamic_worker_pool()
    print("OK  all dynamic-compile tests")
