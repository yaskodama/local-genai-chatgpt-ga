"""Smoke test for tuple literals (組型)."""

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


def test_tuples() -> None:
    out = _run("Tuples.abcl")

    # 1) Heterogeneous tuple from the request
    assert "t1     = (1, 20, test)" in out
    assert "typeof(t1) = tuple(int, int, string)" in out

    # 2) Nested tuple from the request
    assert "t2[0]      = 2" in out
    assert "t2[1][0]   = 3" in out
    assert "t2[1][1]   = 4" in out
    assert "typeof(t2) = tuple(int, tuple(int, int))" in out

    # 3) Empty / 1-tuple
    assert "typeof(empty)  = tuple()" in out
    assert "typeof(single) = tuple(int)" in out
    assert "single[0] = 42" in out

    # 4) Mixed (record / array inside tuple)
    assert "pair[0].name = Alice" in out
    assert "pair[1][2]   = 3" in out
    assert "typeof(pair) = tuple(record{name:string, age:int}, array[int])" in out

    # 5) array_len works on tuples
    assert "array_len(t1) = 3" in out
    assert "array_len(t2) = 2" in out

    # 6) Field-level tuple + actor returning a tuple
    assert "moved = (13, 3)" in out
    assert "typeof(moved) = tuple(int, int)" in out
    assert "origin = (0, 0)" in out
    assert "meta   = (city, 100, 35.6)" in out
    assert "typeof(meta)   = tuple(string, int, float)" in out
    print("OK  Tuples.abcl")


if __name__ == "__main__":
    test_tuples()
    print("OK  tuple tests")
