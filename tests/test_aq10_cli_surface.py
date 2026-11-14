#!/usr/bin/env python3
"""AQ-10 / TRUE-1: CLI surface consistency — advertised == real.

Aspirational help defeats tool-only discovery: every advertised command/tool must
be a real, invokable command, and the agent-facing tool surface (EAV_MCP_TOOLS)
must not name anything the CLI doesn't implement. This guards both directions:
  * every registered subcommand answers `--help` (it is a real argparse command);
  * every advertised MCP tool maps to a registered command (no phantom tools).
"""
import importlib
import os
import re
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")


def _registered_commands():
    out = subprocess.run([sys.executable, SC, "--help"],
                         capture_output=True, text=True, encoding="utf-8").stdout
    m = re.search(r"\{([a-z][a-z,_\-]+)\}", out)
    assert m, "could not find the subcommand choices in --help"
    return set(m.group(1).split(","))


COMMANDS = _registered_commands()


def test_aq10_corpus_has_a_real_command_surface():
    assert len(COMMANDS) >= 20, f"suspiciously few commands: {COMMANDS}"
    for core in ("check", "run", "build", "test", "docs", "fmt"):
        assert core in COMMANDS, f"core command {core!r} not registered"


@pytest.mark.parametrize("cmd", sorted(_registered_commands()))
def test_aq10_every_registered_command_is_invokable(cmd):
    # `--help` exits 0 only for a real, registered argparse subcommand — an
    # advertised-but-unimplemented command could not answer it.
    r = subprocess.run([sys.executable, SC, cmd, "--help"],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, f"`{cmd} --help` exited {r.returncode}\n{r.stderr[-200:]}"


def test_aq10_advertised_mcp_tools_map_to_registered_commands():
    mcp = getattr(semanticscript, "EAV_MCP_TOOLS", {})
    tools = mcp.keys() if isinstance(mcp, dict) else mcp
    phantom = []
    for tool in tools:
        # MCP names use underscores; CLI uses hyphens. A tool maps if its
        # hyphenated form is a command, or its first segment is (sub-arg tools like
        # docs_index -> `docs index`).
        hy = tool.replace("_", "-")
        head = tool.split("_", 1)[0]
        if hy not in COMMANDS and head not in COMMANDS:
            phantom.append(tool)
    assert not phantom, f"advertised MCP tools with no registered command: {phantom}"
