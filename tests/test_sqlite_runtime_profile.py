import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "semanticscript" / "runtime" / "manifest.json"
SQLITE_CMAKE = (
    ROOT / "legacy" / "SemanticScript" / "runtime" / "native_sqlite" /
    "CMakeLists.txt"
)


def _cmake_block(text, command, target):
    match = re.search(
        rf"{re.escape(command)}\(\s*{re.escape(target)}\s+(.+?)\)",
        text,
        re.S,
    )
    assert match, f"{command}({target} ...) not found"
    return [
        token for token in re.split(r"\s+", match.group(1).strip())
        if token and token not in {"PRIVATE", "PUBLIC", "INTERFACE"}
    ]


def _sqlite_manifest_library():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for library in data["libraries"]:
        if library["name"] == "ss_runtime" and "ss_sqlite_" in library["provides"]:
            return library
    raise AssertionError("SQLite runtime manifest library not found")


def _expected_platform_libs(cmake_tokens, platform):
    mapped = []
    for token in cmake_tokens:
        if token == "Threads::Threads":
            mapped.append("pthread")
        elif token == "${CMAKE_DL_LIBS}":
            if platform == "linux":
                mapped.append("dl")
        elif token == "m":
            mapped.append("m")
        else:
            raise AssertionError(f"unmapped SQLite CMake link token: {token}")
    return mapped


def test_sqlite_runtime_manifest_matches_cmake_profile():
    cmake = SQLITE_CMAKE.read_text(encoding="utf-8")
    cmake_defines = set(
        _cmake_block(cmake, "target_compile_definitions", "sem_sqlite_amalgamation")
    )
    cmake_libs = _cmake_block(cmake, "target_link_libraries", "sem_sqlite_amalgamation")
    manifest = _sqlite_manifest_library()

    assert set(manifest["defines"]) == cmake_defines
    assert "SQLITE_THREADSAFE=2" in manifest["defines"]
    assert "SQLITE_THREADSAFE=0" not in manifest["defines"]

    # Keep the Unix-only CMake link inputs platform-scoped. Linux needs libdl;
    # CMAKE_DL_LIBS is empty on macOS, and Windows must not inherit Unix libs.
    assert manifest.get("libs", []) == []
    assert manifest["platforms"]["linux"]["libs"] == _expected_platform_libs(
        cmake_libs, "linux")
    assert manifest["platforms"]["macos"]["libs"] == _expected_platform_libs(
        cmake_libs, "macos")
    assert "dl" not in manifest["platforms"]["macos"]["libs"]
    assert "windows" not in manifest.get("platforms", {})
