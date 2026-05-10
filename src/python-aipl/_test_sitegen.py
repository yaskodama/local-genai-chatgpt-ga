"""Smoke test for app/website generation builtins."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

THIS = Path(__file__).resolve().parent
ENV = {**os.environ, "AIPL_AI_PROVIDER": "mock"}
OUT = THIS / "out_site"


def _run(sample: str) -> str:
    if OUT.exists():
        shutil.rmtree(OUT)
    result = subprocess.run(
        [sys.executable, "aipl_main.py", f"samples/{sample}"],
        cwd=THIS, env=ENV, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{sample} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def test_sitegen() -> None:
    out = _run("SiteGen.abcl")

    # typeof results showcased in the run
    assert "typeof(logo)             = image(64x64, RGBA)" in out
    assert "typeof(image_size(logo)) = tuple(int, int)" in out
    assert "typeof(image_pixel(logo, 32, 32)) = tuple(int, int, int, int)" in out
    # Recursive record + array + tuple inference for the inline config:
    assert "config typeof = record{site_name:string, tagline:string, theme:record{primary:string, surface:string}, posts:array[record{slug:string, title:string, body:string}]}" in out
    assert "center pixel (32,32) = (255,220,60,255)" in out

    # Filesystem deliverables
    expected = ["index.html", "style.css", "logo.png", "manifest.json"]
    for name in expected:
        p = OUT / name
        assert p.exists() and p.stat().st_size > 0, f"missing/empty: {p}"
    posts_dir = OUT / "posts"
    assert posts_dir.is_dir(), "posts/ dir missing"
    post_names = sorted(p.name for p in posts_dir.iterdir())
    assert post_names == ["actors.html", "hello.html", "type-infer.html"], post_names

    # The PNG header should be present in the binary file.
    with (OUT / "logo.png").open("rb") as f:
        head = f.read(8)
    assert head[:8] == b"\x89PNG\r\n\x1a\n", "logo.png is not a valid PNG"

    # The HTML should reference our generated assets.
    idx_html = (OUT / "index.html").read_text(encoding="utf-8")
    assert "<title>AIPL Demo Blog</title>" in idx_html
    assert "logo.png" in idx_html
    assert "style.css" in idx_html

    # Manifest JSON should round-trip via json_stringify with our shape.
    import json as _json
    manifest = _json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["site"] == "AIPL Demo Blog"
    assert manifest["post_count"] == 3
    assert manifest["logo"]["width"] == 64
    assert manifest["logo"]["height"] == 64
    print("OK  SiteGen.abcl")


if __name__ == "__main__":
    test_sitegen()
    print("OK  site-gen tests")
