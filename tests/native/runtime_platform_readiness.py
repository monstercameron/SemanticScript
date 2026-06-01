#!/usr/bin/env python3
"""R-035 native-runtime platform readiness report and workflow guard."""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SEMANTICSCRIPT = ROOT / "semanticscript" / "compiler" / "semanticscript.py"
MANIFEST = ROOT / "semanticscript" / "runtime" / "manifest.json"
REQUIRED_PLATFORMS = ("windows", "linux", "macos")
REQUIRED_RUNNERS = ("windows-latest", "ubuntu-latest", "macos-latest")
SCRIPT_REL = "tests/native/runtime_platform_readiness.py"

_VALID_MANIFEST_PLATFORMS = {"windows", "linux", "macos", "wasi"}
_VALID_COMPILERS = {"gnu", "clang", "msvc", "zig"}
_WINDOWS_ONLY_LIBS = {
    "advapi32",
    "comctl32",
    "dbghelp",
    "gdi32",
    "iphlpapi",
    "ole32",
    "psapi",
    "shell32",
    "user32",
    "userenv",
    "ws2_32",
}


def _json_line(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text.strip())
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _run_semanticscript(args: list[str]) -> dict[str, Any]:
    command = [sys.executable, str(SEMANTICSCRIPT)] + args
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "command": command,
            "ok": False,
            "status": "tool-error",
            "exitCode": None,
            "error": str(exc),
        }
    payload = _json_line(proc.stdout)
    ok = proc.returncode == 0 and (payload is None or payload.get("ok", True) is True)
    report: dict[str, Any] = {
        "command": command,
        "ok": ok,
        "exitCode": proc.returncode,
        "surface": payload.get("surface") if payload else None,
        "payload": payload,
    }
    if proc.stdout and payload is None:
        report["stdout"] = proc.stdout[-4000:]
    if proc.stderr:
        report["stderr"] = proc.stderr[-4000:]
    return report


def _merge_list(layers: list[dict[str, Any]], field: str) -> list[str]:
    values: list[str] = []
    for layer in layers:
        for value in layer.get(field, []) or []:
            if value not in values:
                values.append(value)
    return values


def _load_manifest() -> tuple[dict[str, Any] | None, list[str]]:
    try:
        with MANIFEST.open(encoding="utf-8") as handle:
            manifest = json.load(handle)
    except Exception as exc:
        return None, [f"cannot read runtime manifest: {exc}"]
    errors: list[str] = []
    if manifest.get("schema") != 2:
        errors.append(f"manifest schema is {manifest.get('schema')!r}, expected 2")
    if not isinstance(manifest.get("libraries"), list) or not manifest["libraries"]:
        errors.append("manifest has no runtime libraries")
    return manifest, errors


def _manifest_dry_run_for_platform(manifest: dict[str, Any], target: str) -> dict[str, Any]:
    runtime_dir = MANIFEST.parent
    libraries = manifest.get("libraries") or []
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    resolved_libs: set[str] = set()

    for library in libraries:
        name = library.get("name") or "<unnamed>"
        platforms = library.get("platforms") or {}
        compilers = library.get("compiler") or {}
        unknown_platforms = sorted(set(platforms) - _VALID_MANIFEST_PLATFORMS)
        unknown_compilers = sorted(set(compilers) - _VALID_COMPILERS)
        for key in unknown_platforms:
            errors.append(f"{name}: unknown platform overlay {key!r}")
        for key in unknown_compilers:
            errors.append(f"{name}: unknown compiler overlay {key!r}")

        layers = [library, platforms.get(target, {})]
        sources = _merge_list(layers, "sources")
        includes = _merge_list(layers, "include")
        defines = _merge_list(layers, "defines")
        libs = _merge_list(layers, "libs")
        resolved_libs.update(libs)

        missing_sources = [
            source for source in sources
            if not (runtime_dir / source).resolve().exists()
        ]
        missing_includes = [
            include for include in includes
            if not (runtime_dir / include).resolve().exists()
        ]
        if missing_sources:
            errors.append(f"{name}: missing source(s) for {target}: {missing_sources}")
        if missing_includes:
            errors.append(f"{name}: missing include dir(s) for {target}: {missing_includes}")

        entries.append({
            "name": name,
            "provides": list(library.get("provides", []) or []),
            "sourceCount": len(sources),
            "includeCount": len(includes),
            "defineCount": len(defines),
            "libs": libs,
            "status": "fail" if missing_sources or missing_includes else "pass",
        })

    windows_lib_leaks = sorted(resolved_libs & _WINDOWS_ONLY_LIBS) if target != "windows" else []
    if windows_lib_leaks:
        errors.append(f"{target}: Windows-only libraries leaked into manifest plan: {windows_lib_leaks}")

    return {
        "target": target,
        "status": "pass" if not errors else "fail",
        "libraryCount": len(libraries),
        "resolvedLibs": sorted(resolved_libs),
        "windowsOnlyLibLeak": windows_lib_leaks,
        "libraries": entries,
        "errors": errors,
    }


def build_report() -> dict[str, Any]:
    manifest, manifest_errors = _load_manifest()
    manifest_runs: dict[str, Any] = {}
    if manifest is not None:
        for target in REQUIRED_PLATFORMS:
            manifest_runs[target] = _manifest_dry_run_for_platform(manifest, target)

    native_readiness = _run_semanticscript(["readiness", "--json"])
    native_status = _run_semanticscript(["status", "--json"])
    manifest_ok = not manifest_errors and all(
        run.get("status") == "pass" for run in manifest_runs.values()
    )
    ok = manifest_ok and native_readiness.get("ok") and native_status.get("ok")
    return {
        "surface": "sem.runtimePlatformReadiness.v1",
        "ok": bool(ok),
        "status": "ok" if ok else "degraded",
        "host": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "ciMatrixRequired": list(REQUIRED_RUNNERS),
        "nativeReadiness": native_readiness,
        "nativeStatus": native_status,
        "manifest": {
            "path": str(MANIFEST.relative_to(ROOT)),
            "status": "pass" if manifest_ok else "fail",
            "errors": manifest_errors,
            "dryRuns": manifest_runs,
        },
        "skipped": [
            {
                "target": "wasi",
                "status": "skipped",
                "reason": "R-035 lane records native host readiness; wasm/wasi is excluded from this native-runtime matrix.",
            }
        ],
    }


def verify_workflow(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return {
            "surface": "sem.runtimePlatformWorkflowCheck.v1",
            "ok": False,
            "status": "missing-workflow",
            "workflow": str(path),
            "checks": [{"name": "read", "ok": False, "detail": str(exc)}],
        }

    checks = [
        {
            "name": "job",
            "ok": "runtime-platform:" in text,
            "detail": "workflow declares a runtime-platform job",
        },
        {
            "name": "readiness-script",
            "ok": SCRIPT_REL in text,
            "detail": f"workflow invokes {SCRIPT_REL}",
        },
        {
            "name": "artifact",
            "ok": "runtime-platform-readiness.json" in text and "upload-artifact" in text,
            "detail": "workflow uploads the JSON readiness report",
        },
    ]
    for runner in REQUIRED_RUNNERS:
        checks.append({
            "name": f"runner:{runner}",
            "ok": runner in text,
            "detail": f"matrix includes {runner}",
        })
    ok = all(check["ok"] for check in checks)
    return {
        "surface": "sem.runtimePlatformWorkflowCheck.v1",
        "ok": ok,
        "status": "ok" if ok else "failed",
        "workflow": str(path),
        "checks": checks,
    }


def _emit(payload: dict[str, Any], want_json: bool) -> None:
    if want_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    if payload.get("surface") == "sem.runtimePlatformWorkflowCheck.v1":
        print(f"runtime-platform workflow: {payload['status']}")
        for check in payload.get("checks", []):
            mark = "PASS" if check.get("ok") else "FAIL"
            print(f"{mark}: {check['name']} - {check['detail']}")
        return
    print(f"runtime-platform readiness: {payload['status']}")
    print(f"host: {payload['host']['system']} {payload['host']['machine']}")
    print(f"native readiness: {payload['nativeReadiness'].get('surface')} exit={payload['nativeReadiness'].get('exitCode')}")
    print(f"native status: {payload['nativeStatus'].get('surface')} exit={payload['nativeStatus'].get('exitCode')}")
    for target, run in payload["manifest"]["dryRuns"].items():
        print(f"manifest {target}: {run['status']} ({run['libraryCount']} libraries)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument("--output", help="also write the JSON report to this path")
    parser.add_argument("--verify-workflow", metavar="PATH",
                        help="verify the runtime-platform workflow matrix/guard")
    args = parser.parse_args(argv)

    if args.verify_workflow:
        payload = verify_workflow((ROOT / args.verify_workflow).resolve())
    else:
        payload = build_report()
    if args.output:
        Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                     encoding="utf-8")
    _emit(payload, args.json)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
