#!/usr/bin/env python3
"""Stamp release-specific values into the distribution manifests.

The committed manifests (scoop, winget, registry server.json) carry placeholder
versions and zeroed SHA-256 hashes. At release time this script fills in the
real version, download URLs, and hashes computed from the built artifacts, then
writes release-ready copies into an output directory for publishing.

Usage:
    python packaging/release_manifests.py \
        --exe dist/sem.exe \
        --mcpb dist/semanticscript.mcpb \
        --tag v0.0.1 \
        --outdir dist/manifests
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = "monstercameron/SemanticScript"
PKG_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PKG_ROOT.parent
VERSION_PATH = REPO_ROOT / "version.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_version() -> str:
    return json.loads(VERSION_PATH.read_text(encoding="utf-8"))["version"]


def _download_base(tag: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{tag}"


def render_scoop(version: str, base: str, exe_sha: str) -> str:
    manifest = json.loads((PKG_ROOT / "scoop" / "semanticscript.json").read_text(encoding="utf-8"))
    manifest["version"] = version
    manifest["architecture"]["64bit"]["url"] = f"{base}/sem.exe"
    manifest["architecture"]["64bit"]["hash"] = exe_sha
    return json.dumps(manifest, indent=2) + "\n"


def render_server_json(version: str, mcpb_url: str, mcpb_sha: str) -> str:
    doc = json.loads((PKG_ROOT / "registry" / "server.json").read_text(encoding="utf-8"))
    doc["version"] = version
    package = doc["packages"][0]
    package["version"] = version
    package["identifier"] = mcpb_url
    package["fileSha256"] = mcpb_sha
    return json.dumps(doc, indent=2) + "\n"


def render_winget(name: str, version: str, base: str, exe_sha: str) -> tuple[str, set[str]]:
    lines = (PKG_ROOT / "winget" / name).read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    replaced: set[str] = set()
    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("PackageVersion:"):
            out.append(f"{indent}PackageVersion: {version}")
            replaced.add("PackageVersion")
        elif stripped.startswith("InstallerUrl:"):
            out.append(f"{indent}InstallerUrl: {base}/sem.exe")
            replaced.add("InstallerUrl")
        elif stripped.startswith("InstallerSha256:"):
            out.append(f"{indent}InstallerSha256: {exe_sha.upper()}")
            replaced.add("InstallerSha256")
        else:
            out.append(line)
    return "\n".join(out) + "\n", replaced


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", required=True, type=Path, help="path to the built sem.exe")
    parser.add_argument("--mcpb", required=True, type=Path, help="path to the built .mcpb bundle")
    parser.add_argument("--version", help="release version (default: version.json)")
    parser.add_argument("--tag", help="git release tag (default: v<version>)")
    parser.add_argument("--mcpb-url", help="canonical .mcpb download URL (default: tagged release URL)")
    parser.add_argument("--outdir", required=True, type=Path, help="output directory")
    args = parser.parse_args(argv)

    version = args.version or _repo_version()
    tag = args.tag or f"v{version}"
    base = _download_base(tag)
    exe_sha = _sha256(args.exe)
    mcpb_sha = _sha256(args.mcpb)
    mcpb_url = args.mcpb_url or f"{base}/semanticscript.mcpb"

    outdir = args.outdir
    (outdir / "scoop").mkdir(parents=True, exist_ok=True)
    (outdir / "winget").mkdir(parents=True, exist_ok=True)
    (outdir / "registry").mkdir(parents=True, exist_ok=True)

    (outdir / "scoop" / "semanticscript.json").write_text(
        render_scoop(version, base, exe_sha), encoding="utf-8"
    )
    (outdir / "registry" / "server.json").write_text(
        render_server_json(version, mcpb_url, mcpb_sha), encoding="utf-8"
    )
    installer_name = "monstercameron.SemanticScript.installer.yaml"
    for name in (
        "monstercameron.SemanticScript.yaml",
        installer_name,
        "monstercameron.SemanticScript.locale.en-US.yaml",
    ):
        text, replaced = render_winget(name, version, base, exe_sha)
        if "PackageVersion" not in replaced:
            raise SystemExit(f"{name}: PackageVersion was not stamped")
        if name == installer_name and not {"InstallerUrl", "InstallerSha256"} <= replaced:
            raise SystemExit(f"{name}: InstallerUrl/InstallerSha256 were not stamped")
        (outdir / "winget" / name).write_text(text, encoding="utf-8")

    # Guard against shipping an unreplaced SHA-256 placeholder.
    for generated in outdir.rglob("*"):
        if generated.is_file() and "0" * 64 in generated.read_text(encoding="utf-8"):
            raise SystemExit(f"{generated}: zeroed SHA-256 placeholder was not replaced")

    print(f"stamped manifests v{version} (tag {tag}) into {outdir}")
    print(f"  sem.exe sha256:  {exe_sha}")
    print(f"  .mcpb sha256:    {mcpb_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
