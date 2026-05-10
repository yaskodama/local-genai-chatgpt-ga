"""Build a ~10 MB Shakespeare-distribution corpus from Project Gutenberg.

Sources (all in the public domain):
  PG#100  — The Complete Works of William Shakespeare    (~5.5 MB stripped)
  PG#1041 — Shakespeare's Sonnets                         (~140 KB)
  PG#1112 — Romeo and Juliet (alt edition)                (~200 KB)
  PG#1129 — Macbeth        (alt edition)                  (~140 KB)
  PG#2253 — The Plays of Christopher Marlowe              (~1.3 MB; same era)
  PG#2261 — Hamlet (Folger / alt)                         (~250 KB)
  PG#1051 — Hamlet (alt edition)                          (~250 KB)
  PG#1129 — Tragedy of Hamlet                             (~200 KB)
  PG#23042 — The Plays of Ben Jonson, Vol I               (~1.3 MB; same era)

The script:
  1. Downloads each source URL into ./.cache/ (offline-friendly cache).
  2. Strips Project Gutenberg header/footer with the standard markers.
  3. Concatenates the cleaned texts and truncates to exactly 10,000,000
     bytes for a clean round number.
  4. Writes corpus/tinyshake_10MB.txt and prints SHA-256.

After running, paste the SHA-256 into common.py CORPORA["10MB"].
"""

from __future__ import annotations
import hashlib
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
CACHE_DIR = HERE / ".cache"
CORPUS_OUT = HERE / "corpus" / "tinyshake_10MB.txt"
TARGET_BYTES = 10_000_000

# (PG id, label, url)
# We mix Shakespeare core with same-era Early Modern English texts so
# the byte distribution stays close to the 1MB TinyShakespeare corpus
# while expanding the vocabulary the model is exposed to.
SOURCES = [
    (100,  "Shakespeare Complete Works",
     "https://www.gutenberg.org/cache/epub/100/pg100.txt"),
    (10,   "King James Bible (1611, Early Modern English)",
     "https://www.gutenberg.org/cache/epub/10/pg10.txt"),
    (1041, "Shakespeare Sonnets",
     "https://www.gutenberg.org/cache/epub/1041/pg1041.txt"),
    (1112, "Romeo and Juliet (alt)",
     "https://www.gutenberg.org/cache/epub/1112/pg1112.txt"),
    (1129, "Macbeth (alt)",
     "https://www.gutenberg.org/cache/epub/1129/pg1129.txt"),
    (1051, "Hamlet (alt)",
     "https://www.gutenberg.org/cache/epub/1051/pg1051.txt"),
    (2253, "Marlowe Plays (Elizabethan contemporary)",
     "https://www.gutenberg.org/cache/epub/2253/pg2253.txt"),
    (23042, "Ben Jonson Plays Vol I (Elizabethan contemporary)",
     "https://www.gutenberg.org/cache/epub/23042/pg23042.txt"),
]

PG_HEADER_MARK = "*** START OF THE PROJECT GUTENBERG"
PG_FOOTER_MARK = "*** END OF THE PROJECT GUTENBERG"


def fetch(url: str, dest: Path) -> bytes:
    if dest.exists():
        return dest.read_bytes()
    print(f"  downloading {url} → {dest.name}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": "local-genai/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return data


def strip_pg_boilerplate(raw: bytes) -> bytes:
    """Remove Project Gutenberg header/footer if present, normalize CRLF
    to LF, and strip leading BOM. We keep this on the byte stream so the
    output hash is deterministic across machines."""
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("﻿"):
        text = text[1:]
    # Header
    h = text.find(PG_HEADER_MARK)
    if h != -1:
        nl = text.find("\n", h)
        if nl != -1:
            text = text[nl + 1 :]
    # Footer
    f = text.find(PG_FOOTER_MARK)
    if f != -1:
        text = text[:f]
    # Normalize line endings (1MB corpus is LF-only; keep distribution close).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8", errors="ignore")


def main():
    print(f"target: {TARGET_BYTES:,} bytes")
    pieces: list[bytes] = []
    total = 0
    for pg_id, label, url in SOURCES:
        cache_path = CACHE_DIR / f"pg{pg_id}.txt"
        try:
            raw = fetch(url, cache_path)
        except Exception as e:
            print(f"  WARN: could not fetch {pg_id} ({label}): {e}", file=sys.stderr)
            continue
        cleaned = strip_pg_boilerplate(raw)
        pieces.append(cleaned)
        total += len(cleaned)
        print(f"  + PG#{pg_id:>5} {label:<55} {len(cleaned):>10,} bytes  "
              f"(running total {total:,})")
        if total >= TARGET_BYTES:
            break

    if total < TARGET_BYTES:
        print(f"\n  WARN: only {total:,} bytes after all sources — "
              f"need {TARGET_BYTES - total:,} more")
        print("  Add more PG ids to SOURCES (more Elizabethan plays, sermons, etc.)")
        sys.exit(1)

    # Concatenate with a clean separator so individual works keep their
    # internal structure but the boundary is unambiguous.
    sep = b"\n\n\n"
    combined = sep.join(pieces)
    if len(combined) < TARGET_BYTES:
        print(f"  WARN: combined only {len(combined):,} bytes")
        sys.exit(1)
    final = combined[:TARGET_BYTES]
    CORPUS_OUT.parent.mkdir(parents=True, exist_ok=True)
    CORPUS_OUT.write_bytes(final)

    h = hashlib.sha256(final).hexdigest()
    print()
    print(f"wrote {CORPUS_OUT} ({len(final):,} bytes)")
    print(f"sha256 = {h}")
    print()
    print("Next: add this to common.py CORPORA:")
    print(f'    "10MB": (')
    print(f'        HERE / "corpus" / "tinyshake_10MB.txt",')
    print(f'        "{h}",')
    print(f'    ),')


if __name__ == "__main__":
    main()
