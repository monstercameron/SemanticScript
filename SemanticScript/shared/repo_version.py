"""Shared repository version helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSION_FILE = ROOT / "version.json"
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(text: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(text)
    if not match:
        raise ValueError(f"invalid semantic version: {text!r}")
    return tuple(int(part) for part in match.groups())


def format_semver(major: int, minor: int, patch: int) -> str:
    if min(major, minor, patch) < 0:
        raise ValueError("semantic version parts must be non-negative")
    return f"{major}.{minor}.{patch}"


def read_version_payload(path: Path = VERSION_FILE) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path}: version payload must be a JSON object")
    version = payload.get("version", "")
    if not isinstance(version, str):
        raise RuntimeError(f"{path}: version must be a string")
    try:
        parse_semver(version)
    except ValueError as exc:
        raise RuntimeError(f"{path}: {exc}") from exc
    schema = payload.get("schemaVersion", "")
    if schema and schema != "sem.repoVersion.v1":
        raise RuntimeError(f"{path}: unsupported schemaVersion {schema!r}")
    payload.setdefault("schemaVersion", "sem.repoVersion.v1")
    return payload


def read_repo_version(path: Path = VERSION_FILE) -> str:
    return read_version_payload(path)["version"]


def write_repo_version(version: str, path: Path = VERSION_FILE) -> None:
    parse_semver(version)
    payload = {"schemaVersion": "sem.repoVersion.v1", "version": version}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def bump_patch(version: str) -> str:
    major, minor, patch = parse_semver(version)
    return format_semver(major, minor, patch + 1)
