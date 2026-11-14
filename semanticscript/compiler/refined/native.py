"""Ahead-of-time output: an object file, assembly, or a WebAssembly module, for any LLVM target.

    refined build PATH --output FILE [--target TRIPLE] [--kind object|assembly|wasm]

The output is the program's compiled operations; the runtime it calls (output,
regions, traps, the host library) is not part of it. `--kind wasm` targets
`wasm32-unknown-unknown`: the module imports its linear memory, function table,
stack pointer, and runtime functions from the `env` namespace, and a host
supplies them (tests/suite/wasm_host.mjs is a small one for Node).

`--kind executable` links the object, the C runtime in native_runtime.c, and a
generated `main` into a standalone executable with the system C compiler
(cc, gcc, or clang, or $REFINED_CC), statically when the C library allows.
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
    needs = sorted(set(re.findall(r'c"([a-zA-Z]+\.[A-Za-z.]+)\|', ir_text)))
    if needs:
        return False, ("R901 this program calls " + ", ".join(f"`{n}`" for n in needs) + ", which need the host "
                       "library; standalone executables include only the core runtime, so run it with `refined run`")
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
                     f"int main(void) {{ refined_set_floor(refined_stack_here() - {budget}LL); "
                     "return (int)refined_entry(); }\n")
        base = cc + ["-O2", "-o", output, obj, RUNTIME_C, main_c]
        if windows:
            base.append(f"-Wl,--stack,{STACK_BYTES}")
        last = None
        for extra in (["-static"], []):  # static when the platform's C library allows it
            proc = subprocess.run(base + extra, capture_output=True, text=True)
            if proc.returncode == 0:
                return True, f"linked {output} ({'static' if extra else 'dynamic C library'}, {machine})"
            last = proc
        return False, f"linking failed:\n{last.stdout}{last.stderr}"


def build(ir_text: str, output: str, triple: str | None, kind: str, entry: str | None = None) -> int:
    if kind == "executable":
        if entry is None:
            sys.stdout.write("an executable needs a console project with an entry\n")
            return 1
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
