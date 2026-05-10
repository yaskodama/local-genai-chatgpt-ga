"""Smoke test: typeof on builtins and user functions."""

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


def test_signatures() -> None:
    out = _run("Signatures.abcl")

    # Static builtin signatures
    assert "typeof(read_bytes)       = function(path:string) -> array[int]" in out
    assert "typeof(write_file)       = function(path:string, content:string) -> int" in out
    assert "typeof(image_load)       = function(path:string) -> image" in out
    assert "typeof(image_create)     = function(w:int, h:int, r:int, g:int, b:int [, a:int=255]) -> image" in out
    assert "typeof(image_pixel)      = function(image, x:int, y:int) -> tuple(int, int, int, int)" in out
    assert "typeof(image_size)       = function(image) -> tuple(int, int)" in out
    assert "typeof(json_parse)       = function(text:string) -> any" in out
    assert "typeof(json_stringify)   = function(value:any [, indent:int]) -> string" in out
    assert "typeof(list_dir)         = function(path:string) -> array[string]" in out

    # AI call signatures with provider override + multimodal
    assert "typeof(ai_call)                  = function([provider:int|string,] prompt:string) -> string" in out
    assert "typeof(ai_call_with_system)      = function([provider,] system:string, prompt:string) -> string" in out
    assert "typeof(ai_call_image)            = function([provider,] prompt:string, image+) -> string" in out
    assert "typeof(ai_call_image_with_system)= function([provider,] system:string, prompt:string, image+) -> string" in out

    # Meta builtins
    assert "typeof(compile)        = function(source:string) -> int" in out
    assert "typeof(spawn)          = function(class_name:string [, args+]) -> actor" in out
    assert "typeof(add_method)     = function(target:string|actor, source:string) -> int" in out
    assert "typeof(typeof)         = function(value:any) -> string" in out

    # User-defined function trace inference
    assert "typeof(fib) = function(n:int) -> int" in out
    assert "typeof(describe) (after int+string+float) = function(x:float | int | string) -> string" in out

    # Builtin signature vs value type — the punchline
    assert "typeof(image_create(8,8,0,200,100,255)) = image(8x8, RGBA)" in out
    assert "typeof(image_pixel(img,0,0))    = tuple(int, int, int, int)" in out
    assert "typeof(json_stringify({a:1, b:[2,3]}, 2)) = string" in out
    assert "typeof(ai_call(2,\"hi\"))             = string" in out
    print("OK  Signatures.abcl")


if __name__ == "__main__":
    test_signatures()
    print("OK  signature tests")
