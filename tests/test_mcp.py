#!/usr/bin/env python3
"""MCP server smoke test (TOOL-0).

Drives the `semanticscript mcp` stdio JSON-RPC server through a full handshake —
`initialize` -> `tools/list` -> `tools/call` for every advertised tool, plus the
unknown-tool error path — and asserts each tool actually runs (no argparse error,
no traceback) and returns its `sem.<tool>.v1`-style surface. Exit 0 iff the MCP
is in working order.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")
FIXTURE = "examples/hello_world.sem"  # ROOT-relative; a real, parseable project


def _drive(frames):
    """Feed JSON-RPC frames to the server and return {id: response}."""
    stdin = "\n".join(json.dumps(f) for f in frames) + "\n"
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "mcp"],
                          input=stdin, capture_output=True, text=True,
                          cwd=ROOT, timeout=180)
    out = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            return None, "non-JSON line on stdout: %r" % line[:80]
        out[r.get("id")] = r
    return out, proc.stderr


def main():
    # Discover the advertised tool set from tools/list first.
    init = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "smoke", "version": "0"}}}
    listing = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    responses, stderr = _drive([init, listing])
    if responses is None:
        print("MCP FAIL:", stderr)
        return 1

    if responses.get(0, {}).get("result", {}).get("serverInfo", {}).get("name") != "semanticscript":
        print("MCP FAIL: initialize did not return serverInfo.name=semanticscript")
        return 1
    tools = responses.get(1, {}).get("result", {}).get("tools", [])
    if not tools:
        print("MCP FAIL: tools/list returned no tools")
        return 1

    # Build a tools/call per tool, supplying a value for every required input the
    # advertised schema declares (path + any positional like query/code/dimension,
    # plus the persistent-docs-index `db` that docs_index/docs_search_index need).
    # docs_index is advertised before docs_search_index, so the index is created
    # before it is searched (same db path).
    db_path = os.path.join(tempfile.mkdtemp(prefix="mcp-smoke-"), "docs.sqlite")
    ARG_FIXTURES = {
        "path": FIXTURE,
        "query": "cleanup a database handle",  # search
        "code": "SS1502",                       # explain
        "dimension": "effects",                 # query
        "db": db_path,                          # docs_index / docs_search_index
        "edit": {"op": "addLet", "operation": "main",
                 "name": "mcpSmokeTemp", "type": "Int64", "value": "1"},
    }
    frames = [init]
    idmap = {}
    rid = 100
    for tool in tools:
        name = tool["name"]
        required = tool.get("inputSchema", {}).get("required", [])
        args = {k: ARG_FIXTURES[k] for k in required if k in ARG_FIXTURES}
        missing = [k for k in required if k not in ARG_FIXTURES]
        if missing:
            print("MCP FAIL: tool %r needs un-fixtured required args %s" % (name, missing))
            return 1
        frames.append({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                       "params": {"name": name, "arguments": args}})
        idmap[rid] = name
        rid += 1
    # An unknown tool must be a JSON-RPC error, not a masked success.
    frames.append({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                   "params": {"name": "definitely-not-a-tool", "arguments": {}}})
    unknown_id = rid

    responses, stderr = _drive(frames)
    if responses is None:
        print("MCP FAIL:", stderr)
        return 1

    failures = []
    for cid, name in idmap.items():
        r = responses.get(cid)
        if r is None or "result" not in r:
            failures.append((name, "no result: %s" % (r and r.get("error"))))
            continue
        content = r["result"].get("content", [{}])
        text = content[0].get("text", "") if content else ""
        if not text.strip() or "Traceback" in text or "error:" in text.splitlines()[0:1]:
            failures.append((name, text[:70].replace("\n", " ")))

    unk = responses.get(unknown_id, {})
    if "error" not in unk:
        failures.append(("<unknown-tool>", "expected JSON-RPC error, got %r" % unk.get("result")))

    print("MCP tools: %d advertised, %d/%d callable OK"
          % (len(tools), len(idmap) - len(failures), len(idmap)))
    for name, detail in failures:
        print("  FAIL %-14s %s" % (name, detail))
    if failures:
        return 1
    print("MCP: handshake + all tools + error path OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
