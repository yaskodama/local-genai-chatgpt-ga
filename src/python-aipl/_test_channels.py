"""Phase 13 — CSP channel smoke tests."""

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


def test_channels() -> None:
    out = _run("Channels.abcl")

    # typeof shows element type + capacity.
    assert "typeof(ch1) = channel[string, cap=4]" in out

    # Producer sent 5; consumer drained 5.
    for i in range(5):
        assert f"alpha/{i}" in out, f"missing producer msg alpha/{i}"
    assert "drained 5 messages" in out

    # select_recv: slow channel preloaded with 999 → idx=1 value=999.
    assert "select pick = idx 1 value 999" in out
    # Timeout case: both channels empty → idx=-1.
    assert "timeout pick = idx -1 value None" in out

    # Pipeline: 1..5 squared.
    for sq in (1, 4, 9, 16, 25):
        assert f"squared: {sq}" in out, f"missing pipeline output: {sq}"
    print("OK  Channels.abcl")


if __name__ == "__main__":
    test_channels()
    print("OK  channel tests")
