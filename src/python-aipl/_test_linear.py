"""Phase 14 — linear ownership smoke tests."""

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


def test_linear() -> None:
    out = _run("Linear.abcl")
    # Correct linear-pipeline runs OK.
    assert "ok_pipeline = 0" in out
    assert "ok_branch   = 0" in out
    # Three intentional use-after-move bugs flagged.
    assert "type_check() found 3 issue(s):" in out
    for needle in (
        "function bad_double_use: use of moved linear variable `fh`",
        "function bad_double_close: use of moved linear variable `fh`",
        "function bad_branch: use of moved linear variable `fh`",
    ):
        assert needle in out, f"missing 14 detection: {needle}"
    # Correct ok_branch must NOT be flagged (return-terminating then-branch
    # doesn't poison the post-if moved set).
    assert "ok_branch: use of moved" not in out
    print("OK  Linear.abcl")


if __name__ == "__main__":
    test_linear()
    print("OK  linear tests")
