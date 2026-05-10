"""Smoke test for the AIPL `name[N]` array syntax + indexed access/assign."""

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


def test_arrays() -> None:
    out = _run("Arrays.abcl")
    # Local var workers[3] write/read cycle
    for line in ("workers[0] = alice", "workers[1] = bob", "workers[2] = carol"):
        assert line in out, f"missing: {line}"
    # Default-initialized local array (-1 default, two slots overridden)
    assert "t[0] = 20" in out
    assert "t[1] = -1" in out
    assert "t[2] = -1" in out
    assert "t[3] = 35" in out
    assert "sum = 53" in out  # 20+(-1)+(-1)+35
    # Field-level counts[10]: bumped 3 times for bucket 3, once for 7
    assert "bucket[3] = 3" in out
    assert "bucket[7] = 1" in out
    assert "bucket[0] = 0" in out
    # Field-level labels[5] = "blank" with 3 overrides
    assert "label[0] = Mon" in out
    assert "label[1] = blank" in out
    assert "label[2] = Wed" in out
    assert "label[3] = blank" in out
    assert "label[4] = Fri" in out
    print("OK  Arrays.abcl")


if __name__ == "__main__":
    test_arrays()
    print("OK  array syntax tests")
