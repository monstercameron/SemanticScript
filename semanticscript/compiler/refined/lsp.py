"""A Language Server Protocol server for refined source, on standard input and output.

    refined lsp

It speaks JSON-RPC with `Content-Length` framing and supports:

- `initialize`, `initialized`, `shutdown`, `exit`;
- `textDocument/didOpen`, `didChange` (whole text), `didSave`, `didClose`: the
  project around the document is checked with the editor's unsaved text, and
  diagnostics are published for every file of the project;
- `textDocument/formatting`: the formatter's layout as one edit;
- `textDocument/hover`: a rule code's summary, or the `purpose` of the entity
  named under the cursor.
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Optional
from urllib.parse import unquote, urlparse
from urllib.request import pathname2url

from . import check as checker
from .diagnostics import CODES
from .fmt import format_text

_open: dict[str, str] = {}  # uri -> text
_published: set[str] = set()


def _path(uri: str) -> str:
    parsed = urlparse(uri)
    path = unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", path):
        path = path[1:]
    return os.path.normpath(path)


def _uri(path: str) -> str:
    return "file:" + pathname2url(os.path.abspath(path))


def _send(message: dict) -> None:
    body = json.dumps(message).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


def _read() -> Optional[dict]:
    length = None
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            break
        name, _, value = line.decode("ascii", "replace").partition(":")
        if name.strip().lower() == "content-length":
            length = int(value.strip())
    if length is None:
        return None
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))


def _project_of(path: str) -> str:
    d = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.exists(os.path.join(d, "build.sem")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return path
        d = parent


def _publish(uri: str) -> None:
    checker.OVERLAY.clear()
    for u, text in _open.items():
        checker.OVERLAY[os.path.normcase(os.path.abspath(_path(u)))] = text
    target = _project_of(_path(uri))
    try:
        diags = checker.check_path(target).diagnostics
    except Exception as exc:  # the server must outlive any single bad document
        diags = []
        _send({"jsonrpc": "2.0", "method": "window/logMessage",
               "params": {"type": 1, "message": f"refined check failed: {exc!r}"}})
    by_file: dict[str, list] = {}
    for d in diags:
        by_file.setdefault(_uri(d.file), []).append({
            "range": {"start": {"line": max(d.line - 1, 0), "character": 0},
                      "end": {"line": max(d.line - 1, 0), "character": 1000}},
            "severity": 1, "code": d.code, "source": "refined", "message": d.message})
    for u in set(_published) | set(by_file) | {uri}:
        _send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics",
               "params": {"uri": u, "diagnostics": by_file.get(u, [])}})
    _published.clear()
    _published.update(by_file)


def _hover(uri: str, line: int, character: int) -> Optional[dict]:
    text = _open.get(uri)
    if text is None:
        return None
    lines = text.splitlines()
    if line >= len(lines):
        return None
    row = lines[line]
    for m in re.finditer(r"[A-Za-z0-9_.]+", row):
        if m.start() <= character <= m.end():
            word = m.group(0)
            break
    else:
        return None
    if word in CODES:
        return {"contents": {"kind": "markdown", "value": f"**{word}**: {CODES[word]}"}}
    name = word.split(".")[-1]
    for other in lines:
        found = re.match(rf'^{re.escape(name)} purpose "(.*)"\s*$', other)
        if found:
            return {"contents": {"kind": "markdown", "value": f"`{name}`: {found.group(1)}"}}
    return None


def main() -> int:
    shutting_down = False
    while True:
        msg = _read()
        if msg is None:
            return 0 if shutting_down else 1
        method, mid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
        if method == "initialize":
            _send({"jsonrpc": "2.0", "id": mid, "result": {
                "capabilities": {"textDocumentSync": 1, "documentFormattingProvider": True, "hoverProvider": True},
                "serverInfo": {"name": "refined", "version": "1"}}})
        elif method == "shutdown":
            shutting_down = True
            _send({"jsonrpc": "2.0", "id": mid, "result": None})
        elif method == "exit":
            return 0 if shutting_down else 1
        elif method in ("textDocument/didOpen", "textDocument/didChange", "textDocument/didSave"):
            doc = params["textDocument"]
            if method == "textDocument/didOpen":
                _open[doc["uri"]] = doc["text"]
            elif method == "textDocument/didChange":
                _open[doc["uri"]] = params["contentChanges"][-1]["text"]
            _publish(doc["uri"])
        elif method == "textDocument/didClose":
            _open.pop(params["textDocument"]["uri"], None)
        elif method == "textDocument/formatting":
            uri = params["textDocument"]["uri"]
            text = _open.get(uri, "")
            new = format_text(text)
            edits = [] if new is None or new == text else [{
                "range": {"start": {"line": 0, "character": 0}, "end": {"line": len(text.splitlines()) + 1,
                                                                          "character": 0}},
                "newText": new}]
            _send({"jsonrpc": "2.0", "id": mid, "result": edits})
        elif method == "textDocument/hover":
            pos = params["position"]
            _send({"jsonrpc": "2.0", "id": mid,
                   "result": _hover(params["textDocument"]["uri"], pos["line"], pos["character"])})
        elif mid is not None:
            _send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"`{method}` is not supported"}})
