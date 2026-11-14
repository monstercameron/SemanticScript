"""Ahead-of-time output: an object file, assembly, or a WebAssembly module, for any LLVM target.

    refined build PATH --output FILE [--target TRIPLE] [--kind object|assembly|wasm]

The output is the program's compiled operations; the runtime it calls (output,
regions, traps, the host library) is not part of it. `--kind wasm` targets
`wasm32-unknown-unknown`: the module imports its linear memory, function table,
stack pointer, and runtime functions from the `env` namespace, and a host
supplies them (tests/suite/wasm_host.mjs is a small one for Node).

`--kind executable` links the object, the C runtime in native_runtime.c, and a
generated `main(argc, argv)` into a standalone executable with the system C
compiler (cc, gcc, or clang, or $REFINED_CC), statically when the C library
allows. The C runtime implements most of the host library natively (D-80); a
program that calls a target it does not implement is refused (R901, D-81).

`--kind executable --runtime semanticscript` (D-124) links the program instead
with the runtime written in SemanticScript (semanticscript/runtime), compiled to
a second object, and no C library: no CRT start files, no libc, the entry point
`refined_entry`, and only kernel32 (plus the compiler's own support library, for
stack probes). It runs on Windows so far. A program that needs a runtime
function or host target that runtime does not provide yet is refused (R901)
before anything is linked.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile

from llvmlite import binding as llvm

_READY = [False]


def _init() -> None:
    if not _READY[0]:
        llvm.initialize_all_targets()
        llvm.initialize_all_asmprinters()
        _READY[0] = True


_DEFINE = re.compile(r'^(define [^@\n]*@"?([^"(\s]+)"?\([^\n]*\))[^\n]*$', re.M)


def _export_all(ir_text: str) -> str:
    """WebAssembly: export every compiled operation under its own name, so a host can call `main`."""
    return _DEFINE.sub(lambda m: f'{m.group(1)} "wasm-export-name"="{m.group(2)}"', ir_text)


def emit(ir_text: str, triple: str | None, kind: str) -> bytes:
    _init()
    if kind == "wasm":
        triple = triple or "wasm32-unknown-unknown"
        ir_text = _export_all(ir_text)
    triple = triple or llvm.get_default_triple()
    mod = llvm.parse_assembly(ir_text)
    mod.triple = triple
    target = llvm.Target.from_triple(triple)
    tm = target.create_target_machine(reloc="pic" if kind != "wasm" else "static", codemodel="default", opt=2)
    mod.data_layout = str(tm.target_data)
    mod.verify()
    if kind == "assembly":
        return tm.emit_assembly(mod).encode("utf-8")
    return tm.emit_object(mod)


RUNTIME_C = os.path.join(os.path.dirname(os.path.abspath(__file__)), "native_runtime.c")
STACK_BYTES = 256 * 1024 * 1024
_TARGET_ROW = re.compile(r'^\s*\{"([A-Za-z.]+)", (\w+), (-?\d+)\},$', re.M)


def native_targets() -> dict[str, int]:
    """D-80: the host targets the C runtime implements (its `TARGETS` table), each with the index of its scoped
    parameter or -1. A program that calls any other host target is refused as an executable (R901, D-81)."""
    with open(RUNTIME_C, encoding="utf-8") as fh:
        return {m.group(1): int(m.group(3)) for m in _TARGET_ROW.finditer(fh.read())}


def _runtime_object(cc: list[str], machine: str, folder: str) -> str:
    """The C runtime compiled once per compiler and source text, kept in the temporary directory, so linking a
    program compiles only its small `main`."""
    import hashlib
    with open(RUNTIME_C, "rb") as fh:
        source = fh.read()
    digest = hashlib.sha256(source + "\0".join(cc + [machine]).encode()).hexdigest()[:20]
    cached = os.path.join(tempfile.gettempdir(), f"refined-runtime-{digest}.o")
    if os.path.exists(cached):
        return cached
    fresh = os.path.join(folder, "runtime.o")
    proc = subprocess.run(cc + ["-O2", "-c", "-o", fresh, RUNTIME_C], capture_output=True, text=True)
    if proc.returncode != 0:
        return RUNTIME_C  # let the link report the error
    try:
        partial = f"{cached}.{os.getpid()}"
        shutil.copyfile(fresh, partial)
        os.replace(partial, cached)
        return cached
    except OSError:
        return fresh


def find_cc() -> list[str] | None:
    """The C compiler that links executables: $REFINED_CC, else cc, gcc, or clang on PATH, else `zig cc` if the
    `ziglang` package is installed."""
    if os.environ.get("REFINED_CC"):
        return os.environ["REFINED_CC"].split()
    for name in ("cc", "gcc", "clang"):
        found = shutil.which(name)
        if found:
            return [found]
    try:
        import ziglang  # noqa: F401
        return [sys.executable, "-m", "ziglang", "cc"]
    except ImportError:
        return None


def executable(ir_text: str, entry: str, output: str) -> tuple[bool, str]:
    """Link the program's object, the C runtime (native_runtime.c), and a `main` into one executable."""
    native = native_targets()
    needs = sorted(set(re.findall(r'c"([a-zA-Z]+\.[A-Za-z.]+)\|', ir_text)) - set(native))
    if needs:
        return False, ("R901 this program calls " + ", ".join(f"`{n}`" for n in needs) + ", which need the host "
                       "library; standalone executables include the native part of it only (D-81), so run it with "
                       "`refined run`")
    cc = find_cc()
    if cc is None:
        return False, "no C compiler to link with: install one (cc, gcc, or clang) or set REFINED_CC"
    machine = subprocess.run(cc + ["-dumpmachine"], capture_output=True, text=True).stdout.strip()
    triple = machine or None
    parts = machine.split("-")
    if "mingw" in machine:
        # gcc says `x86_64-w64-mingw32`; LLVM reads that OS as unknown and would emit ELF objects
        triple = parts[0] + "-w64-windows-gnu"
    elif len(parts) == 3 and parts[1] == "linux":
        triple = f"{parts[0]}-unknown-linux-{parts[2]}"  # `x86_64-linux-gnu` names no vendor
    windows = "mingw" in machine or "windows" in machine
    apple = "apple" in machine or "darwin" in machine
    budget = STACK_BYTES - 8 * 1024 * 1024 if windows else 6 * 1024 * 1024
    with tempfile.TemporaryDirectory() as d:
        obj = os.path.join(d, "program.o")
        with open(obj, "wb") as fh:
            fh.write(emit(ir_text, triple, "object"))
        symbol = ("_" if apple else "") + entry
        main_c = os.path.join(d, "main.c")
        with open(main_c, "w", encoding="utf-8") as fh:
            fh.write("#include <stdint.h>\n"
                     f'extern int32_t refined_entry(void) __asm__("{symbol}");\n'
                     f'extern int64_t refined_stack_here(void) __asm__("{"_" if apple else ""}refined_stack_here");\n'
                     "void refined_set_floor(int64_t floor);\n"
                     "void refined_start(int argc, char **argv);\n"
                     "int main(int argc, char **argv) { refined_start(argc, argv); "
                     f"refined_set_floor(refined_stack_here() - {budget}LL); "
                     "return (int)refined_entry(); }\n")
        base = cc + ["-O2", "-o", output, obj, _runtime_object(cc, machine, d), main_c]
        if windows:
            base += [f"-Wl,--stack,{STACK_BYTES}", "-lshell32"]
        last = None
        for extra in (["-static"], []):  # static when the platform's C library allows it
            proc = subprocess.run(base + extra, capture_output=True, text=True)
            if proc.returncode == 0:
                return True, f"linked {output} ({'static' if extra else 'dynamic C library'}, {machine})"
            last = proc
        return False, f"linking failed:\n{last.stdout}{last.stderr}"


# ---------------------------------------------------------------- the runtime in SemanticScript (D-124)

RUNTIME_PROJECT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runtime"))
_DECLARE = re.compile(r'^declare [^@\n]*@"?([A-Za-z_][A-Za-z0-9_.]*)"?\(', re.M)


def runtime_ir() -> tuple[str | None, set[str], str]:
    """The runtime project compiled to LLVM IR with every `abi c` operation as a root: (IR, the symbols it
    defines, a problem). The project must check clean and its authority must be approved (D-53)."""
    from .check import check_path, find_build, unapproved_authority
    from .codegen import compile_roots
    from .semantics import abi_symbol
    build_path = find_build(RUNTIME_PROJECT)
    if build_path is None:
        return None, set(), f"there is no runtime project at {RUNTIME_PROJECT}"
    missing = unapproved_authority(build_path)
    if missing:
        return None, set(), ("the runtime project asks for authority that was not approved: "
                             + ", ".join(f"`allows {r}`" for r in missing))
    res = check_path(RUNTIME_PROJECT)
    if not res.ok:
        return None, set(), "the runtime project does not check:\n" + "\n".join(d.format() for d in res.diagnostics)
    roots = [(m.short, name) for m in res.world.modules.values() for name, ent in m.ops.items()
             if abi_symbol(ent) is not None]
    module, diags = compile_roots(res.world, roots, {"runtime_object": True})
    if diags:
        return None, set(), "the runtime project does not compile:\n" + "\n".join(d.format() for d in diags)
    symbols = {abi_symbol(m.ops[name]) for m in res.world.modules.values() for name in m.ops
               if abi_symbol(m.ops[name]) is not None}
    return str(module), symbols, ""


def _imported(ir_text: str) -> str:
    """D-122: the operating system's functions are imported from their DLL (`__imp_<name>`), not called through a
    stub the import library would add."""
    from .library import SYSTEM_CALLS
    names = "|".join(re.escape(symbol) for symbol, _sig in SYSTEM_CALLS.values())
    return re.sub(rf'^declare ([^@\n]*@"?(?:{names})"?\()', r"declare dllimport \1", ir_text, flags=re.M)


def _ss_runtime_object(triple: str, folder: str) -> tuple[str | None, set[str], str]:
    """The runtime's object, compiled once per runtime and compiler source text and kept in the temporary
    directory, with the symbols it defines."""
    import hashlib
    import json
    h = hashlib.sha256(triple.encode())
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (RUNTIME_PROJECT, here):
        for name in sorted(os.listdir(root)):
            if name.endswith((".sem", ".py", ".approved")):
                with open(os.path.join(root, name), "rb") as fh:
                    h.update(name.encode() + b"\0" + fh.read())
    digest = h.hexdigest()[:20]
    cached = os.path.join(tempfile.gettempdir(), f"refined-runtime-ss-{digest}.o")
    listed = cached + ".symbols"
    if os.path.exists(cached) and os.path.exists(listed):
        with open(listed, encoding="utf-8") as fh:
            return cached, set(json.load(fh)), ""
    ir_text, symbols, problem = runtime_ir()
    if ir_text is None:
        return None, set(), problem
    fresh = os.path.join(folder, "runtime.o")
    with open(fresh, "wb") as fh:
        fh.write(emit(_imported(ir_text), triple, "object"))
    try:
        for path, data in ((cached, None), (listed, json.dumps(sorted(symbols)))):
            partial = f"{path}.{os.getpid()}"
            if data is None:
                shutil.copyfile(fresh, partial)
            else:
                with open(partial, "w", encoding="utf-8") as fh:
                    fh.write(data)
            os.replace(partial, path)
        return cached, symbols, ""
    except OSError:
        return fresh, symbols, ""


def needed_runtime(ir_text: str) -> set[str]:
    """The runtime functions a compiled program calls: the callbacks it declares (codegen declares each when it is
    first used). `memcpy` and the like, which LLVM may call, the runtime always defines."""
    from .codegen import CALLBACKS
    return {name for name in _DECLARE.findall(ir_text) if name in CALLBACKS}


def executable_semanticscript(ir_text: str, entry: str, output: str) -> tuple[bool, str]:
    """D-124: link the program's object and the runtime's object (from semanticscript/runtime) with no C library."""
    cc = find_cc()
    if cc is None:
        return False, "no C compiler to link with: install one (cc, gcc, or clang) or set REFINED_CC"
    machine = subprocess.run(cc + ["-dumpmachine"], capture_output=True, text=True).stdout.strip()
    if "mingw" not in machine and "windows" not in machine:
        return False, (f"R901 the runtime in SemanticScript calls Windows only so far (D-122); `{machine}` needs "
                       "the C runtime (`--runtime c`)")
    triple = machine.split("-")[0] + "-w64-windows-gnu"
    with tempfile.TemporaryDirectory() as d:
        runtime_obj, provided, problem = _ss_runtime_object(triple, d)
        if runtime_obj is None:
            return False, problem
        missing = sorted(needed_runtime(ir_text) - provided)
        if missing:
            return False, ("R901 this program needs " + ", ".join(f"`{n}`" for n in missing) + ", which the runtime "
                           "in SemanticScript does not provide yet (docs/runtime-in-semanticscript.md); build it "
                           "with the C runtime (`--runtime c`)")
        mod, _dot, op = entry.partition(".")
        from .codegen import function_name
        program = (_imported(ir_text) + "\n; the program's entry, which the runtime's `refined_entry` runs (D-124)\n"
                   "define i32 @refined_program_main() {\nentry:\n"
                   f'  %code = call i32 @"{function_name(mod, op)}"()\n  ret i32 %code\n}}\n')
        obj = os.path.join(d, "program.o")
        with open(obj, "wb") as fh:
            fh.write(emit(program, triple, "object"))
        cmd = cc + ["-nostdlib", "-nostartfiles", "-Wl,-e,refined_entry", f"-Wl,--stack,{STACK_BYTES}", "-o", output,
                    obj, runtime_obj, "-lkernel32", "-lgcc"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return False, f"linking failed:\n{proc.stdout}{proc.stderr}"
        return True, f"linked {output} (the runtime in SemanticScript, no C library, {machine})"


def build(ir_text: str, output: str, triple: str | None, kind: str, entry: str | None = None,
          runtime: str = "c") -> int:
    if kind == "executable":
        if entry is None:
            sys.stdout.write("an executable needs a console project with an entry\n")
            return 1
        if runtime == "semanticscript":
            ok, message = executable_semanticscript(ir_text, entry, output)
        else:
            ok, message = executable(ir_text, entry, output)
        sys.stdout.write(message + "\n")
        return 0 if ok else 1
    try:
        data = emit(ir_text, triple, kind)
    except RuntimeError as exc:
        sys.stdout.write(f"build failed: {exc}\n")
        return 1
    with open(output, "wb") as fh:
        fh.write(data)
    shown = triple or ("wasm32-unknown-unknown" if kind == "wasm" else "host")
    sys.stdout.write(f"wrote {output} ({len(data)} bytes, {kind}, {shown})\n")
    return 0
