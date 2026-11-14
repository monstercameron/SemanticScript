"""The formatter: one canonical layout for refined source (LR-01).

    refined fmt PATH [--check]

PATH is a `.sem` file, or a directory whose `.sem` files (recursively) are
formatted. The layout:

- one space between tokens, none at the end of a line; strings and comments
  keep their text (a trailing comment is written `<row> # <comment>`);
- a comment line is `# <comment>`;
- exactly one blank line before each entity's `is` row (and before the comment
  lines directly above it), no blank lines run together, none at the start or
  end of the file, and one line end at the end.

Formatting never changes which rows exist or their order, so it never changes
what the checker sees. A file with a lexical error (R1xx) is left alone and
reported. `--check` changes nothing and exits 1 if any file would change.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

from .diagnostics import Sink
from .lexer import lex


def format_text(text: str) -> Optional[str]:
    """The formatted text, or None when the source has lexical errors."""
    sink = Sink("<fmt>")
    lines = lex(text, sink)
    if sink.items:
        return None
    raw_lines = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    for line, raw in zip(lines, raw_lines):
        # comments are free text: their words and spacing are kept exactly; only the space before them changes
        comment = None
        if line.comment is not None:
            after = line.tokens[-1].col - 1 + len(line.tokens[-1].raw) if line.tokens else 0
            comment = raw[raw.index("#", after):].rstrip()
        if not line.tokens:
            out.append("" if comment is None else comment)
            continue
        row = " ".join(t.raw for t in line.tokens)
        if comment is not None:
            row += " " + comment
        if len(line.tokens) >= 2 and line.tokens[1].raw == "is":
            # a blank line before the entity, above the comment lines that sit directly on its `is` row
            j = len(out)
            while j > 0 and out[j - 1].startswith("#"):
                j -= 1
            if j > 0 and out[j - 1] != "":
                out.insert(j, "")
        out.append(row)
    collapsed: list[str] = []
    for line_text in out:
        if line_text == "" and (not collapsed or collapsed[-1] == ""):
            continue
        collapsed.append(line_text)
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return "\n".join(collapsed) + "\n"


def _files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    found = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "node_modules")
        found += [os.path.join(root, f) for f in sorted(files) if f.endswith(".sem")]
    return found


def main(paths: list[str], check: bool) -> int:
    changed, broken = [], []
    for path in paths:
        for f in _files(path):
            with open(f, encoding="utf-8", newline="") as fh:
                text = fh.read()
            new = format_text(text)
            if new is None:
                broken.append(f)
                continue
            if new != text:
                changed.append(f)
                if not check:
                    with open(f, "w", encoding="utf-8", newline="\n") as fh:
                        fh.write(new)
    for f in broken:
        sys.stdout.write(f"{f}: not formatted: it has lexical errors (run `check`)\n")
    for f in changed:
        sys.stdout.write(f"{f}: {'would be reformatted' if check else 'reformatted'}\n")
    if not changed and not broken:
        sys.stdout.write("ok\n")
    return 1 if broken or (check and changed) else 0
