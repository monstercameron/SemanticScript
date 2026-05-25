"""SemanticScript MCP server.

A thin Model Context Protocol server that exposes the stable ``sem`` JSON
surfaces (see ``SemanticScript/tools/sem.py``) as MCP tools. It shells out to
the same ``sem.py`` CLI the agent contract documents, so ``sem.py`` stays the
single source of truth for behavior and versioning. Each tool returns the
native ``sem.<surface>.vN`` JSON payload unchanged.

Requirements:
    python -m pip install "mcp>=1.2"

Run (stdio transport):
    python SemanticScript/tools/sem_mcp.py

Serve over HTTP for remote or multi-client use:
    python SemanticScript/tools/sem_mcp.py --transport streamable-http --port 8000

Debug interactively with the MCP Inspector:
    npx @modelcontextprotocol/inspector python SemanticScript/tools/sem_mcp.py

Register with an MCP client, for example Claude Code:
    claude mcp add semanticscript -- python /abs/path/SemanticScript/tools/sem_mcp.py

Or in a client config file:
    {
      "mcpServers": {
        "semanticscript": {
          "command": "python",
          "args": ["/abs/path/SemanticScript/tools/sem_mcp.py"]
        }
      }
    }

Adding a tool
-------------
Tools are thin wrappers over ``sem`` subcommands; the goal is to forward to the
CLI, not to reimplement logic. To expose a new surface:

1. Make sure the underlying ``sem`` subcommand exists and emits ``--json`` (it
   is the single source of truth). If it does not, add it in ``sem.py`` first.
2. Add an ``@mcp.tool()`` function here. Name it after the subcommand, give it
   a one-line docstring ending with the payload schema id (``sem.<surface>.vN``),
   type-hinted parameters that map to the subcommand's flags/arguments, and a
   ``cwd: str | None = None`` parameter for path-relative commands. Build the
   argv with ``_argv(...)`` (it drops ``None`` flags) and return
   ``_run_sem(args, cwd=cwd)`` so the native JSON payload passes through:

       @mcp.tool()
       def example(path: str = ".", full: bool = False, cwd: str | None = None) -> dict[str, Any]:
           '''One-line description (sem.example.v1).'''
           args = _argv("example", "--json", "--full" if full else None, path)
           return _run_sem(args, cwd=cwd)

   Put flags before positional ``path`` (the CLI uses argparse REMAINDER for
   trailing compiler args). For slow commands pass ``timeout=...``; for
   file-mutating commands default to a preview mode and gate the destructive
   path behind an explicit boolean (see ``patch``).
3. Add the tool name to ``EXPECTED_TOOLS`` in
   ``SemanticScript/tests/test_sem_mcp.py`` (the registration test asserts the
   exact set) and add a forwarding test if argv assembly is non-trivial.
4. If the bundled tool count is user-visible, update the "MCP server" section of
   ``docs/toolchain/compiler.md``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from io import TextIOWrapper
from pathlib import Path
from typing import Any

import anyio
import anyio.lowlevel
import mcp.types as types
from mcp.shared.message import SessionMessage
from mcp.server.fastmcp import FastMCP

SEM_PY = Path(__file__).resolve().parent / "sem.py"

# Most surfaces are fast; `test` can run harnesses, so it gets a larger budget.
DEFAULT_TIMEOUT_SECONDS = 120
TEST_TIMEOUT_SECONDS = 600
DOCS_INDEX_TIMEOUT_SECONDS = 600
DEFAULT_DOCS_WATCH_INTERVAL_SECONDS = 5.0
DOCS_WATCH_MAX_FILES = 5000
DOCS_DEFAULT_EMBEDDING_PROVIDER = "sentence-transformers"
DOCS_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

mcp = FastMCP("semanticscript")


def _stdio_text_reader(binary_stream: Any) -> TextIOWrapper:
    """Wrap stdio input as UTF-8 while accepting one leading UTF-8 BOM.

    Some PowerShell-driven smoke probes prepend a BOM to the first stdin write.
    Real MCP clients normally send clean UTF-8, but ``utf-8-sig`` is harmless
    for clean input and strips only the start-of-stream marker before JSON-RPC
    parsing sees the first line.
    """
    return TextIOWrapper(binary_stream, encoding="utf-8-sig", errors="replace")


def _sanitize_initial_stdio_line(line: str) -> str:
    """Remove BOM artifacts that can appear before the first JSON-RPC frame."""
    if line.startswith("\ufeff"):
        return line.removeprefix("\ufeff")
    if len(line) >= 2 and line[0] in {"?", "\ufffd"} and line[1] in {"{", "["}:
        return line[1:]
    return line


@asynccontextmanager
async def _stdio_server_bom_tolerant(
    stdin: anyio.AsyncFile[str] | None = None,
    stdout: anyio.AsyncFile[str] | None = None,
):
    """Stdio transport variant that sanitizes only the first input line."""
    if not stdin:
        stdin = anyio.wrap_file(_stdio_text_reader(sys.stdin.buffer))
    if not stdout:
        stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))

    read_stream_writer, read_stream = anyio.create_memory_object_stream(0)
    write_stream, write_stream_reader = anyio.create_memory_object_stream(0)

    async def stdin_reader() -> None:
        first_line = True
        try:
            async with read_stream_writer:
                async for line in stdin:
                    if first_line:
                        line = _sanitize_initial_stdio_line(line)
                        first_line = False
                    try:
                        message = types.JSONRPCMessage.model_validate_json(line)
                    except Exception as exc:
                        await read_stream_writer.send(exc)
                        continue

                    await read_stream_writer.send(SessionMessage(message))
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async def stdout_writer() -> None:
        try:
            async with write_stream_reader:
                async for session_message in write_stream_reader:
                    output = session_message.message.model_dump_json(
                        by_alias=True,
                        exclude_none=True,
                    )
                    await stdout.write(output + "\n")
                    await stdout.flush()
        except anyio.ClosedResourceError:  # pragma: no cover
            await anyio.lowlevel.checkpoint()

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(stdin_reader)
        task_group.start_soon(stdout_writer)
        yield read_stream, write_stream


async def _run_stdio_bom_tolerant_async() -> None:
    """Run stdio transport with stdin tolerant of a leading UTF-8 BOM."""
    async with _stdio_server_bom_tolerant() as (read_stream, write_stream):
        await mcp._mcp_server.run(
            read_stream,
            write_stream,
            mcp._mcp_server.create_initialization_options(),
        )


def _resolve_workspace_path(path: str, cwd: str | None = None) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() and cwd is not None:
        candidate = Path(cwd) / candidate
    return candidate.resolve()


def _docs_default_db(path: str, cwd: str | None = None) -> str:
    root = _resolve_workspace_path(path, cwd)
    if root.is_file() or root.suffix.lower() in {".sem", ".sscript"}:
        root = root.parent
    return str((root / ".sem" / "docs.sqlite").resolve())


def _docs_resolved_db(path: str, db: str | None, cwd: str | None = None) -> str:
    if db:
        return str(_resolve_workspace_path(db, cwd))
    return _docs_default_db(path, cwd)


def _docs_snapshot(path: str, cwd: str | None = None, *, max_files: int = DOCS_WATCH_MAX_FILES) -> tuple[tuple[str, int, int], ...]:
    root = _resolve_workspace_path(path, cwd)
    if root.is_file():
        stat = root.stat()
        return ((str(root), stat.st_mtime_ns, stat.st_size),)
    if not root.exists():
        return tuple()
    ignored = {".git", ".sem", ".claude", "build", "dist", "__pycache__"}
    rows = []
    for pattern in ("*.sem", "*.sscript"):
        for source in root.rglob(pattern):
            try:
                relative = source.relative_to(root)
            except ValueError:
                relative = source
            if any(part in ignored for part in relative.parts[:-1]):
                continue
            try:
                stat = source.stat()
            except OSError:
                continue
            rows.append((str(source.resolve()), stat.st_mtime_ns, stat.st_size))
            if len(rows) > max_files:
                raise RuntimeError(
                    f"docs watcher saw more than {max_files} SemanticScript files under {root}; "
                    "use a narrower docs path or run docs_reindex with background=false"
                )
    return tuple(sorted(rows))


class DocsIndexWorker:
    def __init__(
        self,
        *,
        path: str,
        db: str,
        cwd: str | None,
        include_std: bool,
        interval_seconds: float,
        embedding_provider: str,
        embedding_model: str,
        allow_model_download: bool = False,
        max_files: int = DOCS_WATCH_MAX_FILES,
    ) -> None:
        self.path = path
        self.db = db
        self.cwd = cwd
        self.include_std = include_std
        self.interval_seconds = max(float(interval_seconds), 0.5)
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.allow_model_download = allow_model_download
        self.max_files = max_files
        self._trigger = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_snapshot: tuple[tuple[str, int, int], ...] | None = None
        self._last_payload: dict[str, Any] | None = None
        self._last_error = ""
        self._last_started = 0.0
        self._last_finished = 0.0
        self._index_count = 0
        self._error_count = 0
        self._backoff_until = 0.0
        self._thread = threading.Thread(target=self._run, name="sem-docs-index", daemon=True)
        self._thread.start()
        self.trigger()

    def trigger(self) -> None:
        self._trigger.set()

    def force_reindex(self) -> None:
        with self._lock:
            self._last_snapshot = None
        self.trigger()

    def stop(self) -> None:
        self._stop.set()
        self._trigger.set()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self._thread.is_alive(),
                "path": self.path,
                "db": self.db,
                "cwd": self.cwd,
                "includeStd": self.include_std,
                "intervalSeconds": self.interval_seconds,
                "embeddingProvider": self.embedding_provider,
                "embeddingModel": self.embedding_model,
                "allowModelDownload": self.allow_model_download,
                "maxFiles": self.max_files,
                "lastStarted": self._last_started,
                "lastFinished": self._last_finished,
                "indexCount": self._index_count,
                "errorCount": self._error_count,
                "backoffUntil": self._backoff_until,
                "lastError": self._last_error,
                "lastPayload": self._last_payload,
            }

    def _record_backoff(self, error: str) -> None:
        backoff = min(self.interval_seconds * 2 ** min(self._error_count, 5), 60.0)
        with self._lock:
            self._last_error = error
            self._last_finished = time.time()
            self._error_count += 1
            self._backoff_until = time.time() + backoff
        self._stop.wait(backoff)

    def _index_once(self, snapshot: tuple[tuple[str, int, int], ...]) -> bool:
        args = _argv(
            "docs",
            "index",
            "--json",
            "--path",
            self.path,
            "--db",
            self.db,
            "--include-std" if self.include_std else None,
            "--embedding-provider",
            self.embedding_provider,
            "--embedding-model",
            self.embedding_model,
            "--allow-model-download" if self.allow_model_download else None,
        )
        started = time.time()
        with self._lock:
            self._last_started = started
            self._last_error = ""
        with _docs_db_index_lock(self.db):
            payload = _run_sem(args, cwd=self.cwd, timeout=DOCS_INDEX_TIMEOUT_SECONDS)
        finished = time.time()
        with self._lock:
            self._last_finished = finished
            self._last_payload = payload
            self._index_count += 1
            if payload.get("ok", False):
                self._last_snapshot = snapshot
                self._error_count = 0
                self._backoff_until = 0.0
                self._last_error = ""
                return True
            self._last_error = json.dumps(payload.get("errors") or payload.get("error") or payload, sort_keys=True)
            return False

    def _run(self) -> None:
        while not self._stop.is_set():
            self._trigger.wait(self.interval_seconds)
            self._trigger.clear()
            if self._stop.is_set():
                break
            try:
                snapshot = _docs_snapshot(self.path, self.cwd, max_files=self.max_files)
                if snapshot != self._last_snapshot:
                    if not self._index_once(snapshot):
                        self._record_backoff(self._last_error or "docs index failed")
            except Exception as exc:  # keep background indexing from killing MCP
                self._record_backoff(str(exc))


_DOCS_WORKERS: dict[str, DocsIndexWorker] = {}
_DOCS_WORKERS_LOCK = threading.Lock()
_DOCS_DB_INDEX_LOCKS: dict[str, threading.Lock] = {}


def _docs_db_index_lock(db: str) -> threading.Lock:
    resolved_db = str(_resolve_workspace_path(db, None))
    with _DOCS_WORKERS_LOCK:
        lock = _DOCS_DB_INDEX_LOCKS.get(resolved_db)
        if lock is None:
            lock = threading.Lock()
            _DOCS_DB_INDEX_LOCKS[resolved_db] = lock
        return lock


def _docs_worker_key(
    *,
    path: str,
    db: str,
    cwd: str | None,
    include_std: bool,
    embedding_provider: str,
    embedding_model: str,
    allow_model_download: bool = False,
) -> str:
    return json.dumps(
        {
            "path": str(_resolve_workspace_path(path, cwd)),
            "db": str(_resolve_workspace_path(db, cwd)),
            "includeStd": include_std,
            "embeddingProvider": embedding_provider,
            "embeddingModel": embedding_model,
            "allowModelDownload": allow_model_download,
        },
        sort_keys=True,
    )


def _docs_find_worker_by_db(db: str, cwd: str | None) -> DocsIndexWorker | None:
    resolved_db = str(_resolve_workspace_path(db, cwd))
    for worker in _DOCS_WORKERS.values():
        if worker.status().get("db") == resolved_db:
            return worker
    return None


def _ensure_docs_worker(
    *,
    path: str,
    db: str | None = None,
    cwd: str | None = None,
    include_std: bool = True,
    interval_seconds: float = DEFAULT_DOCS_WATCH_INTERVAL_SECONDS,
    embedding_provider: str = DOCS_DEFAULT_EMBEDDING_PROVIDER,
    embedding_model: str = DOCS_DEFAULT_EMBEDDING_MODEL,
    allow_model_download: bool = False,
    max_files: int = DOCS_WATCH_MAX_FILES,
) -> DocsIndexWorker:
    resolved_db = _docs_resolved_db(path, db, cwd)
    key = _docs_worker_key(
        path=path,
        db=resolved_db,
        cwd=cwd,
        include_std=include_std,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        allow_model_download=allow_model_download,
    )
    with _DOCS_WORKERS_LOCK:
        worker = _DOCS_WORKERS.get(key)
        if worker is None or not worker.status().get("running"):
            for existing_key, existing_worker in list(_DOCS_WORKERS.items()):
                if existing_key != key and existing_worker.status().get("db") == resolved_db:
                    existing_worker.stop()
                    del _DOCS_WORKERS[existing_key]
            worker = DocsIndexWorker(
                path=path,
                db=resolved_db,
                cwd=cwd,
                include_std=include_std,
                interval_seconds=interval_seconds,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                allow_model_download=allow_model_download,
                max_files=max_files,
            )
            _DOCS_WORKERS[key] = worker
        else:
            worker.interval_seconds = max(float(interval_seconds), 0.5)
            worker.max_files = max_files
        return worker


def _sem_command(sub_args: list[str]) -> list[str]:
    """Build the argv that invokes the sem CLI.

    In a frozen (PyInstaller) build ``sys.executable`` is the ``sem``
    executable itself, which routes bare subcommands through its own CLI, so
    there is no separate script to name. Outside a frozen build we run the
    ``sem.py`` script with the current interpreter.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, *sub_args]
    return [sys.executable, str(SEM_PY), *sub_args]


def _run_sem(
    sub_args: list[str],
    cwd: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Invoke the sem CLI with ``--json`` and return the parsed payload.

    ``sem`` exits 0 on success, 1 when there are findings (still valid JSON),
    and 2 on usage errors. The JSON on stdout is authoritative, so a non-zero
    exit code is not treated as failure as long as stdout parses; the native
    ``sem.<surface>.vN`` payload is returned unchanged (its own ``ok``/``status``
    fields convey outcome). When stdout is empty or not JSON, a structured error
    envelope carrying the exit code and stderr is returned instead.
    """
    command = _sem_command(sub_args)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            timeout=timeout,
            # Detach the child from the server's stdio. Under the MCP stdio
            # transport the server's stdin/stdout are the JSON-RPC pipes;
            # letting the child inherit them corrupts the transport on Windows.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "timeout",
            "detail": f"sem did not complete within {timeout}s",
            "argv": command,
        }

    stdout = completed.stdout or ""
    if not stdout.strip():
        return {
            "ok": False,
            "error": "empty-output",
            "exitCode": completed.returncode,
            "stderr": (completed.stderr or "").strip(),
            "argv": command,
        }
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "non-json-output",
            "exitCode": completed.returncode,
            "stdout": stdout.strip(),
            "stderr": (completed.stderr or "").strip(),
            "argv": command,
        }


def _argv(*args: str | None) -> list[str]:
    """Assemble a sem argv, dropping ``None`` entries (unset optional flags)."""
    return [arg for arg in args if arg is not None]


@mcp.tool()
def version() -> dict[str, Any]:
    """Emit SemanticScript toolchain version facts (sem.version.v1)."""
    return _run_sem(["version", "--json"])


@mcp.tool(name="eval")
def eval_snippet(
    code: str,
    show_source: bool = False,
    max_output_bytes: int = 65536,
    timeout: int = 30,
    cwd: str | None = None,
) -> dict[str, Any]:
    """JIT-run a SemanticScript snippet or full program (sem.eval.v1).

    A snippet (bare operation-body rows) is auto-wrapped in a minimal console
    program: module-level declarations (import, error, errorCase, record, enum,
    capability, type, sharedState, and `storage module`) are hoisted above a
    generated `operation main`, and a stdout effect is added when the snippet
    uses `console.`. A complete program (one that declares its own `project`,
    `operation`, or `entry`) is compiled and run verbatim.

    The payload reports diagnostics (with snippet-relative line numbers),
    captured stdout/stderr as both a string and a line array, the program exit
    code, execution time (ns and µs, execution-only vs total), and the process
    peak working set. `ok` reflects harness success (compiled and ran to
    completion); read `execution.exitCode` for the program's own exit code and
    `status` for ok/nonzero-exit/crashed/compile-failed/timeout.

    Args:
        code: SemanticScript snippet rows or a full program.
        show_source: Include the wrapped program source in the payload.
        max_output_bytes: Cap captured stdout/stderr bytes (default 65536).
        timeout: Seconds before the run is abandoned (default 30).
        cwd: Working directory to run sem from.
    """
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".sem", prefix="sem-eval-mcp-",
        delete=False, encoding="utf-8", newline="\n")
    try:
        handle.write(code)
        handle.close()
        args = _argv(
            "eval", "--json",
            "--show-source" if show_source else None,
            "--max-output-bytes", str(int(max_output_bytes)),
            "--timeout", str(int(timeout)),
            handle.name,
        )
        return _run_sem(args, cwd=cwd, timeout=int(timeout) + 15)
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


@mcp.tool()
def doctor() -> dict[str, Any]:
    """Report toolchain health and environment readiness (sem.doctor.v0)."""
    return _run_sem(["doctor", "--json"])


@mcp.tool()
def check(
    path: str = ".",
    with_readiness: bool = False,
    full: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Parse and lint a build.sem project or source file (sem.check.v1).

    Args:
        path: Path to a .sem source file or a project directory.
        with_readiness: Embed target/runtime readiness facts in the payload.
        full: Return the full payload instead of the compact agent windows.
        cwd: Working directory to run sem from (defaults to the server's cwd).
    """
    args = _argv(
        "check",
        "--json",
        "--with-readiness" if with_readiness else None,
        "--full" if full else None,
        path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def readiness(path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Emit target, runtime, and toolchain readiness facts (sem.readiness.v1)."""
    return _run_sem(["readiness", "--json", path], cwd=cwd)


@mcp.tool()
def context(path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Emit project context for agents and tooling (sem.context.v1)."""
    return _run_sem(["context", "--json", path], cwd=cwd)


@mcp.tool()
def symbols(path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Emit a source symbol graph for agents and tooling (sem.symbols.v1)."""
    return _run_sem(["symbols", "--json", path], cwd=cwd)


@mcp.tool()
def graph(
    path: str = ".",
    kind: str = "summary",
    full: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Emit an agent-first architecture graph from source (sem.graph.v1).

    Args:
        path: Path to a .sem source file or a project directory.
        kind: One of summary, calls, effects, capabilities, auth, routes,
            dataflow, types, ownership.
        full: Return the full payload instead of the compact agent windows.
        cwd: Working directory to run sem from.
    """
    args = _argv(
        "graph",
        "--kind",
        kind,
        "--json",
        "--full" if full else None,
        path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def slice(
    path: str = ".",
    operation: str | None = None,
    route: str | None = None,
    symbol: str | None = None,
    effect: str | None = None,
    capability: str | None = None,
    type_name: str | None = None,
    full: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Emit the semantic neighborhood around an anchor (sem.slice.v1).

    Provide exactly one anchor: operation, route (METHOD:/path), symbol,
    effect, capability, or type_name.
    """
    anchors = [operation, route, symbol, effect, capability, type_name]
    provided = [anchor for anchor in anchors if anchor is not None]
    if len(provided) != 1:
        return {
            "ok": False,
            "error": "anchor-arity",
            "detail": (
                "slice requires exactly one anchor "
                "(operation, route, symbol, effect, capability, or type_name)"
            ),
            "provided": len(provided),
        }
    args = _argv(
        "slice",
        "--json",
        "--full" if full else None,
        "--operation" if operation is not None else None,
        operation,
        "--route" if route is not None else None,
        route,
        "--symbol" if symbol is not None else None,
        symbol,
        "--effect" if effect is not None else None,
        effect,
        "--capability" if capability is not None else None,
        capability,
        "--type" if type_name is not None else None,
        type_name,
        path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def size(path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Emit source and helper-footprint facts (sem.size.v1)."""
    return _run_sem(["size", "--json", path], cwd=cwd)


@mcp.tool()
def explain(code: str) -> dict[str, Any]:
    """Explain a compiler, linter, or runtime diagnostic code (sem.explain.v1).

    Args:
        code: A diagnostic code such as SS3104.
    """
    return _run_sem(["explain", "--json", code])


@mcp.tool()
def skills_list() -> dict[str, Any]:
    """List built-in version-matched agent skills (sem.skills.v1)."""
    return _run_sem(["skills", "list", "--json"])


@mcp.tool()
def skills_get(
    names: list[str] | None = None,
    all_skills: bool = False,
    full: bool = False,
) -> dict[str, Any]:
    """Load one or more built-in agent skills (sem.skills.v1).

    Args:
        names: Skill names to load, e.g. ["sem", "sem-agent"].
        all_skills: Return every visible skill instead of named ones.
        full: Include full raw skill bodies instead of the summary-first shape.
    """
    args = _argv(
        "skills",
        "get",
        "--json",
        "--all" if all_skills else None,
        "--full" if full else None,
        *(names or []),
    )
    return _run_sem(args)


@mcp.tool()
def fix_plan(
    path: str = ".",
    include_warnings: bool = False,
    full: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Generate a reviewable structured repair plan (sem.fixPlan.v1).

    This never edits files; it emits a plan. Auto-apply only when the payload
    reports status "actionable" and planUsable true. Save the plan JSON and
    pass it to the patch tool (start with apply=false) to apply it.
    """
    args = _argv(
        "fix",
        "--plan",
        "--json",
        "--include-warnings" if include_warnings else None,
        "--full" if full else None,
        path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def patch(plan_path: str, apply: bool = False, cwd: str | None = None) -> dict[str, Any]:
    """Preview or apply a structured repair plan (sem.patch.v1).

    Args:
        plan_path: Path to a plan JSON file produced by fix_plan.
        apply: When false (default) preview only (--dry-run). When true, apply
            the plan and modify files on disk.
        cwd: Working directory to run sem from.
    """
    mode = "--apply" if apply else "--dry-run"
    return _run_sem(["patch", mode, "--json", plan_path], cwd=cwd)


@mcp.tool()
def test(
    path: str = ".",
    skip_python_harnesses: bool = False,
    allow_red_preflight_harnesses: bool = False,
    full: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run a first-pass SemanticScript and harness test surface (sem.test.v1)."""
    args = _argv(
        "test",
        "--json",
        "--full" if full else None,
        "--skip-python-harnesses" if skip_python_harnesses else None,
        "--allow-red-preflight-harnesses" if allow_red_preflight_harnesses else None,
        path,
    )
    return _run_sem(args, cwd=cwd, timeout=TEST_TIMEOUT_SECONDS)


@mcp.tool()
def dev(
    path: str = ".",
    trace: bool = False,
    full: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Emit an agent-first watch plan for iterative edit loops (sem.dev.v1)."""
    args = _argv(
        "dev",
        "--json",
        "--trace" if trace else None,
        "--full" if full else None,
        path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def deps(
    action: str = "list",
    path: str = ".",
    offline: bool = False,
    force: bool = False,
    lock: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Resolve external dependencies: sync/verify/list/cache/purge (sem.deps.v1).

    `sync` fetches + verifies + locks (network); `verify`/`list`/`cache` are
    offline; `purge` removes cached source. Defaults to the read-only `list`.
    Only `sync` (without `offline`) touches the network."""
    args = _argv(
        "deps",
        action,
        "--json",
        "--offline" if offline else None,
        "--force" if force else None,
        "--lock" if lock else None,
        path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def docs_list(
    module: str | None = None,
    summary_tag: str = "rationale",
    include_internal: bool = False,
    std_path: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """List documented APIs and call targets (sem.docs.v1)."""
    args = _argv(
        "docs",
        "list",
        "--json",
        "--module" if module else None, module,
        "--summary-tag", summary_tag,
        "--all" if include_internal else None,
        "--std-path" if std_path else None, std_path,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def docs_get(
    operation: str,
    module: str | None = None,
    include_internal: bool = False,
    std_path: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Get documentation for one API or call target (sem.docs.v1)."""
    args = _argv(
        "docs",
        "get",
        "--json",
        "--module" if module else None, module,
        "--all" if include_internal else None,
        "--std-path" if std_path else None, std_path,
        operation,
    )
    return _run_sem(args, cwd=cwd)


@mcp.tool()
def docs_watch(
    path: str = ".",
    db: str | None = None,
    include_std: bool = True,
    interval_seconds: float = DEFAULT_DOCS_WATCH_INTERVAL_SECONDS,
    embedding_provider: str = DOCS_DEFAULT_EMBEDDING_PROVIDER,
    embedding_model: str = DOCS_DEFAULT_EMBEDDING_MODEL,
    allow_model_download: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Start or reuse the background docs/vector index worker (sem.docsIndex.v1)."""
    worker = _ensure_docs_worker(
        path=path,
        db=db,
        cwd=cwd,
        include_std=include_std,
        interval_seconds=interval_seconds,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        allow_model_download=allow_model_download,
    )
    worker.trigger()
    return {"ok": True, "status": "watching", "worker": worker.status()}


@mcp.tool()
def docs_reindex(
    path: str = ".",
    db: str | None = None,
    include_std: bool = True,
    background: bool = True,
    embedding_provider: str = DOCS_DEFAULT_EMBEDDING_PROVIDER,
    embedding_model: str = DOCS_DEFAULT_EMBEDDING_MODEL,
    allow_model_download: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Refresh docs index now or queue a background refresh (sem.docsIndex.v1)."""
    resolved_db = _docs_resolved_db(path, db, cwd)
    if background:
        worker = _ensure_docs_worker(
            path=path,
            db=resolved_db,
            cwd=cwd,
            include_std=include_std,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            allow_model_download=allow_model_download,
        )
        worker.force_reindex()
        return {"ok": True, "status": "queued", "worker": worker.status()}
    args = _argv(
        "docs",
        "index",
        "--json",
        "--path",
        path,
        "--db",
        resolved_db,
        "--include-std" if include_std else None,
        "--embedding-provider",
        embedding_provider,
        "--embedding-model",
        embedding_model,
        "--allow-model-download" if allow_model_download else None,
    )
    with _docs_db_index_lock(resolved_db):
        return _run_sem(args, cwd=cwd, timeout=DOCS_INDEX_TIMEOUT_SECONDS)


@mcp.tool()
def docs_index_status(
    path: str = ".",
    db: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Return docs index DB status plus background worker state (sem.docsIndex.v1)."""
    resolved_db = _docs_resolved_db(path, db, cwd)
    payload = _run_sem(_argv("docs", "status", "--json", "--path", path, "--db", resolved_db), cwd=cwd)
    with _DOCS_WORKERS_LOCK:
        worker = _docs_find_worker_by_db(resolved_db, cwd)
    payload["worker"] = worker.status() if worker is not None else {"running": False}
    return payload


@mcp.tool()
def docs_search(
    query: str,
    path: str = ".",
    db: str | None = None,
    limit: int = 10,
    watch: bool = False,
    include_std: bool = True,
    embedding_provider: str = "auto",
    embedding_model: str | None = None,
    allow_model_download: bool = False,
    include_docs: bool = False,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Search cached docs with hybrid FTS/vector ranking (sem.docsSearch.v1)."""
    resolved_db = _docs_resolved_db(path, db, cwd)
    worker: DocsIndexWorker | None = None
    if watch:
        with _DOCS_WORKERS_LOCK:
            worker = _docs_find_worker_by_db(resolved_db, cwd)
        if worker is not None:
            worker.trigger()
        else:
            worker = _ensure_docs_worker(
                path=path,
                db=resolved_db,
                cwd=cwd,
                include_std=include_std,
                embedding_provider=DOCS_DEFAULT_EMBEDDING_PROVIDER if embedding_provider == "auto" else embedding_provider,
                embedding_model=embedding_model or DOCS_DEFAULT_EMBEDDING_MODEL,
                allow_model_download=allow_model_download,
            )
    args = _argv(
        "docs",
        "search",
        "--json",
        "--path",
        path,
        "--db",
        resolved_db,
        "--limit",
        str(limit),
        "--embedding-provider",
        embedding_provider,
        "--embedding-model" if embedding_model else None,
        embedding_model,
        "--allow-model-download" if allow_model_download else None,
        "--include-docs" if include_docs else None,
        query,
    )
    payload = _run_sem(args, cwd=cwd)
    if payload.get("status") == "index-missing" and watch:
        if worker is None:
            with _DOCS_WORKERS_LOCK:
                worker = _docs_find_worker_by_db(resolved_db, cwd)
        payload["worker"] = worker.status() if worker is not None else {"running": False}
    return payload


@mcp.tool()
def help(path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Recommend the next-step agent workflow for a project (sem.help.v1).

    Returns project state plus an ordered, replayable nextCommands list so an
    agent always has a concrete next action."""
    return _run_sem(_argv("help", "--json", path), cwd=cwd)


def main(argv: list[str] | None = None) -> None:
    """Run the MCP server.

    Defaults to the stdio transport (the form MCP desktop clients launch). Pass
    ``--transport streamable-http`` (with optional ``--host``/``--port``/``--path``)
    to serve over HTTP for remote or multi-client use.
    """
    import argparse

    parser = argparse.ArgumentParser(prog="sem mcp", add_help=True)
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="transport to serve on (default: stdio)",
    )
    parser.add_argument("--host", help="bind host for HTTP transports (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, help="bind port for HTTP transports (default: 8000)")
    parser.add_argument("--path", help="HTTP route for the streamable-http transport")
    parser.add_argument("--docs-path", help="start a background docs index worker for this project/source path")
    parser.add_argument("--docs-db", help="SQLite docs index path for the background docs worker")
    parser.add_argument("--docs-watch-interval", type=float, default=DEFAULT_DOCS_WATCH_INTERVAL_SECONDS, help="background docs polling interval in seconds")
    parser.add_argument("--docs-allow-model-download", action="store_true", help="allow the docs worker to download the embedding model when it is not cached")
    parser.add_argument("--no-docs-std", action="store_true", help="do not include std docs in the background docs index")
    args = parser.parse_args(argv)

    if args.host is not None:
        mcp.settings.host = args.host
    if args.port is not None:
        mcp.settings.port = args.port
    if args.path is not None:
        mcp.settings.streamable_http_path = args.path

    if args.docs_path is not None:
        _ensure_docs_worker(
            path=args.docs_path,
            db=args.docs_db,
            cwd=None,
            include_std=not args.no_docs_std,
            interval_seconds=args.docs_watch_interval,
            allow_model_download=args.docs_allow_model_download,
        )

    # The server exposes file-mutating (patch) and code-executing (eval, test)
    # tools. `eval` JIT-compiles and runs arbitrary SemanticScript, so over HTTP
    # it is remote code execution for anything that can hit the bind address.
    # Warn loudly when the effective bind host is beyond loopback. Checking the
    # effective host (not just an explicit --host) keeps the guard correct even
    # if the SDK's default host ever changes.
    if args.transport != "stdio":
        loopback = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}
        effective_host = args.host if args.host is not None else getattr(mcp.settings, "host", None)
        if effective_host is not None and effective_host not in loopback:
            print(
                f"WARNING: serving MCP over {args.transport} on {effective_host} exposes "
                "file-mutating (patch) and code-executing (eval, test) tools to any "
                "client that can reach this address; `eval` runs arbitrary compiled "
                "code. Bind a loopback host unless the network is trusted.",
                file=sys.stderr,
            )

    if args.transport == "stdio":
        anyio.run(_run_stdio_bom_tolerant_async)
    else:
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
