"""Smoke test for multi-dim arrays + dynamic sizes in AIPL."""

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


def test_multi_dim_arrays() -> None:
    out = _run("MultiDimArrays.abcl")

    # 1) 2D local array `var pad[R][C] = 7;` with R=3, C=6, diagonal updates
    assert "Pad 3x6 (default 7)" in out
    # Row 0: diagonal cell = 0
    assert "0 7 7 7 7 7" in out
    # Row 1: diagonal cell = 10
    assert "7 10 7 7 7 7" in out
    # Row 2: diagonal cell = 20
    assert "7 7 20 7 7 7" in out

    # 2) 1D dynamic size `var sieve[4+1] = 1;`
    assert "Sieve of length 5" in out
    assert "sieve[0] = 0" in out  # explicitly cleared
    assert "sieve[1] = 0" in out  # explicitly cleared
    assert "sieve[2] = 1" in out  # default 1
    assert "sieve[4] = 1" in out

    # 3) 2D field-level array via Matrix actor
    assert "Matrix 4x5:" in out
    assert "0 1 2 3 4" in out      # i + j for i=0
    assert "3 4 5 6 7" in out      # i + j for i=3
    assert "trace = 12" in out     # 0+2+4+6 (since cols=5, lim=min=4)

    # 4) 3D cube
    assert "cube[1][2][3] = 999" in out
    assert "layer 0 row 0: 100 -1 -1 -1" in out
    assert "layer 0 row 2: -1 42 -1 -1" in out
    assert "layer 1 row 2: -1 -1 -1 999" in out
    print("OK  MultiDimArrays.abcl")


def test_single_dim_still_works() -> None:
    """Make sure the single-dim Arrays.abcl from the prior turn still passes
    after the multi-dim refactor (regression check)."""
    out = _run("Arrays.abcl")
    assert "workers[0] = alice" in out
    assert "sum = 53" in out
    assert "bucket[3] = 3" in out
    assert "label[2] = Wed" in out
    print("OK  Arrays.abcl (regression)")


if __name__ == "__main__":
    test_multi_dim_arrays()
    test_single_dim_still_works()
    print("OK  multi-dim + dynamic-size tests")
