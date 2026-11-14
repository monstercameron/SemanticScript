"""Staleness flag for context rows (LR-06 rule 4).

`refined stale PATH --base REF` compares every `.sem` file under PATH with its
version at the git revision REF. An entity whose structural rows changed while
none of its context rows (`purpose`, `invariant`, `rationale`, `risk`, `note`,
`todo`, `deprecated`, and label context) changed is flagged with R605: its prose
may no longer describe it. The author re-confirms by rewriting the prose or by
adding a `note` row that says why it still holds (decision D-17).
"""
from __future__ import annotations

import os
import subprocess
from typing import Optional

from . import shapes as S
from .diagnostics import Diagnostic, Sink
from .lexer import lex
from .parser import parse

CONTEXT_PREDICATES = set(S.CONTEXT_SHAPES)
LABEL_CONTEXT = {"purpose", "rationale", "risk", "note", "todo"}


def _split(entity) -> tuple[tuple, tuple]:
    structural, context = [], []
    for r in entity.rows[1:]:
        toks = tuple(t.raw for t in r.tokens)
        is_context = r.predicate in CONTEXT_PREDICATES or (r.predicate == "label" and r.text(1) in LABEL_CONTEXT)
        (context if is_context else structural).append(toks)
    return tuple(structural), tuple(context)


def _entities(text: str, path: str) -> dict:
    src = parse(lex(text, Sink(path)), path, Sink(path))
    out = {}
    for e in src.entities:
        out[(e.kind, e.name, e.owner if e.kind in S.OWNED_KINDS else None)] = e
    return out


def _git(args: list[str], cwd: str) -> Optional[str]:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    return proc.stdout if proc.returncode == 0 else None


def stale(path: str, base: str) -> list[Diagnostic]:
    root_dir = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    top = _git(["rev-parse", "--show-toplevel"], root_dir)
    if top is None:
        return [Diagnostic("R605", "not inside a git repository, so there is nothing to compare with", path, 1)]
    top = top.strip()
    files = []
    if os.path.isdir(path):
        for dirpath, _dirs, names in os.walk(path):
            files += [os.path.join(dirpath, n) for n in names if n.endswith(".sem")]
    else:
        files = [path]
    out: list[Diagnostic] = []
    for f in sorted(files):
        rel = os.path.relpath(os.path.abspath(f), top).replace(os.sep, "/")
        old = _git(["show", f"{base}:{rel}"], top)
        if old is None:
            continue  # new file: nothing to compare
        with open(f, encoding="utf-8") as fh:
            new = fh.read()
        before, after = _entities(old, f), _entities(new, f)
        for key, ent in after.items():
            prev = before.get(key)
            if prev is None or ent.kind is None:
                continue
            s_old, c_old = _split(prev)
            s_new, c_new = _split(ent)
            if s_old != s_new and c_old == c_new and (c_new or ent.kind in S.PURPOSE_REQUIRED):
                out.append(Diagnostic("R605", f"`{ent.name}` changed since {base} but its context rows did not; "
                                      "rewrite them, or add a `note` saying why they still hold", f, ent.line))
    return out
