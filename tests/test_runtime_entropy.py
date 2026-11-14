import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "semanticscript" / "compiler"))

import semanticscript  # noqa: E402


def _runtime_library(name: str) -> dict:
    manifest = json.loads((ROOT / "semanticscript" / "runtime" / "manifest.json").read_text(encoding="utf-8"))
    for library in manifest["libraries"]:
        if library.get("name") == name:
            return library
    raise AssertionError(f"runtime library {name!r} not found")


def test_bcrypt_randomness_routes_through_native_platform_entropy():
    runtime = ROOT / "semanticscript" / "runtime"
    bcrypt_source = (runtime / "native_bcrypt" / "sem_bcrypt_runtime.c").read_text(encoding="utf-8")

    assert 'native_platform/ss_platform_entropy.h' in bcrypt_source
    assert "ss_platform_random_bytes" in bcrypt_source
    assert "BCryptGenRandom" not in bcrypt_source
    assert "getrandom(" not in bcrypt_source
    assert "/dev/urandom" not in bcrypt_source

    platform_source = (runtime / "native_platform" / "ss_platform_entropy.c").read_text(encoding="utf-8")
    assert "BCryptGenRandom" in platform_source
    assert "getrandom(" in platform_source
    assert 'open("/dev/urandom"' in platform_source


def test_bcrypt_manifest_declares_platform_entropy_source_and_windows_lib():
    library = _runtime_library("ss_bcrypt")
    assert "native_platform/ss_platform_entropy.c" in library["sources"]
    assert "native_platform" in library["include"]

    windows = semanticscript._resolve_runtime_links(library, "windows")
    linux = semanticscript._resolve_runtime_links(library, "linux")
    macos = semanticscript._resolve_runtime_links(library, "macos")

    assert "bcrypt" in windows["libs"]
    assert "bcrypt" not in linux["libs"]
    assert "bcrypt" not in macos["libs"]
