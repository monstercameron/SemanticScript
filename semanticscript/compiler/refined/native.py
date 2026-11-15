"""Ahead-of-time output: an object file, assembly, a WebAssembly module, a standalone executable, or the runtime.

    refined build PATH --output FILE [--target TRIPLE] [--kind object|assembly|wasm|executable|runtime]

The output of `object`, `assembly`, and `wasm` is the program's compiled operations; the runtime it calls (output,
regions, traps, the host library) is not part of it. `--kind wasm` targets `wasm32-unknown-unknown`: the module
imports its linear memory, function table, stack pointer, and runtime functions from the `env` namespace, and a host
supplies them (tests/suite/wasm_host.mjs is a small one for Node).

`--kind executable` links the program with the runtime written in SemanticScript (semanticscript/runtime, D-124),
the two compiled into one LLVM module that keeps only what the entry reaches (D-135), and no C library: no CRT start
files, no libc, the C compiler (cc, gcc, or clang, or $REFINED_CC) used only as the linker. On Windows the entry is
`refined_entry` and the executable imports kernel32 alone (with the compiler's own support library for stack
probes); on x86_64 Linux it is static, its entry the runtime's `_start`, and it reaches the kernel through system
calls (D-138, D-139). macOS has no system layer and is refused (D-141). A program that needs a runtime function or
host target the runtime does not provide is refused (R901) before anything is linked.

`--kind runtime`, for the runtime project, writes the runtime alone as an object for the C compiler's platform, every
`abi c` operation an external symbol, to link with C that defines `refined_program_main` (stage0's, D-142).
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
        llvm.initialize_native_asmparser()  # D-139: the runtime's assembly on Linux (system calls, stacks)
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


STACK_BYTES = 256 * 1024 * 1024  # the main thread's stack on Windows (Linux maps its own, D-139)


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


# ---------------------------------------------------------------- the runtime in SemanticScript (D-124)

RUNTIME_PROJECT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "runtime"))
_DECLARE = re.compile(r'^declare [^@\n]*@"?([A-Za-z_][A-Za-z0-9_.]*)"?\(', re.M)

# D-140: what an executable on Linux cannot have: a foreign library is loaded by the C library's dynamic loader,
# and an executable with no C library has none.
LINUX_REFUSED = ("ffi.",)


def platform(cc: list[str]) -> tuple[str, str | None, str]:
    """The C compiler's machine (`gcc -dumpmachine`), the LLVM triple an executable for it is compiled for, and a
    problem (empty when it can be linked): Windows and Linux on x86_64 have the runtime's system layer (D-122,
    D-138); macOS has none."""
    machine = subprocess.run(cc + ["-dumpmachine"], capture_output=True, text=True).stdout.strip()
    arch = machine.split("-")[0]
    if "mingw" in machine or "windows" in machine:
        # gcc says `x86_64-w64-mingw32`; LLVM reads that OS as unknown and would emit ELF objects
        return machine, arch + "-w64-windows-gnu", ""
    if "linux" in machine:
        if arch != "x86_64":
            return machine, None, (f"R901 the runtime in SemanticScript reaches Linux through x86_64 system calls "
                                   f"(D-138); `{machine}` is another architecture")
        return machine, "x86_64-unknown-linux-gnu", ""
    if "apple" in machine or "darwin" in machine:
        return machine, None, (f"R901 standalone executables are built for Windows and Linux; macOS (`{machine}`) "
                               "has no system layer in the runtime yet (D-141), so run the program with `refined run`")
    return machine, None, f"R901 standalone executables are built for Windows and Linux, not `{machine}`"


def runtime_ir(triple: str | None = None) -> tuple[str | None, set[str], str]:
    """The runtime project compiled to LLVM IR for a target triple, with every `abi c` operation as a root: (IR, the
    symbols it defines, a problem). The project must check clean and its authority must be approved (D-53)."""
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
    options = {"runtime_object": True, **({"triple": triple} if triple else {})}
    module, diags = compile_roots(res.world, roots, options)
    if diags:
        return None, set(), "the runtime project does not compile:\n" + "\n".join(d.format() for d in diags)
    symbols = {abi_symbol(m.ops[name]) for m in res.world.modules.values() for name in m.ops
               if abi_symbol(m.ops[name]) is not None}
    return str(module), symbols, ""


def _imported(ir_text: str, triple: str) -> str:
    """D-122: the operating system's functions are imported from their DLL (`__imp_<name>`), not called through a
    stub the import library would add. Linux has no DLLs: its system calls are instructions (D-138)."""
    from .codegen import target_os
    from .library import SYSTEM_CALLS
    if target_os(triple) != "windows":
        return ir_text
    names = "|".join(re.escape(symbol) for symbol, _sig in SYSTEM_CALLS.values())
    return re.sub(rf'^declare ([^@\n]*@"?(?:{names})"?\()', r"declare dllimport \1", ir_text, flags=re.M)


_KEPT = ("refined_entry", "memcpy", "memmove", "memset", "memcmp")  # the entry, and what LLVM's code may call


def _ss_runtime_bitcode(triple: str) -> tuple[bytes | None, set[str], str]:
    """The runtime as LLVM bitcode for a target triple, compiled once per runtime and compiler source text and
    triple and kept in the temporary directory, with the symbols it defines."""
    import hashlib
    import json
    h = hashlib.sha256(b"bitcode\0" + triple.encode())
    here = os.path.dirname(os.path.abspath(__file__))
    for root in (RUNTIME_PROJECT, here):
        for name in sorted(os.listdir(root)):
            if name.endswith((".sem", ".py", ".approved")):
                with open(os.path.join(root, name), "rb") as fh:
                    h.update(name.encode() + b"\0" + fh.read())
    digest = h.hexdigest()[:20]
    cached = os.path.join(tempfile.gettempdir(), f"refined-runtime-ss-{digest}.bc")
    listed = cached + ".symbols"
    if os.path.exists(cached) and os.path.exists(listed):
        with open(cached, "rb") as fh, open(listed, encoding="utf-8") as fl:
            return fh.read(), set(json.load(fl)), ""
    ir_text, symbols, problem = runtime_ir(triple)
    if ir_text is None:
        return None, set(), problem
    _init()
    bitcode = llvm.parse_assembly(_imported(ir_text, triple)).as_bitcode()
    try:
        for path, data, mode in ((cached, bitcode, "wb"), (listed, json.dumps(sorted(symbols)), "w")):
            partial = f"{path}.{os.getpid()}"
            with open(partial, mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as fh:
                fh.write(data)
            os.replace(partial, path)
    except OSError:
        pass
    return bitcode, symbols, ""


def _simplify(module, tm) -> None:
    """D-138: fold `system.linux` and drop what it rules out (the other operating system's branches), then what
    nothing reaches from the entry (global dead code elimination)."""
    passes = llvm.create_new_module_pass_manager()
    passes.add_sroa_pass()
    passes.add_sccp_pass()
    passes.add_simplify_cfg_pass()
    passes.add_global_dead_code_eliminate_pass()
    passes.add_strip_dead_prototype_pass()
    passes.run(module, llvm.create_pass_builder(tm, llvm.create_pipeline_tuning_options()))


def _whole_program(runtime_bitcode: bytes, program_ir: str, triple: str) -> bytes:
    """D-135: the runtime and the program as one LLVM module, every function but the entry (and `memcpy` and the
    like) internal, and what nothing reaches from the entry dropped (global dead code elimination), emitted as one
    object. The runtime's own functions are made internal before the program is linked in, so a program operation
    named like one of them is a different function."""
    from .codegen import CALLBACKS
    _init()
    runtime = llvm.parse_bitcode(runtime_bitcode)
    for fn in runtime.functions:
        if not fn.is_declaration and fn.name not in CALLBACKS and fn.name not in _KEPT \
                and fn.name != "refined_task_entry":
            fn.linkage = llvm.Linkage.internal
    runtime.link_in(llvm.parse_assembly(program_ir))
    for fn in runtime.functions:
        if not fn.is_declaration and fn.name not in _KEPT:
            fn.linkage = llvm.Linkage.internal
    target = llvm.Target.from_triple(triple)
    tm = target.create_target_machine(reloc="pic", codemodel="default", opt=2)
    runtime.triple = triple
    runtime.data_layout = str(tm.target_data)
    _simplify(runtime, tm)
    runtime.verify()
    return tm.emit_object(runtime)


_HOST_TARGET_CELL = re.compile(r'^hostTargets cell \w+ name "([A-Za-z0-9.]+)"$', re.M)


def runtime_host_targets(triple: str | None = None) -> set[str]:
    """The host targets the runtime in SemanticScript implements: the `hostTargets` table of its host module, which
    its `refined_host` dispatches over (D-130); for Linux, less those it cannot have there (D-140)."""
    from .codegen import target_os
    path = os.path.join(RUNTIME_PROJECT, "host.sem")
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as fh:
        found = set(_HOST_TARGET_CELL.findall(fh.read()))
    if triple is not None and target_os(triple) == "linux":
        found = {t for t in found if not t.startswith(LINUX_REFUSED)}
    return found


def needed_runtime(ir_text: str) -> set[str]:
    """The runtime functions a compiled program calls: the callbacks it declares (codegen declares each when it is
    first used). `memcpy` and the like, which LLVM may call, the runtime always defines."""
    from .codegen import CALLBACKS
    return {name for name in _DECLARE.findall(ir_text) if name in CALLBACKS}


def _link_command(cc: list[str], triple: str, output: str, objects: list[str]) -> list[str]:
    """D-124, D-138: no CRT start files and no C library. Windows: the entry `refined_entry`, a main thread of
    STACK_BYTES, kernel32 and the compiler's support library (stack probes). Linux: static, the entry `_start` (the
    runtime's), and the compiler's support library only."""
    from .codegen import target_os
    if target_os(triple) == "windows":
        return cc + ["-nostdlib", "-nostartfiles", "-Wl,-e,refined_entry", f"-Wl,--stack,{STACK_BYTES}",
                     "-Wl,--gc-sections", "-s", "-o", output, *objects, "-lkernel32", "-lgcc"]
    return cc + ["-nostdlib", "-nostartfiles", "-static", "-Wl,-e,_start", "-Wl,--gc-sections", "-Wl,--build-id=none",
                 "-s", "-o", output, *objects, "-lgcc"]


def executable(ir_text: str, entry: str, output: str) -> tuple[bool, str]:
    """D-124, D-141: link the program and the runtime in SemanticScript (semanticscript/runtime) with no C library."""
    cc = find_cc()
    if cc is None:
        return False, "no C compiler to link with: install one (cc, gcc, or clang) or set REFINED_CC"
    machine, triple, problem = platform(cc)
    if triple is None:
        return False, problem
    runtime_bitcode, provided, problem = _ss_runtime_bitcode(triple)
    if runtime_bitcode is None:
        return False, problem
    missing = sorted(needed_runtime(ir_text) - provided)
    missing += sorted(set(re.findall(r'c"([a-zA-Z]+\.[A-Za-z0-9.]+)\|', ir_text)) - runtime_host_targets(triple))
    if missing:
        return False, ("R901 this program needs " + ", ".join(f"`{n}`" for n in missing) + ", which the runtime "
                       f"in SemanticScript does not provide yet on `{machine}` (docs/runtime-in-semanticscript.md); run "
                       "it with `refined run`")
    mod, _dot, op = entry.partition(".")
    from .codegen import function_name
    program = (_imported(ir_text, triple) + "\n; the program's entry, which the runtime's `refined_entry` runs "
               "(D-124)\ndefine i32 @refined_program_main() {\nentry:\n"
               f'  %code = call i32 @"{function_name(mod, op)}"()\n  ret i32 %code\n}}\n')
    with tempfile.TemporaryDirectory() as d:
        obj = os.path.join(d, "program.o")
        with open(obj, "wb") as fh:
            fh.write(_whole_program(runtime_bitcode, program, triple))
        proc = subprocess.run(_link_command(cc, triple, output, [obj]), capture_output=True, text=True)
        if proc.returncode != 0:
            return False, f"linking failed:\n{proc.stdout}{proc.stderr}"
        return True, f"linked {output} (the runtime in SemanticScript, no C library, {machine})"


def runtime_object(output: str) -> tuple[bool, str]:
    """D-142: the runtime in SemanticScript as a standalone object for the C compiler's platform, every `abi c`
    operation an external symbol (`refined_entry`, `refined_trap`, `memcpy`, ...), the program's
    `refined_program_main` left for the object linked with it to define. stage0's C links it."""
    cc = find_cc()
    if cc is None:
        return False, "no C compiler to link with: install one (cc, gcc, or clang) or set REFINED_CC"
    machine, triple, problem = platform(cc)
    if triple is None:
        return False, problem
    runtime_bitcode, _provided, problem = _ss_runtime_bitcode(triple)
    if runtime_bitcode is None:
        return False, problem
    _init()
    module = llvm.parse_bitcode(runtime_bitcode)
    tm = llvm.Target.from_triple(triple).create_target_machine(reloc="pic", codemodel="default", opt=2)
    module.triple = triple
    module.data_layout = str(tm.target_data)
    _simplify(module, tm)
    module.verify()
    data = tm.emit_object(module)
    with open(output, "wb") as fh:
        fh.write(data)
    return True, f"wrote {output} (the runtime in SemanticScript, {len(data)} bytes, {machine})"


def build(ir_text: str | None, output: str, triple: str | None, kind: str, entry: str | None = None) -> int:
    if kind == "runtime":
        ok, message = runtime_object(output)
        sys.stdout.write(message + "\n")
        return 0 if ok else 1
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
