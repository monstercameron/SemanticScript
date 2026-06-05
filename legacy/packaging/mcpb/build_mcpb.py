#!/usr/bin/env python3
"""Pack the SemanticScript MCP server into an .mcpb Desktop Extension bundle.

An .mcpb file is a zip archive with manifest.json at the root plus the server
payload. This bundles the single-file `sem` executable so users can one-click
install the MCP server into MCP desktop clients (e.g. Claude Desktop).

Usage:
    python packaging/mcpb/build_mcpb.py --sem-exe dist/sem.exe --output dist/semanticscript.mcpb

The bundle version is taken from version.json (kept in sync with the toolchain),
and the live tool list is injected when the mcp SDK is importable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).resolve().parent / "manifest.json"
VERSION_PATH = REPO_ROOT / "version.json"


def _repo_version() -> str:
    return json.loads(VERSION_PATH.read_text(encoding="utf-8"))["version"]


def _live_tools() -> list[dict[str, str]] | None:
    """Enumerate the server's tools, or None if the SDK is unavailable."""
    import asyncio

    server_root = str(REPO_ROOT / "SemanticScript")
    sys.path.insert(0, server_root)
    try:
        from tools import sem_mcp
    except ModuleNotFoundError:
        return None
    finally:
        if sys.path and sys.path[0] == server_root:
            sys.path.pop(0)
    tools = asyncio.run(sem_mcp.mcp.list_tools())
    return [{"name": tool.name, "description": tool.description or ""} for tool in tools]


def build_manifest() -> dict:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["version"] = _repo_version()
    tools = _live_tools()
    if tools is not None:
        manifest["tools"] = tools
    return manifest


def pack(sem_exe: Path, output: Path) -> None:
    if not sem_exe.is_file():
        raise SystemExit(f"sem executable not found: {sem_exe}")
    manifest = build_manifest()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        (stage / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        server_dir = stage / "server"
        server_dir.mkdir()
        shutil.copy2(sem_exe, server_dir / "sem.exe")

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
            for item in sorted(stage.rglob("*")):
                if item.is_file():
                    bundle.write(item, item.relative_to(stage).as_posix())

    print(f"wrote {output} ({output.stat().st_size} bytes), manifest version {manifest['version']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sem-exe", required=True, type=Path, help="path to the built sem executable")
    parser.add_argument("--output", required=True, type=Path, help="output .mcpb path")
    args = parser.parse_args(argv)
    pack(args.sem_exe, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
