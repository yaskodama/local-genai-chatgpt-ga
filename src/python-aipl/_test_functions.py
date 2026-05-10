"""Smoke test for user-defined functions + return + trace-inferred typeof."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
ENV = {**os.environ, "AIPL_AI_PROVIDER": "mock"}


def _run(sample: str) -> str:
    result = subprocess.run(
        [sys.executable, "aipl_main.py", f"samples/{sample}"],
        cwd=THIS, env=ENV, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{sample} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def test_functions() -> None:
    out = _run("Functions.abcl")

    # 1) Plain calls
    assert "add(3, 4)   = 7" in out
    assert "fib(10)     = 55" in out                   # recursion
    assert "describe(42) = int : 42" in out

    # 2) FunctionRef + trace-based typeof signatures
    assert "typeof(add)      = function(a:int, b:int) -> int" in out
    assert "typeof(fib)      = function(n:int) -> int" in out
    # describe was first called with int, then with string and float; union shows up.
    assert "typeof(describe) (after mixed args) = function(x:float | int | string) -> string" in out

    # 3) typeof of a function call returns the value's type
    assert "typeof(fib(15)) = int" in out

    # 4) In-class function used by a method, calling a sibling in-class function
    assert "[StatActor] count=3 avg=49.333333333333336" in out
    assert "avg from actor = 49.333333333333336" in out
    print("OK  Functions.abcl")


if __name__ == "__main__":
    test_functions()
    print("OK  user-function tests")
