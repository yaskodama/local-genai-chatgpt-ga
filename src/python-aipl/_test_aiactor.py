"""Smoke test: auto-spawned AI actor + now/future dispatch."""

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


def test_ai_actor() -> None:
    out = _run("AIActor.abcl")

    # Auto-spawned AI is reachable from user code without `new AI()`.
    assert "typeof(AI) = actor(AI, methods=[ask, ask_p, ask_sys, ask_sys_p, cost, remaining, see, see_p, see_sys, see_sys_p, usage])" in out

    # (1) now AI.ask returns string
    assert "typeof(r1) = string" in out
    assert "r1 = [mock] reply for: Hello AI" in out

    # (2) provider override
    assert "Gemini    : [mock] reply for: ping" in out
    assert "Anthropic : [mock] reply for: ping" in out
    assert "OpenAI    : [mock] reply for: ping" in out

    # (3) parallel future
    assert "typeof(f1) = future" in out
    for q in ("Q1", "Q2", "Q3"):
        assert f"{q} -> [mock] reply for: {q}" in out

    # (4) system + provider
    assert "[mock] reply sys=(Be brief....) for: Tell me a fact about actors." in out

    # (5) vision
    assert "typeof(img) = image(8x8, RGBA)" in out
    assert "[mock] reply img=(image/png) for: describe this" in out

    # (6) future vision + system + provider
    assert "[mock] reply sys=(Be terse....) img=(image/png) for: What pattern?" in out

    # (7) pool
    assert "a -> [mock] reply for: from a" in out
    assert "b -> [mock] reply for: from b" in out
    assert "c -> [mock] reply for: from c" in out

    # (8) typeof on call results vs builtin signatures
    assert "typeof(now AI.ask(\"x\"))             = string" in out
    assert "typeof(now AI.see(\"x\", img))        = string" in out
    assert "typeof(future AI.ask(\"x\"))          = future" in out
    assert "typeof(ai_call)        (builtin sig) = function([provider:int|string,] prompt:string) -> string" in out
    assert "typeof(ai_call_image)  (builtin sig) = function([provider,] prompt:string, image+) -> string" in out
    print("OK  AIActor.abcl")


if __name__ == "__main__":
    test_ai_actor()
    print("OK  AI actor tests")
