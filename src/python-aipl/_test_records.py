"""Smoke test for record literals + dot-field access + typeof."""

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


def test_records() -> None:
    out = _run("Records.abcl")

    # 1) Local record literal access
    assert "alice.name  = Alice" in out
    assert "alice.age   = 30" in out
    assert "alice.score = 95.5" in out
    # 2) Structural typeof
    assert "typeof(alice) = record{name:string, age:int, score:float}" in out
    # 3) Field assign
    assert "after birthday, age = 31" in out
    # 4) Mixed record + nested field access
    assert "config.host       = localhost" in out
    assert "config.owner.name = ops" in out
    assert "typeof(config)    = record{host:string, port:int, ssl:int, owner:record{name:string}}" in out
    # 5) Empty record + array/scalar typeof variants
    assert "typeof(empty_rec) = record{}" in out
    assert "typeof(42)        = int" in out
    assert "typeof(3.14)      = float" in out
    assert "typeof(\"hi\")      = string" in out
    assert "typeof([1,2,3])   = array[int]" in out
    assert "typeof([1,\"a\"])   = array[int | string]" in out
    # 6) Field-level record through actor (Profile)
    assert "owner = admin (id=0)" in out          # rename worked
    assert "stats = hits:3 misses:1" in out       # 3 hits + 1 miss
    assert "peek leaf = 42" in out                 # 3-level nesting
    assert "nested.outer.inner.leaf = 42" in out
    assert "typeof(stats)  = record{hits:int, misses:int}" in out
    assert "typeof(nested) = record{outer:record{inner:record{leaf:int}}}" in out
    print("OK  Records.abcl")


if __name__ == "__main__":
    test_records()
    print("OK  record/typeof tests")
