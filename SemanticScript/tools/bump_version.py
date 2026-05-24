#!/usr/bin/env python3
"""Bump and synchronize the repository semantic version."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEMANTICSCRIPT_ROOT = ROOT / "SemanticScript"
if str(SEMANTICSCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SEMANTICSCRIPT_ROOT))

from shared.repo_version import (  # noqa: E402
    VERSION_FILE,
    bump_patch,
    parse_semver,
    read_repo_version,
    write_repo_version,
)


PACKAGE_JSON = ROOT / "vscode-semanticscript" / "package.json"


def read_package_version(path: Path | None = None) -> str:
    path = path or PACKAGE_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    version = payload.get("version", "")
    if not isinstance(version, str):
        raise RuntimeError(f"{path}: version must be a string")
    try:
        parse_semver(version)
    except ValueError as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    return version


def write_package_version(version: str, path: Path | None = None) -> None:
    path = path or PACKAGE_JSON
    parse_semver(version)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    payload["version"] = version
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_version(version: str, *, version_path: Path | None = None, package_path: Path | None = None) -> dict:
    version_path = version_path or VERSION_FILE
    package_path = package_path or PACKAGE_JSON
    parse_semver(version)
    previous = read_repo_version(version_path)
    write_repo_version(version, version_path)
    write_package_version(version, package_path)
    return {
        "ok": True,
        "previousVersion": previous,
        "version": version,
        "filesUpdated": [str(version_path), str(package_path)],
    }


def check_sync(*, version_path: Path | None = None, package_path: Path | None = None) -> dict:
    version_path = version_path or VERSION_FILE
    package_path = package_path or PACKAGE_JSON
    repo_version = read_repo_version(version_path)
    package_version = read_package_version(package_path)
    ok = repo_version == package_version
    return {
        "ok": ok,
        "version": repo_version,
        "packageVersion": package_version,
        "versionPath": str(version_path),
        "packagePath": str(package_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bump and synchronize the repository semantic version.",
    )
    parser.add_argument("--bump-patch", action="store_true", help="increment the patch segment")
    parser.add_argument("--set", metavar="VERSION", help="set the exact semantic version")
    parser.add_argument("--check", action="store_true", help="verify version.json and package.json stay synchronized")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    actions = int(args.bump_patch) + int(bool(args.set)) + int(args.check)
    if actions != 1:
        parser.error("choose exactly one of --bump-patch, --set, or --check")

    try:
        if args.check:
            payload = check_sync(version_path=VERSION_FILE, package_path=PACKAGE_JSON)
            rc = 0 if payload["ok"] else 1
        else:
            target = args.set if args.set else bump_patch(read_repo_version(VERSION_FILE))
            payload = apply_version(target, version_path=VERSION_FILE, package_path=PACKAGE_JSON)
            rc = 0
    except (RuntimeError, ValueError) as exc:
        print(f"bump_version: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["version"])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
