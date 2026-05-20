#!/usr/bin/env python3
"""Print release-relevant SemanticScript component versions."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _python_assignment(path: Path, name: str) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    match = re.search(rf"^{re.escape(name)}\s*=\s*['\"]([^'\"]+)['\"]", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{path}: missing {name} assignment")
    return match.group(1)


def collect_versions() -> dict:
    components = [
        {
            "name": "semsc",
            "kind": "command",
            "path": "SemanticScript/compiler/semsc.py",
            "version": _python_assignment(ROOT / "SemanticScript" / "compiler" / "semsc.py", "__version__"),
            "versionSource": "__version__",
        },
        {
            "name": "semlint",
            "kind": "command",
            "path": "SemanticScript/linter/semlint.py",
            "version": _python_assignment(ROOT / "SemanticScript" / "linter" / "semlint.py", "__version__"),
            "versionSource": "__version__",
        },
        {
            "name": "semfmt",
            "kind": "command",
            "path": "SemanticScript/formatter/semfmt.py",
            "version": _python_assignment(ROOT / "SemanticScript" / "formatter" / "semfmt.py", "__version__"),
            "versionSource": "__version__",
        },
        {
            "name": "sem",
            "kind": "command",
            "path": "SemanticScript/tools/sem.py",
            "version": _python_assignment(ROOT / "SemanticScript" / "tools" / "sem.py", "VERSION"),
            "versionSource": "VERSION",
        },
    ]

    package_path = ROOT / "vscode-semanticscript" / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{package_path}: {exc}") from exc
    components.append({
        "name": package.get("name", "semanticscript-vscode"),
        "kind": "vscode-extension",
        "path": "vscode-semanticscript/package.json",
        "version": package.get("version", ""),
        "versionSource": "package.json.version",
        "publisher": package.get("publisher", ""),
        "license": package.get("license", ""),
    })

    return {
        "schemaVersion": "sem.releaseVersions.v0",
        "versionPolicy": "component-local versions are allowed when recorded in the release matrix",
        "components": components,
    }


def print_table(payload: dict) -> None:
    rows = payload["components"]
    widths = {
        "name": max(len("component"), *(len(row["name"]) for row in rows)),
        "version": max(len("version"), *(len(row["version"]) for row in rows)),
        "kind": max(len("kind"), *(len(row["kind"]) for row in rows)),
    }
    print(payload["versionPolicy"])
    print()
    print(f"{'component':<{widths['name']}}  {'version':<{widths['version']}}  {'kind':<{widths['kind']}}  path")
    print(f"{'-' * widths['name']}  {'-' * widths['version']}  {'-' * widths['kind']}  ----")
    for row in rows:
        print(
            f"{row['name']:<{widths['name']}}  "
            f"{row['version']:<{widths['version']}}  "
            f"{row['kind']:<{widths['kind']}}  "
            f"{row['path']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print release-relevant SemanticScript component versions.",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable version data")
    args = parser.parse_args(argv)
    try:
        payload = collect_versions()
    except RuntimeError as exc:
        print(f"release_versions: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_table(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
