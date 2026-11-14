"""Build a SemanticScript program to WebAssembly via the vendored emscripten.

Pipeline: tape -> LLVM IR (semsc, retargeted with SEMSC_TRIPLE) -> emcc ->
`.wasm` + `.js` loader. The IR is lowered for `wasm32-unknown-emscripten`,
which skips host-only codegen (e.g. the Windows SEH crash filter) and binds
console/format calls to emscripten's libc.

The emscripten toolchain lives in the `third_party/emsdk` submodule, which is
registered `update = none` so a normal clone (even `--recursive`) skips it --
nobody pays the download unless they build wasm. The installed toolchain is also
NOT in git (emsdk's own .gitignore excludes the multi-GB binaries). A developer
opts in once with:

    git submodule update --init --checkout third_party/emsdk
    python third_party/emsdk/emsdk.py install latest
    python third_party/emsdk/emsdk.py activate latest

CLI:
    python SemanticScript/tools/build_wasm.py SOURCE.sem [-o OUT.js] [--run]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
STD_ROOT = REPO_ROOT / "SemanticScript" / "std"
EMSDK_ROOT = REPO_ROOT / "third_party" / "emsdk"
EMSDK_PY = EMSDK_ROOT / "emsdk.py"
EMCC = EMSDK_ROOT / "upstream" / "emscripten" / "emcc.py"
EM_CONFIG = EMSDK_ROOT / ".emscripten"

WASM_TRIPLE = "wasm32-unknown-emscripten"

# `import ALIAS standard.MODULE` row, the only way a program pulls in a std
# module (and thus its JavaScript runtime adapter).
_IMPORT_RE = re.compile(r"^\s*import\s+\S+\s+(standard\.[A-Za-z0-9_.]+)\s*$", re.M)


class ToolchainMissing(RuntimeError):
    """Raised when the emscripten toolchain has not been installed yet."""


def toolchain_ready() -> bool:
    return EMCC.is_file() and EM_CONFIG.is_file()


def _require_toolchain() -> None:
    if toolchain_ready():
        return
    # The emsdk submodule is registered `update = none`, so a normal clone does
    # not fetch it. Distinguish "submodule not checked out" from "toolchain not
    # installed" so the message names the right next step.
    if not EMSDK_PY.is_file():
        raise ToolchainMissing(
            "the emscripten submodule is not checked out (it is opt-in so a "
            "normal clone stays small). Fetch and install it with:\n"
            "  git submodule update --init --checkout third_party/emsdk\n"
            f"  python {EMSDK_PY} install latest\n"
            f"  python {EMSDK_PY} activate latest"
        )
    raise ToolchainMissing(
        f"emscripten toolchain not installed under {EMSDK_ROOT}. Install it with:\n"
        f"  python {EMSDK_PY} install latest\n"
        f"  python {EMSDK_PY} activate latest"
    )


def emit_ir(source: Path, ir_path: Path) -> None:
    env = dict(os.environ, SEMSC_TRIPLE=WASM_TRIPLE)
    result = subprocess.run(
        [sys.executable, str(SEMSC), "--emit-ir", str(ir_path), str(source)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not ir_path.is_file():
        raise RuntimeError(
            f"semsc failed to emit wasm IR for {source}:\n{result.stdout}\n{result.stderr}"
        )


def _std_module_main(module_path: str) -> Path | None:
    """Resolve a `standard.X.Y` module path to its main source file, if present."""
    rel = module_path.split(".", 1)[1].replace(".", os.sep)
    for ext in (".sem", ".sscript"):
        candidate = STD_ROOT / rel / f"main{ext}"
        if candidate.is_file():
            return candidate
    return None


def discover_js_libraries(source: Path) -> list[Path]:
    """Return the JS runtime adapters for the std modules `source` needs.

    A std module ships its emscripten js-library adapter at
    `std/<module>/native/*.js`. The native (clang) build links a module's C
    adapter via `nativeRuntimeSource`; the wasm build links its JS adapter
    here instead. Imports are followed transitively, so a program that reaches
    a JS-adapter module through an intermediate std module still links it.
    """
    libs: list[Path] = []
    seen_modules: set[str] = set()
    seen_libs: set[Path] = set()
    pending = [source]
    scanned_files: set[Path] = set()

    while pending:
        current = pending.pop()
        if current in scanned_files:
            continue
        scanned_files.add(current)
        text = current.read_text(encoding="utf-8", errors="replace")
        for module_path in _IMPORT_RE.findall(text):
            if module_path in seen_modules:
                continue
            seen_modules.add(module_path)
            module_name = module_path.split(".", 1)[1].replace(".", os.sep)
            native_dir = STD_ROOT / module_name / "native"
            if native_dir.is_dir():
                for lib in sorted(native_dir.glob("*.js")):
                    if lib not in seen_libs:
                        seen_libs.add(lib)
                        libs.append(lib)
            module_main = _std_module_main(module_path)
            if module_main is not None:
                pending.append(module_main)
    return libs


_ASYNC_IMPORT_RE = re.compile(r"(\w+)__async\s*:\s*true")


def _async_import_names(js_libs: list[Path]) -> list[str]:
    # Names of adapter imports declared `<name>__async: true`. These suspend the
    # wasm stack and so must be listed in ASYNCIFY_IMPORTS, otherwise Asyncify
    # does not instrument their callers and the returned Promise is dropped.
    names: list[str] = []
    for lib in js_libs:
        for name in _ASYNC_IMPORT_RE.findall(lib.read_text(encoding="utf-8", errors="replace")):
            if name not in names:
                names.append(name)
    return names


def emcc_compile(ir_path: Path, out_js: Path, extra_args: list[str] | None = None) -> None:
    _require_toolchain()
    env = dict(os.environ, EM_CONFIG=str(EM_CONFIG))
    cmd = [sys.executable, str(EMCC), str(ir_path), "-o", str(out_js)]
    cmd.extend(extra_args or [])
    result = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    wasm_path = out_js.with_suffix(".wasm")
    if result.returncode != 0 or not wasm_path.is_file():
        raise RuntimeError(
            f"emcc failed to compile {ir_path}:\n{' '.join(cmd)}\n{result.stdout}\n{result.stderr}"
        )


def link_args_for(source: Path, asyncify: bool | None = None) -> list[str]:
    """Compute emcc link args for a program: js-library adapters + Asyncify."""
    js_libs = discover_js_libraries(source)
    args: list[str] = []
    for lib in js_libs:
        args.append(f"--js-library={lib}")
    async_imports = _async_import_names(js_libs)
    use_asyncify = bool(async_imports) if asyncify is None else asyncify
    if use_asyncify:
        # ASYNCIFY lets an imported `__async` JS function suspend the wasm
        # stack and resume from the browser/Node event loop. The imports must
        # be enumerated so Asyncify instruments their call paths.
        args.append("-sASYNCIFY")
        if async_imports:
            args.append("-sASYNCIFY_IMPORTS=" + ",".join(async_imports))
    return args


def build_wasm(source: Path, out_js: Path, asyncify: bool | None = None,
               extra_args: list[str] | None = None) -> Path:
    """Compile `source` to wasm, returning the path to the emitted `.wasm`.

    JS runtime adapters for imported std modules are linked automatically, and
    Asyncify is enabled when any adapter declares an `__async` import.
    """
    out_js.parent.mkdir(parents=True, exist_ok=True)
    ir_path = out_js.with_suffix(".ll")
    emit_ir(source, ir_path)
    args = link_args_for(source, asyncify=asyncify)
    args.extend(extra_args or [])
    emcc_compile(ir_path, out_js, extra_args=args)
    return out_js.with_suffix(".wasm")


def _node_exe() -> str:
    # Prefer a system node; fall back to the one emsdk vendors.
    bundled = sorted(EMSDK_ROOT.glob("node/*/bin/node*"))
    return "node" if bundled == [] else (os.environ.get("SEMSC_NODE") or "node")


def run_wasm(out_js: Path) -> str:
    result = subprocess.run(
        [_node_exe(), str(out_js)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"node failed to run {out_js}:\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a SemanticScript program to wasm via emscripten.")
    parser.add_argument("source", help="path to the .sem source file")
    parser.add_argument("-o", "--output", help="output .js path (default: <source>.js beside the source)")
    parser.add_argument("--run", action="store_true", help="run the result under node and print stdout")
    parser.add_argument("--asyncify", dest="asyncify", action="store_true", default=None,
                        help="force-enable Asyncify (auto-detected from adapters by default)")
    parser.add_argument("--no-asyncify", dest="asyncify", action="store_false",
                        help="disable Asyncify even if an adapter requests it")
    parser.add_argument("--emcc-arg", dest="emcc_args", action="append", default=[],
                        help="extra raw emcc argument (repeatable)")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    out_js = Path(args.output).resolve() if args.output else source.with_suffix(".js")

    libs = discover_js_libraries(source)
    if libs:
        print("js adapters: " + ", ".join(str(p.relative_to(REPO_ROOT)) for p in libs))
    wasm = build_wasm(source, out_js, asyncify=args.asyncify, extra_args=args.emcc_args)
    print(f"wrote {wasm}")
    if args.run:
        sys.stdout.write(run_wasm(out_js))
    return 0


if __name__ == "__main__":
    sys.exit(main())
