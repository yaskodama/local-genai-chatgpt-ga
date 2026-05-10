"""Smoke test: provider override + multimodal ai_call_*."""

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


def test_multi_provider_and_image() -> None:
    out = _run("MultiProvider.abcl")
    # Provider override (text only): each path reaches the mock under
    # AIPL_AI_PROVIDER=mock, so all should produce the same canned reply.
    for label in ("default (auto):", "Gemini    [1]:", "Anthropic [2]:",
                  "OpenAI    [3]:", "string alias:"):
        assert label in out, f"missing label: {label}"
        # Each path should return mock output.
    # System-prompt path includes the truncated system in the trace.
    assert "[mock] reply sys=(Be very brief....) for: Say hello in one word." in out
    # Image path (image_create result, 16x16 RGBA): typeof + img tag.
    assert "image typeof:  image(16x16, RGBA)" in out
    assert "img=(image/png) for: Describe the test pattern in this image." in out
    # Bytes path: read_bytes -> array[int], mime sniffed.
    assert "typeof(raw) = array[int]" in out
    assert "Gemini:  [mock] reply img=(image/png) for: What format is this file?" in out
    # System + image combo.
    assert "Claude:  [mock] reply sys=(You are a curt visio...) img=(image/png) for: Pattern check:" in out
    # typeof results.
    assert "typeof(ai_call(1, \"hi\"))      = string" in out
    assert "typeof(ai_call_image(2, p, img)) = string" in out
    assert "typeof(image_create(2,2,0,0,0,255)) = image(2x2, RGBA)" in out
    print("OK  MultiProvider.abcl")


if __name__ == "__main__":
    test_multi_provider_and_image()
    print("OK  multi-provider tests")
