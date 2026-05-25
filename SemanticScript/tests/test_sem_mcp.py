import argparse
import asyncio
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from SemanticScript.tools import sem

MCP_AVAILABLE = importlib.util.find_spec("mcp") is not None

if MCP_AVAILABLE:
    from SemanticScript.tools import sem_mcp

EXPECTED_TOOLS = {
    "version",
    "eval",
    "bootstrap",
    "agent_docs",
    "doctor",
    "check",
    "readiness",
    "context",
    "symbols",
    "graph",
    "slice",
    "size",
    "explain",
    "skills_list",
    "skills_get",
    "fix_plan",
    "patch",
    "test",
    "dev",
    "deps",
    "docs_list",
    "docs_get",
    "docs_watch",
    "docs_reindex",
    "docs_index_status",
    "docs_search",
    "help",
}

MINIMAL_SOURCE = """\
project ProbeProgram
target console
runtime native 1
module examples.probeProgram
entry console main
operation main
output operation main ExitCode
storage local immutable successExitCode ExitCode 0
return value successExitCode
"""


def _structured(result: object) -> dict:
    """Extract the structured JSON dict from a FastMCP call_tool result."""
    if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], dict):
        return result[1]
    raise AssertionError(f"unexpected call_tool result shape: {result!r}")


@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
class TestSemMcpServer(unittest.TestCase):
    def test_expected_tools_registered(self) -> None:
        tools = asyncio.run(sem_mcp.mcp.list_tools())
        self.assertEqual({tool.name for tool in tools}, EXPECTED_TOOLS)

    def test_every_tool_has_a_description(self) -> None:
        tools = asyncio.run(sem_mcp.mcp.list_tools())
        for tool in tools:
            self.assertTrue(
                tool.description and tool.description.strip(),
                f"tool {tool.name} is missing a description",
            )

    def test_version_tool_returns_version_payload(self) -> None:
        result = asyncio.run(sem_mcp.mcp.call_tool("version", {}))
        payload = _structured(result)
        self.assertIn("compiler", payload)

    def test_initialize_instructions_point_to_starting_skill_and_docs(self) -> None:
        instructions = sem_mcp.mcp.instructions
        self.assertIn('agent_docs {"path":"."}', instructions)
        self.assertIn('skills_get {"names":["sem-start","sem","sem-agent","sem-syntax"]}', instructions)
        self.assertIn('help {"path":"."}', instructions)
        self.assertIn("docs_search", instructions)
        self.assertIn("eval", instructions)

    def test_bootstrap_tool_returns_bootstrap_payload(self) -> None:
        result = asyncio.run(sem_mcp.mcp.call_tool("bootstrap", {"path": "."}))
        payload = _structured(result)
        self.assertEqual(payload["schemaVersion"], "sem.bootstrap.v1")
        self.assertEqual(payload["mcp"]["firstToolCalls"][0]["tool"], "agent_docs")
        self.assertEqual(payload["mcp"]["firstToolCalls"][1]["tool"], "skills_get")
        self.assertEqual(payload["languageSmoke"]["mcp"]["tool"], "eval")

    def test_explain_tool_returns_explain_schema(self) -> None:
        result = asyncio.run(sem_mcp.mcp.call_tool("explain", {"code": "SS3104"}))
        payload = _structured(result)
        self.assertEqual(payload["schemaVersion"], "sem.explain.v1")

    def test_eval_tool_runs_a_snippet(self) -> None:
        code = ('storage local immutable greeting String "mcp-eval"\n'
                "call printCall console.writeLine\n"
                "argument printCall text String greeting\n"
                "run printCall\n")
        result = asyncio.run(sem_mcp.mcp.call_tool("eval", {"code": code}))
        payload = _structured(result)
        self.assertEqual(payload["schemaVersion"], "sem.eval.v1")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["output"]["stdout"], "mcp-eval\n")
        self.assertEqual(payload["execution"]["exitCode"], 0)
        self.assertIn("linter", payload["notes"])


@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
class TestSemMcpWrapper(unittest.TestCase):
    def test_run_sem_parses_json_payload(self) -> None:
        payload = sem_mcp._run_sem(["version", "--json"])
        self.assertIn("compiler", payload)

    def test_run_sem_returns_empty_output_envelope(self) -> None:
        # `explain` without a code argument is an argparse usage error (exit 2)
        # that prints to stderr and leaves stdout empty.
        payload = sem_mcp._run_sem(["explain", "--json"])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "empty-output")
        self.assertEqual(payload["exitCode"], 2)
        self.assertTrue(payload["stderr"])

    def test_run_sem_non_json_envelope_surfaces_exit_code(self) -> None:
        completed = mock.Mock(returncode=1, stdout="not json at all", stderr="boom")
        with mock.patch.object(sem_mcp.subprocess, "run", return_value=completed):
            payload = sem_mcp._run_sem(["version", "--json"])
        self.assertEqual(payload["error"], "non-json-output")
        self.assertEqual(payload["exitCode"], 1)
        self.assertEqual(payload["stderr"], "boom")

    def test_sem_command_uses_script_outside_frozen_build(self) -> None:
        with mock.patch.object(sem_mcp.sys, "frozen", False, create=True):
            command = sem_mcp._sem_command(["version", "--json"])
        self.assertEqual(command[1], str(sem_mcp.SEM_PY))
        self.assertEqual(command[2:], ["version", "--json"])

    def test_sem_command_omits_script_in_frozen_build(self) -> None:
        with mock.patch.object(sem_mcp.sys, "frozen", True, create=True):
            command = sem_mcp._sem_command(["version", "--json"])
        # In a frozen build the executable *is* sem; no script path is inserted.
        self.assertEqual(command[1:], ["version", "--json"])
        self.assertNotIn(str(sem_mcp.SEM_PY), command)

    def test_slice_requires_exactly_one_anchor(self) -> None:
        with mock.patch.object(sem_mcp, "_run_sem") as run:
            no_anchor = sem_mcp.slice(path="proj")
            two_anchors = sem_mcp.slice(path="proj", operation="main", effect="write")
            run.assert_not_called()
        self.assertEqual(no_anchor["error"], "anchor-arity")
        self.assertEqual(two_anchors["error"], "anchor-arity")

    def test_slice_forwards_single_anchor(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.slice(path="proj", operation="main")
        self.assertEqual(recorded["args"], ["slice", "--json", "--operation", "main", "proj"])

    def test_check_argv_places_flags_before_path(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.check(path="main.sem", with_readiness=True, full=True)
        self.assertEqual(
            recorded["args"],
            ["check", "--json", "--with-readiness", "--full", "main.sem"],
        )

    def test_deps_forwards_action_and_flags(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.deps(action="sync", path="proj", force=True)
        self.assertEqual(recorded["args"], ["deps", "sync", "--json", "--force", "proj"])

    def test_deps_defaults_to_readonly_list(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.deps(path="proj")
        self.assertEqual(recorded["args"], ["deps", "list", "--json", "proj"])

    def test_help_forwards_path(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.help(path="proj")
        self.assertEqual(recorded["args"], ["help", "--json", "proj"])

    def test_bootstrap_forwards_path(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.bootstrap(path="proj")
        self.assertEqual(recorded["args"], ["bootstrap", "--json", "proj"])

    def test_agent_docs_forwards_path(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            recorded["cwd"] = cwd
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.agent_docs(path="proj", max_bytes=123, cwd="root")
        self.assertEqual(recorded["args"], ["agent-docs", "--json", "--max-bytes", "123", "proj"])
        self.assertEqual(recorded["cwd"], "root")

    def test_docs_list_and_get_forward_docs_surface(self) -> None:
        recorded: list[list[str]] = []

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded.append(sub_args)
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.docs_list(module="http", include_internal=True, std_path="std")
            sem_mcp.docs_get(operation="http.clientGet", module="http", std_path="std")

        self.assertEqual(
            recorded[0],
            ["docs", "list", "--json", "--module", "http", "--summary-tag", "rationale", "--all", "--std-path", "std"],
        )
        self.assertEqual(
            recorded[1],
            ["docs", "get", "--json", "--module", "http", "--std-path", "std", "http.clientGet"],
        )

    def test_docs_worker_key_includes_path_and_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = sem_mcp._docs_worker_key(
                path="project-a",
                db=sem_mcp._docs_resolved_db("project-a", None, tmp),
                cwd=tmp,
                include_std=True,
                embedding_provider=sem_mcp.DOCS_DEFAULT_EMBEDDING_PROVIDER,
                embedding_model="model-a",
            )
            second = sem_mcp._docs_worker_key(
                path="project-b",
                db=sem_mcp._docs_resolved_db("project-b", None, tmp),
                cwd=tmp,
                include_std=True,
                embedding_provider=sem_mcp.DOCS_DEFAULT_EMBEDDING_PROVIDER,
                embedding_model="model-a",
            )
            third = sem_mcp._docs_worker_key(
                path="project-a",
                db=sem_mcp._docs_resolved_db("project-a", None, tmp),
                cwd=tmp,
                include_std=False,
                embedding_provider=sem_mcp.DOCS_DEFAULT_EMBEDDING_PROVIDER,
                embedding_model="model-a",
            )

        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)

    def test_docs_worker_does_not_complete_snapshot_after_failed_payload(self) -> None:
        worker = object.__new__(sem_mcp.DocsIndexWorker)
        worker.path = "proj"
        worker.db = "docs.sqlite"
        worker.cwd = None
        worker.include_std = True
        worker.interval_seconds = 5.0
        worker.embedding_provider = sem_mcp.DOCS_DEFAULT_EMBEDDING_PROVIDER
        worker.embedding_model = sem_mcp.DOCS_DEFAULT_EMBEDDING_MODEL
        worker.allow_model_download = False
        worker.max_files = sem_mcp.DOCS_WATCH_MAX_FILES
        worker._lock = sem_mcp.threading.Lock()
        worker._last_snapshot = None
        worker._last_payload = None
        worker._last_error = ""
        worker._last_started = 0.0
        worker._last_finished = 0.0
        worker._index_count = 0
        worker._error_count = 0
        worker._backoff_until = 0.0

        with mock.patch.object(sem_mcp, "_run_sem", return_value={"ok": False, "errors": ["boom"]}):
            failed = worker._index_once((("main.sem", 1, 1),))

        self.assertFalse(failed)
        self.assertIsNone(worker._last_snapshot)
        self.assertIn("boom", worker._last_error)

        with mock.patch.object(sem_mcp, "_run_sem", return_value={"ok": True}):
            succeeded = worker._index_once((("main.sem", 1, 1),))

        self.assertTrue(succeeded)
        self.assertEqual(worker._last_snapshot, (("main.sem", 1, 1),))

    def test_docs_reindex_foreground_uses_db_lock(self) -> None:
        recorded: dict[str, list[str]] = {}
        lock = mock.MagicMock()
        lock.__enter__.return_value = None
        lock.__exit__.return_value = None

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_docs_db_index_lock", return_value=lock) as lock_factory:
            with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
                sem_mcp.docs_reindex(path="proj", db="docs.sqlite", background=False)

        lock_factory.assert_called_once()
        lock.__enter__.assert_called_once()
        lock.__exit__.assert_called_once()
        self.assertEqual(recorded["args"][:4], ["docs", "index", "--json", "--path"])

    def test_docs_search_starts_worker_and_forwards_query(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True, "status": "ok", "results": []}

        fake_worker = mock.Mock()
        fake_worker.status.return_value = {"running": True}
        with mock.patch.object(sem_mcp, "_ensure_docs_worker", return_value=fake_worker) as ensure:
            with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
                sem_mcp.docs_search(query="write http response", path="proj", db="docs.sqlite", limit=3, watch=True)
        ensure.assert_called_once()
        self.assertEqual(recorded["args"][:6], ["docs", "search", "--json", "--path", "proj", "--db"])
        self.assertEqual(Path(recorded["args"][6]).name, "docs.sqlite")
        self.assertIn("write http response", recorded["args"])

    def test_docs_search_uses_path_derived_default_db(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": False, "status": "index-missing", "results": []}

        fake_worker = mock.Mock()
        fake_worker.status.return_value = {"running": True}
        with tempfile.TemporaryDirectory() as tmp:
            expected_db = str((Path(tmp) / "proj" / ".sem" / "docs.sqlite").resolve())
            with mock.patch.object(sem_mcp, "_ensure_docs_worker", return_value=fake_worker):
                with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
                    payload = sem_mcp.docs_search(query="task", path="proj", db=None, cwd=tmp, watch=True)

        self.assertEqual(recorded["args"][recorded["args"].index("--db") + 1], expected_db)
        self.assertEqual(payload["worker"], {"running": True})

    def test_docs_search_reuses_existing_worker_for_same_db(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True, "status": "ok", "results": []}

        fake_worker = mock.Mock()
        fake_worker.status.return_value = {"running": True, "db": str(Path("docs.sqlite").resolve())}
        with mock.patch.object(sem_mcp, "_docs_find_worker_by_db", return_value=fake_worker):
            with mock.patch.object(sem_mcp, "_ensure_docs_worker") as ensure:
                with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
                    sem_mcp.docs_search(query="task", path="proj", db="docs.sqlite", include_std=True, watch=True)

        ensure.assert_not_called()
        fake_worker.trigger.assert_called_once()
        self.assertIn("task", recorded["args"])

    def test_docs_search_does_not_start_worker_by_default(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True, "status": "ok", "results": []}

        with mock.patch.object(sem_mcp, "_ensure_docs_worker") as ensure:
            with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
                sem_mcp.docs_search(query="task", path="proj", db="docs.sqlite")

        ensure.assert_not_called()
        self.assertIn("task", recorded["args"])

    def test_run_sem_timeout_envelope(self) -> None:
        with mock.patch(
            "SemanticScript.tools.sem_mcp.subprocess.run",
            side_effect=__import__("subprocess").TimeoutExpired(cmd="sem", timeout=1),
        ):
            payload = sem_mcp._run_sem(["version", "--json"], timeout=1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "timeout")

    def test_check_tool_on_minimal_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(MINIMAL_SOURCE, encoding="utf-8")
            payload = sem_mcp.check(path=str(source))
        self.assertEqual(payload["schemaVersion"], "sem.check.v1")
        self.assertTrue(payload["ok"])

    def test_patch_apply_flag_selects_mode(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.patch(plan_path="plan.json", apply=False)
            self.assertIn("--dry-run", recorded["args"])
            self.assertNotIn("--apply", recorded["args"])

            sem_mcp.patch(plan_path="plan.json", apply=True)
            self.assertIn("--apply", recorded["args"])
            self.assertNotIn("--dry-run", recorded["args"])

    def test_graph_kind_is_forwarded(self) -> None:
        recorded: dict[str, list[str]] = {}

        def fake_run(sub_args, cwd=None, timeout=sem_mcp.DEFAULT_TIMEOUT_SECONDS):
            recorded["args"] = sub_args
            return {"ok": True}

        with mock.patch.object(sem_mcp, "_run_sem", side_effect=fake_run):
            sem_mcp.graph(path="proj", kind="routes")
        self.assertEqual(recorded["args"][:3], ["graph", "--kind", "routes"])


class TestSemMcpSubcommand(unittest.TestCase):
    """The `sem mcp` subcommand should work without importing the SDK eagerly."""

    def test_mcp_subcommand_dispatches_to_command_mcp(self) -> None:
        parser = sem.build_parser()
        args = parser.parse_args(["mcp"])
        self.assertIs(args.func, sem.command_mcp)

    def test_command_mcp_reports_missing_sdk(self) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "tools" and "sem_mcp" in (fromlist or ()):
                raise ModuleNotFoundError("No module named 'mcp'", name="mcp")
            return real_import(name, globals, locals, fromlist, level)

        stderr = io.StringIO()
        with mock.patch("builtins.__import__", side_effect=fake_import):
            with mock.patch("sys.stderr", stderr):
                exit_code = sem.command_mcp(argparse.Namespace())

        self.assertEqual(exit_code, 2)
        self.assertIn("pip install", stderr.getvalue())

    @unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
    def test_command_mcp_runs_server_when_sdk_present(self) -> None:
        # sem.py puts the SemanticScript dir on sys.path, so `tools.sem_mcp` is
        # the same module object that command_mcp imports.
        import tools.sem_mcp  # noqa: F401

        args = argparse.Namespace(transport="stdio", host=None, port=None, path=None, docs_allow_model_download=False)
        with mock.patch("tools.sem_mcp.main") as fake_main:
            exit_code = sem.command_mcp(args)

        fake_main.assert_called_once_with(["--transport", "stdio"])
        self.assertEqual(exit_code, 0)

    @unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
    def test_command_mcp_forwards_docs_worker_options(self) -> None:
        import tools.sem_mcp  # noqa: F401

        args = argparse.Namespace(
            transport="stdio",
            host=None,
            port=None,
            path=None,
            docs_path="proj",
            docs_db="docs.sqlite",
            docs_watch_interval=1.5,
            docs_allow_model_download=True,
            no_docs_std=True,
        )
        with mock.patch("tools.sem_mcp.main") as fake_main:
            sem.command_mcp(args)

        fake_main.assert_called_once_with([
            "--transport", "stdio",
            "--docs-path", "proj",
            "--docs-db", "docs.sqlite",
            "--docs-watch-interval", "1.5",
            "--docs-allow-model-download",
            "--no-docs-std",
        ])

    @unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
    def test_command_mcp_forwards_http_transport_options(self) -> None:
        import tools.sem_mcp  # noqa: F401

        args = argparse.Namespace(
            transport="streamable-http", host="0.0.0.0", port=9000, path="/mcp", docs_allow_model_download=False
        )
        with mock.patch("tools.sem_mcp.main") as fake_main:
            sem.command_mcp(args)

        fake_main.assert_called_once_with(
            ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000", "--path", "/mcp"]
        )


@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
class TestSemMcpTransport(unittest.TestCase):
    def test_main_defaults_to_stdio(self) -> None:
        with mock.patch.object(sem_mcp.anyio, "run") as run:
            sem_mcp.main([])
        run.assert_called_once_with(sem_mcp._run_stdio_bom_tolerant_async)

    def test_stdio_reader_strips_initial_utf8_bom(self) -> None:
        raw = io.BytesIO(b'\xef\xbb\xbf{"jsonrpc":"2.0"}\n{"jsonrpc":"2.0"}\n')
        reader = sem_mcp._stdio_text_reader(raw)

        self.assertEqual(reader.readline(), '{"jsonrpc":"2.0"}\n')
        self.assertEqual(reader.readline(), '{"jsonrpc":"2.0"}\n')

    def test_stdio_initial_line_sanitizer_handles_powershell_bom_artifacts(self) -> None:
        expected = '{"jsonrpc":"2.0"}'
        self.assertEqual(sem_mcp._sanitize_initial_stdio_line(f"\ufeff{expected}"), expected)
        self.assertEqual(sem_mcp._sanitize_initial_stdio_line(f"?{expected}"), expected)
        self.assertEqual(sem_mcp._sanitize_initial_stdio_line(f"\ufffd{expected}"), expected)
        self.assertEqual(sem_mcp._sanitize_initial_stdio_line("?not-json"), "?not-json")

    def test_main_configures_streamable_http(self) -> None:
        with mock.patch.object(sem_mcp.mcp, "run") as run:
            sem_mcp.main(
                ["--transport", "streamable-http", "--host", "1.2.3.4", "--port", "9100", "--path", "/x"]
            )
        run.assert_called_once_with(transport="streamable-http")
        self.assertEqual(sem_mcp.mcp.settings.host, "1.2.3.4")
        self.assertEqual(sem_mcp.mcp.settings.port, 9100)
        self.assertEqual(sem_mcp.mcp.settings.streamable_http_path, "/x")

    def test_main_warns_on_non_loopback_http_bind(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(sem_mcp.mcp, "run"), mock.patch("sys.stderr", stderr):
            sem_mcp.main(["--transport", "streamable-http", "--host", "0.0.0.0"])
        self.assertIn("WARNING", stderr.getvalue())

    def test_main_does_not_warn_on_loopback_http_bind(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(sem_mcp.mcp, "run"), mock.patch("sys.stderr", stderr):
            sem_mcp.main(["--transport", "streamable-http", "--host", "127.0.0.1"])
        self.assertEqual(stderr.getvalue(), "")


class TestDistributionManifests(unittest.TestCase):
    """Committed manifests must not drift from version.json."""

    def test_committed_manifest_versions_match_version_json(self) -> None:
        root = Path(__file__).resolve().parents[2]
        version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]

        mcpb = json.loads((root / "packaging/mcpb/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(mcpb["version"], version)

        server = json.loads((root / "packaging/registry/server.json").read_text(encoding="utf-8"))
        self.assertEqual(server["version"], version)
        self.assertEqual(server["packages"][0]["version"], version)

        scoop = json.loads(
            (root / "packaging/scoop/semanticscript.json").read_text(encoding="utf-8")
        )
        self.assertEqual(scoop["version"], version)

        winget_dir = root / "packaging/winget"
        for name in (
            "monstercameron.SemanticScript.yaml",
            "monstercameron.SemanticScript.installer.yaml",
            "monstercameron.SemanticScript.locale.en-US.yaml",
        ):
            text = (winget_dir / name).read_text(encoding="utf-8")
            self.assertIn(f"PackageVersion: {version}", text, name)

    def test_pyinstaller_version_info_embeds_mcp_bootstrap_metadata(self) -> None:
        root = Path(__file__).resolve().parents[2]
        version = json.loads((root / "version.json").read_text(encoding="utf-8"))["version"]
        helper_path = root / "packaging" / "pyinstaller" / "sem_version_info.py"
        spec = importlib.util.spec_from_file_location("sem_version_info_test", helper_path)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        rendered = module.render_version_info(version)

        self.assertIn(f"StringStruct('FileVersion', '{version}')", rendered)
        self.assertIn("StringStruct('Comments', 'MCP stdio server: run sem.exe mcp.", rendered)
        self.assertIn("Load project docs: agent_docs path dot", rendered)
        self.assertIn("Then load versioned skills: skills_get names sem-start sem sem-agent sem-syntax", rendered)
        self.assertIn("StringStruct('McpServerCommand', 'sem.exe mcp')", rendered)
        self.assertIn("StringStruct('McpServerTransport', 'stdio')", rendered)
        self.assertIn(
            'StringStruct(\'McpClientConfig\', \'{"command":"sem.exe","args":["mcp"],'
            '"cwd":"<project-root>"}\')',
            rendered,
        )

    def test_release_workflows_include_mcp_bootstrap_notes(self) -> None:
        root = Path(__file__).resolve().parents[2]
        required_fragments = (
            "MCP bootstrap:",
            "Copy this block into an MCP-aware agent",
            "Start command: sem.exe mcp",
            '"args": ["mcp"]',
            '"cwd": "<project-root>"',
            'agent_docs with path "."',
            'skills_get with names ["sem-start", "sem", "sem-agent", "sem-syntax"]',
            "$noteParts += $mcpBootstrapLines",
        )

        for workflow in (
            root / ".github" / "workflows" / "release.yml",
            root / ".github" / "workflows" / "compiler-exe.yml",
        ):
            text = workflow.read_text(encoding="utf-8")
            for fragment in required_fragments:
                self.assertIn(fragment, text, workflow)
            self.assertNotIn("$mcpBootstrapLines,", text, workflow)


if __name__ == "__main__":
    unittest.main()
