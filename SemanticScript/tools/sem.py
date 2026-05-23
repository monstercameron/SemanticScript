#!/usr/bin/env python3
"""SemanticScript tool driver.

This is intentionally thin for 1.0: it discovers a project build tape and
delegates to the reference tools without inventing a second build engine.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parents[1]
SYNTAX_PAYLOAD_VERSION = "sem.syntaxCutover.v1"
CALL_DISPOSITION_VARIANTS = ("value", "ok", "error", "void")
AUTHORITY_ACTIONS = frozenset({
    "allocate",
    "close",
    "execute",
    "open",
    "read",
    "send",
    "write",
})
CLEAN_DIRECTORY_NAMES = frozenset({"build", ".semcache", "__pycache__"})
CLEAN_FILE_SUFFIXES = frozenset({
    ".exe",
    ".ll",
    ".bc",
    ".obj",
    ".o",
    ".pdb",
    ".res",
    ".rc",
    ".vsix",
})
CLEAN_EXACT_RELATIVE_PATHS = frozenset({"apps/taskforge-tui/todos.json"})
SKILL_REGISTRY = (
    {
        "name": "language-core",
        "description": "Core SemanticScript language shape: modules, operations, rows, types, and dataflow.",
        "files": (
            "docs/language/README.md",
            "docs/language/program-structure.md",
            "docs/language/operations-dataflow.md",
            "docs/language/types-values.md",
        ),
    },
    {
        "name": "errors-effects-capabilities",
        "description": "Effect, failure, capability, and authority guidance for agent-safe SemanticScript edits.",
        "files": (
            "docs/language/errors-effects-capabilities.md",
            "docs/language/concurrency-time-cleanup.md",
        ),
    },
    {
        "name": "graph-and-slice",
        "description": "Agent workflows for context retrieval, graph inspection, and semantic slicing.",
        "files": (
            "docs/agents.md",
            "docs/toolchain/agent-workflows.md",
            "experiments/agent-first-tooling-research/README.md",
        ),
    },
    {
        "name": "taskforge-web-patterns",
        "description": "Concrete multi-user web application patterns from TaskForge Web.",
        "files": (
            "apps/taskforge-web/README.md",
            "apps/taskforge-web/main.sem",
        ),
    },
    {
        "name": "sqlite-patterns",
        "description": "SQLite usage, cleanup, and JSON CRUD patterns.",
        "files": (
            "docs/language/json-crud.md",
            "docs/reference/call-targets.md",
            "apps/taskforge-web/main.sem",
        ),
    },
    {
        "name": "http-html-patterns",
        "description": "Native HTTP, route, handler, and HTML boundary patterns.",
        "files": (
            "docs/language/native-http-api.md",
            "docs/language/records-codecs-boundaries.md",
            "apps/taskforge-web/README.md",
        ),
    },
    {
        "name": "patch-and-repair",
        "description": "Structured diagnostic, repair-plan, and patch-application workflow guidance.",
        "files": (
            "docs/toolchain/compiler.md",
            "docs/toolchain/linter.md",
            "experiments/agent-first-tooling-research/README.md",
        ),
    },
)
DIAGNOSTIC_INDEX_PATHS = (
    "docs/toolchain/compiler.md",
    "docs/toolchain/linter.md",
    "docs/agents.md",
    "SemanticScript/linter/test_semlint.py",
)
SKILL_ALIASES = {
    "sem": "language-core",
    "sem-agent": "graph-and-slice",
    "sem-language": "language-core",
    "sem-diagnostics": "patch-and-repair",
    "sem-stdlib": "sqlite-patterns",
    "sem-builds": "patch-and-repair",
    "sem-packages": "patch-and-repair",
    "sem-testing": "graph-and-slice",
}
DIAGNOSTIC_EXPLAINERS = {
    "SS3101": {
        "title": "missing purpose metadata",
        "summary": "Operations should declare a purpose row so agents and reviewers can recover intent without guessing from implementation alone.",
        "whyItMatters": [
            "Long sessions lose context first in business intent, not in syntax.",
            "Purpose rows give repair tools a stable summary of why the operation exists."
        ],
        "commonFixes": [
            "Add a `purpose operation ...` row that states what the operation does in one sentence."
        ],
    },
    "SS3102": {
        "title": "missing invariant metadata",
        "summary": "Operations should declare at least one invariant row describing the safety or business rule that must remain true.",
        "whyItMatters": [
            "Invariants are the facts most likely to drift during multi-file agent edits.",
            "Explicit invariants make semantic regressions easier to catch in review and lint."
        ],
        "commonFixes": [
            "Add an `invariant operation ...` row that states the non-negotiable rule the operation preserves."
        ],
    },
    "SS3104": {
        "title": "missing capability coverage",
        "summary": "An operation declares an effect without an authorizing capability or authority proof.",
        "whyItMatters": [
            "Effects without authority are one of the fastest ways for semantic drift to hide in a codebase.",
            "Agents need explicit proof of who is allowed to perform side effects."
        ],
        "commonFixes": [
            "Add `authority OP ACTION PATH` when the authority is local and obvious.",
            "Declare a reusable capability and attach it with `useCapability` when the same proof recurs."
        ],
    },
    "SS0104": {
        "title": "unused errorCase",
        "summary": "An error case was declared but never constructed on any observed failure path.",
        "whyItMatters": [
            "Dead error variants often mean an incomplete failure path rather than harmless clutter.",
            "Agents should confirm whether the missing raise is the real bug before removing the declaration."
        ],
        "commonFixes": [
            "Wire the error case into the intended failure path.",
            "Remove the dead variant only if the domain truly no longer uses it."
        ],
    },
    "SSRUN001": {
        "title": "runtime panic",
        "summary": "The program trapped with SemanticScript runtime panic context enabled.",
        "whyItMatters": [
            "This means execution reached a runtime safety boundary that static checks did not eliminate.",
            "The panic block should identify the source row, operation, and call involved."
        ],
        "commonFixes": [
            "Re-run under dev panic mode and inspect the referenced operation, call, and source row.",
            "Use `sem inspect-ir` or trace output when the failure depends on runtime lowering."
        ],
    },
}


def _source_fingerprint(source: Path) -> str:
    try:
        return hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        return ""


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _safe_stem(path: Path) -> str:
    stem = path.stem or "source"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return safe or "source"


def _artifact_run_dir(source: Path, kind: str) -> Path:
    fingerprint = _source_fingerprint(source)[:12] or "nofingerprint"
    timestamp_ns = time.time_ns()
    root = source.resolve().parent / ".semcache" / "observability"
    run_dir = root / f"{kind}-{_safe_stem(source)}-{fingerprint}-{timestamp_ns}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json_artifact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def _read_agent_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") == "sem.artifactIndex.v0":
        profile_path = payload.get("artifacts", {}).get("profilePath")
        if profile_path:
            return _read_agent_json(Path(profile_path))
    return payload


def _nested_get(payload: dict, dotted: str, default=0):
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _counter_delta(baseline: dict, candidate: dict) -> dict:
    keys = sorted(set(baseline) | set(candidate))
    return {
        key: {
            "baseline": baseline.get(key, 0),
            "candidate": candidate.get(key, 0),
            "delta": candidate.get(key, 0) - baseline.get(key, 0),
        }
        for key in keys
    }


def _profile_delta_payload(baseline_path: Path, candidate_path: Path) -> dict:
    baseline = _read_agent_json(baseline_path)
    candidate = _read_agent_json(candidate_path)
    return {
        "schemaVersion": "sem.profileDelta.v0",
        "tool": {"name": "sem", "version": VERSION},
        "inputs": {
            "baselinePath": str(baseline_path.resolve()),
            "candidatePath": str(candidate_path.resolve()),
            "baselineSchema": baseline.get("schemaVersion", ""),
            "candidateSchema": candidate.get("schemaVersion", ""),
        },
        "source": {
            "baselineFingerprint": _nested_get(baseline, "source.fingerprint", ""),
            "candidateFingerprint": _nested_get(candidate, "source.fingerprint", ""),
            "sameSource": (
                _nested_get(baseline, "source.fingerprint", "")
                == _nested_get(candidate, "source.fingerprint", "")
            ),
        },
        "build": {
            "baselineFingerprint": _nested_get(baseline, "build.fingerprint", ""),
            "candidateFingerprint": _nested_get(candidate, "build.fingerprint", ""),
            "sameBuild": (
                _nested_get(baseline, "build.fingerprint", "")
                == _nested_get(candidate, "build.fingerprint", "")
            ),
        },
        "run": {
            "durationNs": {
                "baseline": _nested_get(baseline, "run.durationNs", 0),
                "candidate": _nested_get(candidate, "run.durationNs", 0),
                "delta": (
                    _nested_get(candidate, "run.durationNs", 0)
                    - _nested_get(baseline, "run.durationNs", 0)
                ),
            },
            "traceEventCount": {
                "baseline": _nested_get(baseline, "run.traceEventCount", 0),
                "candidate": _nested_get(candidate, "run.traceEventCount", 0),
                "delta": (
                    _nested_get(candidate, "run.traceEventCount", 0)
                    - _nested_get(baseline, "run.traceEventCount", 0)
                ),
            },
        },
        "hot": {
            "operations": _counter_delta(
                _nested_get(baseline, "hot.operations", {}),
                _nested_get(candidate, "hot.operations", {})),
            "calls": _counter_delta(
                _nested_get(baseline, "hot.calls", {}),
                _nested_get(candidate, "hot.calls", {})),
            "branches": _counter_delta(
                _nested_get(baseline, "hot.branches", {}),
                _nested_get(candidate, "hot.branches", {})),
            "runtimeExternalCalls": _counter_delta(
                _nested_get(baseline, "hot.runtimeExternalCalls", {}),
                _nested_get(candidate, "hot.runtimeExternalCalls", {})),
        },
    }


def _find_build_tape(start: Path) -> Path | None:
    candidate = start.resolve()
    if candidate.is_file():
        if candidate.name.lower() in {"build.sem", "build.sscript"}:
            return candidate
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        for build_name in ("build.sem", "build.sscript"):
            build_path = directory / build_name
            if build_path.is_file():
                return build_path
    return None


def _strip_separator(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def _has_compiler_action(args: list[str]) -> bool:
    action_flags = {
        "--emit-exe",
        "--emit-ir",
        "--run",
        "--parse-only",
        "--lint",
        "--strict",
        "--inspect-ir",
        "--emit-trace-map",
        "--trace",
    }
    return any(arg in action_flags for arg in args)


def _run_compiler(source: Path, compiler_args: list[str]) -> int:
    semsc_path = ROOT / "compiler" / "semsc.py"
    command = [sys.executable, str(semsc_path), str(source), *compiler_args]
    return subprocess.call(command)


def _capture_compiler(source: Path, compiler_args: list[str],
                      timeout: int | None = None) -> subprocess.CompletedProcess:
    semsc_path = ROOT / "compiler" / "semsc.py"
    command = [sys.executable, str(semsc_path), str(source), *compiler_args]
    return subprocess.run(command, capture_output=True, text=True,
                          timeout=timeout)


def _extract_flag(args: list[str], flag: str) -> tuple[bool, list[str]]:
    found = False
    kept = []
    for arg in args:
        if arg == flag:
            found = True
            continue
        kept.append(arg)
    return found, kept


def _repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return ROOT.parent.resolve()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_ignored(path: Path, repo_root: Path) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _clean_roots(paths: list[str], repo_root: Path) -> list[Path]:
    if not paths:
        return [repo_root]
    roots = []
    for raw_path in paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if not _is_under(resolved, repo_root):
            raise ValueError(f"clean path escapes repository root: {raw_path}")
        roots.append(resolved)
    return roots


def _format_clean_target(path: Path, repo_root: Path) -> str:
    try:
        display = path.relative_to(repo_root)
    except ValueError:
        display = path
    text = str(display).replace(os.sep, "/")
    if path.is_dir() and not path.is_symlink():
        text += "/"
    return text


def _collect_clean_targets(paths: list[str]) -> tuple[Path, list[Path]]:
    repo_root = _repo_root()
    roots = _clean_roots(paths, repo_root)
    targets = set()

    for root in roots:
        if root.is_file():
            if root.suffix in CLEAN_FILE_SUFFIXES and _is_ignored(root, repo_root):
                targets.add(root)
            continue
        if not root.exists():
            continue
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            if ".git" in dirs:
                dirs.remove(".git")
            if "third_party" in dirs:
                dirs.remove("third_party")
            for dirname in list(dirs):
                child = current_path / dirname
                if dirname in CLEAN_DIRECTORY_NAMES and _is_ignored(child, repo_root):
                    targets.add(child)
                    dirs.remove(dirname)
            for filename in files:
                child = current_path / filename
                if child.suffix in CLEAN_FILE_SUFFIXES and _is_ignored(child, repo_root):
                    targets.add(child)

    for relative in CLEAN_EXACT_RELATIVE_PATHS:
        candidate = repo_root / relative
        if candidate.exists() and any(_is_under(candidate, root) for root in roots):
            if _is_ignored(candidate, repo_root):
                targets.add(candidate)

    return repo_root, sorted(targets, key=lambda item: str(item).lower())


def _remove_clean_target(path: Path, repo_root: Path) -> None:
    resolved = path.resolve()
    if not _is_under(resolved, repo_root):
        raise ValueError(f"refusing to clean path outside repository: {path}")
    if resolved.is_dir() and not resolved.is_symlink():
        shutil.rmtree(resolved)
    else:
        resolved.unlink()


def _version_command(command: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (proc.stdout or proc.stderr).splitlines()
    detail = text[0] if text else f"exit {proc.returncode}"
    return proc.returncode == 0, detail


def _doctor_check(name: str, ok: bool, detail: str, fix: str = "", optional: bool = False) -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        "fix": fix,
        "optional": bool(optional),
    }


def _pkg_config_exists(package_name: str) -> tuple[bool, str]:
    pkg_config = shutil.which("pkg-config")
    if not pkg_config:
        return False, "pkg-config missing"
    try:
        proc = subprocess.run(
            [pkg_config, "--modversion", package_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = (proc.stdout or proc.stderr).strip() or f"exit {proc.returncode}"
    return proc.returncode == 0, detail


def _env_file_exists(var_name: str) -> tuple[bool, str]:
    value = os.environ.get(var_name, "")
    if not value:
        return False, f"{var_name} unset"
    path = Path(value)
    return path.exists(), str(path)


def _env_any_file_exists(var_names: list[str]) -> tuple[bool, str]:
    details = []
    for var_name in var_names:
        ok, detail = _env_file_exists(var_name)
        if ok:
            return True, f"{var_name}={detail}"
        details.append(detail)
    return False, "; ".join(details)


def _env_header_exists(
    header_path: str,
    *,
    root_var: str,
    include_var: str,
) -> tuple[bool, str]:
    candidates = []
    include_value = os.environ.get(include_var, "")
    if include_value:
        candidates.append(Path(include_value))
    root_value = os.environ.get(root_var, "")
    if root_value:
        candidates.append(Path(root_value) / "include")
    if not candidates:
        return False, f"{include_var}/{root_var} unset"
    for directory in candidates:
        candidate = directory / header_path
        if candidate.exists():
            return True, str(candidate)
    return False, "; ".join(str(directory / header_path) for directory in candidates)


def _doctor_payload() -> dict:
    python_ok = sys.version_info >= (3, 11)
    checks = [
        _doctor_check(
            "python",
            python_ok,
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "Install Python 3.11 or newer and re-run from that interpreter.",
        ),
        _doctor_check(
            "llvmlite",
            importlib.util.find_spec("llvmlite") is not None,
            "available" if importlib.util.find_spec("llvmlite") is not None else "missing",
            "Run: python -m pip install -r requirements.txt",
        ),
    ]

    clang_env = os.environ.get("SEMSC_CLANG", "")
    clang_path = clang_env or shutil.which("clang") or ""
    clang_ok = bool(clang_path) and (clang_env == "" or Path(clang_path).exists())
    checks.append(_doctor_check(
        "clang",
        clang_ok,
        clang_path or "missing",
        "Install LLVM/clang or set SEMSC_CLANG to clang.exe.",
    ))

    if (ROOT.parent / "vscode-semanticscript").exists():
        node_path = shutil.which("node")
        node_ok = bool(node_path)
        node_detail = node_path or "missing"
        if node_ok:
            ok, detail = _version_command(["node", "--version"])
            node_ok = ok
            node_detail = detail
        checks.append(_doctor_check(
            "node",
            node_ok,
            node_detail,
            "Install Node.js 20 or newer for VS Code extension checks.",
        ))

    cmake_path = shutil.which("cmake")
    cmake_ok = bool(cmake_path)
    cmake_detail = cmake_path or "missing"
    if cmake_ok:
        ok, detail = _version_command(["cmake", "--version"])
        cmake_ok = ok
        cmake_detail = detail
    git_path = shutil.which("git")
    git_ok = bool(git_path)
    checks.append(_doctor_check(
        "native-http-runtime",
        cmake_ok and clang_ok,
        f"cmake={cmake_detail}; clang={clang_path or 'missing'}",
        "Install CMake and LLVM/clang before building SemanticScript/runtime/native_http.",
    ))

    libuv_pkg_ok, libuv_pkg_detail = _pkg_config_exists("libuv")
    libuv_lib_ok, libuv_lib_detail = _env_any_file_exists(
        ["SEM_LIBUV_LIB", "SEM_LIBUV_LIBRARY"])
    libuv_header_ok, libuv_header_detail = _env_header_exists(
        "uv.h",
        root_var="SEM_LIBUV_ROOT",
        include_var="SEM_LIBUV_INCLUDE_DIR",
    )
    libuv_env_ok = libuv_lib_ok and libuv_header_ok
    libuv_fetch_ok = cmake_ok and git_ok
    libuv_fetch_detail = (
        "system libuv missing; CMake FetchContent fallback available"
        if libuv_fetch_ok else
        "system libuv missing; install git+CMake or set SEM_LIBUV_*"
    )
    checks.append(_doctor_check(
        "native-async-libuv",
        libuv_pkg_ok or libuv_env_ok or libuv_fetch_ok,
        (
            libuv_pkg_detail if libuv_pkg_ok
            else f"{libuv_lib_detail}; {libuv_header_detail}" if libuv_env_ok
            else libuv_fetch_detail
        ),
        "Install libuv 1.x, set SEM_LIBUV_ROOT/SEM_LIBUV_INCLUDE_DIR/SEM_LIBUV_LIB, or allow CMake FetchContent.",
        optional=True,
    ))

    curl_pkg_ok, curl_pkg_detail = _pkg_config_exists("libcurl")
    curl_lib_ok, curl_lib_detail = _env_any_file_exists(
        ["SEM_CURL_LIB", "SEM_CURL_LIBRARY"])
    curl_header_ok, curl_header_detail = _env_header_exists(
        "curl/curl.h",
        root_var="SEM_CURL_ROOT",
        include_var="SEM_CURL_INCLUDE_DIR",
    )
    curl_env_ok = curl_lib_ok and curl_header_ok
    curl_fetch_ok = cmake_ok and git_ok
    curl_fetch_detail = (
        "system libcurl missing; CMake FetchContent fallback available"
        if curl_fetch_ok else
        "system libcurl missing; install git+CMake or set SEM_CURL_*"
    )
    checks.append(_doctor_check(
        "native-http-client-libcurl",
        curl_pkg_ok or curl_env_ok or curl_fetch_ok,
        (
            curl_pkg_detail if curl_pkg_ok
            else f"{curl_lib_detail}; {curl_header_detail}" if curl_env_ok
            else curl_fetch_detail
        ),
        "Install libcurl, set SEM_CURL_ROOT/SEM_CURL_INCLUDE_DIR/SEM_CURL_LIB, or allow CMake FetchContent.",
        optional=True,
    ))

    return {
        "schemaVersion": "sem.doctor.v0",
        "tool": {"name": "sem", "version": VERSION},
        "checks": checks,
        "ok": all(check["ok"] or check.get("optional", False) for check in checks),
    }


def _module_version_from_path(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("__version__"):
                _name, _equals, value = stripped.partition("=")
                return value.strip().strip("\"'")
    except OSError:
        return ""
    return ""


def _load_semlint_module():
    module_name = "_sem_driver_semlint"
    if module_name in sys.modules:
        return sys.modules[module_name]
    semlint_path = ROOT / "linter" / "semlint.py"
    spec = importlib.util.spec_from_file_location(module_name, semlint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load semlint from {semlint_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _line_payload(line) -> dict:
    return {
        "path": str(Path(line.path).resolve()),
        "line": int(line.number),
        "column": int(line.column),
    }


def _row_value(facts, verb: str, index: int = 0, default: str = "") -> str:
    for source_line in facts.lines:
        if source_line.tokens and source_line.verb == verb and len(source_line.args) > index:
            return source_line.args[index]
    return default


def _row_values(facts, verb: str, index: int = 0) -> list[str]:
    values = []
    for source_line in facts.lines:
        if source_line.tokens and source_line.verb == verb and len(source_line.args) > index:
            values.append(source_line.args[index])
    return values


def _syntax_status_counts() -> dict:
    syntax_path = ROOT.parent / "SYNTAX.md"
    counts = {"implemented": 0, "partial": 0, "notImplemented": 0}
    try:
        text = syntax_path.read_text(encoding="utf-8")
    except OSError:
        return counts
    counts["implemented"] = text.count("| Impl'd |")
    counts["partial"] = text.count("| Partial |")
    counts["notImplemented"] = text.count("| Not impl'd |")
    return counts


def _runtime_feature_flags() -> dict:
    runtime_root = ROOT / "runtime"
    third_party_root = ROOT.parent / "third_party"
    return {
        "nativeHttpRuntime": (runtime_root / "native_http" / "sem_http_runtime.c").exists(),
        "nativeJsonRuntime": (runtime_root / "native_json" / "sem_json_runtime.c").exists(),
        "nativeSqliteRuntime": (runtime_root / "native_sqlite" / "sem_sqlite_runtime.c").exists(),
        "nativeWin32GuiRuntime": (
            runtime_root / "native_win32_gui" / "sem_win32_gui_runtime.c"
        ).exists(),
        "nativeWinui3GuiScaffold": (
            runtime_root / "native_winui3_gui" / "sem_winui3_gui_runtime.h"
        ).exists(),
        "nativeBcryptRuntime": (runtime_root / "native_bcrypt" / "sem_bcrypt_runtime.c").exists(),
        "vendoredSqlite": (third_party_root / "sqlite" / "sqlite3.c").exists(),
        "vendoredBcrypt": (third_party_root / "bcrypt").exists(),
    }


def _build_context_payload(path: Path) -> dict:
    semlint = _load_semlint_module()
    requested = path
    build_tape = _find_build_tape(path)
    source_for_facts = build_tape if build_tape is not None else path
    facts = semlint.parse_file(source_for_facts) if source_for_facts.exists() else None
    source_files, _errors = _symbol_source_files(path)
    syntax_counts = _syntax_status_counts()
    project = {
        "requestedPath": str(requested.resolve()),
        "projectRoot": str(build_tape.parent.resolve()) if build_tape else "",
        "buildTape": str(build_tape.resolve()) if build_tape else "",
        "buildProject": _row_value(facts, "buildProject") if facts else "",
        "projectName": _row_value(facts, "project") if facts else "",
        "modulePath": _row_value(facts, "modulePath", 1) if facts else "",
        "sourceRoots": [],
        "mainFile": _row_value(facts, "mainFile", 1) if facts else "",
        "mainOperation": _row_value(facts, "mainOperation", 1) if facts else "",
        "targetRuntime": _row_value(facts, "targetRuntime", 1) if facts else "",
        "asyncRuntime": _row_value(facts, "asyncRuntime", 1) if facts else "",
        "guiBackend": _row_value(facts, "guiBackend", 1) if facts else "",
        "targets": _row_values(facts, "target") if facts else [],
        "nativeOutput": _row_value(facts, "nativeOutput", 1) if facts else "",
    }
    if facts:
        project["sourceRoots"] = _row_values(facts, "sourceRoot", 1)
    return {
        "schemaVersion": "sem.context.v1",
        "tool": {"name": "sem", "version": VERSION},
        "project": project,
        "sourceFiles": [str(source.resolve()) for source in source_files],
        "tools": {
            "compiler": {
                "path": str((ROOT / "compiler" / "semsc.py").resolve()),
                "version": _module_version_from_path(ROOT / "compiler" / "semsc.py"),
            },
            "linter": {
                "path": str((ROOT / "linter" / "semlint.py").resolve()),
                "version": _module_version_from_path(ROOT / "linter" / "semlint.py"),
            },
            "formatter": {
                "path": str((ROOT / "formatter" / "semfmt.py").resolve()),
                "version": _module_version_from_path(ROOT / "formatter" / "semfmt.py"),
            },
        },
        "runtimeFeatureFlags": _runtime_feature_flags(),
        "supportedSyntax": {
            "inventoryPath": str((ROOT.parent / "SYNTAX.md").resolve()),
            "statusCounts": syntax_counts,
            "languageModes": ["strictExecutable", "refinedSyntax"],
            "schemaVersion": SYNTAX_PAYLOAD_VERSION,
            "normalCommandsAutoMigrateOldSyntax": False,
            "currentRows": {
                "argument": "argument CALL PARAM TYPE VALUE",
                "bind": ["bind value NAME TYPE CALL", "bind ok NAME TYPE CALL", "bind error NAME TYPE CALL"],
                "branch": [
                    "branch if condition CONDITION target LABEL",
                    "branch error source CALL target LABEL",
                    "branch else target LABEL",
                ],
                "jump": "jump target LABEL",
                "return": ["return value VALUE", "return ok VALUE", "return error VALUE", "return void"],
                "ignore": [
                    "ignore value source CALL type TYPE",
                    "ignore ok source CALL type TYPE",
                    "ignore error source CALL",
                    "ignore void source CALL",
                ],
                "input": "input operation OP NAME TYPE",
                "output": "output operation OP TYPE",
                "authority": "authority OP ACTION PATH",
            },
        },
        "knownDeferredFeatures": {
            "partialSyntaxRows": syntax_counts["partial"],
            "notImplementedSyntaxRows": syntax_counts["notImplemented"],
        },
    }


def _symbol_source_files(path: Path) -> tuple[list[Path], list[str]]:
    semlint = _load_semlint_module()
    errors: list[str] = []
    requested = path.resolve()
    build_tape = _find_build_tape(path)
    if requested.is_file() and requested.name.lower() not in {"build.sem", "build.sscript"}:
        return [requested], errors
    if build_tape is None:
        return ([requested] if requested.is_file() else []), errors

    source_files = [build_tape.resolve()]
    try:
        build_facts = semlint.parse_file(build_tape)
        registered, main_files = semlint._collect_registered_modules(build_facts)
        for module_name, (_line, raw_path) in sorted(registered.items()):
            resolved = semlint._resolve_registered_module_source(
                module_name, raw_path, build_tape, main_files)
            if resolved is None:
                errors.append(f"registered module {module_name} did not resolve")
                continue
            source_files.append(Path(resolved).resolve())
    except (OSError, RuntimeError) as exc:
        errors.append(str(exc))

    deduped = []
    seen = set()
    for source in source_files:
        if source in seen:
            continue
        seen.add(source)
        deduped.append(source)
    return deduped, errors


def _source_ref(line) -> dict:
    payload = _line_payload(line)
    payload["raw"] = line.raw
    return payload


def _operation_rows(operation, verb: str) -> list:
    return [
        source_line for source_line in operation.lines
        if source_line.tokens and source_line.verb == verb
    ]


def _signature_input_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb != "input":
        return None
    if len(args) >= 4 and args[0] == "operation" and args[1] == operation.name:
        return {
            "subjectKind": args[0],
            "name": args[2],
            "type": args[3],
            "location": _line_payload(source_line),
        }
    if len(args) >= 3 and args[0] == operation.name:
        return {
            "subjectKind": "operation",
            "name": args[1],
            "type": args[2],
            "location": _line_payload(source_line),
        }
    return None


def _signature_output_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb != "output":
        return None
    if len(args) >= 3 and args[0] == "operation" and args[1] == operation.name:
        return {
            "subjectKind": args[0],
            "type": args[2],
            "values": args[2:],
            "location": _line_payload(source_line),
        }
    if len(args) >= 2 and args[0] == operation.name:
        return {
            "subjectKind": "operation",
            "type": args[1],
            "values": args[1:],
            "location": _line_payload(source_line),
        }
    return None


def _effect_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb == "effect" and len(args) >= 3 and args[0] == operation.name:
        return {
            "action": args[1],
            "path": args[2],
            "location": _line_payload(source_line),
        }
    return None


def _authority_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb != "authority" or len(args) < 3 or args[0] != operation.name:
        return None
    if args[1] in AUTHORITY_ACTIONS:
        action, path = args[1], args[2]
    else:
        path, action = args[1], args[2]
    return {
        "action": action,
        "path": path,
        "location": _line_payload(source_line),
    }


def _call_reference_from_line(source_line) -> str:
    args = source_line.args
    if not args:
        return ""
    verb = source_line.verb
    if verb in {"argument", "run", "start", "await", "case", "startInGroup", "timeout", "cancelOn"}:
        return args[0]
    if verb == "arg":
        return args[0]
    if verb == "bind":
        if len(args) >= 4 and args[0] in {"value", "ok", "error"}:
            return args[3]
        if len(args) >= 3:
            return args[2]
    if verb in {"bindOk", "bindError"} and len(args) >= 3:
        return args[2]
    if verb == "ignore":
        if len(args) >= 3 and args[0] in CALL_DISPOSITION_VARIANTS and args[1] == "source":
            return args[2]
    if verb in {"ignoreOk", "ignoreValue"}:
        return args[0]
    if verb == "branch" and len(args) >= 5 and args[0] == "error" and args[1] == "source":
        return args[2]
    if verb == "branchIfError":
        return args[0]
    return ""


def _bind_variant_payload(source_line) -> tuple[str, dict] | None:
    args = source_line.args
    if source_line.verb == "bind":
        if len(args) >= 4 and args[0] in {"value", "ok", "error"}:
            return args[0], {
                "name": args[1],
                "type": args[2],
                "source": args[3],
                "location": _line_payload(source_line),
            }
        if len(args) >= 3:
            return "value", {
                "name": args[0],
                "type": args[1],
                "source": args[2],
                "location": _line_payload(source_line),
            }
    if source_line.verb == "bindOk" and len(args) >= 3:
        return "ok", {
            "name": args[0],
            "type": args[1],
            "source": args[2],
            "location": _line_payload(source_line),
        }
    if source_line.verb == "bindError" and len(args) >= 3:
        return "error", {
            "name": args[0],
            "type": args[1],
            "source": args[2],
            "location": _line_payload(source_line),
        }
    return None


def _ignore_variant_payload(source_line) -> tuple[str, dict] | None:
    args = source_line.args
    if source_line.verb == "ignore" and len(args) >= 3:
        variant = args[0]
        if variant in CALL_DISPOSITION_VARIANTS and args[1] == "source":
            payload = {
                "source": args[2],
                "location": _line_payload(source_line),
            }
            if len(args) >= 5 and args[3] == "type":
                payload["type"] = args[4]
            return variant, payload
    if source_line.verb == "ignoreOk" and len(args) >= 1:
        payload = {"source": args[0], "location": _line_payload(source_line)}
        if len(args) >= 2:
            payload["type"] = args[1]
        return "ok", payload
    if source_line.verb == "ignoreValue" and len(args) >= 1:
        variant = "void" if len(args) >= 2 and args[1] == "Void" else "value"
        payload = {"source": args[0], "location": _line_payload(source_line)}
        if variant == "value" and len(args) >= 2:
            payload["type"] = args[1]
        return variant, payload
    return None


def _branch_payload(source_line) -> dict | None:
    args = source_line.args
    if source_line.verb == "branch":
        if len(args) >= 5 and args[0] == "if" and args[1] == "condition" and args[3] == "target":
            return {
                "kind": "branch if",
                "condition": args[2],
                "target": args[4],
                "location": _line_payload(source_line),
            }
        if len(args) >= 5 and args[0] == "error" and args[1] == "source" and args[3] == "target":
            return {
                "kind": "branch error",
                "source": args[2],
                "target": args[4],
                "location": _line_payload(source_line),
            }
        if len(args) >= 3 and args[0] == "else" and args[1] == "target":
            return {
                "kind": "branch else",
                "target": args[2],
                "location": _line_payload(source_line),
            }
        if len(args) >= 1:
            return {
                "kind": "jump",
                "target": args[0],
                "location": _line_payload(source_line),
            }
    if source_line.verb == "branchIf" and len(args) >= 2:
        return {
            "kind": "branch if",
            "condition": args[0],
            "target": args[1],
            "location": _line_payload(source_line),
        }
    if source_line.verb == "branchIfError" and len(args) >= 2:
        return {
            "kind": "branch error",
            "source": args[0],
            "target": args[1],
            "location": _line_payload(source_line),
        }
    if source_line.verb == "jump" and len(args) >= 2 and args[0] == "target":
        return {
            "kind": "jump",
            "target": args[1],
            "location": _line_payload(source_line),
        }
    return None


def _return_payload(source_line) -> dict | None:
    args = source_line.args
    if source_line.verb == "return" and args and args[0] in CALL_DISPOSITION_VARIANTS:
        payload = {
            "variant": args[0],
            "location": _line_payload(source_line),
        }
        if args[0] != "void" and len(args) >= 2:
            payload["value"] = args[1]
        return payload
    legacy_variants = {
        "returnValue": "value",
        "returnOk": "ok",
        "returnError": "error",
        "returnVoid": "void",
    }
    if source_line.verb in legacy_variants:
        payload = {
            "variant": legacy_variants[source_line.verb],
            "location": _line_payload(source_line),
        }
        if payload["variant"] != "void" and args:
            payload["value"] = args[0]
        return payload
    return None


def _operation_call_payloads(operation) -> list[dict]:
    calls: dict[str, dict] = {}
    order: dict[str, int] = {}

    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        if source_line.verb == "call" and len(args) >= 2:
            calls[args[0]] = {
                "name": args[0],
                "target": args[1],
                "location": _line_payload(source_line),
                "arguments": [],
                "disposition": {
                    "run": False,
                    "start": False,
                    "await": False,
                    "bind": {variant: [] for variant in ("value", "ok", "error")},
                    "ignore": {variant: [] for variant in CALL_DISPOSITION_VARIANTS},
                    "branchError": [],
                },
            }
            order[args[0]] = source_line.number

    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        call_name = _call_reference_from_line(source_line)
        call_payload = calls.get(call_name)
        if call_payload is None:
            continue
        if source_line.verb == "argument" and len(args) >= 4:
            call_payload["arguments"].append({
                "parameter": args[1],
                "type": args[2],
                "value": args[3],
                "location": _line_payload(source_line),
            })
        elif source_line.verb == "arg" and len(args) >= 3:
            call_payload["arguments"].append({
                "parameter": args[1],
                "type": "",
                "value": args[2],
                "location": _line_payload(source_line),
            })
        elif source_line.verb in {"run", "start", "await"}:
            call_payload["disposition"][source_line.verb] = True
        elif source_line.verb == "case":
            call_payload["disposition"]["await"] = True
        else:
            bind_payload = _bind_variant_payload(source_line)
            if bind_payload is not None:
                variant, payload = bind_payload
                call_payload["disposition"]["bind"][variant].append(payload)
                continue
            ignore_payload = _ignore_variant_payload(source_line)
            if ignore_payload is not None:
                variant, payload = ignore_payload
                call_payload["disposition"]["ignore"][variant].append(payload)
                continue
            branch_payload = _branch_payload(source_line)
            if branch_payload is not None and branch_payload["kind"] == "branch error":
                call_payload["disposition"]["branchError"].append(branch_payload)

    return [
        calls[name]
        for name in sorted(calls, key=lambda item: order.get(item, 0))
    ]


def _operation_symbol(operation, semlint, facts=None) -> dict:
    inputs = []
    outputs = []
    effects = []
    capabilities = []
    authorities = []
    control_flow = []
    returns = []

    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        input_payload = _signature_input_payload(source_line, operation)
        output_payload = _signature_output_payload(source_line, operation)
        effect_payload = _effect_payload(source_line, operation)
        authority_payload = _authority_payload(source_line, operation)
        branch_payload = _branch_payload(source_line)
        return_payload = _return_payload(source_line)
        if input_payload is not None:
            inputs.append(input_payload)
        elif output_payload is not None:
            outputs.append(output_payload)
        elif effect_payload is not None:
            effects.append(effect_payload)
        elif source_line.verb == "useCapability" and len(args) >= 2 and args[0] == operation.name:
            capabilities.append({
                "name": args[1],
                "location": _line_payload(source_line),
            })
        elif authority_payload is not None:
            authorities.append(authority_payload)
        elif branch_payload is not None:
            control_flow.append(branch_payload)
        elif return_payload is not None:
            returns.append(return_payload)
    if facts is not None:
        for source_line in facts.lines:
            authority_payload = _authority_payload(source_line, operation)
            if authority_payload is not None and authority_payload not in authorities:
                authorities.append(authority_payload)

    return {
        "name": operation.name,
        "location": _line_payload(operation.line),
        "inputs": inputs,
        "outputs": outputs,
        "effects": effects,
        "capabilities": capabilities,
        "authorities": authorities,
        "calls": _operation_call_payloads(operation),
        "controlFlow": control_flow,
        "returns": returns,
    }


def _symbol_payload_for_file(path: Path, semlint) -> tuple[dict, list[dict]]:
    facts = semlint.parse_file(path)
    operations = [
        _operation_symbol(operation, semlint, facts)
        for operation in sorted(facts.operations.values(), key=lambda item: item.line.number)
    ]
    routes = [
        {
            "server": route.server,
            "method": route.method,
            "path": route.path,
            "handler": route.handler,
            "location": _line_payload(route.line),
        }
        for route in facts.routes
    ]
    unresolved = []
    operation_names = set(facts.operations)
    for operation in facts.operations.values():
        calls = {
            source_line.args[0]
            for source_line in operation.lines
            if source_line.tokens and source_line.verb == "call" and len(source_line.args) >= 2
        }
        call_targets = {
            source_line.args[0]: source_line.args[1]
            for source_line in operation.lines
            if source_line.tokens and source_line.verb == "call" and len(source_line.args) >= 2
        }
        for source_line in operation.lines:
            if not source_line.tokens or not source_line.args:
                continue
            maybe_call = _call_reference_from_line(source_line)
            if maybe_call and maybe_call not in calls:
                unresolved.append({
                    "kind": "callAttachment",
                    "operation": operation.name,
                    "name": maybe_call,
                    "location": _line_payload(source_line),
                })
        for call_name, call_target in call_targets.items():
            if "." not in call_target and call_target not in operation_names:
                unresolved.append({
                    "kind": "localCallTarget",
                    "operation": operation.name,
                    "name": call_target,
                    "location": _line_payload(next(
                        line for line in operation.lines
                        if line.tokens and line.verb == "call" and line.args[0] == call_name
                    )),
                })
    file_payload = {
        "path": str(path.resolve()),
        "module": _row_value(facts, "module"),
        "imports": [
            {
                "module": item.module_name,
                "alias": item.alias or "",
                "syntax": item.syntax,
                "location": _line_payload(item.line),
            }
            for item in facts.module_imports
        ],
        "operations": operations,
        "routes": routes,
    }
    return file_payload, unresolved


def _symbol_graph_payload(path: Path) -> dict:
    semlint = _load_semlint_module()
    source_files, errors = _symbol_source_files(path)
    files = []
    unresolved = []
    for source in source_files:
        if not source.exists() or source.suffix.lower() not in {".sem", ".sscript"}:
            continue
        try:
            file_payload, file_unresolved = _symbol_payload_for_file(source, semlint)
            files.append(file_payload)
            unresolved.extend(file_unresolved)
        except OSError as exc:
            errors.append(str(exc))
    return {
        "schemaVersion": "sem.symbols.v1",
        "tool": {"name": "sem", "version": VERSION},
        "syntax": {
            "schemaVersion": SYNTAX_PAYLOAD_VERSION,
            "normalCommandsAutoMigrateOldSyntax": False,
            "rowForms": [
                "argument CALL PARAM TYPE VALUE",
                "bind value NAME TYPE CALL",
                "bind ok NAME TYPE CALL",
                "bind error NAME TYPE CALL",
                "branch if condition CONDITION target LABEL",
                "branch error source CALL target LABEL",
                "branch else target LABEL",
                "jump target LABEL",
                "return value VALUE",
                "return ok VALUE",
                "return error VALUE",
                "return void",
                "ignore value source CALL type TYPE",
                "ignore ok source CALL type TYPE",
                "ignore error source CALL",
                "ignore void source CALL",
                "input operation OP NAME TYPE",
                "output operation OP TYPE",
                "authority OP ACTION PATH",
            ],
        },
        "sourceFiles": [str(source.resolve()) for source in source_files],
        "files": files,
        "summary": {
            "fileCount": len(files),
            "operationCount": sum(len(file["operations"]) for file in files),
            "callCount": sum(
                len(operation["calls"])
                for file in files
                for operation in file["operations"]
            ),
            "routeCount": sum(len(file["routes"]) for file in files),
            "unresolvedReferenceCount": len(unresolved),
        },
        "unresolvedReferences": unresolved,
        "errors": errors,
    }


def _version_payload() -> dict:
    return {
        "schemaVersion": "sem.version.v1",
        "tool": {"name": "sem", "version": VERSION},
        "compiler": {
            "path": str((ROOT / "compiler" / "semsc.py").resolve()),
            "version": _module_version_from_path(ROOT / "compiler" / "semsc.py"),
        },
        "linter": {
            "path": str((ROOT / "linter" / "semlint.py").resolve()),
            "version": _module_version_from_path(ROOT / "linter" / "semlint.py"),
        },
        "formatter": {
            "path": str((ROOT / "formatter" / "semfmt.py").resolve()),
            "version": _module_version_from_path(ROOT / "formatter" / "semfmt.py"),
        },
        "runtimeFeatureFlags": _runtime_feature_flags(),
        "syntax": {
            "schemaVersion": SYNTAX_PAYLOAD_VERSION,
            "statusCounts": _syntax_status_counts(),
        },
    }


def _collect_facts_bundle(path: Path) -> dict:
    semlint = _load_semlint_module()
    source_files, errors = _symbol_source_files(path)
    bundle = []
    for source in source_files:
        if not source.exists() or source.suffix.lower() not in {".sem", ".sscript"}:
            continue
        try:
            bundle.append({
                "path": source,
                "facts": semlint.parse_file(source),
            })
        except (OSError, RuntimeError) as exc:
            errors.append(str(exc))
    return {
        "semlint": semlint,
        "sourceFiles": source_files,
        "files": bundle,
        "errors": errors,
    }


def _diagnostic_expected_actual(diagnostic: dict) -> tuple[str, str]:
    code = diagnostic.get("code", "")
    kind = diagnostic.get("kind", "")
    gap_edge = diagnostic.get("gapEdge", "")
    subject = diagnostic.get("subjectName", "")
    if code == "SS3104":
        return (
            "capability or authority covering the declared effect",
            f"no capability proof found for {subject or 'operation'}",
        )
    if code == "SS3101":
        return (
            "purpose row describing the operation intent",
            "purpose metadata is missing",
        )
    if code == "SS3102":
        return (
            "invariant row describing the safety or business rule",
            "invariant metadata is missing",
        )
    if code.startswith("SS01"):
        return (
            "at least one valid use site or removal of the dead declaration",
            "no live use sites were discovered",
        )
    if gap_edge:
        return (
            f"supporting `{gap_edge}` row or equivalent evidence",
            "supporting row was not found",
        )
    if kind:
        return (
            f"rule `{kind}` satisfied",
            "rule violation detected",
        )
    return ("valid SemanticScript row graph", "validation gap detected")


def _normalize_lint_diagnostic(diagnostic: dict) -> dict:
    expected, actual = _diagnostic_expected_actual(diagnostic)
    primary = diagnostic.get("primary", {})
    fix_candidates = list(diagnostic.get("fixCandidates", []))
    auto_applicable = any(candidate.get("autoApplicable") for candidate in fix_candidates)
    fix_safety = "requires-human-review"
    if auto_applicable:
        fix_safety = "local-edit"
    elif diagnostic.get("code") in {"SS3104", "SS3101", "SS3102"}:
        fix_safety = "local-edit"
    return {
        "code": diagnostic.get("code", ""),
        "severity": diagnostic.get("severity", ""),
        "source": "linter",
        "kind": diagnostic.get("kind", ""),
        "message": (
            diagnostic.get("intentSlogan")
            or diagnostic.get("invariantRule")
            or diagnostic.get("kind")
            or diagnostic.get("code", "")
        ),
        "span": {
            "file": str(Path(primary.get("path", "")).resolve()) if primary.get("path") else "",
            "line": int(primary.get("line", 0) or 0),
            "column": int(primary.get("column", 0) or 0),
            "role": primary.get("role", ""),
        },
        "subjectName": diagnostic.get("subjectName", ""),
        "subjectKind": diagnostic.get("subjectKind", ""),
        "gapEdge": diagnostic.get("gapEdge", ""),
        "expected": expected,
        "actual": actual,
        "help": diagnostic.get("agentHint", ""),
        "invariantRule": diagnostic.get("invariantRule", ""),
        "specAnchor": diagnostic.get("specAnchor", ""),
        "blocksCompile": bool(diagnostic.get("blocksCompile", False)),
        "confidence": diagnostic.get("confidence", ""),
        "effort": diagnostic.get("effort", ""),
        "citations": list(diagnostic.get("citations", [])),
        "fixCandidates": fix_candidates,
        "repair": {
            "id": fix_candidates[0].get("name", "") if fix_candidates else "",
            "safe": auto_applicable or diagnostic.get("code") in {"SS3104"},
            "fixSafety": fix_safety,
        },
        "explain": {
            "code": diagnostic.get("code", ""),
            "command": f"sem explain {diagnostic.get('code', '')} --json".strip(),
        },
    }


def _collect_lint_diagnostics(path: Path) -> tuple[list[dict], list[str]]:
    bundle = _collect_facts_bundle(path)
    semlint = bundle["semlint"]
    diagnostics: list[dict] = []
    errors: list[str] = list(bundle["errors"])
    for item in bundle["files"]:
        source = item["path"]
        try:
            for diagnostic in semlint.lint_path(source):
                diagnostics.append(_normalize_lint_diagnostic(diagnostic.to_json()))
        except (OSError, RuntimeError) as exc:
            errors.append(f"{source}: {exc}")
    diagnostics.sort(key=lambda item: (
        not item.get("blocksCompile", False),
        item.get("severity", ""),
        item.get("code", ""),
        item.get("span", {}).get("file", ""),
        item.get("span", {}).get("line", 0),
        item.get("span", {}).get("column", 0),
    ))
    return diagnostics, errors


def _compiler_check_probe(source: Path, compiler_args: list[str]) -> dict:
    try:
        proc = _capture_compiler(
            source,
            ["--parse-only", "--lint", "--diagnostics-format", "json", *compiler_args],
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "attempted": True,
            "ok": False,
            "returnCode": 2,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "returnCode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _build_check_payload(path: Path, compiler_args: list[str]) -> dict:
    context = _build_context_payload(path)
    symbols = _symbol_graph_payload(path)
    diagnostics, lint_errors = _collect_lint_diagnostics(path)
    build_tape = _find_build_tape(path)
    compiler_source = build_tape if build_tape is not None else path
    compiler = _compiler_check_probe(compiler_source, compiler_args)
    readiness = _readiness_payload(path)
    errors = sum(1 for item in diagnostics if item.get("severity") == "error" or item.get("blocksCompile"))
    warnings = sum(1 for item in diagnostics if item.get("severity") == "warning" and not item.get("blocksCompile"))
    ok = bool(compiler["ok"] and errors == 0 and not lint_errors and not symbols["errors"])
    status = "ok"
    if not ok:
        status = "diagnostics"
    elif warnings:
        status = "ok-with-warnings"
    payload = {
        "schemaVersion": "sem.check.v1",
        "tool": {"name": "sem", "version": VERSION},
        "input": {
            "requestedPath": str(path.resolve()),
            "compilerSource": str(compiler_source.resolve()) if compiler_source.exists() else str(compiler_source),
            "buildTape": context["project"].get("buildTape", ""),
        },
        "ok": ok,
        "status": status,
        "project": context["project"],
        "sourceFiles": context["sourceFiles"],
        "diagnostics": diagnostics,
        "summary": {
            "errors": errors + len(lint_errors),
            "warnings": warnings,
            "repairable": sum(1 for item in diagnostics if item.get("repair", {}).get("id")),
            "compileBlocking": sum(1 for item in diagnostics if item.get("blocksCompile")),
        },
        "compiler": {
            "attempted": compiler["attempted"],
            "ok": compiler["ok"],
            "returnCode": compiler["returnCode"],
            "stdoutSnippet": (compiler["stdout"] or "")[:2000],
            "stderrSnippet": (compiler["stderr"] or "")[:2000],
        },
        "unresolvedReferences": symbols["unresolvedReferences"],
        "graphSummary": symbols["summary"],
        "runtimeFeatureFlags": context["runtimeFeatureFlags"],
        "supportedSyntax": context["supportedSyntax"],
        "targetReadiness": readiness,
        "errors": lint_errors + list(symbols["errors"]),
    }
    if not compiler["ok"] and payload["status"] == "diagnostics":
        payload["status"] = "compiler-error"
    return payload


def _narrative_entries_for_operation(operation_name: str, facts) -> dict[str, list[dict]]:
    entries = {
        "purpose": [],
        "invariant": [],
        "warning": [],
        "security": [],
        "observability": [],
    }
    for source_line in facts.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        verb = source_line.verb
        if verb not in {"purpose", "invariant", "warning", "security", "observability"}:
            continue
        text = ""
        if len(args) >= 3 and args[0] == "operation" and args[1] == operation_name:
            text = args[2]
        elif len(args) >= 2 and args[0] == operation_name:
            text = args[1]
        if text:
            entries[verb].append({
                "text": text,
                "location": _line_payload(source_line),
            })
    return entries


def _module_narrative_entries(facts) -> list[dict]:
    entries = []
    interesting_verbs = {
        "purpose",
        "invariant",
        "moduleOwns",
        "moduleDoesNotOwn",
        "moduleWarning",
        "moduleSecurity",
        "moduleObservability",
    }
    for source_line in facts.lines:
        if not source_line.tokens or source_line.verb not in interesting_verbs:
            continue
        text = source_line.args[-1] if source_line.args else ""
        entries.append({
            "kind": source_line.verb,
            "text": text,
            "location": _line_payload(source_line),
        })
    return entries


def _facts_operation_lookup(bundle: dict) -> dict[str, tuple[Path, object, object]]:
    lookup = {}
    for item in bundle["files"]:
        source = item["path"]
        facts = item["facts"]
        for operation in facts.operations.values():
            lookup.setdefault(operation.name, (source, facts, operation))
    return lookup


def _graph_payload(path: Path, kind: str) -> dict:
    symbols = _symbol_graph_payload(path)
    bundle = _collect_facts_bundle(path)
    kind = kind or "summary"
    edges = []
    nodes = []

    if kind == "summary":
        return {
            "schemaVersion": "sem.graph.v1",
            "tool": {"name": "sem", "version": VERSION},
            "kind": "summary",
            "inputPath": str(path.resolve()),
            "summary": symbols["summary"],
            "sourceFiles": symbols["sourceFiles"],
            "errors": list(symbols["errors"]) + list(bundle["errors"]),
        }

    if kind == "calls":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                nodes.append({"kind": "operation", "name": operation["name"], "file": file_payload["path"]})
                for call in operation["calls"]:
                    edges.append({
                        "kind": "call",
                        "fromOperation": operation["name"],
                        "callName": call["name"],
                        "target": call["target"],
                        "location": call["location"],
                    })
    elif kind == "effects":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                for effect in operation["effects"]:
                    edges.append({
                        "kind": "effect",
                        "operation": operation["name"],
                        "action": effect["action"],
                        "path": effect["path"],
                        "location": effect["location"],
                    })
    elif kind == "capabilities":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                for capability in operation["capabilities"]:
                    edges.append({
                        "kind": "useCapability",
                        "operation": operation["name"],
                        "capability": capability["name"],
                        "location": capability["location"],
                    })
    elif kind == "routes":
        for file_payload in symbols["files"]:
            for route in file_payload["routes"]:
                edges.append({
                    "kind": "route",
                    "method": route["method"],
                    "path": route["path"],
                    "handler": route["handler"],
                    "location": route["location"],
                })
    elif kind == "dataflow":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                edges.append({
                    "kind": "operationDataflow",
                    "operation": operation["name"],
                    "inputs": operation["inputs"],
                    "outputs": operation["outputs"],
                    "calls": operation["calls"],
                    "returns": operation["returns"],
                })
    elif kind == "types":
        for item in bundle["files"]:
            facts = item["facts"]
            for name, fields in sorted(facts.records.items()):
                edges.append({
                    "kind": "record",
                    "name": name,
                    "fields": [{"name": field_name, "type": field_type} for field_name, field_type in fields],
                    "file": str(item["path"].resolve()),
                })
            for result in facts.result_types.values():
                edges.append({
                    "kind": "result",
                    "name": result.name,
                    "okType": result.ok_type,
                    "errorType": result.error_type,
                    "file": str(item["path"].resolve()),
                })
    elif kind == "ownership":
        for item in bundle["files"]:
            entries = _module_narrative_entries(item["facts"])
            if entries:
                edges.append({
                    "kind": "moduleOwnership",
                    "file": str(item["path"].resolve()),
                    "entries": entries,
                })
    else:
        return {
            "schemaVersion": "sem.graph.v1",
            "tool": {"name": "sem", "version": VERSION},
            "kind": kind,
            "inputPath": str(path.resolve()),
            "ok": False,
            "error": f"unsupported graph kind: {kind}",
            "supportedKinds": ["summary", "calls", "effects", "capabilities", "routes", "dataflow", "types", "ownership"],
        }

    return {
        "schemaVersion": "sem.graph.v1",
        "tool": {"name": "sem", "version": VERSION},
        "kind": kind,
        "inputPath": str(path.resolve()),
        "sourceFiles": symbols["sourceFiles"],
        "summary": {
            "edgeCount": len(edges),
            "nodeCount": len(nodes),
            "fileCount": len(symbols["files"]),
        },
        "nodes": nodes,
        "edges": edges,
        "errors": list(symbols["errors"]) + list(bundle["errors"]),
    }


def _find_related_paths(root: Path, needle: str) -> list[str]:
    if not needle:
        return []
    candidates = []
    for pattern in ("**/*test*.py", "**/*.test.sem", "**/*.test.sscript", "**/README.md", "**/*.md"):
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if needle in text:
                candidates.append(str(path.resolve()))
    return sorted(set(candidates))


def _slice_operation_payload(path: Path, operation_name: str) -> dict:
    bundle = _collect_facts_bundle(path)
    symbols = _symbol_graph_payload(path)
    lookup = _facts_operation_lookup(bundle)
    target = lookup.get(operation_name)
    if target is None:
        return {
            "schemaVersion": "sem.slice.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "anchor": {"kind": "operation", "name": operation_name},
            "error": f"unknown operation: {operation_name}",
        }
    source, facts, operation = target
    operation_symbol = _operation_symbol(operation, bundle["semlint"], facts)
    callers = []
    routes = []
    for file_payload in symbols["files"]:
        for candidate in file_payload["operations"]:
            for call in candidate["calls"]:
                if call["target"] == operation_name:
                    callers.append({
                        "operation": candidate["name"],
                        "callName": call["name"],
                        "location": call["location"],
                    })
        for route in file_payload["routes"]:
            if route["handler"] == operation_name:
                routes.append(route)
    narratives = _narrative_entries_for_operation(operation_name, facts)
    project_root = _find_build_tape(path).parent if _find_build_tape(path) is not None else source.parent
    related_tests = _find_related_paths(project_root, operation_name)
    related_docs = _find_related_paths(ROOT.parent / "docs", operation_name)
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "anchor": {"kind": "operation", "name": operation_name},
        "files": [str(source.resolve())],
        "operation": operation_symbol,
        "effects": operation_symbol["effects"],
        "capabilities": operation_symbol["capabilities"],
        "calledOperations": [
            {
                "callName": call["name"],
                "target": call["target"],
                "location": call["location"],
            }
            for call in operation_symbol["calls"]
        ],
        "callers": callers,
        "routes": routes,
        "purposes": narratives["purpose"],
        "invariants": narratives["invariant"],
        "warnings": narratives["warning"],
        "securityNotes": narratives["security"],
        "observabilityNotes": narratives["observability"],
        "relatedTests": related_tests[:20],
        "relatedDocs": related_docs[:20],
    }


def _slice_capability_payload(path: Path, capability_name: str) -> dict:
    symbols = _symbol_graph_payload(path)
    uses = []
    declarations = []
    bundle = _collect_facts_bundle(path)
    for item in bundle["files"]:
        facts = item["facts"]
        capability = facts.capabilities.get(capability_name)
        if capability is not None:
            declarations.append({
                "name": capability.name,
                "effectPath": capability.effect_path,
                "access": capability.access,
                "location": _line_payload(capability.line),
            })
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for capability in operation["capabilities"]:
                if capability["name"] == capability_name:
                    uses.append({
                        "operation": operation["name"],
                        "location": capability["location"],
                    })
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": bool(declarations or uses),
        "anchor": {"kind": "capability", "name": capability_name},
        "declarations": declarations,
        "uses": uses,
    }


def _slice_effect_payload(path: Path, effect_query: str) -> dict:
    symbols = _symbol_graph_payload(path)
    matches = []
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for effect in operation["effects"]:
                effect_name = f"{effect['action']} {effect['path']}"
                if effect_query in effect_name or effect_query == effect["path"]:
                    matches.append({
                        "operation": operation["name"],
                        "action": effect["action"],
                        "path": effect["path"],
                        "location": effect["location"],
                    })
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": bool(matches),
        "anchor": {"kind": "effect", "name": effect_query},
        "matches": matches,
    }


def _slice_type_payload(path: Path, type_name: str) -> dict:
    symbols = _symbol_graph_payload(path)
    bundle = _collect_facts_bundle(path)
    matches = []
    record_fields = []
    result_types = []
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for item in operation["inputs"]:
                if item.get("type") == type_name:
                    matches.append({"kind": "input", "operation": operation["name"], "location": item["location"], "name": item.get("name", "")})
            for item in operation["outputs"]:
                if item.get("type") == type_name:
                    matches.append({"kind": "output", "operation": operation["name"], "location": item["location"]})
            for call in operation["calls"]:
                for argument in call["arguments"]:
                    if argument.get("type") == type_name:
                        matches.append({"kind": "argument", "operation": operation["name"], "callName": call["name"], "location": argument["location"]})
                for bind_list in call["disposition"]["bind"].values():
                    for bind in bind_list:
                        if bind.get("type") == type_name:
                            matches.append({"kind": "bind", "operation": operation["name"], "callName": call["name"], "location": bind["location"], "name": bind["name"]})
    for item in bundle["files"]:
        facts = item["facts"]
        if type_name in facts.records:
            record_fields = [{"name": field_name, "type": field_type} for field_name, field_type in facts.records[type_name]]
        if type_name in facts.result_types:
            result = facts.result_types[type_name]
            result_types.append({"name": result.name, "okType": result.ok_type, "errorType": result.error_type})
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": bool(matches or record_fields or result_types),
        "anchor": {"kind": "type", "name": type_name},
        "uses": matches,
        "recordFields": record_fields,
        "resultTypes": result_types,
    }


def _slice_payload(path: Path, args: argparse.Namespace) -> dict:
    if args.operation:
        return _slice_operation_payload(path, args.operation)
    if args.route:
        method, _, route_path = args.route.partition(":")
        symbols = _symbol_graph_payload(path)
        for file_payload in symbols["files"]:
            for route in file_payload["routes"]:
                if route["method"].upper() == method.upper() and route["path"] == route_path:
                    payload = _slice_operation_payload(path, route["handler"])
                    payload["anchor"] = {"kind": "route", "name": args.route}
                    payload["route"] = route
                    return payload
        return {
            "schemaVersion": "sem.slice.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "anchor": {"kind": "route", "name": args.route},
            "error": f"unknown route: {args.route}",
        }
    if args.symbol:
        return _slice_operation_payload(path, args.symbol)
    if args.effect:
        return _slice_effect_payload(path, args.effect)
    if args.capability:
        return _slice_capability_payload(path, args.capability)
    if args.type_name:
        return _slice_type_payload(path, args.type_name)
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": False,
        "error": "slice requires one of --operation, --route, --symbol, --effect, --capability, or --type",
    }


def _size_payload(path: Path) -> dict:
    bundle = _collect_facts_bundle(path)
    symbols = _symbol_graph_payload(path)
    total_bytes = 0
    total_lines = 0
    helper_counts: dict[str, int] = {}
    source_sizes = []
    for item in bundle["files"]:
        source = item["path"]
        try:
            text = source.read_text(encoding="utf-8")
        except OSError:
            text = ""
        size = len(text.encode("utf-8"))
        line_count = len(text.splitlines())
        total_bytes += size
        total_lines += line_count
        source_sizes.append({
            "path": str(source.resolve()),
            "bytes": size,
            "lines": line_count,
        })
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for call in operation["calls"]:
                target = call["target"]
                family = target.split(".", 1)[0] if "." in target else "local"
                helper_counts[family] = helper_counts.get(family, 0) + 1
    retained_helpers = [
        {"family": family, "callCount": count}
        for family, count in sorted(helper_counts.items())
    ]
    return {
        "schemaVersion": "sem.size.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "summary": {
            "fileCount": len(source_sizes),
            "sourceBytes": total_bytes,
            "sourceLines": total_lines,
            "operationCount": symbols["summary"]["operationCount"],
            "callCount": symbols["summary"]["callCount"],
            "routeCount": symbols["summary"]["routeCount"],
        },
        "sourceFiles": source_sizes,
        "retainedHelpers": retained_helpers,
        "runtimeFeatureFlags": _runtime_feature_flags(),
        "profileBudget": {
            "status": "not-yet-computed",
            "note": "Artifact-size and backend-retention accounting is not yet computed by this wrapper; this payload currently summarizes source and helper-family footprint.",
        },
        "errors": list(bundle["errors"]) + list(symbols["errors"]),
    }


def _runtime_requirements(symbols: dict) -> list[str]:
    families = set()
    for file_payload in symbols["files"]:
        if file_payload["routes"]:
            families.add("nativeHttpRuntime")
        for operation in file_payload["operations"]:
            for effect in operation["effects"]:
                effect_path = effect["path"]
                if effect_path.startswith("http."):
                    families.add("nativeHttpRuntime")
                elif effect_path.startswith("database.") or effect_path.startswith("sqlite."):
                    families.add("nativeSqliteRuntime")
            for call in operation["calls"]:
                target = call["target"]
                if target.startswith("http."):
                    families.add("nativeHttpRuntime")
                elif target.startswith("sqlite."):
                    families.add("nativeSqliteRuntime")
                elif target.startswith("json."):
                    families.add("nativeJsonRuntime")
                elif target.startswith("bcrypt."):
                    families.add("nativeBcryptRuntime")
                elif target.startswith("gui."):
                    families.add("nativeWin32GuiRuntime")
    return sorted(families)


def _readiness_payload(path: Path) -> dict:
    context = _build_context_payload(path)
    symbols = _symbol_graph_payload(path)
    doctor = _doctor_payload()
    checks = {check["name"]: check for check in doctor["checks"]}
    required_runtimes = _runtime_requirements(symbols)
    runtime_flags = context["runtimeFeatureFlags"]
    missing_runtimes = [name for name in required_runtimes if not runtime_flags.get(name, False)]
    blocking_checks = []
    if not checks.get("python", {}).get("ok", False):
        blocking_checks.append("python")
    if not checks.get("llvmlite", {}).get("ok", False):
        blocking_checks.append("llvmlite")
    partial_checks = []
    if not checks.get("clang", {}).get("ok", False):
        partial_checks.append("clang")
    status = "supported"
    if blocking_checks or missing_runtimes:
        status = "blocked"
    elif partial_checks:
        status = "partial"
    return {
        "schemaVersion": "sem.readiness.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "status": status,
        "requestedTargets": list(context["project"].get("targets", [])) or ["host"],
        "requiredRuntimeAdapters": required_runtimes,
        "missingRuntimeAdapters": missing_runtimes,
        "blockingChecks": [
            {
                "name": name,
                "detail": checks.get(name, {}).get("detail", ""),
                "fix": checks.get(name, {}).get("fix", ""),
            }
            for name in blocking_checks
        ],
        "partialChecks": [
            {
                "name": name,
                "detail": checks.get(name, {}).get("detail", ""),
                "fix": checks.get(name, {}).get("fix", ""),
            }
            for name in partial_checks
        ],
        "doctorStatus": doctor["ok"],
        "graphSummary": symbols["summary"],
        "runtimeFeatureFlags": runtime_flags,
        "note": (
            "supported means the wrapper sees no obvious environment or runtime-adapter blockers. "
            "It does not yet guarantee backend-specific artifact emission for every target."
        ),
    }


def _interface_fingerprints(path: Path) -> dict:
    bundle = _collect_facts_bundle(path)
    module_hashes = []
    for item in bundle["files"]:
        module_hashes.append({
            "path": str(item["path"].resolve()),
            "sha256": _file_sha256(item["path"]),
        })
    hasher = hashlib.sha256()
    for module in module_hashes:
        hasher.update(module["path"].encode("utf-8"))
        hasher.update(module["sha256"].encode("utf-8"))
    return {
        "algorithm": "sha256-sem-interface-v1",
        "projectHash": hasher.hexdigest(),
        "modules": module_hashes,
    }


def _dev_payload(path: Path, trace: bool) -> dict:
    context = _build_context_payload(path)
    readiness = _readiness_payload(path)
    symbols = _symbol_graph_payload(path)
    rerun = ["check", "test", "graph"]
    restart_on_success = symbols["summary"]["routeCount"] > 0
    watch_files = list(context["sourceFiles"])
    if context["project"].get("buildTape"):
        watch_files.append(context["project"]["buildTape"])
    watch_files = sorted(set(watch_files))
    return {
        "schemaVersion": "sem.dev.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "mode": "watch-plan",
        "inputPath": str(path.resolve()),
        "watch": {
            "planOnly": True,
            "files": watch_files,
            "rerun": rerun,
            "restartOnSuccess": restart_on_success,
        },
        "restart": {
            "runnableCli": restart_on_success,
            "reason": "routes detected in project graph" if restart_on_success else "no route-hosting surface detected",
        },
        "trace": {
            "enabled": True,
            "requested": bool(trace),
            "phaseTiming": bool(trace),
            "cacheFacts": bool(trace),
            "diagnosticsPassthrough": True,
        },
        "interfaceFingerprints": _interface_fingerprints(path),
        "targetReadiness": readiness,
        "actions": [
            {"kind": "check", "command": f"sem check --json {path}"},
            {"kind": "test", "command": f"sem test --json {path}"},
            {"kind": "graph", "command": f"sem graph --kind calls --json {path}"},
            {"kind": "restart", "enabled": restart_on_success},
        ],
    }


def _discover_test_entries(path: Path) -> list[dict]:
    requested = path.resolve()
    build_tape = _find_build_tape(path)
    if requested.is_file() and requested.suffix.lower() in {".sem", ".sscript"} and ".test." in requested.name:
        return [{"kind": "semantic", "path": requested, "name": requested.stem}]
    roots = []
    if build_tape is not None:
        roots.append(build_tape.parent.resolve())
    elif requested.is_dir():
        roots.append(requested)
    else:
        roots.append(requested.parent)
    discovered = []
    seen = set()
    for root in roots:
        for pattern, kind in (
            ("**/*.test.sem", "semantic"),
            ("**/*.test.sscript", "semantic"),
            ("**/build.test.sem", "semantic"),
            ("**/scripts/test_*.py", "python"),
            ("**/tests/test_*.py", "python"),
        ):
            for candidate in root.glob(pattern):
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                discovered.append({"kind": kind, "path": resolved, "name": resolved.stem})
    return sorted(discovered, key=lambda item: (item["kind"], str(item["path"]).lower()))


def _run_test_payload(path: Path, include_python_harnesses: bool = True) -> dict:
    discovered = _discover_test_entries(path)
    results = []
    passed = 0
    failed = 0
    skipped = 0
    for entry in discovered:
        start = time.time()
        if entry["kind"] == "semantic":
            payload = _build_check_payload(entry["path"], [])
            ok = bool(payload["ok"])
            duration_ms = int((time.time() - start) * 1000)
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "path": str(entry["path"]),
                "status": "passed" if ok else "failed",
                "durationMs": duration_ms,
                "summary": payload["summary"],
            })
            if ok:
                passed += 1
            else:
                failed += 1
            continue
        if entry["kind"] == "python" and not include_python_harnesses:
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "path": str(entry["path"]),
                "status": "skipped",
                "reason": "python harness execution disabled",
            })
            skipped += 1
            continue
        proc = subprocess.run(
            [sys.executable, str(entry["path"])],
            cwd=str(ROOT.parent),
            capture_output=True,
            text=True,
            timeout=600,
        )
        duration_ms = int((time.time() - start) * 1000)
        ok = proc.returncode == 0
        results.append({
            "name": entry["name"],
            "kind": entry["kind"],
            "path": str(entry["path"]),
            "status": "passed" if ok else "failed",
            "durationMs": duration_ms,
            "stdoutSnippet": proc.stdout[:2000],
            "stderrSnippet": proc.stderr[:2000],
        })
        if ok:
            passed += 1
        else:
            failed += 1
    return {
        "schemaVersion": "sem.test.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "ok": failed == 0,
        "discoveredTests": len(discovered),
        "selectedTests": len(discovered),
        "passedTests": passed,
        "failedTests": failed,
        "skippedTests": skipped,
        "results": results,
    }


def _skill_registry_payload() -> list[dict]:
    payload = []
    for entry in SKILL_REGISTRY:
        files = [str((ROOT.parent / relative).resolve()) for relative in entry["files"]]
        payload.append({
            "name": entry["name"],
            "description": entry["description"],
            "files": files,
        })
    return payload


def _skill_content(name: str) -> dict | None:
    for entry in SKILL_REGISTRY:
        if entry["name"] != name:
            continue
        sections = []
        for relative in entry["files"]:
            path = ROOT.parent / relative
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            sections.append(f"# Source: {relative}\n\n{text.strip()}\n")
        return {
            "name": entry["name"],
            "description": entry["description"],
            "files": [str((ROOT.parent / relative).resolve()) for relative in entry["files"]],
            "content": "\n".join(sections).strip() + ("\n" if sections else ""),
        }
    return None


def _diagnostic_index_payload() -> dict[str, dict]:
    index: dict[str, dict] = {
        "SSRUN001": {
            "code": "SSRUN001",
            "title": "runtime panic",
            "summary": "The program trapped with SemanticScript runtime panic context.",
            "references": [],
            "relatedCodes": [],
        }
    }
    comment_pattern = re.compile(r"#\s*((?:SS(?:RUN)?\d{4,5})(?:\s*/\s*SS(?:RUN)?\d{4,5})*)\s+(.*)")
    code_pattern = re.compile(r"SS(?:RUN)?\d{4,5}")
    for relative in DIAGNOSTIC_INDEX_PATHS:
        path = ROOT.parent / relative
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for index_line, line in enumerate(lines, start=1):
            matches = code_pattern.findall(line)
            if not matches:
                continue
            title = ""
            comment_match = comment_pattern.match(line.strip())
            if comment_match:
                title = comment_match.group(2).strip()
                title = re.sub(r"\s+\(.*$", "", title).strip()
            excerpt = line.strip()
            for code in matches:
                entry = index.setdefault(code, {
                    "code": code,
                    "title": title or code,
                    "summary": title or code,
                    "references": [],
                    "relatedCodes": [],
                })
                if title and entry.get("title", code) == code:
                    entry["title"] = title
                    entry["summary"] = title
                entry["references"].append({
                    "path": str(path.resolve()),
                    "line": index_line,
                    "excerpt": excerpt,
                })
                related = [item for item in matches if item != code]
                if related:
                    current = set(entry.get("relatedCodes", []))
                    current.update(related)
                    entry["relatedCodes"] = sorted(current)
    return index


def _diagnostic_explain_payload(code: str) -> dict:
    index = _diagnostic_index_payload()
    entry = index.get(code)
    curated = DIAGNOSTIC_EXPLAINERS.get(code, {})
    if entry is None:
        return {
            "schemaVersion": "sem.explain.v1",
            "tool": {"name": "sem", "version": VERSION},
            "code": code,
            "found": False,
            "title": curated.get("title", ""),
            "summary": curated.get("summary", ""),
            "references": [],
            "relatedCodes": [],
            "whyItMatters": curated.get("whyItMatters", []),
            "commonFixes": curated.get("commonFixes", []),
        }
    return {
        "schemaVersion": "sem.explain.v1",
        "tool": {"name": "sem", "version": VERSION},
        "code": code,
        "found": True,
        "title": curated.get("title", entry.get("title", code)),
        "summary": curated.get("summary", entry.get("summary", entry.get("title", code))),
        "references": entry.get("references", []),
        "relatedCodes": entry.get("relatedCodes", []),
        "whyItMatters": curated.get("whyItMatters", []),
        "commonFixes": curated.get("commonFixes", []),
        "note": "This is a repository-backed explainer built from the current docs and linter tests. Use the cited sources for full rule context.",
    }


def _operation_insert_anchor(operation) -> int:
    line_numbers = [
        source_line.number
        for source_line in operation.lines
        if source_line.tokens
        and source_line.verb in {
            "input",
            "output",
            "effect",
            "useCapability",
            "authority",
            "memory",
            "async",
            "purpose",
            "invariant",
        }
    ]
    return max(line_numbers) if line_numbers else operation.line.number


def _repair_plan_for_diagnostic(path: Path, diagnostic: dict, bundle: dict) -> dict:
    lookup = _facts_operation_lookup(bundle)
    code = diagnostic.get("code", "")
    subject_name = diagnostic.get("subjectName", "")
    subject_kind = diagnostic.get("subjectKind", "")
    fix_candidates = list(diagnostic.get("fixCandidates", []))
    repair = {
        "diagnostic": code,
        "kind": diagnostic.get("kind", ""),
        "subjectName": subject_name,
        "subjectKind": subject_kind,
        "fixSafety": diagnostic.get("repair", {}).get("fixSafety", "requires-human-review"),
        "edits": [],
        "suggestions": [
            {
                "name": candidate.get("name", ""),
                "shape": candidate.get("shape", ""),
                "autoApplicable": bool(candidate.get("autoApplicable", False)),
            }
            for candidate in fix_candidates
        ],
        "verification": [
            f"sem check --json {path}",
            f"sem fmt --check {path}",
        ],
    }
    operation_entry = lookup.get(subject_name)
    if operation_entry is None and subject_kind == "operation":
        return repair
    if code == "SS3104" and operation_entry is not None:
        source, _facts, operation = operation_entry
        for source_line in operation.lines:
            if not source_line.tokens or source_line.verb != "effect":
                continue
            args = source_line.args
            if len(args) >= 3 and args[0] == subject_name:
                repair["edits"].append({
                    "op": "insertAfterLine",
                    "file": str(source.resolve()),
                    "afterLine": _operation_insert_anchor(operation),
                    "text": f"authority {subject_name} {args[1]} {args[2]}",
                })
                break
    elif code == "SS3101" and operation_entry is not None:
        source, _facts, operation = operation_entry
        repair["fixSafety"] = "requires-human-review"
        repair["edits"].append({
            "op": "insertAfterLine",
            "file": str(source.resolve()),
            "afterLine": _operation_insert_anchor(operation),
            "text": f'purpose operation {subject_name} "<describe {subject_name} purpose>"',
        })
    elif code == "SS3102" and operation_entry is not None:
        source, _facts, operation = operation_entry
        repair["fixSafety"] = "requires-human-review"
        repair["edits"].append({
            "op": "insertAfterLine",
            "file": str(source.resolve()),
            "afterLine": _operation_insert_anchor(operation),
            "text": f'invariant operation {subject_name} "<state the key invariant for {subject_name}>"',
        })
    return repair


def _build_fix_plan_payload(path: Path, compiler_args: list[str]) -> dict:
    check_payload = _build_check_payload(path, compiler_args)
    bundle = _collect_facts_bundle(path)
    file_hashes = {}
    for item in bundle["files"]:
        file_hashes[str(item["path"].resolve())] = _file_sha256(item["path"])
    repairs = [
        _repair_plan_for_diagnostic(path.resolve(), diagnostic, bundle)
        for diagnostic in check_payload["diagnostics"]
        if diagnostic.get("repair", {}).get("id") or diagnostic.get("code") in {"SS3101", "SS3102", "SS3104"}
    ]
    return {
        "schemaVersion": "sem.fixPlan.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "ok": True,
        "diagnosticCount": len(check_payload["diagnostics"]),
        "repairCount": len(repairs),
        "repairs": repairs,
        "preconditions": {
            "fileHashes": file_hashes,
        },
        "checkSummary": check_payload["summary"],
    }


def _load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_insert_after_line(lines: list[str], after_line: int, text: str) -> list[str]:
    new_lines = list(lines)
    insertion_index = max(0, min(len(new_lines), int(after_line)))
    new_lines[insertion_index:insertion_index] = [text + "\n"]
    return new_lines


def _apply_replace_line(lines: list[str], line_number: int, text: str) -> list[str]:
    new_lines = list(lines)
    index = max(0, min(len(new_lines) - 1, int(line_number) - 1))
    new_lines[index] = text + "\n"
    return new_lines


def _execute_patch_plan(plan: dict, mode: str) -> dict:
    file_hashes = dict(plan.get("preconditions", {}).get("fileHashes", {}))
    stale = []
    for file_name, expected_hash in sorted(file_hashes.items()):
        current_hash = _file_sha256(Path(file_name))
        if expected_hash and current_hash and expected_hash != current_hash:
            stale.append({
                "file": file_name,
                "expectedHash": expected_hash,
                "actualHash": current_hash,
            })
    if stale:
        return {
            "schemaVersion": "sem.patch.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "mode": mode,
            "error": "patch precondition failed; one or more target files changed since the plan was generated",
            "staleFiles": stale,
            "filesChanged": [],
            "editCount": 0,
            "verification": {"formatOk": None, "checkOk": None, "checkSummary": {}},
        }
    changed_files = {}
    for repair in plan.get("repairs", []):
        for edit in repair.get("edits", []):
            target = Path(edit["file"]).resolve()
            current = changed_files.get(target)
            if current is None:
                current = target.read_text(encoding="utf-8").splitlines(keepends=True)
            if edit.get("op") == "insertAfterLine":
                current = _apply_insert_after_line(current, int(edit.get("afterLine", 0)), edit.get("text", ""))
            elif edit.get("op") == "replaceLine":
                current = _apply_replace_line(current, int(edit.get("line", 1)), edit.get("text", ""))
            changed_files[target] = current

    if mode == "apply":
        for target, lines in changed_files.items():
            target.write_text("".join(lines), encoding="utf-8", newline="\n")
        if changed_files:
            semfmt_path = ROOT / "formatter" / "semfmt.py"
            subprocess.run(
                [sys.executable, str(semfmt_path), *[str(path) for path in changed_files]],
                check=False,
                capture_output=True,
                text=True,
            )

    verification = {"formatOk": True, "checkOk": None, "checkSummary": {}}
    if mode == "apply":
        input_path = Path(plan.get("inputPath", Path.cwd()))
        check_payload = _build_check_payload(input_path, [])
        verification["checkOk"] = bool(check_payload.get("ok", False))
        verification["checkSummary"] = check_payload.get("summary", {})
    return {
        "schemaVersion": "sem.patch.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "mode": mode,
        "filesChanged": [str(path) for path in sorted(changed_files, key=lambda item: str(item).lower())],
        "editCount": sum(len(repair.get("edits", [])) for repair in plan.get("repairs", [])),
        "verification": verification,
    }


def _parse_trace_events(stderr_text: str) -> tuple[list[dict], str]:
    events = []
    non_trace_lines = []
    for line in stderr_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            non_trace_lines.append(line)
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            non_trace_lines.append(line)
            continue
        if event.get("schemaVersion") == "sem.traceEvent.v0":
            events.append(event)
        else:
            non_trace_lines.append(line)
    return events, "\n".join(non_trace_lines)


def _counter_dict(items):
    counts = {}
    for item in items:
        key = item or ""
        counts[key] = counts.get(key, 0) + 1
    return counts


def _profile_from_trace(source: Path, proc: subprocess.CompletedProcess,
                        events: list[dict], duration_ns: int,
                        inspect_payload: dict | None = None) -> dict:
    operations = _counter_dict(
        event.get("operation")
        for event in events
        if event.get("event") == "op.enter")
    calls = _counter_dict(
        f"{event.get('operation')}::{event.get('name')}->{event.get('target')}"
        for event in events
        if event.get("event") == "call.start")
    branches = _counter_dict(
        f"{event.get('operation')}::{event.get('name')}->{event.get('target')}"
        for event in events
        if event.get("event") == "branch.decision")
    returns = _counter_dict(
        f"{event.get('operation')}::{event.get('name')}:{event.get('valueStatus')}"
        for event in events
        if event.get("event") == "return.value")
    source_info = {}
    build_info = {}
    trace_map_info = {}
    if inspect_payload:
        source_info = inspect_payload.get("source", {})
        build_info = inspect_payload.get("build", {})
        trace_map_info = {
            "schemaVersion": inspect_payload.get("traceMap", {}).get("schemaVersion", ""),
            "siteCount": len(inspect_payload.get("traceMap", {}).get("sites", [])),
        }
    return {
        "schemaVersion": "sem.profile.v0",
        "tool": {"name": "sem", "version": VERSION},
        "source": {
            "path": str(source.resolve()),
            "fingerprint": source_info.get("fingerprint", ""),
        },
        "build": {
            "fingerprint": build_info.get("fingerprint", ""),
            "profile": build_info.get("profile", ""),
            "runtimeChecks": build_info.get("runtimeChecks", ""),
            "optLevel": build_info.get("optLevel", None),
        },
        "traceMap": trace_map_info,
        "run": {
            "returnCode": proc.returncode,
            "durationNs": duration_ns,
            "wallTimeNs": duration_ns,
            "startupTimeNs": 0,
            "startupTimeSource": "notSeparatedForJitDriver",
            "stdoutBytes": len(proc.stdout.encode("utf-8")),
            "stderrBytes": len(proc.stderr.encode("utf-8")),
            "traceEventCount": len(events),
        },
        "hot": {
            "operations": operations,
            "calls": calls,
            "branches": branches,
            "returns": returns,
            "runtimeExternalCalls": _counter_dict(
                event.get("target")
                for event in events
                if event.get("event") == "call.start"
                and str(event.get("target", "")).startswith((
                    "http.", "sqlite.", "json.", "gui.", "bcrypt.", "c."))),
        },
        "http": {
            "requestCount": 0,
            "note": "HTTP request tracing is runtime-adapter work; no request loop was observed by this run.",
        },
        "measurement": {
            "traceInstrumentation": "enabled",
            "profileSource": "aggregatedTraceEvents",
            "overheadWarning": "Trace instrumentation changes runtime cost; compare profiles against profiles, not raw non-traced runs.",
        },
    }


def _inspect_payload(source: Path, compiler_args: list[str]) -> dict | None:
    proc = _capture_compiler(source, ["--inspect-ir", *compiler_args])
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _parse_runtime_panic(stderr_text: str) -> dict:
    lines = stderr_text.splitlines()
    panic_index = next(
        (idx for idx, line in enumerate(lines)
         if "SSRUN001" in line and "runtime panic" in line),
        None)
    if panic_index is None:
        return {}
    block = lines[panic_index:]
    result = {"code": "SSRUN001", "raw": "\n".join(block)}
    current_section = ""
    for line in block:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith(("file:", "line:", "operation:", "call:", "reason:", "status:")):
            current_section = stripped[:-1].lower()
            continue
        if stripped.startswith("reason:"):
            result["reason"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("status:"):
            result["status"] = stripped.split(":", 1)[1].strip()
        elif current_section == "location" and stripped.startswith("file:"):
            result["file"] = stripped.split(":", 1)[1].strip()
        elif current_section == "location" and stripped.startswith("line:"):
            raw_line = stripped.split(":", 1)[1].strip()
            try:
                result["line"] = int(raw_line)
            except ValueError:
                result["line"] = raw_line
        elif current_section == "location" and stripped.startswith("operation:"):
            result["operation"] = stripped.split(":", 1)[1].strip()
        elif current_section == "location" and stripped.startswith("call:"):
            result["call"] = stripped.split(":", 1)[1].strip()
        elif current_section == "source" and "|" in stripped:
            result["sourceRow"] = stripped
        elif current_section == "direction":
            result.setdefault("direction", stripped)
    return result


def _explain_crash(source: Path, compiler_args: list[str]) -> int:
    inspect = _inspect_payload(source, compiler_args)
    artifact_dir = _artifact_run_dir(source, "crash")
    exe_path = artifact_dir / ("sem-crash.exe" if os.name == "nt" else "sem-crash")
    trace_map_path = artifact_dir / "trace-map.json"
    trace_events_path = artifact_dir / "trace-events.jsonl"
    crash_report_path = artifact_dir / "crash.json"
    artifact_index_path = artifact_dir / "artifact-index.json"
    compile_args = [
        "--trace",
        "--emit-exe", str(exe_path),
        "--emit-trace-map", str(trace_map_path),
        "--build-dir", str(artifact_dir / "build"),
        "--quiet",
        *compiler_args,
    ]
    compile_proc = _capture_compiler(source, compile_args, timeout=300)
    common_artifacts = {
        "artifactDir": str(artifact_dir),
        "artifactIndexPath": str(artifact_index_path),
        "crashReportPath": str(crash_report_path),
        "traceMapPath": str(trace_map_path) if trace_map_path.exists() else "",
        "traceEventsPath": str(trace_events_path),
        "executablePath": str(exe_path),
    }
    if compile_proc.returncode != 0 or not exe_path.exists():
        payload = {
            "schemaVersion": "sem.crash.v0",
            "tool": {"name": "sem", "version": VERSION},
            "phase": "compile",
            "source": {"path": str(source.resolve())},
            "compile": {
                "returnCode": compile_proc.returncode,
                "stdout": compile_proc.stdout,
                "stderr": compile_proc.stderr,
            },
            "suspectedCategory": "compileFailure",
            "fixCandidates": [
                "Inspect compiler diagnostics before runtime crash analysis.",
                "Run sem inspect-ir to verify source-to-LLVM lowering context.",
            ],
            "artifacts": common_artifacts,
        }
        _write_json_artifact(crash_report_path, payload)
        _write_json_artifact(artifact_index_path, {
            "schemaVersion": "sem.artifactIndex.v0",
            "tool": {"name": "sem", "version": VERSION},
            "kind": "crash",
            "phase": "compile",
            "source": payload["source"],
            "artifacts": common_artifacts,
        })
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    start = time.perf_counter_ns()
    run_proc = subprocess.run([str(exe_path)], capture_output=True, text=True)
    duration_ns = time.perf_counter_ns() - start
    events, non_trace_stderr = _parse_trace_events(run_proc.stderr)
    trace_events_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8", newline="\n")
    panic = _parse_runtime_panic(non_trace_stderr)
    compiler_args_text = " ".join(compiler_args)
    build_profile = "prod" if "--build-profile prod" in compiler_args_text else "dev"
    runtime_checks = "panic"
    if "--runtime-checks off" in compiler_args_text:
        runtime_checks = "off"
    elif "--runtime-checks traps" in compiler_args_text or build_profile == "prod":
        runtime_checks = "traps"
    last_event = events[-1] if events else {}
    context_operation = (
        panic.get("operation")
        or last_event.get("operation")
        or ""
    )
    route_contexts = [
        {
            "server": route.get("server", ""),
            "method": route.get("method", ""),
            "path": route.get("path", ""),
            "handler": route.get("handler", ""),
            "siteId": route.get("siteId", ""),
        }
        for route in (inspect or {}).get("routes", [])
        if route.get("handler") == context_operation
    ]
    payload = {
        "schemaVersion": "sem.crash.v0",
        "tool": {"name": "sem", "version": VERSION},
        "phase": "run",
        "source": {
            "path": str(source.resolve()),
            "fingerprint": (inspect or {}).get("source", {}).get("fingerprint", ""),
        },
        "build": {
            "fingerprint": (inspect or {}).get("build", {}).get("fingerprint", ""),
            "profile": build_profile,
            "runtimeChecks": runtime_checks,
        },
        "run": {
            "returnCode": run_proc.returncode,
            "durationNs": duration_ns,
            "stdout": run_proc.stdout,
            "stderrNonTrace": non_trace_stderr,
        },
        "panic": panic,
        "semanticContext": {
            "operation": context_operation,
            "call": panic.get("call", ""),
            "routes": route_contexts,
            "lastEvent": last_event,
        },
        "lastTraceEvents": events[-20:],
        "suspectedCategory": (
            "runtimePanic" if panic.get("code") == "SSRUN001"
            else "nativeTrap" if run_proc.returncode != 0
            else "noCrash"),
        "fixCandidates": [
            "Patch the SemanticScript source row named by panic.sourceRow or the last trace event.",
            "Use sem inspect-ir to inspect the operation, call, and LLVM block mapping.",
            "If this is prod/traps mode, rerun with --build-profile dev --runtime-checks panic for source context.",
        ],
        "artifacts": common_artifacts,
    }
    _write_json_artifact(crash_report_path, payload)
    _write_json_artifact(artifact_index_path, {
        "schemaVersion": "sem.artifactIndex.v0",
        "tool": {"name": "sem", "version": VERSION},
        "kind": "crash",
        "phase": "run",
        "source": payload["source"],
        "build": payload["build"],
        "artifacts": common_artifacts,
        "suspectedCategory": payload["suspectedCategory"],
    })
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if run_proc.returncode != 0 else 1


def command_build(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    if build_tape is None:
        print(f"sem: no build.sem found from {args.path}", file=sys.stderr)
        return 2

    compiler_args = _strip_separator(list(args.compiler_args))
    if not _has_compiler_action(compiler_args):
        compiler_args = ["--emit-exe", *compiler_args]
    return _run_compiler(build_tape, compiler_args)


def command_run(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    compiler_args = _strip_separator(list(args.compiler_args))
    trace, compiler_args = _extract_flag(compiler_args, "--trace")
    profile, compiler_args = _extract_flag(compiler_args, "--profile")
    json_output, compiler_args = _extract_flag(compiler_args, "--json")
    explain_crash, compiler_args = _extract_flag(compiler_args, "--explain-crash")
    trace = trace or bool(getattr(args, "trace", False))
    profile = profile or bool(getattr(args, "profile", False))
    json_output = json_output or bool(getattr(args, "json", False))
    explain_crash = explain_crash or bool(getattr(args, "explain_crash", False))

    if explain_crash:
        return _explain_crash(source, compiler_args)

    if profile:
        artifact_dir = _artifact_run_dir(source, "profile")
        profile_path = artifact_dir / "profile.json"
        trace_events_path = artifact_dir / "trace-events.jsonl"
        inspect_ir_path = artifact_dir / "inspect-ir.json"
        artifact_index_path = artifact_dir / "artifact-index.json"
        inspect = _inspect_payload(source, compiler_args)
        run_args = ["--run", "--trace", *compiler_args]
        start = time.perf_counter_ns()
        proc = _capture_compiler(source, run_args)
        duration_ns = time.perf_counter_ns() - start
        events, non_trace_stderr = _parse_trace_events(proc.stderr)
        if proc.returncode != 0 and not events:
            payload = {
                "schemaVersion": "sem.profileFailure.v0",
                "tool": {"name": "sem", "version": VERSION},
                "phase": "compile",
                "source": {
                    "path": str(source.resolve()),
                    "fingerprint": (inspect or {}).get("source", {}).get("fingerprint", ""),
                },
                "build": {
                    "fingerprint": (inspect or {}).get("build", {}).get("fingerprint", ""),
                    "profile": (inspect or {}).get("build", {}).get("profile", ""),
                    "runtimeChecks": (inspect or {}).get("build", {}).get("runtimeChecks", ""),
                },
                "compile": {
                    "returnCode": proc.returncode,
                    "durationNs": duration_ns,
                    "stdout": proc.stdout,
                    "stderr": non_trace_stderr,
                },
                "suspectedCategory": "compileFailure",
                "fixCandidates": [
                    "Inspect compiler diagnostics before profile analysis.",
                    "Run sem inspect-ir to verify source-to-LLVM lowering context.",
                    "Do not treat this payload as a performance profile.",
                ],
                "artifacts": {
                    "artifactDir": str(artifact_dir),
                    "artifactIndexPath": str(artifact_index_path),
                    "profilePath": str(profile_path),
                    "traceEventsPath": str(trace_events_path),
                    "inspectIrPath": str(inspect_ir_path) if inspect is not None else "",
                },
            }
            trace_events_path.write_text("", encoding="utf-8", newline="\n")
            if inspect is not None:
                _write_json_artifact(inspect_ir_path, inspect)
            _write_json_artifact(profile_path, payload)
            _write_json_artifact(artifact_index_path, {
                "schemaVersion": "sem.artifactIndex.v0",
                "tool": {"name": "sem", "version": VERSION},
                "kind": "profileFailure",
                "phase": "compile",
                "source": payload["source"],
                "build": payload["build"],
                "artifacts": payload["artifacts"],
                "suspectedCategory": payload["suspectedCategory"],
            })
            print(json.dumps(payload, indent=2, sort_keys=True))
            return proc.returncode
        payload = _profile_from_trace(source, proc, events, duration_ns, inspect)
        payload["artifacts"] = {
            "artifactDir": str(artifact_dir),
            "artifactIndexPath": str(artifact_index_path),
            "profilePath": str(profile_path),
            "traceEventsPath": str(trace_events_path),
            "inspectIrPath": str(inspect_ir_path) if inspect is not None else "",
        }
        payload["optimizationLoop"] = {
            "schemaVersion": "sem.optimizationLoop.v0",
            "steps": [
                "inspect-ir",
                "profile-baseline",
                "patch-source",
                "check-and-test",
                "profile-candidate",
                "compare-profile-delta",
            ],
            "comparisonKey": payload.get("build", {}).get("fingerprint", ""),
            "deltaFields": [
                "run.durationNs",
                "run.traceEventCount",
                "hot.operations",
                "hot.calls",
                "hot.branches",
                "hot.runtimeExternalCalls",
            ],
        }
        trace_events_path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
            encoding="utf-8", newline="\n")
        if inspect is not None:
            _write_json_artifact(inspect_ir_path, inspect)
        _write_json_artifact(profile_path, payload)
        index_payload = {
            "schemaVersion": "sem.artifactIndex.v0",
            "tool": {"name": "sem", "version": VERSION},
            "kind": "profile",
            "source": payload.get("source", {}),
            "build": payload.get("build", {}),
            "artifacts": payload["artifacts"],
            "comparisonKey": payload["optimizationLoop"]["comparisonKey"],
        }
        _write_json_artifact(artifact_index_path, index_payload)
        # Profile mode is an agent surface. Keep stdout as the JSON report and
        # embed application stdout/stderr sizes instead of interleaving streams.
        print(json.dumps(payload, indent=2, sort_keys=True))
        if non_trace_stderr:
            print(non_trace_stderr, file=sys.stderr)
        return proc.returncode

    run_args = ["--run"]
    if trace:
        run_args.append("--trace")
    run_args.extend(compiler_args)
    return _run_compiler(source, run_args)


def command_check(args: argparse.Namespace) -> int:
    if getattr(args, "json", False):
        payload = _build_check_payload(Path(args.path), _strip_separator(list(args.compiler_args)))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--parse-only", "--lint", *_strip_separator(list(args.compiler_args))])


def command_emit_ir(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--emit-ir", *_strip_separator(list(args.compiler_args))])


def command_clean(args: argparse.Namespace) -> int:
    if args.all_ignored:
        mode = "-Xdf" if args.force else "-Xdn"
        pathspecs = list(args.paths) or ["."]
        command = ["git", "clean", mode, "--", *pathspecs]
        return subprocess.call(command)
    try:
        repo_root, targets = _collect_clean_targets(list(args.paths))
        if not targets:
            print("sem clean: no ignored SemanticScript build artifacts found")
            return 0
        for target in targets:
            prefix = "Removing" if args.force else "Would remove"
            print(f"{prefix} {_format_clean_target(target, repo_root)}")
        if not args.force:
            print("sem clean: dry run; pass --force to remove listed artifacts")
            return 0
        for target in sorted(targets, key=lambda item: len(item.parts), reverse=True):
            _remove_clean_target(target, repo_root)
        return 0
    except (OSError, ValueError) as exc:
        print(f"sem clean: {exc}", file=sys.stderr)
        return 2


def command_inspect_ir(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--inspect-ir", *_strip_separator(list(args.compiler_args))])


def command_lint(args: argparse.Namespace) -> int:
    if args.engine != "semlint":
        print(f"sem lint: unsupported engine {args.engine}", file=sys.stderr)
        return 2
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    semlint_path = ROOT / "linter" / "semlint.py"
    command = [
        sys.executable,
        str(semlint_path),
        str(source),
        *_strip_separator(list(args.linter_args)),
    ]
    return subprocess.call(command)


def command_fmt(args: argparse.Namespace) -> int:
    semfmt_path = ROOT / "formatter" / "semfmt.py"
    formatter_args = _strip_separator(list(args.formatter_args))
    if args.check and "--check" not in formatter_args:
        formatter_args.insert(0, "--check")
    if args.diff and "--diff" not in formatter_args:
        formatter_args.insert(0, "--diff")
    if args.paths:
        formatter_args.extend(args.paths)
    elif not formatter_args:
        formatter_args.append(".")
    command = [sys.executable, str(semfmt_path), *formatter_args]
    return subprocess.call(command)


def command_compare_profiles(args: argparse.Namespace) -> int:
    payload = _profile_delta_payload(Path(args.baseline), Path(args.candidate))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_bench(args: argparse.Namespace) -> int:
    bench_script = ROOT / "bench" / "run_benchmarks.py"
    command = [sys.executable, str(bench_script)]
    if args.json:
        command.append("--json")
    if args.runs is not None:
        command.extend(["--runs", str(args.runs)])
    if args.warmup is not None:
        command.extend(["--warmup", str(args.warmup)])
    for name in args.benchmark:
        command.extend(["--benchmark", name])
    return subprocess.call(command)


def command_doctor(args: argparse.Namespace) -> int:
    payload = _doctor_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in payload["checks"]:
            status = "ok" if check["ok"] else "missing"
            print(f"{status:7} {check['name']}: {check['detail']}")
            if not check["ok"] and check["fix"]:
                print(f"        fix: {check['fix']}")
    return 0 if payload["ok"] else 1


def command_version(args: argparse.Namespace) -> int:
    payload = _version_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"sem {VERSION}")
    return 0


def command_readiness(args: argparse.Namespace) -> int:
    payload = _readiness_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"status: {payload['status']}")
        print(f"targets: {', '.join(payload['requestedTargets'])}")
        if payload["blockingChecks"]:
            print("blocking:")
            for check in payload["blockingChecks"]:
                print(f"- {check['name']}: {check['detail']}")
        if payload["partialChecks"]:
            print("partial:")
            for check in payload["partialChecks"]:
                print(f"- {check['name']}: {check['detail']}")
    return 0 if payload["status"] != "blocked" else 1


def command_context(args: argparse.Namespace) -> int:
    payload = _build_context_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    project = payload["project"]
    print(f"project root: {project.get('projectRoot') or '(single file)'}")
    print(f"build tape: {project.get('buildTape') or '(none)'}")
    print(f"source files: {len(payload['sourceFiles'])}")
    print("use --json for machine-readable context")
    return 0


def command_symbols(args: argparse.Namespace) -> int:
    payload = _symbol_graph_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not payload["errors"] else 1
    summary = payload["summary"]
    print(f"files: {summary['fileCount']}")
    print(f"operations: {summary['operationCount']}")
    print(f"calls: {summary['callCount']}")
    print(f"routes: {summary['routeCount']}")
    print(f"unresolved references: {summary['unresolvedReferenceCount']}")
    print("use --json for machine-readable symbol graph")
    return 0 if not payload["errors"] else 1


def command_size(args: argparse.Namespace) -> int:
    payload = _size_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not payload.get("errors") else 1
    summary = payload["summary"]
    print(f"files: {summary['fileCount']}")
    print(f"source bytes: {summary['sourceBytes']}")
    print(f"operations: {summary['operationCount']}")
    print(f"calls: {summary['callCount']}")
    print("use --json for machine-readable size output")
    return 0 if not payload.get("errors") else 1


def command_dev(args: argparse.Namespace) -> int:
    payload = _dev_payload(Path(args.path), bool(args.trace))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print("watch plan only; use --json for machine-readable agent workflow facts")
    print(f"watch files: {len(payload['watch']['files'])}")
    print(f"rerun: {', '.join(payload['watch']['rerun'])}")
    return 0


def command_test(args: argparse.Namespace) -> int:
    payload = _run_test_payload(Path(args.path), include_python_harnesses=not args.skip_python_harnesses)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"discovered: {payload['discoveredTests']}")
        print(f"passed: {payload['passedTests']}")
        print(f"failed: {payload['failedTests']}")
        print(f"skipped: {payload['skippedTests']}")
    return 0 if payload["ok"] else 1


def command_graph(args: argparse.Namespace) -> int:
    payload = _graph_payload(Path(args.path), args.kind)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("ok", True) and not payload.get("errors") else 1
    summary = payload.get("summary", {})
    print(f"kind: {payload.get('kind', '')}")
    print(f"files: {summary.get('fileCount', 0)}")
    print(f"edges: {summary.get('edgeCount', 0)}")
    print("use --json for machine-readable graph output")
    return 0 if payload.get("ok", True) and not payload.get("errors") else 1


def command_slice(args: argparse.Namespace) -> int:
    payload = _slice_payload(Path(args.path), args)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("ok") else 1
    anchor = payload.get("anchor", {})
    print(f"anchor: {anchor.get('kind', '')} {anchor.get('name', '')}")
    if payload.get("operation"):
        operation = payload["operation"]
        print(f"operation: {operation.get('name', '')}")
        print(f"calls: {len(operation.get('calls', []))}")
        print(f"effects: {len(operation.get('effects', []))}")
    elif payload.get("matches") is not None:
        print(f"matches: {len(payload.get('matches', []))}")
    elif payload.get("uses") is not None:
        print(f"uses: {len(payload.get('uses', []))}")
    else:
        print(payload.get("error", "use --json for machine-readable slice output"))
    return 0 if payload.get("ok") else 1


def command_explain(args: argparse.Namespace) -> int:
    payload = _diagnostic_explain_payload(args.code)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("found") else 1
    if not payload.get("found"):
        print(f"unknown diagnostic code: {args.code}", file=sys.stderr)
        return 1
    print(f"{payload['code']}: {payload['title']}")
    if payload.get("summary"):
        print(payload["summary"])
    if payload.get("relatedCodes"):
        print(f"related: {', '.join(payload['relatedCodes'])}")
    for reference in payload.get("references", [])[:8]:
        print(f"- {reference['path']}:{reference['line']}  {reference['excerpt']}")
    return 0


def command_fix(args: argparse.Namespace) -> int:
    if not args.plan:
        print("sem fix currently supports --plan only", file=sys.stderr)
        return 2
    payload = _build_fix_plan_payload(Path(args.path), _strip_separator(list(args.compiler_args)))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"repairs: {len(payload['repairs'])}")
        for repair in payload["repairs"]:
            print(f"- {repair['diagnostic']} {repair['kind']} edits={len(repair['edits'])}")
    return 0


def command_patch(args: argparse.Namespace) -> int:
    mode = "apply" if args.apply else "dry-run"
    plan = _load_plan(Path(args.plan_path))
    payload = _execute_patch_plan(plan, mode)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"mode: {payload['mode']}")
        print(f"files changed: {len(payload['filesChanged'])}")
        for path in payload["filesChanged"]:
            print(f"- {path}")
    if payload["mode"] == "apply":
        return 0 if payload["verification"]["checkOk"] else 1
    return 0


def command_skills(args: argparse.Namespace) -> int:
    if args.skills_command == "list":
        payload = {
            "schemaVersion": "sem.skills.v1",
            "tool": {"name": "sem", "version": VERSION},
            "skills": _skill_registry_payload(),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for skill in payload["skills"]:
                print(f"{skill['name']}: {skill['description']}")
        return 0
    if args.skills_command == "get":
        names = [SKILL_ALIASES.get(name, name) for name in args.names]
        if args.all:
            names = [skill["name"] for skill in _skill_registry_payload()]
        entries = []
        for name in names:
            skill = _skill_content(name)
            if skill is not None:
                entries.append(skill)
        payload = {
            "schemaVersion": "sem.skills.v1",
            "tool": {"name": "sem", "version": VERSION},
            "skills": entries,
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for skill in entries:
                print(f"== {skill['name']} ==")
                print(skill["content"])
        return 0 if entries else 1
    print("sem skills requires a subcommand", file=sys.stderr)
    return 2


def command_migrate_syntax(args: argparse.Namespace) -> int:
    migration_path = ROOT / "tools" / "syntax_migration.py"
    command = [sys.executable, str(migration_path)]
    if args.write:
        command.append("--write")
    if args.diff:
        command.append("--diff")
    if args.json:
        command.append("--json")
    command.extend(args.paths)
    return subprocess.call(command)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sem",
        description="SemanticScript project tool driver",
    )
    parser.add_argument("--version", action="version", version=f"sem {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build",
        help="discover build.sem and compile the project",
    )
    build.add_argument("path", nargs="?", default=".")
    build.add_argument("compiler_args", nargs=argparse.REMAINDER)
    build.set_defaults(func=command_build)

    run = subparsers.add_parser(
        "run",
        help="discover build.sem or use a source file and run it through the JIT",
    )
    run.add_argument("--trace", action="store_true",
                     help="emit agent JSONL trace events to stderr")
    run.add_argument("--profile", action="store_true",
                     help="aggregate trace events into an agent profile JSON report")
    run.add_argument("--json", action="store_true",
                     help="request JSON output for agent run modes")
    run.add_argument("--explain-crash", dest="explain_crash",
                     action="store_true",
                     help="run as a subprocess and emit a crash triage JSON report")
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("compiler_args", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    version = subparsers.add_parser(
        "version",
        help="emit SemanticScript toolchain version facts",
    )
    version.add_argument("--json", action="store_true",
                         help="emit machine-readable version facts")
    version.set_defaults(func=command_version)

    check = subparsers.add_parser(
        "check",
        help="parse and lint a build.sem project or source file",
    )
    check.add_argument("--json", action="store_true",
                       help="emit machine-readable check diagnostics and context")
    check.add_argument("path", nargs="?", default=".")
    check.add_argument("compiler_args", nargs=argparse.REMAINDER)
    check.set_defaults(func=command_check)

    emit_ir = subparsers.add_parser(
        "emit-ir",
        help="discover build.sem or use a source file and emit LLVM IR",
    )
    emit_ir.add_argument("path", nargs="?", default=".")
    emit_ir.add_argument("compiler_args", nargs=argparse.REMAINDER)
    emit_ir.set_defaults(func=command_emit_ir)

    clean = subparsers.add_parser(
        "clean",
        help="preview or remove ignored SemanticScript build artifacts",
    )
    clean.add_argument("--force", action="store_true",
                       help="delete artifacts instead of printing a dry run")
    clean.add_argument("--all-ignored", action="store_true",
                       help="target all ignored files under the provided paths")
    clean.add_argument("paths", nargs="*",
                       help="optional git pathspecs; defaults to known generated artifact patterns")
    clean.set_defaults(func=command_clean)

    inspect_ir = subparsers.add_parser(
        "inspect-ir",
        help="emit agent-readable JSON mapping SemanticScript source to LLVM IR",
    )
    inspect_ir.add_argument("path", nargs="?", default=".")
    inspect_ir.add_argument("compiler_args", nargs=argparse.REMAINDER)
    inspect_ir.set_defaults(func=command_inspect_ir)

    compare_profiles = subparsers.add_parser(
        "compare-profiles",
        help="compare two agent profile JSON reports or artifact indexes",
    )
    compare_profiles.add_argument("baseline")
    compare_profiles.add_argument("candidate")
    compare_profiles.set_defaults(func=command_compare_profiles)

    lint = subparsers.add_parser(
        "lint",
        help="run the SemanticScript linter for a project or source file",
    )
    lint.add_argument("--engine", default="semlint", choices=("semlint",),
                      help="linter engine to use")
    lint.add_argument("path", nargs="?", default=".")
    lint.add_argument("linter_args", nargs=argparse.REMAINDER)
    lint.set_defaults(func=command_lint)

    fmt = subparsers.add_parser(
        "fmt",
        help="format SemanticScript .sem and .sscript files",
    )
    fmt.add_argument("--check", action="store_true",
                     help="exit non-zero when formatting drift is found")
    fmt.add_argument("--diff", action="store_true",
                     help="print unified diffs instead of writing files")
    fmt.add_argument("paths", nargs="*")
    fmt.add_argument("formatter_args", nargs=argparse.REMAINDER)
    fmt.set_defaults(func=command_fmt)

    bench = subparsers.add_parser(
        "bench",
        help="run SemanticScript LLVM benchmarks",
    )
    bench.add_argument("--json", action="store_true",
                       help="emit stable benchmark JSON")
    bench.add_argument("--runs", type=int,
                       help="measured iterations per benchmark")
    bench.add_argument("--warmup", type=int,
                       help="warmup iterations per benchmark")
    bench.add_argument("--benchmark", action="append", default=[],
                       help="benchmark name to run; may be repeated")
    bench.set_defaults(func=command_bench)

    doctor = subparsers.add_parser(
        "doctor",
        help="check local SemanticScript toolchain prerequisites",
    )
    doctor.add_argument("--json", action="store_true",
                        help="emit machine-readable prerequisite checks")
    doctor.set_defaults(func=command_doctor)

    readiness = subparsers.add_parser(
        "readiness",
        help="emit target, runtime, and toolchain readiness facts for agent workflows",
    )
    readiness.add_argument("--json", action="store_true",
                           help="emit machine-readable readiness facts")
    readiness.add_argument("path", nargs="?", default=".")
    readiness.set_defaults(func=command_readiness)

    context = subparsers.add_parser(
        "context",
        help="emit project context for agents and tooling",
    )
    context.add_argument("--json", action="store_true",
                         help="emit machine-readable project context")
    context.add_argument("path", nargs="?", default=".")
    context.set_defaults(func=command_context)

    symbols = subparsers.add_parser(
        "symbols",
        help="emit a source symbol graph for agents and tooling",
    )
    symbols.add_argument("--json", action="store_true",
                         help="emit machine-readable symbol graph")
    symbols.add_argument("path", nargs="?", default=".")
    symbols.set_defaults(func=command_symbols)

    graph = subparsers.add_parser(
        "graph",
        help="emit an agent-first architecture graph derived from SemanticScript source",
    )
    graph.add_argument("--kind", default="summary",
                       choices=("summary", "calls", "effects", "capabilities", "routes", "dataflow", "types", "ownership"),
                       help="graph view to emit")
    graph.add_argument("--json", action="store_true",
                       help="emit machine-readable graph payload")
    graph.add_argument("path", nargs="?", default=".")
    graph.set_defaults(func=command_graph)

    slice_cmd = subparsers.add_parser(
        "slice",
        help="emit the semantic neighborhood around an operation, route, effect, capability, or type",
    )
    slice_cmd.add_argument("--json", action="store_true",
                           help="emit machine-readable slice payload")
    slice_cmd.add_argument("--operation")
    slice_cmd.add_argument("--route",
                           help="route anchor in METHOD:/path form, for example POST:/todos")
    slice_cmd.add_argument("--symbol",
                           help="symbol anchor; currently resolves operations")
    slice_cmd.add_argument("--effect")
    slice_cmd.add_argument("--capability")
    slice_cmd.add_argument("--type", dest="type_name")
    slice_cmd.add_argument("path", nargs="?", default=".")
    slice_cmd.set_defaults(func=command_slice)

    explain = subparsers.add_parser(
        "explain",
        help="explain a SemanticScript compiler, linter, or runtime diagnostic code",
    )
    explain.add_argument("--json", action="store_true",
                         help="emit machine-readable diagnostic explanation")
    explain.add_argument("code")
    explain.set_defaults(func=command_explain)

    fix = subparsers.add_parser(
        "fix",
        help="generate structured repair plans for SemanticScript diagnostics",
    )
    fix.add_argument("--plan", action="store_true",
                     help="emit a reviewable repair plan instead of applying edits")
    fix.add_argument("--json", action="store_true",
                     help="emit machine-readable repair plans")
    fix.add_argument("path", nargs="?", default=".")
    fix.add_argument("compiler_args", nargs=argparse.REMAINDER)
    fix.set_defaults(func=command_fix)

    patch = subparsers.add_parser(
        "patch",
        help="apply or preview a structured SemanticScript repair plan",
    )
    mode = patch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="preview a plan without changing files")
    mode.add_argument("--apply", action="store_true",
                      help="apply a previously generated plan")
    patch.add_argument("--json", action="store_true",
                       help="emit machine-readable patch results")
    patch.add_argument("plan_path")
    patch.set_defaults(func=command_patch)

    skills = subparsers.add_parser(
        "skills",
        help="list or load version-matched agent skills from the current repository",
    )
    skills_subparsers = skills.add_subparsers(dest="skills_command", required=True)
    skills_list = skills_subparsers.add_parser(
        "list",
        help="list built-in SemanticScript agent skills",
    )
    skills_list.add_argument("--json", action="store_true",
                             help="emit machine-readable skill inventory")
    skills_list.set_defaults(func=command_skills)

    skills_get = skills_subparsers.add_parser(
        "get",
        help="load one or more built-in SemanticScript agent skills",
    )
    skills_get.add_argument("--json", action="store_true",
                            help="emit machine-readable skill content")
    skills_get.add_argument("--all", action="store_true",
                            help="return every visible built-in skill")
    skills_get.add_argument("--full", action="store_true",
                            help="compatibility flag; returns full content")
    skills_get.add_argument("names", nargs="*")
    skills_get.set_defaults(func=command_skills)

    size = subparsers.add_parser(
        "size",
        help="emit agent-readable source and helper-footprint facts",
    )
    size.add_argument("--json", action="store_true",
                      help="emit machine-readable size facts")
    size.add_argument("path", nargs="?", default=".")
    size.set_defaults(func=command_size)

    dev = subparsers.add_parser(
        "dev",
        help="emit an agent-first watch plan for iterative edit loops",
    )
    dev.add_argument("--json", action="store_true",
                     help="emit machine-readable watch-plan facts")
    dev.add_argument("--trace", action="store_true",
                     help="include phase-timing and cache-fact intent in the watch plan")
    dev.add_argument("path", nargs="?", default=".")
    dev.set_defaults(func=command_dev)

    test = subparsers.add_parser(
        "test",
        help="run a first-pass SemanticScript and harness test surface",
    )
    test.add_argument("--json", action="store_true",
                      help="emit machine-readable test results")
    test.add_argument("--skip-python-harnesses", action="store_true",
                      help="skip Python-based app harnesses and run only SemanticScript test files")
    test.add_argument("path", nargs="?", default=".")
    test.set_defaults(func=command_test)

    migrate_syntax = subparsers.add_parser(
        "migrate-syntax",
        help="explicitly convert legacy SemanticScript row syntax",
    )
    migrate_syntax.add_argument("--write", action="store_true",
                                help="rewrite files in place")
    migrate_syntax.add_argument("--diff", action="store_true",
                                help="print unified diffs")
    migrate_syntax.add_argument("--json", action="store_true",
                                help="emit machine-readable migration results")
    migrate_syntax.add_argument("paths", nargs="+")
    migrate_syntax.set_defaults(func=command_migrate_syntax)

    return parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if "--version" in argv and "--json" in argv and len(argv) == 2:
        print(json.dumps(_version_payload(), indent=2, sort_keys=True))
        return 0
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
