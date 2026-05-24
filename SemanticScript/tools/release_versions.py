#!/usr/bin/env python3
"""Print release-relevant SemanticScript component versions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEMANTICSCRIPT_ROOT = ROOT / "SemanticScript"
if str(SEMANTICSCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SEMANTICSCRIPT_ROOT))

from shared.repo_version import read_repo_version  # noqa: E402


def _package_metadata(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path}: package metadata must be a JSON object")
    return payload


def collect_versions() -> dict:
    repo_version = read_repo_version()
    components = [
        {
            "name": "semsc",
            "kind": "command",
            "path": "SemanticScript/compiler/semsc.py",
            "version": repo_version,
            "versionSource": "version.json",
        },
        {
            "name": "semlint",
            "kind": "command",
            "path": "SemanticScript/linter/semlint.py",
            "version": repo_version,
            "versionSource": "version.json",
        },
        {
            "name": "semfmt",
            "kind": "command",
            "path": "SemanticScript/formatter/semfmt.py",
            "version": repo_version,
            "versionSource": "version.json",
        },
        {
            "name": "sem",
            "kind": "command",
            "path": "SemanticScript/tools/sem.py",
            "version": repo_version,
            "versionSource": "version.json",
        },
    ]

    package_path = ROOT / "vscode-semanticscript" / "package.json"
    package = _package_metadata(package_path)
    package_version = package.get("version", "")
    if package_version != repo_version:
        raise RuntimeError(
            f"{package_path}: package.json version {package_version!r} must match version.json {repo_version!r}"
        )
    components.append({
        "name": package.get("name", "semanticscript-vscode"),
        "kind": "vscode-extension",
        "path": "vscode-semanticscript/package.json",
        "version": repo_version,
        "versionSource": "version.json -> package.json.version",
        "publisher": package.get("publisher", ""),
        "license": package.get("license", ""),
    })

    return {
        "schemaVersion": "sem.releaseVersions.v1",
        "repoVersion": repo_version,
        "versionPolicy": "repository-wide semantic version; command tools and the VS Code package must stay synchronized to version.json",
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
