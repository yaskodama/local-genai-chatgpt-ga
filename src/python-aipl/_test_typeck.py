"""Phase 11 — gradual static type checker smoke tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
ENV = {**os.environ, "AIPL_AI_PROVIDER": "mock"}


def _run(sample: str, *extra_args: str) -> tuple[str, str, int]:
    result = subprocess.run(
        [sys.executable, "aipl_main.py", *extra_args, f"samples/{sample}"],
        cwd=THIS, env=ENV, capture_output=True, text=True, timeout=30,
    )
    return result.stdout, result.stderr, result.returncode


def test_typecheck_via_builtin() -> None:
    out, _, rc = _run("Typecheck.abcl")
    assert rc == 0, f"unexpected exit: {rc}"
    # Trace+annotation-driven signatures
    assert "typeof(add)       = function(a:int, b:int) -> int" in out
    assert "typeof(greet)     = function(name:string) -> string" in out
    assert "typeof(bad_return)= function(a:int) -> int" in out
    # Phase 11a's 5 + Phase 11b's call-site detection of `greet(a)` = 6 total.
    assert "type_check() returned 6 issue(s):" in out
    for needle in (
        "function bad_return: return type mismatch  (expected int, got string)",
        "function bad_param: call to function `greet` arg `name` mismatch",
        "field Mismatch.label: field initializer mismatch  (expected string, got int)",
        "method Mismatch.add_one: return type mismatch  (expected int, got string)",
        "global: `var bad_age` initializer mismatch  (expected int, got string)",
        "global: `var bad_msg` initializer mismatch  (expected string, got int)",
    ):
        assert needle in out, f"missing: {needle}"
    # Well-typed code still executes.
    assert "add(3, 4)   = 7" in out
    assert "counter.get = 2" in out
    print("OK  Typecheck.abcl (via type_check() builtin)")


def test_cli_typecheck_flag() -> None:
    out, err, rc = _run("Typecheck.abcl", "--type-check")
    for needle in (
        "function bad_return: return type mismatch",
        "function bad_param: call to function `greet` arg `name` mismatch",
        "field Mismatch.label: field initializer mismatch",
        "method Mismatch.add_one: return type mismatch",
        "global: `var bad_age` initializer mismatch",
        "global: `var bad_msg` initializer mismatch",
        "[type] 6 issue(s)",
    ):
        assert needle in err, f"missing in stderr: {needle}"
    assert rc == 0
    assert "add(3, 4)   = 7" in out
    print("OK  --type-check CLI flag")


def test_cli_strict_aborts() -> None:
    out, err, rc = _run("Typecheck.abcl", "--type-check", "--strict")
    assert rc == 2, f"expected exit 2 in --strict, got {rc}"
    assert "[type] 6 issue(s)" in err
    assert "add(3, 4)" not in out
    print("OK  --strict halts on type errors")


def test_phase_11c_unions_generics() -> None:
    out, _, rc = _run("Typecheck11c.abcl")
    assert rc == 0
    # Generics work at runtime: id returns the input, pair returns tuple, head returns first.
    assert "id(42)    = 42" in out
    assert "id(hello) = hello" in out
    assert "head(int) = 10" in out
    # Union annotations accept either side.
    assert "u1 = 42" in out
    assert "u2 = hello" in out
    assert "describe int = got 7" in out
    # Static checker catches all 4 intentional bugs.
    assert "type_check() found 4 issue(s):" in out
    for needle in (
        "call to function `pair` arg `b`: type-var `T` already bound to int, got string",
        "call to function `head` arg `arr` mismatch  (expected array[T], got int)",
        "call to function `describe` arg `x` mismatch  (expected int | string, got array[int, 2])",
        "`var bad_union` initializer mismatch  (expected int | string, got float)",
    ):
        assert needle in out, f"missing 11c detection: {needle}"
    print("OK  Typecheck11c.abcl")


def test_phase_12_effects() -> None:
    out, _, rc = _run("Effects.abcl")
    assert rc == 0
    # Well-annotated calls run.
    assert "classify     = [mock] reply" in out
    # Four declared-but-incomplete effect sets are flagged (Demo.run
    # has no annotation so it's skipped under gradual mode).
    assert "type_check() found 4 issue(s):" in out
    for needle in (
        "function bad_silent: effect set incomplete — declared {∅} but uses {fs}; missing: {fs}",
        "function bad_partial: effect set incomplete — declared {fs} but uses {ai, fs, net}; missing: {ai, net}",
        "function bad_evolve: effect set incomplete — declared {∅} but uses {mut}; missing: {mut}",
        "function bad_indirect: effect set incomplete — declared {∅} but uses {ai, fs, net}; missing: {ai, fs, net}",
    ):
        assert needle in out, f"missing 12 detection: {needle}"
    print("OK  Effects.abcl")


def test_phase_11de_narrowing_and_lengths() -> None:
    out, _, rc = _run("Typecheck11de.abcl")
    assert rc == 0
    # 11d narrowing — well-typed under both branches
    assert "describe(42)  = int: 43" in out
    assert "describe(hi)  = str: hi" in out
    assert "safe_len(99)    = 0" in out
    assert "safe_len(hello) = 5" in out
    # 11e — 4 length / out-of-bounds bugs detected
    assert "type_check() found 4 issue(s):" in out
    for needle in (
        "`var short` initializer mismatch  (expected array[int, 5], got array[int, 2])",
        "index 5 out of bounds for `trio: array[..., 3]`",
        "`var also_bad` initializer mismatch  (expected array[int, 4], got array[int, 3])",
        "`counts = ...` mismatch  (expected array[int, 3], got array[int, 2])",
    ):
        assert needle in out, f"missing: {needle}"
    print("OK  Typecheck11de.abcl")


def test_phase_11b_callsite() -> None:
    out, _, rc = _run("Typecheck11b.abcl")
    assert rc == 0
    # Each of the 6 intentional bugs is caught.
    assert "type_check() found 6 issue(s):" in out
    for needle in (
        "call to function `read_file` arg `path` mismatch  (expected string, got int)",
        "call to function `add` arg `a` mismatch  (expected int, got string)",
        "call to function `add`: arity 3 vs declared [2]",
        "call to now c.tick arg `by` mismatch  (expected int, got string)",
        "call to new Counter arg `start` mismatch  (expected int, got string)",
        "call to function `path_join` arg `parts` mismatch  (expected string, got int)",
    ):
        assert needle in out, f"missing 11b detection: {needle}"
    # `now c.get()` infers `int` from the method's return annotation.
    # NOTE: at runtime `count` was poisoned by `now c.tick("nope")` which
    # mutated count to a string ("15" + "nope"), so the *runtime* typeof
    # actually reports `string` — a great demo of why the static check helps.
    print("OK  Typecheck11b.abcl")


if __name__ == "__main__":
    test_typecheck_via_builtin()
    test_cli_typecheck_flag()
    test_cli_strict_aborts()
    test_phase_11b_callsite()
    test_phase_11c_unions_generics()
    test_phase_11de_narrowing_and_lengths()
    test_phase_12_effects()
    print("OK  type-check tests")
