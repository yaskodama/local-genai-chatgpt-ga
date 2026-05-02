#!/usr/bin/env python3
"""abcl_fmt — reformat a .abcl source file.

Text-based, deliberately conservative.  Walks the source one
character at a time and emits:

  - each `{` on the same line as the preceding token, then a newline
  - each `}` on its own line
  - each `;`-terminated statement on its own line
  - indentation = 2 spaces × current `{`-block depth
  - line comments (`// ...`) preserved with the next statement

It does not normalise whitespace inside expressions and it does not
parse.  Comments are kept verbatim.  Strings are scanned for escapes
so a `;` inside a string doesn't accidentally terminate a line.

Usage:
  abcl_fmt FILE             # write reformatted source to stdout
  abcl_fmt -i FILE          # rewrite the file in place
"""

import sys


def reformat(src: str) -> str:
    out: list = []
    depth = 0
    line: list = []
    in_str = False
    escape = False
    i = 0
    n = len(src)

    def flush_line():
        nonlocal line
        text = "".join(line).strip()
        if text:
            out.append("  " * depth + text)
        line = []

    while i < n:
        c = src[i]
        # Inside a string: copy verbatim until the unescaped closing quote.
        if in_str:
            line.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            line.append(c)
            in_str = True
            i += 1
            continue
        # Line comment — keep until newline, attach to current line.
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                line.append(src[i])
                i += 1
            # collapse to a single-line element
            text = "".join(line).strip()
            if text:
                out.append("  " * depth + text)
            line = []
            continue
        if c == "\n":
            # Soft-wrap inside an expression — turn into a single space.
            if line and line[-1] not in (" ", "\n"):
                line.append(" ")
            i += 1
            continue
        if c == "{":
            head = "".join(line).strip()
            line = []
            if head:
                out.append("  " * depth + head + " {")
            else:
                out.append("  " * depth + "{")
            depth += 1
            i += 1
            continue
        if c == "}":
            flush_line()
            depth = max(0, depth - 1)
            out.append("  " * depth + "}")
            i += 1
            continue
        if c == ";":
            line.append(";")
            flush_line()
            i += 1
            continue
        # Squash runs of whitespace down to one space inside a line.
        if c in (" ", "\t"):
            if line and line[-1] != " ":
                line.append(" ")
            i += 1
            continue
        line.append(c)
        i += 1

    flush_line()
    return "\n".join(out) + ("\n" if out else "")


def main() -> int:
    args = sys.argv[1:]
    in_place = False
    if args and args[0] == "-i":
        in_place = True
        args = args[1:]
    if len(args) != 1:
        print("usage: abcl_fmt [-i] FILE", file=sys.stderr)
        return 2
    path = args[0]
    with open(path) as f:
        src = f.read()
    out = reformat(src)
    if in_place:
        with open(path, "w") as f:
            f.write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
