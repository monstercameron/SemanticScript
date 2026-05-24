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

    def test_explain_tool_returns_explain_schema(self) -> None:
        result = asyncio.run(sem_mcp.mcp.call_tool("explain", {"code": "SS3104"}))
        payload = _structured(result)
        self.assertEqual(payload["schemaVersion"], "sem.explain.v1")


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

        args = argparse.Namespace(transport="stdio", host=None, port=None, path=None)
        with mock.patch("tools.sem_mcp.main") as fake_main:
            exit_code = sem.command_mcp(args)

        fake_main.assert_called_once_with(["--transport", "stdio"])
        self.assertEqual(exit_code, 0)

    @unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
    def test_command_mcp_forwards_http_transport_options(self) -> None:
        import tools.sem_mcp  # noqa: F401

        args = argparse.Namespace(
            transport="streamable-http", host="0.0.0.0", port=9000, path="/mcp"
        )
        with mock.patch("tools.sem_mcp.main") as fake_main:
            sem.command_mcp(args)

        fake_main.assert_called_once_with(
            ["--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000", "--path", "/mcp"]
        )


@unittest.skipUnless(MCP_AVAILABLE, "mcp SDK not installed")
class TestSemMcpTransport(unittest.TestCase):
    def test_main_defaults_to_stdio(self) -> None:
        with mock.patch.object(sem_mcp.mcp, "run") as run:
            sem_mcp.main([])
        run.assert_called_once_with(transport="stdio")

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


if __name__ == "__main__":
    unittest.main()
