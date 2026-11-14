"""The build cache: unchanged projects skip checking and code generation.

A cache entry is keyed by a hash of the compiler's own sources, every `.sem`
file of the project (paths and contents), and the command's options. `check`
caches its diagnostics; `run` caches the generated IR. Entries live in
`<project>/.refined-cache/` and are only ever reused for byte-identical
inputs, so a stale entry cannot be used: any edit, to the program or to the
compiler, makes a new key. `--no-cache` bypasses the cache.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
DIRNAME = ".refined-cache"


def _compiler_digest() -> str:
    h = hashlib.sha256()
    for f in sorted(os.listdir(HERE)):
        if f.endswith(".py"):
            with open(os.path.join(HERE, f), "rb") as fh:
                h.update(f.encode() + b"\0" + fh.read() + b"\0")
    return h.hexdigest()


_COMPILER = None


def project_files(path: str) -> tuple[str, list[str]]:
    """(cache directory, source files) for a project directory, a build.sem, or a single module file."""
    path = os.path.abspath(path)
    if os.path.isdir(path) or os.path.basename(path) == "build.sem":
        root = path if os.path.isdir(path) else os.path.dirname(path)
        files: list[str] = []
        pending, seen = [root], set()
        while pending:  # D-109: required packages are part of the program, wherever they live
            here = os.path.normcase(os.path.abspath(pending.pop(0)))
            if here in seen:
                continue
            seen.add(here)
            for d, dirs, names in os.walk(here):
                dirs[:] = sorted(x for x in dirs if not x.startswith("."))
                files += [os.path.join(d, n) for n in sorted(names) if n.endswith(".sem") or n == "authority.approved"]
            build = os.path.join(here, "build.sem")
            if os.path.isfile(build):
                with open(build, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        parts = line.split('"')
                        if len(parts) >= 5 and " requires " in parts[0]:
                            pending.append(os.path.join(here, parts[1]))
        return os.path.join(root, DIRNAME), files
    test = path[:-4] + ".test.sem"
    return os.path.join(os.path.dirname(path), DIRNAME), [path] + ([test] if os.path.exists(test) else [])


def key(path: str, options: dict) -> tuple[str, str]:
    global _COMPILER
    if _COMPILER is None:
        _COMPILER = _compiler_digest()
    directory, files = project_files(path)
    h = hashlib.sha256(_COMPILER.encode())
    h.update(json.dumps(options, sort_keys=True).encode())
    base = os.path.dirname(directory)
    for f in files:
        h.update(os.path.abspath(f).replace(os.sep, "/").encode() + b"\0")
        with open(f, "rb") as fh:
            h.update(fh.read() + b"\0")
    return directory, h.hexdigest()


def load(path: str, options: dict, suffix: str) -> Optional[str]:
    directory, k = key(path, options)
    try:
        with open(os.path.join(directory, f"{k}.{suffix}"), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def store(path: str, options: dict, suffix: str, content: str) -> None:
    directory, k = key(path, options)
    try:
        os.makedirs(directory, exist_ok=True)
        tmp = os.path.join(directory, f"{k}.{suffix}.tmp{os.getpid()}")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(tmp, os.path.join(directory, f"{k}.{suffix}"))
    except OSError:
        pass  # a cache that cannot be written is only a slower build
