"""Phase 15 — symbol_owned encapsulation tests.

Verifies that the static checker:
  - allows external read of a `pub` field
  - flags external read of a private field
  - flags external write to ANY actor field (pub or not), since
    callers must go through a method
  - allows in-class methods to read/write any of their own fields
  - leaves record (non-actor) field reads/writes alone
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import aipl_parser
import aipl_interp
import aipl_typeck


def _check(src):
    prog = aipl_parser.parse(src)
    issues = aipl_typeck.check(prog, aipl_interp.BUILTIN_SIGNATURES)
    return [i.message for i in issues
            if "private field" in i.message or "external write" in i.message]


def test_pub_read_ok():
    msgs = _check("""
class A { pub var name: string = "x"; }
class D { method run() { var a = new A(); print(a.name); } }
""")
    assert msgs == [], msgs


def test_private_read_flagged():
    msgs = _check("""
class A { var secret: int = 42; }
class D { method run() { var a = new A(); var s = a.secret; } }
""")
    assert any("private field `a.secret`" in m for m in msgs), msgs


def test_external_write_to_pub_flagged():
    msgs = _check("""
class A { pub var name: string = "x"; }
class D { method run() { var a = new A(); a.name = "y"; } }
""")
    assert any("external write to `a.name`" in m for m in msgs), msgs


def test_external_write_to_private_flagged():
    msgs = _check("""
class A { var k: int = 0; }
class D { method run() { var a = new A(); a.k = 9; } }
""")
    assert any("external write to `a.k`" in m for m in msgs), msgs


def test_method_writes_own_field_ok():
    msgs = _check("""
class A { var k: int = 0; method tick() { k = k + 1; } }
class D { method run() { var a = new A(); send a.tick(); } }
""")
    assert msgs == [], msgs


def test_record_field_unaffected():
    msgs = _check("""
class D {
  method run() {
    var r = { name: "alice", age: 30 };
    var n = r.name;
    r.age = 31;
  }
}
""")
    assert msgs == [], msgs


def test_pub_array_field_read_ok():
    msgs = _check("""
class P { pub var xs[3] = 0; }
class D { method run() { var p = new P(); var v = p.xs; } }
""")
    assert msgs == [], msgs


def test_owned_sample_clean():
    here = os.path.dirname(__file__)
    src = open(os.path.join(here, "samples", "Owned.abcl")).read()
    assert _check(src) == []


def test_owned_violations_sample_emits_three():
    here = os.path.dirname(__file__)
    src = open(os.path.join(here, "samples", "Owned_violations.abcl")).read()
    msgs = _check(src)
    assert len(msgs) == 3, msgs


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK  {name}")
    print("phase 15 tests passed")
