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
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

SEM_PY = Path(__file__).resolve().parent / "sem.py"

# Most surfaces are fast; `test` can run harnesses, so it gets a larger budget.
DEFAULT_TIMEOUT_SECONDS = 120
TEST_TIMEOUT_SECONDS = 600

mcp = FastMCP("semanticscript")


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
def help(path: str = ".", cwd: str | None = None) -> dict[str, Any]:
    """Recommend the next-step agent workflow for a project (sem.help.v1).

    Returns project state plus an ordered, replayable nextCommands list so an
    agent always has a concrete next action."""
    return _run_sem(_argv("help", "--json", path), cwd=cwd)


def tool_catalog() -> list[dict[str, Any]]:
    """Return the registered MCP tools as plain dicts.

    Lets agents see the tool surface without scripting the JSON-RPC
    ``initialize`` -> ``tools/list`` handshake. Uses the public async
    ``FastMCP.list_tools`` API, driven synchronously here.
    """
    import asyncio

    tools = asyncio.run(mcp.list_tools())
    catalog = []
    for tool in tools:
        catalog.append({
            "name": tool.name,
            "description": (tool.description or "").strip(),
            "inputSchema": getattr(tool, "inputSchema", None),
        })
    catalog.sort(key=lambda entry: entry["name"])
    return catalog


def main(argv: list[str] | None = None) -> None:
    """Run the MCP server.

    Defaults to the stdio transport (the form MCP desktop clients launch). Pass
    ``--transport streamable-http`` (with optional ``--host``/``--port``/``--path``)
    to serve over HTTP for remote or multi-client use. Pass ``--list-tools`` to
    print the tool catalog as JSON and exit without serving.
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
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="print the MCP tool catalog as JSON and exit without serving",
    )
    args = parser.parse_args(argv)

    if args.list_tools:
        catalog = tool_catalog()
        print(json.dumps({
            "schemaVersion": "sem.mcpTools.v1",
            "server": "semanticscript",
            "toolCount": len(catalog),
            "tools": catalog,
        }, indent=2, sort_keys=True))
        return

    if args.host is not None:
        mcp.settings.host = args.host
    if args.port is not None:
        mcp.settings.port = args.port
    if args.path is not None:
        mcp.settings.streamable_http_path = args.path

    # The server exposes file-mutating (patch) and code-executing (test) tools.
    # Over HTTP that is reachable by anything that can hit the bind address, so
    # warn loudly when the effective bind host is beyond loopback. Checking the
    # effective host (not just an explicit --host) keeps the guard correct even
    # if the SDK's default host ever changes.
    if args.transport != "stdio":
        loopback = {"127.0.0.1", "localhost", "::1", "::ffff:127.0.0.1"}
        effective_host = args.host if args.host is not None else getattr(mcp.settings, "host", None)
        if effective_host is not None and effective_host not in loopback:
            print(
                f"WARNING: serving MCP over {args.transport} on {effective_host} exposes "
                "file-mutating (patch) and code-executing (test) tools to any client "
                "that can reach this address. Bind a loopback host unless the network "
                "is trusted.",
                file=sys.stderr,
            )

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
