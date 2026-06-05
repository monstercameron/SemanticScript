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
    bump_semver,
    parse_semver,
    read_repo_version,
    write_repo_version,
)


PACKAGE_JSON = ROOT / "vscode-semanticscript" / "package.json"
PACKAGE_LOCK_JSON = ROOT / "vscode-semanticscript" / "package-lock.json"


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


def read_package_lock_version(path: Path | None = None) -> str:
    path = path or PACKAGE_LOCK_JSON
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path}: package lock metadata must be a JSON object")
    version = payload.get("version", "")
    if not isinstance(version, str):
        raise RuntimeError(f"{path}: version must be a string")
    try:
        parse_semver(version)
    except ValueError as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    packages = payload.get("packages")
    if not isinstance(packages, dict):
        raise RuntimeError(f"{path}: packages must be a JSON object")
    root_package = packages.get("")
    if not isinstance(root_package, dict):
        raise RuntimeError(f"{path}: packages[''] must be a JSON object")
    root_version = root_package.get("version", "")
    if not isinstance(root_version, str):
        raise RuntimeError(f"{path}: packages[''].version must be a string")
    try:
        parse_semver(root_version)
    except ValueError as exc:
        raise RuntimeError(f"{path}: packages[''].{exc}") from exc
    if root_version != version:
        raise RuntimeError(f"{path}: top-level version {version!r} does not match packages[''].version {root_version!r}")
    return version


def write_package_lock_version(version: str, path: Path | None = None) -> None:
    path = path or PACKAGE_LOCK_JSON
    parse_semver(version)
    if not path.exists():
        raise RuntimeError(f"{path}: package-lock.json is required")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path}: package lock metadata must be a JSON object")
    payload["version"] = version
    packages = payload.get("packages")
    if not isinstance(packages, dict):
        raise RuntimeError(f"{path}: packages must be a JSON object")
    root_package = packages.get("")
    if not isinstance(root_package, dict):
        raise RuntimeError(f"{path}: packages[''] must be a JSON object")
    root_package["version"] = version
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def apply_version(
    version: str,
    *,
    version_path: Path | None = None,
    package_path: Path | None = None,
    package_lock_path: Path | None = None,
) -> dict:
    version_path = version_path or VERSION_FILE
    package_path = package_path or PACKAGE_JSON
    package_lock_path = package_lock_path or PACKAGE_LOCK_JSON
    parse_semver(version)
    previous = read_repo_version(version_path)
    write_repo_version(version, version_path)
    write_package_version(version, package_path)
    write_package_lock_version(version, package_lock_path)
    files_updated = [str(version_path), str(package_path), str(package_lock_path)]
    return {
        "ok": True,
        "previousVersion": previous,
        "version": version,
        "filesUpdated": files_updated,
    }


def check_sync(
    *,
    version_path: Path | None = None,
    package_path: Path | None = None,
    package_lock_path: Path | None = None,
) -> dict:
    version_path = version_path or VERSION_FILE
    package_path = package_path or PACKAGE_JSON
    package_lock_path = package_lock_path or PACKAGE_LOCK_JSON
    repo_version = read_repo_version(version_path)
    package_version = read_package_version(package_path)
    package_lock_version = read_package_lock_version(package_lock_path)
    ok = repo_version == package_version and repo_version == package_lock_version
    payload = {
        "ok": ok,
        "version": repo_version,
        "packageVersion": package_version,
        "versionPath": str(version_path),
        "packagePath": str(package_path),
    }
    payload["packageLockVersion"] = package_lock_version
    payload["packageLockPath"] = str(package_lock_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bump and synchronize the repository semantic version.",
    )
    parser.add_argument("--bump", choices=("major", "minor", "patch"), help="increment the selected semantic version segment")
    parser.add_argument("--bump-patch", action="store_true", help="increment the patch segment")
    parser.add_argument("--set", metavar="VERSION", help="set the exact semantic version")
    parser.add_argument("--check", action="store_true", help="verify version.json, package.json, and package-lock.json stay synchronized")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    actions = int(bool(args.bump)) + int(args.bump_patch) + int(bool(args.set)) + int(args.check)
    if actions != 1:
        parser.error("choose exactly one of --bump, --bump-patch, --set, or --check")

    try:
        if args.check:
            payload = check_sync(version_path=VERSION_FILE, package_path=PACKAGE_JSON, package_lock_path=PACKAGE_LOCK_JSON)
            rc = 0 if payload["ok"] else 1
        else:
            if args.set:
                target = args.set
            elif args.bump:
                target = bump_semver(read_repo_version(VERSION_FILE), args.bump)
            else:
                target = bump_patch(read_repo_version(VERSION_FILE))
            payload = apply_version(target, version_path=VERSION_FILE, package_path=PACKAGE_JSON, package_lock_path=PACKAGE_LOCK_JSON)
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
