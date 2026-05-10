"""Smoke test for dynamic method injection / removal / inspection."""

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


def test_method_patch() -> None:
    out = _run("MethodPatch.abcl")

    # Initial state
    assert "[g1] hello, Alice" in out
    assert "[g2] hello, Bob" in out
    assert "methods_of(\"Greeter\") = ['greet', 'init']" in out
    assert "typeof(g1)             = actor(Greeter, methods=[greet, init])" in out

    # (2) class-level injection
    assert "[g1] HEY!! Charlie" in out
    assert "[g2] HEY!! Diana" in out
    assert "methods_of(\"Greeter\") = ['greet', 'init', 'shout']" in out

    # (3) replace at class level
    assert "[g1] (NEW) hi, Eve" in out
    assert "[g2] (NEW) hi, Frank" in out

    # (4) per-actor injection — g1 only
    assert "[g1] (psst) Grace" in out
    # g2.whisper is dropped silently — assert nothing about Heidi
    assert "Heidi" not in out
    assert "methods_of(g1) = ['greet', 'init', 'shout', 'whisper']" in out
    assert "methods_of(g2) = ['greet', 'init', 'shout']" in out
    assert "typeof(g1) = actor(Greeter, methods=[greet, init, shout, whisper])" in out
    assert "typeof(g2) = actor(Greeter, methods=[greet, init, shout])" in out

    # (5) per-actor override of existing method
    assert "[g1] (g1-ONLY) salutations, Ivy" in out
    assert "[g2] (NEW) hi, Jack" in out               # g2 still class-level

    # (6) remove per-actor override
    assert "[g1] (NEW) hi, Ken" in out                 # falls back to class-level NEW

    # (7) remove class-level method
    assert "Liam" not in out                           # shout dropped
    assert "Mary" not in out
    assert "final methods_of(g1) = ['greet', 'init', 'whisper']" in out
    assert "final methods_of(g2) = ['greet', 'init']" in out
    print("OK  MethodPatch.abcl")


if __name__ == "__main__":
    test_method_patch()
    print("OK  method-patch tests")
