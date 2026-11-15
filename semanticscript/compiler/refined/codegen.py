"""LLVM backend for the refined front end.

Generates LLVM IR straight from the checked refined model (no legacy compiler,
no lowering bridge). It compiles only what is reachable from the roots it is
given (the project entry, or one test), so a module that uses features the
backend does not support yet only blocks programs that actually reach it.

Value representation:
- integers, `Byte`, `ExitCode`: fixed-width integers; `Bool`: i1; floats: f32/f64
- `String`: {i8* bytes, i64 length} (not NUL-terminated, LR-27)
- records: a literal struct of their fields, by value
- enums (including error enums) whose payloads are all integer-like, `Bool`, or payload-free enums:
  {i32 tag, i64 payload}; any other enum: {i32 tag, one field per variant that has a payload}
- operation references: function pointers

Calling convention: an operation that raises returns {i1 failed, output, error};
one that does not returns its output (or void).

Run-time rules enforced here (LR-12, LR-22, LR-38): overflow, division by zero,
narrowing conversions, out-of-range shifts, `maxIterations` (counted as returns
to the loop header from inside the loop), and `maxRecursion`. Each traps through
`refined_trap` with a message naming the source.

Tasks run in parallel (D-31): `start` fills a frame with the task's arguments
and hands the runtime a thunk that runs the task on its own thread; `join`
waits for it and reads its results back from the frame. Task groups, `cancel`,
and `awaitSlot` are runtime calls (tasks.py). Recursion depth and the stack
floor are checked per thread. Cleanups registered with
`defer` run at every later `return`, newest first. A generic operation is
compiled once per set of type arguments its instances name.

Library targets that need the host (files, sockets, processes, the clock,
maps, sets, channels, byte buffers, HTTP) go through one callback,
`refined_host`: arguments are flattened into 64-bit slots and the runtime
dispatches by name (host.py). Values the host owns (handles) are `i64`.

Every program that checks clean compiles; R901 remains only as a guard against a
backend defect (a target or type the backend does not know).
"""
from __future__ import annotations

from typing import Optional

from llvmlite import ir

from . import shapes as S
from .diagnostics import Diagnostic
from .check import TEST_OFFSET
from .runtime import default_triple
from .host import HANDLERS as HOST_TARGETS
from .library import INTEGER_RANGES, INTEGER_TYPES as INTEGER_TARGET_TYPES, LINUX_CALLS, STATE_BYTES, SYSTEM_CALLS
from .semantics import (CallInfo, Module, OpInfo, World, abi_symbol, library_symbol, library_variadic, pair_record, grant_scope, instance_scope, resolve_type,
                        resolve_variant, type_params_of)

I1, I8, I16, I32, I64 = ir.IntType(1), ir.IntType(8), ir.IntType(16), ir.IntType(32), ir.IntType(64)
F32, F64 = ir.FloatType(), ir.DoubleType()
PTR = I8.as_pointer()
STR = ir.LiteralStructType([PTR, I64])
ENUM = ir.LiteralStructType([I32, I64])
INT_TYPES = {"Int8": I8, "Int16": I16, "Int32": I32, "Int64": I64, "UInt8": I8, "UInt16": I16, "UInt32": I32,
             "UInt64": I64, "Byte": I8, "ExitCode": I32}
UNSIGNED = {"UInt8", "UInt16", "UInt32", "UInt64", "Byte"}

# callbacks provided by the runtime (runtime.py)
CALLBACKS = {
    "refined_trap": ir.FunctionType(ir.VoidType(), [PTR, I64]),
    "refined_write": ir.FunctionType(I32, [I32, PTR, I64, I32]),
    "refined_write_int": ir.FunctionType(I32, [I32, I64, I32]),
    "refined_bytes_equal": ir.FunctionType(I32, [PTR, I64, PTR, I64]),
    "refined_assert_int": ir.FunctionType(ir.VoidType(), [I64, I64, PTR, I64]),
    "refined_assert_true": ir.FunctionType(ir.VoidType(), [I32, PTR, I64]),
    "refined_assert_str": ir.FunctionType(ir.VoidType(), [PTR, I64, PTR, I64, PTR, I64]),
    "refined_fail": ir.FunctionType(ir.VoidType(), [PTR, I64, PTR, I64]),
    "refined_region_new": ir.FunctionType(PTR, [I64, PTR, I64]),
    "refined_region_alloc": ir.FunctionType(PTR, [PTR, I64]),
    "refined_region_remaining": ir.FunctionType(I64, [PTR]),
    "refined_handle_region": ir.FunctionType(PTR, [I64]),
    "refined_region_free": ir.FunctionType(ir.VoidType(), [PTR]),
    "refined_write_float": ir.FunctionType(I32, [I32, F64, I32]),
    "refined_format_int": ir.FunctionType(PTR, [I64, PTR, I64.as_pointer()]),
    "refined_find": ir.FunctionType(I64, [PTR, I64, PTR, I64]),
    "refined_parse_int": ir.FunctionType(I32, [PTR, I64, I64.as_pointer()]),
    # D-91: a Float64 as the shortest text that reads back as it, and decimal text as a Float64
    "refined_format_float": ir.FunctionType(PTR, [F64, PTR, I64.as_pointer()]),
    "refined_parse_float": ir.FunctionType(I32, [PTR, I64, F64.as_pointer()]),
    "refined_host": ir.FunctionType(I32, [PTR, I64, I64.as_pointer(), I64.as_pointer(), I64.as_pointer()]),
    "refined_task_frame": ir.FunctionType(PTR, [I64]),
    "refined_task_spawn": ir.FunctionType(I64, [PTR, PTR, I64]),
    "refined_task_join": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_task_cancel": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_task_release": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_group_new": ir.FunctionType(I64, [I64]),
    "refined_group_await": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_group_join": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_group_cancel": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_group_free": ir.FunctionType(ir.VoidType(), [I64]),
    # D-48: a failing task reports its error to its group (ignored outside a group); a group's join reads it back
    "refined_task_fail": ir.FunctionType(ir.VoidType(), [PTR, I64]),
    "refined_group_error": ir.FunctionType(I32, [I64, PTR, I64]),
    "refined_recursion_enter": ir.FunctionType(I32, [I64, I64, I64]),
    "refined_recursion_leave": ir.FunctionType(ir.VoidType(), [I64]),
    "refined_frame_push": ir.FunctionType(ir.VoidType(), [PTR, I64]),
    "refined_frame_pop": ir.FunctionType(ir.VoidType(), []),
    # instrumentation (only when compiled with --trace, --coverage, or --debug): one call on entering each block,
    # with the block's name, and for --debug the addresses and a description of the operation's values
    "refined_block": ir.FunctionType(ir.VoidType(), [PTR, I64, PTR.as_pointer(), I64, PTR, I64]),
}
TEST_CALLBACKS = ("refined_assert_int", "refined_assert_true", "refined_assert_str", "refined_fail", "refined_block")
HOST_GENERICS = ("map.Map", "set.Set", "channel.Channel", "ffi.Function")
# list.List value: pointer to {length, capacity, data, region}
# {length, capacity, data, region, identity}: the identity is unique per list (D-100), so a position from an
# indexed list carries it and is refused by any other list
LIST_HEADER = ir.LiteralStructType([I64, I64, PTR, PTR, I64])
POSITION_BITS = 32
LIST = LIST_HEADER.as_pointer()


class _AsmModule(ir.Module):
    """An LLVM module that can carry module-level assembly: the few routines of the runtime on Linux that switch
    stacks, and its process entry `_start` (D-139)."""

    def __init__(self, name: str = ""):
        super().__init__(name=name)
        self.asm_parts: dict[str, list[str]] = {}

    def _get_body_lines(self):
        lines = [f'module asm "{line}"' for part in self.asm_parts.values() for line in part]
        return lines + super()._get_body_lines()


def target_os(triple: str) -> str:
    """`windows`, `linux`, or `other`, from an LLVM target triple."""
    if "windows" in triple or "mingw" in triple or "win32" in triple:
        return "windows"
    if "linux" in triple:
        return "linux"
    return "other"


# D-139: the runtime's own stacks on Linux x86_64 (System V): the callee-saved registers go on the running stack,
# its stack pointer is kept at the save slot, and the resumed stack pops them back.
_X86_64_STACKS = [
    ".text",
    ".p2align 4",
    ".globl refined_switch_stack",
    ".type refined_switch_stack,@function",
    "refined_switch_stack:",
    "  pushq %rbp", "  pushq %rbx", "  pushq %r12", "  pushq %r13", "  pushq %r14", "  pushq %r15",
    "  movq %rsp, (%rdi)",
    "  movq %rsi, %rsp",
    "  popq %r15", "  popq %r14", "  popq %r13", "  popq %r12", "  popq %rbx", "  popq %rbp",
    "  retq",
    ".p2align 4",
    ".globl refined_start_stack",
    ".type refined_start_stack,@function",
    "refined_start_stack:",
    "  pushq %rbp", "  pushq %rbx", "  pushq %r12", "  pushq %r13", "  pushq %r14", "  pushq %r15",
    "  movq %rsp, (%rdi)",
    "  movq %rsi, %rsp",
    "  movq %rcx, %rdi",
    "  xorl %ebp, %ebp",
    "  callq *%rdx",
    "  ud2",
    ".p2align 4",
    ".globl refined_run_on_stack",
    ".type refined_run_on_stack,@function",
    "refined_run_on_stack:",
    "  pushq %rbp",
    "  movq %rsp, %rbp",
    "  movq %rdi, %rsp",
    "  callq *%rsi",
    "  movq %rbp, %rsp",
    "  popq %rbp",
    "  retq",
]
# the same on AArch64 (AAPCS64): x19 to x30 and d8 to d15 are the callee-saved registers
_AARCH64_SAVE = ["  sub sp, sp, #160", "  stp x19, x20, [sp, #0]", "  stp x21, x22, [sp, #16]",
                 "  stp x23, x24, [sp, #32]", "  stp x25, x26, [sp, #48]", "  stp x27, x28, [sp, #64]",
                 "  stp x29, x30, [sp, #80]", "  stp d8, d9, [sp, #96]", "  stp d10, d11, [sp, #112]",
                 "  stp d12, d13, [sp, #128]", "  stp d14, d15, [sp, #144]", "  mov x9, sp", "  str x9, [x0]"]
_AARCH64_STACKS = [
    ".text",
    ".p2align 4",
    ".globl refined_switch_stack",
    "refined_switch_stack:",
    *_AARCH64_SAVE,
    "  mov sp, x1",
    "  ldp x19, x20, [sp, #0]", "  ldp x21, x22, [sp, #16]", "  ldp x23, x24, [sp, #32]",
    "  ldp x25, x26, [sp, #48]", "  ldp x27, x28, [sp, #64]", "  ldp x29, x30, [sp, #80]",
    "  ldp d8, d9, [sp, #96]", "  ldp d10, d11, [sp, #112]", "  ldp d12, d13, [sp, #128]",
    "  ldp d14, d15, [sp, #144]", "  add sp, sp, #160",
    "  ret",
    ".p2align 4",
    ".globl refined_start_stack",
    "refined_start_stack:",
    *_AARCH64_SAVE,
    "  mov sp, x1",
    "  mov x0, x3",
    "  mov x29, xzr",
    "  blr x2",
    "  brk #0",
    ".p2align 4",
    ".globl refined_run_on_stack",
    "refined_run_on_stack:",
    "  stp x29, x30, [sp, #-16]!",
    "  mov x29, sp",
    "  mov sp, x0",
    "  blr x1",
    "  mov sp, x29",
    "  ldp x29, x30, [sp], #16",
    "  ret",
]
# D-139: the process entry of a Linux executable with no C library: the kernel starts it with the stack holding
# argc, argv, and envp; `refined_entry` is given that address and the stack aligned for a call.
_X86_64_START = [
    ".text",
    ".p2align 4",
    ".globl _start",
    ".type _start,@function",
    "_start:",
    "  xorl %ebp, %ebp",
    "  movq %rsp, %rdi",
    "  andq $-16, %rsp",
    "  callq refined_entry",
    "  ud2",
]
_AARCH64_START = [
    ".text",
    ".p2align 4",
    ".globl _start",
    ".type _start,@function",
    "_start:",
    "  mov x29, xzr",
    "  mov x30, xzr",
    "  mov x0, sp",
    "  and x9, x0, #-16",
    "  mov sp, x9",
    "  bl refined_entry",
    "  brk #0",
]
# D-163: setjmp's and longjmp's routines. The buffer (glibc's __jmp_buf_tag, 200 bytes on x86_64 and 312 on AArch64,
# opaque to the program) holds, on x86_64 Linux, rbx rbp r12 r13 r14 r15, the caller's stack pointer, and the return
# address (on Windows x64 also rdi, rsi, and xmm6 to xmm15, which its convention keeps); on AArch64, Linux and
# Windows alike, x19 to x30, sp, and d8 to d15 (D-170). The signal mask is neither kept nor restored (sigsetjmp's
# `savemask` is noted and ignored).
_CONTEXT_ROUTINES = {
    ("x86_64", "linux", "save"): "\n".join([
        "movq %rbx, 0(%rdi)", "movq %rbp, 8(%rdi)", "movq %r12, 16(%rdi)", "movq %r13, 24(%rdi)",
        "movq %r14, 32(%rdi)", "movq %r15, 40(%rdi)", "leaq 8(%rsp), %rdx", "movq %rdx, 48(%rdi)",
        "movq (%rsp), %rdx", "movq %rdx, 56(%rdi)", "movl $$0, 64(%rdi)", "xorl %eax, %eax", "retq"]),
    ("x86_64", "linux", "resume"): "\n".join([
        "movq 0(%rdi), %rbx", "movq 8(%rdi), %rbp", "movq 16(%rdi), %r12", "movq 24(%rdi), %r13",
        "movq 32(%rdi), %r14", "movq 40(%rdi), %r15", "movq 48(%rdi), %rsp", "movl %esi, %eax", "testl %eax, %eax",
        "jnz 1f", "incl %eax", "1:", "jmpq *56(%rdi)"]),
    ("x86_64", "windows", "save"): "\n".join([
        "movq %rbx, 0(%rcx)", "movq %rbp, 8(%rcx)", "movq %r12, 16(%rcx)", "movq %r13, 24(%rcx)",
        "movq %r14, 32(%rcx)", "movq %r15, 40(%rcx)", "leaq 8(%rsp), %rdx", "movq %rdx, 48(%rcx)",
        "movq (%rsp), %rdx", "movq %rdx, 56(%rcx)", "movq %rdi, 64(%rcx)", "movq %rsi, 72(%rcx)",
        "movdqu %xmm6, 80(%rcx)", "movdqu %xmm7, 96(%rcx)", "movdqu %xmm8, 112(%rcx)", "movdqu %xmm9, 128(%rcx)",
        "movdqu %xmm10, 144(%rcx)", "movdqu %xmm11, 160(%rcx)", "movdqu %xmm12, 176(%rcx)",
        "movdqu %xmm13, 192(%rcx)", "movdqu %xmm14, 208(%rcx)", "movdqu %xmm15, 224(%rcx)", "xorl %eax, %eax",
        "retq"]),
    ("x86_64", "windows", "resume"): "\n".join([
        "movq 0(%rcx), %rbx", "movq 8(%rcx), %rbp", "movq 16(%rcx), %r12", "movq 24(%rcx), %r13",
        "movq 32(%rcx), %r14", "movq 40(%rcx), %r15", "movq 64(%rcx), %rdi", "movq 72(%rcx), %rsi",
        "movdqu 80(%rcx), %xmm6", "movdqu 96(%rcx), %xmm7", "movdqu 112(%rcx), %xmm8", "movdqu 128(%rcx), %xmm9",
        "movdqu 144(%rcx), %xmm10", "movdqu 160(%rcx), %xmm11", "movdqu 176(%rcx), %xmm12",
        "movdqu 192(%rcx), %xmm13", "movdqu 208(%rcx), %xmm14", "movdqu 224(%rcx), %xmm15",
        "movq 48(%rcx), %rsp", "movl %edx, %eax", "testl %eax, %eax", "jnz 1f", "incl %eax", "1:",
        "jmpq *56(%rcx)"]),
    ("aarch64", "linux", "save"): "\n".join([
        "stp x19, x20, [x0, #0]", "stp x21, x22, [x0, #16]", "stp x23, x24, [x0, #32]", "stp x25, x26, [x0, #48]",
        "stp x27, x28, [x0, #64]", "stp x29, x30, [x0, #80]", "mov x2, sp", "str x2, [x0, #104]",
        "stp d8, d9, [x0, #112]", "stp d10, d11, [x0, #128]", "stp d12, d13, [x0, #144]", "stp d14, d15, [x0, #160]",
        "str wzr, [x0, #176]", "mov w0, #0", "ret"]),
    ("aarch64", "linux", "resume"): "\n".join([
        "ldp x19, x20, [x0, #0]", "ldp x21, x22, [x0, #16]", "ldp x23, x24, [x0, #32]", "ldp x25, x26, [x0, #48]",
        "ldp x27, x28, [x0, #64]", "ldp x29, x30, [x0, #80]", "ldr x2, [x0, #104]", "mov sp, x2",
        "ldp d8, d9, [x0, #112]", "ldp d10, d11, [x0, #128]", "ldp d12, d13, [x0, #144]", "ldp d14, d15, [x0, #160]",
        "cmp w1, #0", "csinc w0, w1, wzr, ne", "br x30"]),
}
# D-166: a thread's start: clone (CLONE_VM, FS, FILES, SIGHAND, THREAD, SYSVSEM, SETTLS, PARENT_SETTID, and
# CHILD_CLEARTID) onto a new stack with the record and the function on it; the new thread calls the function
# (refined_c_thread_main, which the compiler passes) with the record and ends
# with the exit system call (its stack and record are the joiner's to give back)
_THREAD_START = {
    "x86_64": [".text", ".p2align 4", ".globl refined_start_thread", ".type refined_start_thread,@function",
               "refined_start_thread:", "  subq $16, %rdi", "  movq %rcx, (%rdi)", "  movq %r8, 8(%rdi)",
               "  movq %rdx, %r10", "  movq %rsi, %r8", "  movq %rdi, %rsi", "  movl $0x3d0f00, %edi",
               "  movq %r10, %rdx", "  movl $56, %eax", "  syscall", "  testq %rax, %rax", "  jnz 1f",
               "  xorl %ebp, %ebp", "  movq (%rsp), %rdi", "  movq 8(%rsp), %rax", "  andq $-16, %rsp",
               "  callq *%rax", "  movl $60, %eax", "  xorl %edi, %edi", "  syscall", "  ud2", "1:", "  retq"],
    "aarch64": [".text", ".p2align 4", ".globl refined_start_thread", ".type refined_start_thread,@function",
                "refined_start_thread:", "  sub x0, x0, #16", "  str x3, [x0]", "  str x4, [x0, #8]", "  mov x4, x2",
                "  mov x3, x1", "  mov x1, x0", "  movz x0, #0x0f00", "  movk x0, #0x3d, lsl #16", "  mov x8, #220",
                "  svc #0", "  cbnz x0, 1f", "  ldr x0, [sp]", "  ldr x9, [sp, #8]", "  mov x29, xzr", "  mov x30, xzr",
                "  blr x9", "  mov x0, #0", "  mov x8, #93", "  svc #0", "  brk #0", "1:", "  ret"],
}
class _LongFloat(ir.Type):
    """D-174: an LLVM floating type llvmlite does not name (x86_fp80, fp128), spelled as LLVM spells it."""

    def __init__(self, spelling: str):
        self.spelling = spelling

    def _to_string(self) -> str:
        return self.spelling

    def __eq__(self, other) -> bool:
        return isinstance(other, _LongFloat) and other.spelling == self.spelling

    def __hash__(self) -> int:
        return hash(self.spelling)


def _glibc_messages() -> list:
    """D-172: strerror's message for each number from 0 to 4095 that glibc has one for (None for the rest), when this
    machine's C library is glibc; an empty list anywhere else."""
    import os as host_os
    import platform as host
    if host.libc_ver()[0] != "glibc":
        return []
    found = []
    for number in range(4096):
        text = host_os.strerror(number)
        found.append(None if text == f"Unknown error {number}" else text)
    while found and found[-1] is None:
        found.pop()
    return found


def _host_assembles_x86() -> bool:
    """Whether this machine's LLVM can assemble x86 instructions: llvmlite registers only the host's own assembler
    parser, so an x86_64 host can and an ARM64 one cannot (D-170)."""
    import platform as host
    return host.machine().lower() in ("amd64", "x86_64", "x64")


# D-147: what a Linux signal handler returns through (SA_RESTORER): the rt_sigreturn system call
_X86_64_RESTORER = [
    ".text",
    ".p2align 4",
    ".globl refined_signal_restorer",
    ".type refined_signal_restorer,@function",
    "refined_signal_restorer:",
    "  movq $15, %rax",
    "  syscall",
    "  ud2",
]
_AARCH64_RESTORER = [
    ".text",
    ".p2align 4",
    ".globl refined_signal_restorer",
    ".type refined_signal_restorer,@function",
    "refined_signal_restorer:",
    "  mov x8, #139",
    "  svc #0",
    "  brk #0",
]


class _Callbacks:
    """The runtime functions compiled code calls, declared when first used. In a program that implements the runtime
    (D-124) a callback its `abi c` operations define is that operation, so the runtime calls itself directly."""

    def __init__(self, backend: "Backend"):
        self.be = backend
        self.made: dict[str, ir.Value] = {}

    def __getitem__(self, name: str):
        if name not in self.made:
            self.made[name] = self.be.callback(name)
        return self.made[name]


class Unsupported(Exception):
    def __init__(self, file: str, line: int, message: str):
        super().__init__(message)
        self.file, self.line, self.message = file, line, message


def _same_shape(got: ir.FunctionType, want: ir.FunctionType) -> bool:
    """Whether two function types agree but for what their pointers point at (LLVM's pointers are opaque)."""
    def same(a, b) -> bool:
        return a == b or (isinstance(a, ir.PointerType) and isinstance(b, ir.PointerType))
    return len(got.args) == len(want.args) and same(got.return_type, want.return_type) and \
        all(same(a, b) for a, b in zip(got.args, want.args))


def function_name(module: str, op: str) -> str:
    return f"{module}.{op}"


class Backend:
    def __init__(self, world: World, options: Optional[dict] = None):
        self.world = world
        self.options = dict(options or {})
        self.instrument = bool(self.options.get("trace") or self.options.get("coverage") or self.options.get("debug"))
        self.block_names: list[str] = []  # every block compiled, for coverage reports
        self.module = _AsmModule(name="refined")
        # the target the module is compiled for: the JIT's own, or the executable's (D-138: `system` targets are
        # the operating system's of this triple, and `system.linux` is a constant of it)
        self.module.triple = self.options.get("triple") or default_triple()
        self.os = target_os(self.module.triple)
        self.functions: dict[tuple[str, str], ir.Function] = {}
        self.pending: list[tuple[Module, OpInfo, ir.Function, dict]] = []
        self.strings: dict[bytes, ir.GlobalVariable] = {}
        # D-123: the operations exported to C, by symbol
        self.abi = {abi_symbol(ent): (m.short, name) for m in world.modules.values() for name, ent in m.ops.items()
                    if abi_symbol(ent) is not None}
        # D-153: the functions of the runtime's C library, by their C names
        self.library = {library_symbol(ent): (m.short, name) for m in world.modules.values()
                        for name, ent in m.ops.items() if library_symbol(ent) is not None}
        # D-124: a program that defines runtime functions is the runtime. Its operations keep no shadow call stack
        # and count recursion in place, since those calls would reach the runtime itself
        self.bare = bool(set(self.abi) & set(CALLBACKS))
        self.callbacks = _Callbacks(self)
        self.tables: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.depth: dict[str, int] = {}
        self._types: dict[str, ir.Type] = {}
        if not self.options.get("runtime_object"):  # the program linked with the runtime defines it
            self._stack_guard()

    def callback(self, name: str):
        """A runtime function: the program's own `abi c` operation of that symbol when it is the runtime, otherwise a
        declaration the runtime (runtime.py under the JIT, semanticscript/runtime in an executable) resolves."""
        want = CALLBACKS[name]
        # the runtime's own tests, under `refined test`, report through the test runner's callbacks; only the
        # runtime object built for an executable calls its own assertions and instrumentation (D-134)
        own = self.options.get("runtime_object") or name not in TEST_CALLBACKS
        if self.bare and name in self.abi and own:
            mod, op = self.abi[name]
            fn = self.function_for(mod, op, None, 0)
            return fn
        return ir.Function(self.module, want, name=name)

    def system_function(self, target: str) -> ir.Function:
        """D-122: the operating system's function behind a `system` target, declared by its own name. A standalone
        executable imports it (native.py marks the declaration `dllimport`); the JIT binds it in this process."""
        symbol, sig = SYSTEM_CALLS[target]
        fn = self.module.globals.get(symbol)
        if fn is None:
            fn = ir.Function(self.module, self.fn_type(sig, "", 0), name=symbol)
        return fn

    def c_library(self) -> ir.GlobalVariable:
        """D-153: the table of the runtime's C library, every `abi library` operation sorted by name: the count, then
        each name's address, its length, and the function's address (three words each)."""
        g = self.module.globals.get("refined.c.library")
        if g is not None:
            return g
        rows = []
        for symbol in sorted(self.library, key=lambda t: t.encode("utf-8")):
            fn = self.library_function(symbol)
            self.string(symbol)
            data = symbol.encode("utf-8")
            rows.append([self.strings[data].gep([I32(0), I32(0)]), I64(len(data)), fn.bitcast(PTR)])
        row = ir.LiteralStructType([PTR, I64, PTR])
        table = ir.LiteralStructType([I64, ir.ArrayType(row, len(rows))])
        g = ir.GlobalVariable(self.module, table, "refined.c.library")
        g.initializer = ir.Constant(table, [I64(len(rows)), ir.Constant(ir.ArrayType(row, len(rows)),
                                                                        [ir.Constant(row, r) for r in rows])])
        g.global_constant = True
        g.linkage = "internal"
        return g

    def long_double(self) -> ir.Type:
        """D-174: C's long double for the module's target: x86_fp80 on x86_64 Linux, fp128 on AArch64 Linux, double
        elsewhere (Windows's long double is a double)."""
        arch = self.linux_arch()
        if arch == "x86_64":
            return _LongFloat("x86_fp80")
        if arch == "aarch64":
            return _LongFloat("fp128")
        return F64

    def error_messages(self) -> ir.GlobalVariable:
        """D-172: strerror's table: the count, then each number's message (a C string) or null. The messages are
        glibc's own, read when the compiler runs on a glibc system (os.strerror calls glibc's strerror there);
        anywhere else the table is empty and strerror says `Unknown error N`."""
        g = self.module.globals.get("refined.c.errors")
        if g is not None:
            return g
        messages = _glibc_messages()
        entries = []
        for number, text in enumerate(messages):
            if text is None:
                entries.append(ir.Constant(PTR, None))
                continue
            data = bytearray(text.encode("utf-8") + b"\0")
            arr = ir.ArrayType(I8, len(data))
            cell = ir.GlobalVariable(self.module, arr, name=f"refined.c.error.{number}")
            cell.global_constant = True
            cell.linkage = "private"
            cell.initializer = ir.Constant(arr, data)
            entries.append(cell.bitcast(PTR))
        table = ir.LiteralStructType([I64, ir.ArrayType(PTR, len(entries))])
        g = ir.GlobalVariable(self.module, table, "refined.c.errors")
        g.initializer = ir.Constant(table, [I64(len(entries)), ir.Constant(ir.ArrayType(PTR, len(entries)), entries)])
        g.global_constant = True
        g.linkage = "internal"
        return g

    def library_function(self, symbol: str) -> ir.Function:
        """The function a C caller calls for a name of the runtime's C library: the operation's own, except where
        it takes or gives a record of two numbers (D-157, D-175), which a wrapper passes as the C ABI passes the
        struct (`pair_abi`)."""
        mod, op = self.library[symbol]
        fn = self.function_for(mod, op, None, 0)
        if not fn.name.endswith(".pair"):
            return fn
        wrapper = self.module.globals.get(f"refined.c.{symbol}")
        if wrapper is not None:
            return wrapper
        info = self.world.modules[mod].op_infos[op]
        sig = info.sig
        out_kind = pair_record(self.world, sig.output)
        in_kinds = [pair_record(self.world, p.type) for p in sig.inputs]
        sret = out_kind is not None and self.pair_abi(out_kind)[1] == "memory"
        params = ([PTR] if sret else []) + [self.pair_abi(k)[0] if k else t
                                            for k, t in zip(in_kinds, fn.ftype.args)]
        ret = PTR if sret else (self.pair_abi(out_kind)[0] if out_kind else fn.ftype.return_type)
        wrapper = ir.Function(self.module, ir.FunctionType(ret, params), name=f"refined.c.{symbol}")
        wb = ir.IRBuilder(wrapper.append_basic_block("entry"))
        given = list(wrapper.args[1:] if sret else wrapper.args)
        inner = [self.pair_from_abi(wb, a, k, t) if k else a for a, k, t in zip(given, in_kinds, fn.ftype.args)]
        value = wb.call(fn, inner)
        if sret:
            out = wrapper.args[0]
            wb.store(value, wb.bitcast(out, ir.PointerType(fn.ftype.return_type)), align=8)
            wb.ret(out)
        elif out_kind:
            wb.ret(self.pair_to_abi(wb, value, out_kind, fn.ftype.return_type))
        elif isinstance(ret, ir.VoidType):
            wb.ret_void()
        else:
            wb.ret(value)
        return wrapper

    def pair_abi(self, kind: str) -> tuple:
        """D-175: how the C ABI passes a struct of two numbers (kind "i64", "f64", "f32") on this target: (the
        LLVM type it is passed as, "value" or "memory"). Windows x64 passes a 16-byte struct by reference and returns
        it through memory the caller gives, and a struct of two floats as one integer register; x86_64 Linux packs
        two floats in one vector register and splits two doubles or two longs into two registers; AArch64 (Linux and
        Windows) passes two doubles or two floats in two vector registers (an HFA) and two longs in two integer
        registers."""
        arch = self.module.triple.split("-")[0]
        struct = {"i64": ir.LiteralStructType([I64, I64]), "f64": ir.LiteralStructType([F64, F64]),
                  "f32": ir.LiteralStructType([F32, F32])}[kind]
        if arch == "x86_64" and self.os == "windows":
            if kind == "f32":
                return I64, "value"
            return PTR, "memory"
        if arch == "x86_64" and kind == "f32":
            return ir.VectorType(F32, 2), "value"
        return struct, "value"

    def pair_from_abi(self, b: ir.IRBuilder, value, kind: str, struct):
        """A struct of two numbers as the C ABI passed it, made the record's own value."""
        t = value.type
        if isinstance(t, ir.PointerType):
            return b.load(b.bitcast(value, ir.PointerType(struct)), align=8)
        if isinstance(t, ir.IntType):
            value = b.bitcast(value, ir.VectorType(F32, 2))
            t = value.type
        if isinstance(t, ir.VectorType):
            out = ir.Constant(struct, ir.Undefined)
            out = b.insert_value(out, b.extract_element(value, I32(0)), 0)
            return b.insert_value(out, b.extract_element(value, I32(1)), 1)
        return value

    def pair_to_abi(self, b: ir.IRBuilder, value, kind: str, struct):
        """A record of two numbers made the form the C ABI passes it in (a register's worth; not memory)."""
        abi, _how = self.pair_abi(kind)
        if isinstance(abi, ir.LiteralStructType):
            return value
        vector = ir.Constant(ir.VectorType(F32, 2), ir.Undefined)
        vector = b.insert_element(vector, b.extract_value(value, 0), I32(0))
        vector = b.insert_element(vector, b.extract_value(value, 1), I32(1))
        if isinstance(abi, ir.IntType):
            return b.bitcast(vector, I64)
        return vector

    def machine_state(self) -> ir.GlobalVariable:
        """D-121: one zeroed block of STATE_BYTES for the runtime's process-wide state, shared by every object that
        names it (common linkage)."""
        g = self.module.globals.get("refined_machine_state")
        if g is None:
            arr = ir.ArrayType(I8, STATE_BYTES)
            g = ir.GlobalVariable(self.module, arr, "refined_machine_state")
            g.initializer = ir.Constant(arr, None)
            g.linkage = "common"
            g.align = 16
        return g

    def _stack_guard(self) -> None:
        """`refined_stack_here` gives the runtime an address on the calling thread's stack, from which it sets
        that thread's stack floor; a recursive operation traps when its frame lies below it (LR-12, D-25)."""
        fn = ir.Function(self.module, ir.FunctionType(I64, []), name="refined_stack_here")
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        b.ret(b.ptrtoint(b.alloca(I8, name="probe"), I64))

    # ------------------------------------------------------------ driver

    def build(self, roots: list[tuple[str, str]]) -> ir.Module:
        for mod, op in roots:
            self.function_for(mod, op, None, 1)
        while self.pending:
            m, info, fn, sub = self.pending.pop()
            if self.context_routine(info, fn):
                continue
            OpGen(self, m, info, fn, sub).emit()
        if self.options.get("runtime_object") and "refined_entry" in self.abi and self.linux_arch():
            # D-139: the process entry calls refined_entry
            self.module.asm_parts["start"] = _AARCH64_START if self.linux_arch() == "aarch64" else _X86_64_START
        return self.module

    # ------------------------------------------------------------ the operating system (D-122, D-138, D-139)

    def linux_arch(self) -> str:
        """`x86_64` or `aarch64` for Linux on an architecture the runtime has system calls for (D-138, D-150), else
        empty."""
        if self.os != "linux":
            return ""
        arch = self.module.triple.split("-")[0]
        if arch == "x86_64":
            return "x86_64"
        if arch in ("aarch64", "arm64"):
            return "aarch64"
        return ""

    def linux_x86_64(self) -> bool:
        return self.linux_arch() == "x86_64"

    def off_target(self, b: ir.IRBuilder, out: Optional[ir.Type]):
        """A `system` target of another operating system than the module's: it is never reached (the runtime
        branches on `system.linux`), so it traps, and refers to nothing the linker would have to find."""
        trap = self.module.declare_intrinsic("llvm.trap", fnty=ir.FunctionType(ir.VoidType(), []))
        b.call(trap, [])
        return ir.Constant(out, ir.Undefined) if out is not None else None

    def linux_syscall(self, b: ir.IRBuilder, number: int, values: list, name: str = ""):
        """D-138: a raw Linux system call, the x86_64 `syscall` instruction: the number in rax, the arguments in
        rdi, rsi, rdx, r10, r8, r9, the result (a negative errno for a failure) in rax. D-150: on AArch64 `svc #0`,
        the number (the generic table's, AARCH64_NUMBERS) in x8, the arguments in x0 to x5, the result in x0; `poll`,
        `fork`, and `dup2`, which AArch64 does not have, become `ppoll`, `clone`, and `dup3`."""
        arch = self.linux_arch()
        if arch == "x86_64":
            regs = ["rdi", "rsi", "rdx", "r10", "r8", "r9"][:len(values)]
            constraint = ",".join(["={rax}", "{rax}"] + [f"{{{r}}}" for r in regs] + ["~{rcx}", "~{r11}", "~{memory}"])
            fty = ir.FunctionType(I64, [I64] * (len(values) + 1))
            return b.asm(fty, "syscall", constraint, [I64(number)] + values, side_effect=True)
        if arch != "aarch64":
            return self.off_target(b, I64)
        from .library import AARCH64_NUMBERS
        if name not in AARCH64_NUMBERS:  # a call AArch64 has no number for (`archPrctl`): never reached there
            return self.off_target(b, I64)
        number = AARCH64_NUMBERS[name]
        if name == "poll":  # ppoll(fds, count, timeout or NULL, NULL, 8): milliseconds as a timespec
            spec = b.alloca(ir.ArrayType(I64, 2), name="pollspec")
            ms = values[2]
            secs, rest = b.sdiv(ms, I64(1000)), b.srem(ms, I64(1000))
            b.store(secs, b.gep(spec, [I32(0), I32(0)]))
            b.store(b.mul(rest, I64(1000000)), b.gep(spec, [I32(0), I32(1)]))
            negative = b.icmp_signed("<", ms, I64(0))
            where = b.select(negative, I64(0), b.ptrtoint(spec, I64))
            values = [values[0], values[1], where, I64(0), I64(8)]
        elif name == "fork":  # clone(SIGCHLD, 0, 0, 0, 0)
            values = [I64(17), I64(0), I64(0), I64(0), I64(0)]
        elif name == "dup2":  # dup3(fd, target, 0)
            values = [values[0], values[1], I64(0)]
        regs = ["x0", "x1", "x2", "x3", "x4", "x5"][:len(values)]
        constraint = ",".join(["={x0}", "{x8}"] + [f"{{{r}}}" for r in regs] + ["~{memory}"])
        fty = ir.FunctionType(I64, [I64] * (len(values) + 1))
        return b.asm(fty, "svc #0", constraint, [I64(number)] + values, side_effect=True)

    def context_routine(self, info: OpInfo, fn: ir.Function) -> bool:
        """D-163: an `abi library` operation whose one call is `machine.saveContext` or `machine.resumeContext` is
        setjmp's or longjmp's routine: emitted as a naked function of a few instructions for the module's
        architecture and system (on Windows on ARM, where nothing calls it, it traps)."""
        targets = {ci.entity.value("invokes") for ci in info.calls.values()}
        kind = {"machine.saveContext": "save", "machine.resumeContext": "resume"}
        found = [kind[t] for t in targets if t in kind]
        if not found:
            return False
        if len(info.calls) != 1 or library_symbol(info.entity) is None:
            raise Unsupported(info.module.file, info.entity.line, "`machine.saveContext` or `machine.resumeContext` "
                              "outside an `abi library` operation whose one call it is (D-163)")
        arch = self.module.triple.split("-")[0]
        if arch == "arm64":
            arch = "aarch64"
        system = "linux" if self.linux_arch() else ("windows" if self.os == "windows" else "")
        if arch == "aarch64":
            system = "linux"  # D-170: Windows on ARM keeps the same registers as AAPCS64, so one routine serves both
        text = _CONTEXT_ROUTINES.get((arch, system, found[0]))
        if (arch, system) == ("x86_64", "windows") and not _host_assembles_x86():
            # D-170: LLVM assembles a routine with the target's assembler, which a host of another architecture may
            # not have (llvmlite on ARM64 has only its own); such an object traps there instead
            text = None
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        fn.attributes.add("noinline")
        if text is None:
            # Windows: a program reaches the C library through `ffi` there, which cannot use setjmp's return twice
            b.call(self.module.declare_intrinsic("llvm.trap", fnty=ir.FunctionType(ir.VoidType(), [])), [])
            b.unreachable()
            return True
        fn.attributes.add("naked")
        b.asm(ir.FunctionType(ir.VoidType(), []), text, "~{memory}", [], side_effect=True)
        b.unreachable()
        return True

    def stack_routine(self, name: str, ftype: ir.FunctionType) -> Optional[ir.Function]:
        """D-139: one of the routines that switch stacks, written in the module's assembly for its architecture;
        None where the runtime has none (Windows uses its fibers)."""
        arch = self.module.triple.split("-")[0]
        if arch == "x86_64" and self.os == "linux":
            self.module.asm_parts["stacks"] = _X86_64_STACKS
        elif arch in ("aarch64", "arm64"):
            self.module.asm_parts["stacks"] = _AARCH64_STACKS
        else:
            return None
        fn = self.module.globals.get(name)
        if fn is None:
            fn = ir.Function(self.module, ftype, name=name)
        return fn

    # ------------------------------------------------------------ types

    def ltype(self, canon: Optional[str], file: str = "", line: int = 0) -> ir.Type:
        if canon is None:
            raise Unsupported(file, line, "a value of unknown type")
        if canon in INT_TYPES:
            return INT_TYPES[canon]
        if canon == "Bool":
            return I1
        if canon == "Float64":
            return F64
        if canon == "Float32":
            return F32
        if canon in ("String", "Bytes"):
            return STR
        if canon in ("Region", "machine.Address"):
            return PTR
        if canon == "machine.LongDouble":
            return self.long_double()
        if canon in self._types:
            return self._types[canon]
        info = self.world.type_info(canon)
        if info is None:
            raise Unsupported(file, line, f"type `{canon}`")
        if info.kind == "record" and not info.type_params:
            t = ir.LiteralStructType([self.ltype(ft, file, line) for _n, ft in info.fields])
        elif info.kind in ("enum",) and not info.type_params or (info.kind == "instance" and info.variants
                                                                  and info.generic == "option.Option"):
            layout = self.enum_layout(canon)
            if layout is None:
                t = ENUM
            else:
                t = ir.LiteralStructType([I32] + [self.ltype(p, file, line) for _n, p in info.variants
                                                  if p is not None])
        elif info.kind == "instance" and info.generic == "list.List":
            self.ltype(info.args[0], file, line)  # the element type must be supported too
            t = LIST
        elif info.kind in ("opaque", "resource") or (info.kind == "instance" and info.generic in HOST_GENERICS):
            t = I64  # a deadline, or a handle to a value the host keeps
        elif info.kind == "alias":
            t = self.ltype(info.base, file, line)
        elif info.kind == "operationType" and info.sig is not None:
            t = self.fn_type(info.sig, file, line).as_pointer()
        else:
            raise Unsupported(file, line, f"values of type `{canon}`")
        self._types[canon] = t
        return t

    def enum_layout(self, canon: Optional[str]) -> Optional[dict]:
        """None when every payload fits the narrow layout {i32 tag, i64 payload}; otherwise the field index of
        each payload-carrying variant in the wide layout {i32 tag, payload fields...}."""
        info = self.world.type_info(canon)
        if info is None or not info.variants:
            return None
        if all(p is None or p in INT_TYPES or p == "Bool" or self.tag_only(p) for _n, p in info.variants):
            return None
        out, k = {}, 1
        for n, p in info.variants:
            if p is not None:
                out[n] = k
                k += 1
        return out

    def tag_only(self, canon: Optional[str]) -> bool:
        """An enum none of whose variants carries a payload: stored by its tag alone."""
        info = self.world.type_info(canon)
        return info is not None and info.kind == "enum" and all(p is None for _n, p in info.variants)

    def fn_type(self, sig, file: str, line: int) -> ir.FunctionType:
        params = [self.ltype(p.type, file, line) for p in sig.inputs]
        out = self.ltype(sig.output, file, line) if sig.output else None
        if sig.raises:
            ret = ir.LiteralStructType([I1, out or I8, self.ltype(sig.raises, file, line)])
        else:
            ret = out or ir.VoidType()
        return ir.FunctionType(ret, params)

    # ------------------------------------------------------------ functions, strings, tables

    def function_for(self, mod: str, op: str, file: Optional[str], line: int,
                     sub: Optional[dict] = None) -> ir.Function:
        """The function for an operation; a generic operation needs `sub`, its type arguments."""
        sub = dict(sub or {})
        key = (mod, op, tuple(sorted(sub.items())))
        if key in self.functions:
            return self.functions[key]
        m = self.world.modules[mod]
        info = m.op_infos.get(op)
        if info is None:
            raise Unsupported(file or m.file, line, f"`{mod}.{op}`")
        ent = info.entity
        if info.tparams and set(info.tparams.values()) - set(sub):
            raise Unsupported(m.file, ent.line, f"generic operation `{op}` without type arguments")
        sig = self.world.concrete_sig(info.sig, sub) if sub else info.sig
        name = function_name(mod, op) + (f"<{','.join(sub[k] for k in sorted(sub))}>" if sub else "")
        symbol = abi_symbol(ent)
        if symbol in TEST_CALLBACKS and not self.options.get("runtime_object"):
            symbol = None  # D-134: under `refined test` the test runner's own callbacks keep the name
        name = symbol or name  # D-123: exported to C under its symbol
        if library_symbol(ent) is not None:  # D-153: reached through the C library's table, never by its C name
            name = f"refined.c.{library_symbol(ent)}"
            if pair_record(self.world, sig.output) or any(pair_record(self.world, p.type) for p in sig.inputs):
                name += ".pair"  # D-157, D-175: `library_function` wraps it in the C ABI's form of its structs
        ftype = self.fn_type(sig, m.file, ent.line)
        if library_variadic(ent):  # D-157: `...` after its own arguments
            ftype = ir.FunctionType(ftype.return_type, ftype.args, var_arg=True)
        if self.bare and name in CALLBACKS:
            # D-124: the runtime's own definition of a function compiled code calls has the type those calls have;
            # an address may be declared there as a pointer to what it points at (`i64*` for `machine.Address`)
            want = CALLBACKS[name]
            if not _same_shape(ftype, want):
                raise Unsupported(m.file, ent.line, f"`{name}` with a signature other than {want}, the one compiled "
                                                    "code calls it with")
            ftype = want
        fn = ir.Function(self.module, ftype, name=name)
        self.functions[key] = fn
        self.pending.append((m, info, fn, sub))
        return fn

    def list_counter(self) -> ir.GlobalVariable:
        """The program-wide counter that gives each list its identity (D-100)."""
        g = self.module.globals.get("refined.list.identities")
        if g is None:
            g = ir.GlobalVariable(self.module, I64, "refined.list.identities")
            g.initializer = I64(0)
            g.linkage = "internal"
        return g

    def string(self, text: str) -> ir.Constant:
        data = text.encode("utf-8", "surrogateescape")
        g = self.strings.get(data)
        if g is None:
            arr = ir.ArrayType(I8, max(len(data), 1))
            g = ir.GlobalVariable(self.module, arr, name=f"str.{len(self.strings)}")
            g.global_constant = True
            g.linkage = "private"
            g.initializer = ir.Constant(arr, bytearray(data or b"\0"))
            self.strings[data] = g
        return ir.Constant(STR, [g.gep([I32(0), I32(0)]), I64(len(data))])

    def enum_const(self, canon: str, variant: str, payload: int = 0) -> ir.Constant:
        info = self.world.type_info(canon)
        tag = [n for n, _p in info.variants].index(variant)
        t = self.ltype(canon)
        if t == ENUM:
            return ir.Constant(ENUM, [I32(tag), I64(payload)])
        return ir.Constant(t, [I32(tag)] + [ir.Constant(e, None) for e in t.elements[1:]])

    def table(self, m: Module, name: str) -> tuple[ir.GlobalVariable, int, str]:
        key = (m.short, name)
        ent = m.tables[name]
        from .semantics import resolve_type
        rec = resolve_type(self.world, m, ent.value("rowType"), ent.line, quiet=True)
        info = self.world.type_info(rec)
        rtype = self.ltype(rec, m.file, ent.line)
        rows = sorted(ent.facts("row"), key=lambda r: int(r.text(1)))
        if key not in self.tables:
            consts = []
            for r in rows:
                cells = {c.text(1): c.args[2] for c in ent.facts("cell") if c.text(0) == r.text(0)}
                vals = [self.literal(m, cells[fname], ftype, ent.line) for fname, ftype in info.fields]
                consts.append(ir.Constant(rtype, vals))
            arr = ir.ArrayType(rtype, len(consts))
            g = ir.GlobalVariable(self.module, arr, name=f"table.{m.short}.{name}")
            g.global_constant = True
            g.initializer = ir.Constant(arr, consts)
            self.tables[key] = g
        return self.tables[key], len(rows), rec

    def literal(self, m: Module, tok, canon: str, line: int) -> ir.Constant:
        t = self.ltype(canon, m.file, line)
        info = self.world.type_info(canon)
        base = info.base if info is not None and info.kind == "alias" else canon
        if tok.kind == "string":
            return self.string(tok.value)
        raw = tok.raw
        if raw in ("true", "false"):
            return ir.Constant(I1, 1 if raw == "true" else 0)
        if S.is_variant(raw):
            v = resolve_variant(self.world, m, raw, line, quiet=True)
            # the value's own type: in a generic operation's copy it is the concrete instance (D-92)
            info = self.world.type_info(canon)
            return self.enum_const(canon if info is not None and info.variants else v[0], v[1])
        if S.INT.match(raw):
            return ir.Constant(t, int(raw))
        if S.FLOAT.match(raw):
            return ir.Constant(t, float(raw))
        if S.is_name(raw) and raw in m.ops:
            return self.function_for(m.short, raw, m.file, line)
        if S.is_name(raw) and raw in m.op_instances:
            gen, sub = instance_parts(self.world, m, m.op_instances[raw])
            return self.function_for(m.short, gen, m.file, line, sub)
        raise Unsupported(m.file, line, f"literal `{raw}` of type `{base}`")

    def recursion_id(self, name: str) -> int:
        """A number for each recursive operation; the runtime keeps each thread's depth per number."""
        if name not in self.depth:
            self.depth[name] = len(self.depth) + 1
        return self.depth[name]


def instance_parts(world: World, m: Module, ent) -> tuple[str, dict]:
    """An `operationInstance`: its generic operation's name and the type substitution it names."""
    row = ent.fact("instantiates")
    gen = row.text(0)
    params = list(type_params_of(m.ops[gen]).values())
    args = [resolve_type(world, m, tok.raw, row.line, instance_scope(m, ent), quiet=True) for tok in row.args[1:]]
    return gen, dict(zip(params, args))


class OpGen:
    """Emits the body of one operation or test (once per set of type arguments, for a generic one)."""

    def __init__(self, backend: Backend, m: Module, info: OpInfo, fn: ir.Function, sub: Optional[dict] = None):
        self.be, self.m, self.info, self.fn = backend, m, info, fn
        self.sub = sub or {}
        self.ent = info.entity
        self.world = backend.world
        self.allocas: dict[str, ir.AllocaInstr] = {}
        self.failed: dict[str, ir.AllocaInstr] = {}
        self.blocks: dict[str, ir.Block] = {}
        self.steps: dict[str, list] = {}
        self.order: list[str] = []
        self.kinds: dict[str, str] = {}
        self.within: dict[str, str] = {}
        self.bounds: dict[str, str] = {}
        self.counters: dict[str, ir.AllocaInstr] = {}
        self.indexes: dict[str, ir.AllocaInstr] = {}
        self.edge_cache: dict[tuple[str, str], ir.Block] = {}
        self.depth: Optional[int] = None
        self.max_depth: Optional[int] = None
        self.groups: dict[str, ir.AllocaInstr] = {}
        self.task_handles: dict[str, ir.AllocaInstr] = {}
        self.task_frames: dict[str, ir.AllocaInstr] = {}
        self.thunks: dict[str, tuple[ir.Function, ir.Type]] = {}

    def t(self, canon: Optional[str]) -> Optional[str]:
        """A type with this operation's type parameters replaced by its type arguments."""
        return self.world.concrete(canon, self.sub) if canon is not None else None

    def lt(self, canon: Optional[str], line: int = 0) -> ir.Type:
        return self.be.ltype(self.t(canon), *self.where(line))

    def fn_alloca(self, t: ir.Type, name: str):
        """An alloca in the entry block, so loops do not grow the stack."""
        b = ir.IRBuilder(self.fn.entry_basic_block)
        b.position_at_start(self.fn.entry_basic_block)
        return b.alloca(t, name=name)

    def where(self, line: int) -> tuple[str, int]:
        """Rows from a module's `.test.sem` file carry an offset line number (check.TEST_OFFSET)."""
        if line >= TEST_OFFSET:
            return self.m.file[:-4] + ".test.sem", line - TEST_OFFSET
        return self.m.file, line

    def unsupported(self, line: int, what: str):
        raise Unsupported(*self.where(line), what)

    # ------------------------------------------------------------ setup

    def emit(self) -> None:
        ent = self.ent
        self.regions = [o for o in self.info.owned.values() if o.kind == "region"]
        self.cleanups = {o.name: o for o in self.info.owned.values() if o.kind == "cleanup"}
        self.armed: dict[str, ir.AllocaInstr] = {}
        self.defer_order: list[str] = []
        for r in ent.facts("at"):
            lab = r.text(0)
            if lab not in self.steps:
                self.steps[lab] = []
                self.order.append(lab)
            self.steps[lab].append((r.line, r.text(1), [t.raw for t in r.args[2:]]))
            if r.text(1) == "defer" and r.text(2) not in self.defer_order:
                self.defer_order.append(r.text(2))
        for r in ent.facts("label"):
            lab, fact, val = r.text(0), r.text(1), r.text(2)
            if fact == "loopKind":
                self.kinds[lab] = val
            elif fact == "within":
                self.within[lab] = val
            elif fact == "maxIterations":
                self.bounds[lab] = val
        entry = self.fn.append_basic_block("entry")
        b = ir.IRBuilder(entry)
        for name, bind in self.info.bindings.items():
            if bind.kind == "group":
                continue  # a group is a runtime handle (self.groups)
            self.allocas[name] = b.alloca(self.lt(bind.type, bind.line), name=name)
            if self.be.options.get("debug"):  # the debugger reads every value, so none starts as garbage
                b.store(ir.Constant(self.allocas[name].type.pointee, None), self.allocas[name])
        for name in self.cleanups:
            self.armed[name] = b.alloca(I1, name=f"{name}.armed")
            b.store(I1(0), self.armed[name])
        for o in self.info.owned.values():
            if o.kind == "taskGroup":
                self.groups[o.name] = b.alloca(I64, name=f"{o.name}.group")
                b.store(b.call(self.be.callbacks["refined_group_new"], [I64(int(o.value("maxTasks")))]),
                        self.groups[o.name])
                crow = o.fact("catch")
                if crow is not None and crow.text(0) != "none":
                    self.failed[o.name] = b.alloca(I1, name=f"{o.name}.failed")
                    b.store(I1(0), self.failed[o.name])
            elif o.kind == "task":
                self.task_handles[o.name] = b.alloca(I64, name=f"{o.name}.task")
                b.store(I64(0), self.task_handles[o.name])
                self.task_frames[o.name] = b.alloca(PTR, name=f"{o.name}.frame")
        for name, ci in self.info.calls.items():
            if ci.catch is not None:
                self.failed[name] = b.alloca(I1, name=f"{name}.failed")
        for lab, kind in self.kinds.items():
            if kind != "none" and self.bounds.get(lab) not in (None, "unbounded"):
                self.counters[lab] = b.alloca(I64, name=f"{lab}.passes")
            if kind == "forEach":
                self.indexes[lab] = b.alloca(I64, name=f"{lab}.index")
        params = [p.name for p in self.info.sig.inputs]
        for arg, pname in zip(self.fn.args, params):
            slot = self.allocas[pname]
            b.store(arg if arg.type == slot.type.pointee else b.bitcast(arg, slot.type.pointee), slot)
        for reg in self.regions:
            label = self.be.string(f"region `{reg.name}` of `{self.ent.name}`")
            handle = b.call(self.be.callbacks["refined_region_new"],
                            [I64(int(reg.value("maxBytes"))), b.extract_value(label, 0), b.extract_value(label, 1)])
            b.store(handle, self.allocas[reg.name])
        for c in self.m.constants.values():  # D-103: the module's constants, set on entry like immutable lets
            if c.name in self.allocas and c.fact("value") is not None:
                bind = self.info.bindings[c.name]
                b.store(self.be.literal(self.m, c.fact("value").args[0], self.t(bind.type), c.line), self.allocas[c.name])
        for r in ent.facts("let"):
            if r.text(0) == "none":
                continue
            tok = r.args[2]
            if tok.raw == "unset":
                continue
            bind = self.info.bindings[r.text(0)]
            if tok.kind == "word" and S.is_name(tok.raw) and tok.raw in self.info.bindings:
                b.store(b.load(self.allocas[tok.raw]), self.allocas[bind.name])
            else:
                b.store(self.be.literal(self.m, tok, self.t(bind.type), r.line), self.allocas[bind.name])
        mr = ent.value("maxRecursion")
        if mr not in (None, "none") and self.be.bare:
            # D-124: the runtime counts its own recursion in place, in a counter of its own per operation
            self.depth = self.bare_depth()
            self.max_depth = int(mr)
            d = b.add(b.load(self.depth), I64(1))
            b.store(d, self.depth)
            with b.if_then(b.icmp_signed(">", d, I64(self.max_depth)), likely=False):
                self.trap(b, ent.line, f"`{ent.name}` called itself deeper than maxRecursion {self.max_depth}")
        elif mr not in (None, "none"):
            self.depth = self.be.recursion_id(self.fn.name)
            self.max_depth = int(mr)
            here = b.ptrtoint(b.alloca(I8, name="stack.probe"), I64)
            status = b.call(self.be.callbacks["refined_recursion_enter"], [I64(self.depth), I64(self.max_depth), here])
            with b.if_then(b.icmp_signed("==", status, I32(1)), likely=False):
                self.trap(b, ent.line, f"`{ent.name}` called itself deeper than maxRecursion {self.max_depth}")
            with b.if_then(b.icmp_signed("==", status, I32(2)), likely=False):
                self.trap(b, ent.line, f"`{ent.name}` ran out of stack before reaching maxRecursion "
                          f"{self.max_depth}; lower the bound or recurse less deeply")
        # the shadow call stack a trap prints (stack traces): pushed here, popped at every `return`
        if not self.be.bare:
            file, line = self.where(ent.line)
            frame_name = self.be.string(f"{self.m.short}.{ent.name} "
                                        f"({file.replace(chr(92), '/').rsplit('/', 1)[-1]}:{line})")
            b.call(self.be.callbacks["refined_frame_push"], [b.extract_value(frame_name, 0),
                                                             b.extract_value(frame_name, 1)])
        for lab in self.order:
            self.blocks[lab] = self.fn.append_basic_block(lab)
        b.branch(self.edge(None, "begin"))
        for lab in self.order:
            self.emit_block(lab)

    def bare_depth(self) -> ir.GlobalVariable:
        name = f"{self.fn.name}.depth"
        g = self.be.module.globals.get(name)
        if g is None:
            g = ir.GlobalVariable(self.be.module, I64, name)
            g.initializer = I64(0)
            g.linkage = "internal"
        return g

    def ancestors(self, lab: str) -> set:
        out, cur = set(), self.within.get(lab, "none")
        while cur != "none" and cur not in out:
            out.add(cur)
            cur = self.within.get(cur, "none")
        return out

    def trap(self, b: ir.IRBuilder, line: int, message: str) -> None:
        file, ln = self.where(line)
        text = self.be.string(f"{file}:{ln}: {message}")
        b.call(self.be.callbacks["refined_trap"], [b.extract_value(text, 0), b.extract_value(text, 1)])
        b.unreachable()

    def edge(self, frm: Optional[str], to: str) -> ir.Block:
        """The block that performs any loop bookkeeping for the jump frm -> to, then enters `to`."""
        kind = self.kinds.get(to, "none")
        if kind == "none":
            return self.blocks[to]
        key = (frm or "", to)
        if key in self.edge_cache:
            return self.edge_cache[key]
        blk = self.fn.append_basic_block(f"edge.{frm or 'entry'}.{to}")
        self.edge_cache[key] = blk
        b = ir.IRBuilder(blk)
        back = frm is not None and (frm == to or to in self.ancestors(frm))
        if back:
            if to in self.counters:
                n = b.add(b.load(self.counters[to]), I64(1))
                b.store(n, self.counters[to])
                bound = self.bounds[to]
                limit = I64(int(bound)) if S.INT.match(bound) else b.load(self.allocas[bound])
                over = b.icmp_signed(">", n, limit)
                with b.if_then(over, likely=False):
                    self.trap(b, self.steps[to][0][0], f"loop `{to}` in `{self.ent.name}` returned to its header more "
                              f"than maxIterations {bound} times")
        else:
            if to in self.counters:
                b.store(I64(0), self.counters[to])
            if to in self.indexes:
                b.store(I64(0), self.indexes[to])
        b.branch(self.blocks[to])
        return blk

    # ------------------------------------------------------------ steps

    def instrument_block(self, b: ir.IRBuilder, lab: str) -> None:
        name = f"{self.m.short}.{self.ent.name}:{lab}"
        self.be.block_names.append(name)
        text = self.be.string(name)
        count, values, desc = 0, ir.Constant(PTR.as_pointer(), None), self.be.string("")
        if self.be.options.get("debug"):
            shown = [(n, a) for n, a in self.allocas.items() if self.info.bindings.get(n) is not None]
            kinds = []
            for n, a in shown:
                t = a.type.pointee
                kind = ("i1" if t == I1 else f"i{t.width}" if isinstance(t, ir.IntType) else "f64" if t == F64
                        else "str" if t == STR else self.debug_kind(self.info.bindings[n].type, t))
                kinds.append(f"{n}:{kind}:{self.t(self.info.bindings[n].type)}")
            arr = self.fn_alloca(ir.ArrayType(PTR, max(len(shown), 1)), f"{lab}.debugValues")
            for i, (_n, a) in enumerate(shown):
                b.store(b.bitcast(a, PTR), b.gep(arr, [I32(0), I32(i)]))
            count, values, desc = len(shown), b.gep(arr, [I32(0), I32(0)]), self.be.string(";".join(kinds))
        b.call(self.be.callbacks["refined_block"], [b.extract_value(text, 0), b.extract_value(text, 1), values,
                                                    I64(count), b.extract_value(desc, 0), b.extract_value(desc, 1)])

    def debug_kind(self, canon: Optional[str], t: ir.Type) -> str:
        """D-73: how the debugger reads a record of integer and `Bool` fields (`record(name i64,...)`) and an
        enum in the narrow layout (`enum(name,name*,...)`, `*` marking a variant with a payload)."""
        info = self.world.type_info(canon)
        if info is None:
            return "other"
        if info.kind == "record" and isinstance(t, ir.LiteralStructType) and \
                all(isinstance(e, ir.IntType) for e in t.elements):
            return "record(" + ",".join(f"{n} i{e.width}" for (n, _f), e in zip(info.fields, t.elements)) + ")"
        if info.kind == "enum" and t == ENUM and info.variants:
            return "enum(" + ",".join(n + ("*" if p else "") for n, p in info.variants) + ")"
        return "other"

    def emit_block(self, lab: str) -> None:
        b = ir.IRBuilder(self.blocks[lab])
        if self.be.instrument:
            self.instrument_block(b, lab)
        steps = self.steps[lab]
        i = 0
        while i < len(steps):
            line, verb, a = steps[i]
            if verb == "do":
                self.call(b, self.info.calls[a[0]], line)
            elif verb == "start":
                self.start_task(b, self.info.calls[a[0]], a[2] if a[2] != "none" else None, line)
            elif verb == "join" and a[0] in self.groups:
                b.call(self.be.callbacks["refined_group_join"], [b.load(self.groups[a[0]])])
                if a[0] in self.failed:
                    err = self.allocas[self.info.owned[a[0]].fact("catch").text(0)]
                    got = b.call(self.be.callbacks["refined_group_error"],
                                 [b.load(self.groups[a[0]]), b.bitcast(err, PTR), self.sizeof(b, err.type.pointee)])
                    b.store(b.icmp_signed("!=", got, I32(0)), self.failed[a[0]])
            elif verb == "join":
                self.join_task(b, self.info.calls[a[0]])
            elif verb == "cancel" and a[0] in self.groups:
                b.call(self.be.callbacks["refined_group_cancel"], [b.load(self.groups[a[0]])])
            elif verb == "cancel":
                b.call(self.be.callbacks["refined_task_cancel"], [b.load(self.task_handles[a[0]])])
            elif verb == "awaitSlot":
                b.call(self.be.callbacks["refined_group_await"], [b.load(self.groups[a[0]])])
            elif verb == "defer":
                b.store(I1(1), self.armed[a[0]])
            elif verb == "set":
                b.store(b.load(self.allocas[a[1]]), self.allocas[a[0]])
            elif verb == "goto":
                b.branch(self.edge(lab, a[0]))
            elif verb == "branch" and a[0] == "if":
                b.cbranch(b.load(self.allocas[a[1]]), self.edge(lab, a[-4]), self.edge(lab, a[-1]))
            elif verb == "branch" and a[0] == "ifError":
                b.cbranch(b.load(self.failed[a[1]]), self.edge(lab, a[-4]), self.edge(lab, a[-1]))
            elif verb == "branch" and a[0] == "ifNext":
                self.if_next(b, lab, a, line)
            elif verb == "match":
                self.match(b, lab, a, steps[i + 1:], line)
                return
            elif verb == "return":
                self.ret(b, a, line)
            else:
                self.unsupported(line, f"the `{verb}` step")
            i += 1

    def if_next(self, b: ir.IRBuilder, lab: str, a: list, line: int) -> None:
        coll, item, yes, no = a[1], a[3], a[-4], a[-1]
        idx_ptr = self.indexes[lab]
        idx = b.load(idx_ptr)
        cinfo = self.world.type_info(self.t(self.info.bindings[coll].type)) if coll in self.info.bindings else None
        if cinfo is not None and cinfo.generic in ("map.Map", "set.Set"):
            # D-62, D-93: a map is read key by key, a set item by item, in the order they were first put; the
            # host keeps the order
            handle = b.load(self.allocas[coll])
            gen = cinfo.generic
            more = b.icmp_signed("<", idx, self.host_value(b, f"{gen}.length", [handle], I64, f"{lab}.count"))
            take = self.fn.append_basic_block(f"{lab}.take")
            b.cbranch(more, take, self.edge(lab, no))
            tb = ir.IRBuilder(take)
            et = self.lt(self.info.bindings[item].type, line)
            at = "keyAt" if gen == "map.Map" else "itemAt"
            tb.store(self.host_value(tb, f"{gen}.{at}", [handle, idx], et, f"{lab}.key"), self.allocas[item])
            tb.store(tb.add(idx, I64(1)), idx_ptr)
            tb.branch(self.edge(lab, yes))
            return
        if coll in self.m.tables:
            g, n, _rec = self.be.table(self.m, coll)
            more = b.icmp_signed("<", idx, I64(n))
        elif coll in self.allocas:
            hdr = b.load(self.allocas[coll])
            more = b.icmp_signed("<", idx, b.load(b.gep(hdr, [I32(0), I32(0)])))
        else:
            self.unsupported(line, f"`forEach` over `{coll}`")
        take = self.fn.append_basic_block(f"{lab}.take")
        b.cbranch(more, take, self.edge(lab, no))
        tb = ir.IRBuilder(take)
        if coll in self.m.tables:
            elem = tb.load(tb.gep(g, [I32(0), idx]))
        else:
            et = self.lt(self.info.bindings[item].type, line)
            data = tb.bitcast(tb.load(tb.gep(hdr, [I32(0), I32(2)])), et.as_pointer())
            elem = tb.load(tb.gep(data, [idx]))
        tb.store(elem, self.allocas[item])
        tb.store(tb.add(idx, I64(1)), idx_ptr)
        tb.branch(self.edge(lab, yes))

    def match(self, b: ir.IRBuilder, lab: str, a: list, cases: list, line: int) -> None:
        value = b.load(self.allocas[a[0]])
        layout = self.be.enum_layout(self.t(self.info.bindings[a[0]].type))
        tag = b.extract_value(value, 0)
        payload = b.extract_value(value, 1) if layout is None else None
        unreachable = self.fn.append_basic_block(f"{lab}.nomatch")
        ir.IRBuilder(unreachable).unreachable()
        sw = b.switch(tag, unreachable)
        for cline, _verb, ca in cases:
            v = resolve_variant(self.world, self.m, ca[0], cline, quiet=True)
            info = self.world.type_info(v[0])
            tagn = [n for n, _p in info.variants].index(v[1])
            blk = self.fn.append_basic_block(f"{lab}.case.{v[1]}")
            cb = ir.IRBuilder(blk)
            if ca[2] != "none":
                if layout is None:
                    cb.store(self.narrow(cb, payload, self.t(self.info.bindings[ca[2]].type)), self.allocas[ca[2]])
                else:
                    cb.store(cb.extract_value(value, layout[v[1]]), self.allocas[ca[2]])
            cb.branch(self.edge(lab, ca[-1]))
            sw.add_case(I32(tagn), blk)

    def ret(self, b: ir.IRBuilder, a: list, line: int) -> None:
        # the returned value is read before cleanups run; cleanups run newest first, each at most once
        result = b.load(self.allocas[a[1]]) if a[1] != "none" else None
        owner = self.info.sig.output_owner if a[0] == "ok" else None
        if result is not None and owner not in (None, "caller", "none") and owner in self.allocas:
            # D-108: text in the result is copied into the region the output names, before this operation's own
            # regions are released, so a result built from local text stays valid
            result = self.relocate(b, result, self.info.sig.output, b.load(self.allocas[owner]), line)
        for name in reversed(self.defer_order):
            c = self.cleanups[name]
            armed = self.armed[name]
            with b.if_then(b.load(armed)):
                b.store(I1(0), armed)
                ci = self.info.calls[c.value("runs")]
                self.call(b, ci, c.line)
                if c.value("onError") == "trap" and ci.catch is not None:
                    with b.if_then(b.load(self.failed[ci.entity.name]), likely=False):
                        self.trap(b, c.line, f"cleanup `{name}` in `{self.ent.name}` failed (onError trap)")
        for reg in self.regions:
            if reg.value("released") == "atReturn":
                b.call(self.be.callbacks["refined_region_free"], [b.load(self.allocas[reg.name])])
        for g in self.groups.values():
            b.call(self.be.callbacks["refined_group_free"], [b.load(g)])
        if self.be.bare:
            if self.depth is not None:
                b.store(b.sub(b.load(self.depth), I64(1)), self.depth)
        else:
            b.call(self.be.callbacks["refined_frame_pop"], [])
            if self.depth is not None:
                b.call(self.be.callbacks["refined_recursion_leave"], [I64(self.depth)])
        sig = self.info.sig
        rtype = self.fn.function_type.return_type
        if sig.raises:
            out_t = rtype.elements[1]
            if a[0] == "ok":
                out = result if result is not None else ir.Constant(out_t, 0)
                agg = b.insert_value(ir.Constant(rtype, ir.Undefined), I1(0), 0)
                agg = b.insert_value(agg, out, 1)
                agg = b.insert_value(agg, ir.Constant(rtype.elements[2], None), 2)
            else:
                agg = b.insert_value(ir.Constant(rtype, ir.Undefined), I1(1), 0)
                agg = b.insert_value(agg, ir.Constant(out_t, None), 1)
                agg = b.insert_value(agg, result, 2)
            b.ret(agg)
        elif a[1] == "none":
            b.ret_void()
        else:
            b.ret(result)

    # ------------------------------------------------------------ tasks (D-31)

    def task_thunk(self, ci: CallInfo, line: int) -> tuple[ir.Function, ir.Type]:
        """`void thunk(i8* frame)`: read the task's arguments from the frame, make the call exactly as a `do`
        would, and write its result, failure flag, and error back. The frame is {args..., out?, failed, error?}."""
        name = ci.entity.name
        if name in self.thunks:
            return self.thunks[name]
        fields = [self.lt(typ, l) for _s, typ, _v, _m, l in ci.args]
        if ci.out is not None:
            fields.append(self.lt(ci.out[1], line))
        fields.append(I1)
        if ci.catch is not None:
            fields.append(self.lt(ci.catch[1], line))
        frame_t = ir.LiteralStructType(fields)
        fn = ir.Function(self.be.module, ir.FunctionType(ir.VoidType(), [PTR]), name=f"{self.fn.name}.task.{name}")
        saved = (self.fn, self.allocas, self.failed)
        self.fn, self.allocas, self.failed = fn, {}, {}
        try:
            b = ir.IRBuilder(fn.append_basic_block("entry"))
            frame = b.bitcast(fn.args[0], frame_t.as_pointer())
            for i, (_slot, _typ, value, _m, _l) in enumerate(ci.args):
                if value not in self.allocas:
                    self.allocas[value] = b.alloca(fields[i], name=value)
                    b.store(b.load(b.gep(frame, [I32(0), I32(i)])), self.allocas[value])
            k = len(ci.args)
            if ci.out is not None:
                self.allocas[ci.out[0]] = b.alloca(fields[k], name=ci.out[0])
            if ci.catch is not None:
                self.allocas[ci.catch[0]] = b.alloca(fields[-1], name=ci.catch[0])
                self.failed[name] = b.alloca(I1, name=f"{name}.failed")
            # the call goes in its own block: helpers put their allocas at the top of the entry block
            body = fn.append_basic_block("body")
            b.branch(body)
            b.position_at_end(body)
            self.call(b, ci, line)
            if ci.out is not None:
                b.store(b.load(self.allocas[ci.out[0]]), b.gep(frame, [I32(0), I32(k)]))
                k += 1
            if ci.catch is not None:
                b.store(b.load(self.failed[name]), b.gep(frame, [I32(0), I32(k)]))
                b.store(b.load(self.allocas[ci.catch[0]]), b.gep(frame, [I32(0), I32(k + 1)]))
                err = self.allocas[ci.catch[0]]
                with b.if_then(b.load(self.failed[name]), likely=False):
                    b.call(self.be.callbacks["refined_task_fail"],
                           [b.bitcast(err, PTR), self.sizeof(b, err.type.pointee)])
            else:
                b.store(I1(0), b.gep(frame, [I32(0), I32(k)]))
            b.ret_void()
        finally:
            self.fn, self.allocas, self.failed = saved
        self.thunks[name] = (fn, frame_t)
        return self.thunks[name]

    def start_task(self, b: ir.IRBuilder, ci: CallInfo, group: Optional[str], line: int) -> None:
        thunk, frame_t = self.task_thunk(ci, line)
        raw = b.call(self.be.callbacks["refined_task_frame"], [self.sizeof(b, frame_t)])
        frame = b.bitcast(raw, frame_t.as_pointer())
        for i, (_slot, _typ, value, _m, _l) in enumerate(ci.args):
            b.store(self.arg_value(b, value, ci.entity.line), b.gep(frame, [I32(0), I32(i)]))
        group_handle = b.load(self.groups[group]) if group is not None else I64(0)
        handle = b.call(self.be.callbacks["refined_task_spawn"], [b.bitcast(thunk, PTR), raw, group_handle])
        b.store(handle, self.task_handles[ci.entity.name])
        b.store(raw, self.task_frames[ci.entity.name])

    def join_task(self, b: ir.IRBuilder, ci: CallInfo) -> None:
        name = ci.entity.name
        handle = b.load(self.task_handles[name])
        b.call(self.be.callbacks["refined_task_join"], [handle])
        _thunk, frame_t = self.thunks[name] if name in self.thunks else self.task_thunk(ci, ci.entity.line)
        frame = b.bitcast(b.load(self.task_frames[name]), frame_t.as_pointer())
        k = len(ci.args)
        if ci.out is not None:
            b.store(b.load(b.gep(frame, [I32(0), I32(k)])), self.allocas[ci.out[0]])
            k += 1
        if ci.catch is not None:
            b.store(b.load(b.gep(frame, [I32(0), I32(k)])), self.failed[name])
            b.store(b.load(b.gep(frame, [I32(0), I32(k + 1)])), self.allocas[ci.catch[0]])
        b.call(self.be.callbacks["refined_task_release"], [handle])

    # ------------------------------------------------------------ values

    def widen(self, b: ir.IRBuilder, v, canon: str):
        if self.be.tag_only(canon):
            return b.zext(b.extract_value(v, 0), I64)
        if canon == "Bool" or canon in UNSIGNED:
            return b.zext(v, I64) if v.type != I64 else v
        return b.sext(v, I64) if v.type != I64 else v

    def narrow(self, b: ir.IRBuilder, v, canon: str):
        canon = self.t(canon)
        if self.be.tag_only(canon):
            return b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.trunc(v, I32), 0)
        t = self.be.ltype(canon, self.m.file, 0)
        return b.trunc(v, t) if t != I64 else v

    def arg_value(self, b: ir.IRBuilder, value: str, line: int):
        if value in self.allocas:
            return b.load(self.allocas[value])
        if value in self.m.ops:
            return self.be.function_for(self.m.short, value, self.m.file, line)
        if value in self.m.op_instances:
            gen, sub = instance_parts(self.world, self.m, self.m.op_instances[value])
            return self.be.function_for(self.m.short, gen, self.m.file, line, sub)
        self.unsupported(line, f"value `{value}`")

    # ------------------------------------------------------------ calls

    def call(self, b: ir.IRBuilder, ci: CallInfo, line: int) -> None:
        ent = ci.entity
        args = {slot: self.arg_value(b, value, ent.line) for slot, _t, value, _m, _l in ci.args}
        inv = ent.value("invokes")
        out = failed = err = None
        inst = self._instance(inv) if inv else None
        if ci.reference is not None and self._foreign_pairs(ci):
            out, failed, err = self.foreign_pair_call(b, ci, args)
        elif ci.reference is not None:
            fptr = b.load(self.allocas[ci.reference])
            if self.be.module.triple.startswith("x86_64"):
                # D-158: on x86_64 a call through a reference is made as a call of a C function of `...`, which
                # passes every argument where a fixed one goes and also says how many vector registers it used (%al,
                # Linux) or copies a double to its integer register (Windows): what a variadic C function such as
                # printf reads its arguments by, and what any other function ignores
                fty = fptr.type.pointee
                fptr = b.bitcast(fptr, ir.FunctionType(fty.return_type, [], var_arg=True).as_pointer())
            res = b.call(fptr, [args[p.name] for p in self._ref_sig(ci).inputs])
            out, failed, err = self._split(b, res, self._ref_sig(ci))
        elif inst is not None:
            owner, gen, sub = inst
            sub = {k: self.t(v) for k, v in sub.items()}
            fn = self.be.function_for(owner.short, gen, self.m.file, ent.line, sub)
            sig = self.world.concrete_sig(owner.op_infos[gen].sig, sub)
            res = b.call(fn, self.fit(b, fn, [args[p.name] for p in sig.inputs]))
            out, failed, err = self._split(b, res, sig)
        elif inv and len(inv.split(".")) == 2 and inv.split(".")[0] in self.m.tables:
            out, failed, err = self.table_member(b, inv.split(".")[0], inv.split(".")[1], args, ci, ent.line)
        elif ci.callee_op is not None or (inv and inv.split(".")[0] in self.world.modules and len(inv.split(".")) == 2):
            mod, op = (self.m.short, ci.callee_op) if ci.callee_op is not None and "." not in inv else inv.split(".")
            if mod not in self.world.modules or op not in self.world.modules[mod].op_infos:
                self.unsupported(ent.line, f"calling `{inv}` (generic operations are not supported yet)")
            fn = self.be.function_for(mod, op, self.m.file, ent.line)
            sig = self.world.modules[mod].op_infos[op].sig
            res = b.call(fn, self.fit(b, fn, [args[p.name] for p in sig.inputs]))
            out, failed, err = self._split(b, res, sig)
        else:
            out, failed, err = self.intrinsic(b, inv, ci, args, ent.line)
        if ci.out is not None:
            b.store(out, self.allocas[ci.out[0]])
        if ci.catch is not None:
            b.store(failed if failed is not None else I1(0), self.failed[ent.name])
            if err is not None:
                b.store(err, self.allocas[ci.catch[0]])

    @staticmethod
    def fit(b: ir.IRBuilder, fn: ir.Function, values: list) -> list:
        """Arguments for a call of `fn`, an address passed as the pointer type its parameter names (a runtime
        function exported to C has the pointer types compiled code calls it with, D-124)."""
        return [v if v.type == t else b.bitcast(v, t) for v, t in zip(values, fn.function_type.args)]

    def relocate(self, b: ir.IRBuilder, value, canon: str, region, line: int):
        """D-107: `value` with every `String` and `Bytes` inside it (through records and enum payloads) copied into
        `region`. Inactive enum payload fields are zero, so copying them copies nothing."""
        canon = self.t(canon)
        if canon in ("String", "Bytes"):
            n = b.extract_value(value, 1)
            fresh = b.call(self.be.callbacks["refined_region_alloc"], [region, n])
            memcpy = self.be.module.declare_intrinsic("llvm.memcpy", [PTR, PTR, I64])
            b.call(memcpy, [fresh, b.extract_value(value, 0), n, I1(0)])
            return b.insert_value(value, fresh, 0)
        if not self.world.holds(canon, lambda c: self.t(c) in ("String", "Bytes")):
            return value
        info = self.world.type_info(canon)
        if info.kind == "alias":
            return self.relocate(b, value, info.base, region, line)
        if info.kind == "record":
            for i, (_n, ft) in enumerate(info.fields):
                value = b.insert_value(value, self.relocate(b, b.extract_value(value, i), ft, region, line), i)
            return value
        layout = self.be.enum_layout(canon)
        if layout:
            for vname, ptype in info.variants:
                if ptype is not None and vname in layout:
                    k = layout[vname]
                    value = b.insert_value(value, self.relocate(b, b.extract_value(value, k), ptype, region, line), k)
        return value

    def table_member(self, b: ir.IRBuilder, name: str, member: str, args: dict, ci: CallInfo, line: int):
        """D-104: `<table>.length` and `<table>.rowAt`, reading the table's constant array."""
        g, n, rec = self.be.table(self.m, name)
        if member == "length":
            return I64(n), None, None
        if member == "find":
            return self.table_find(b, g, n, rec, args["key"], ci, line)
        row = args["position"]  # the row number as the table writes it: 1 to n (R306)
        inside = b.and_(b.icmp_signed(">=", row, I64(1)), b.icmp_signed("<=", row, I64(n)))
        err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), row, 1)
        idx = b.sub(row, I64(1))
        rtype = self.be.ltype(rec, self.m.file, line)
        start = b.block
        body = self.fn.append_basic_block(f"{ci.entity.name}.row")
        done = self.fn.append_basic_block(f"{ci.entity.name}.done")
        b.cbranch(inside, body, done)
        ib = ir.IRBuilder(body)
        value = ib.load(ib.gep(g, [I32(0), idx]))
        ib.branch(done)
        b.position_at_end(done)
        phi = b.phi(rtype)
        phi.add_incoming(value, body)
        phi.add_incoming(ir.Constant(rtype, None), start)
        return phi, b.not_(inside), err

    def table_find(self, b: ir.IRBuilder, g, n: int, rec: str, key, ci: CallInfo, line: int):
        """D-111: scan the table's constant rows for the first whose first field equals the key."""
        rtype = self.be.ltype(rec, self.m.file, line)
        start = b.block
        head = self.fn.append_basic_block(f"{ci.entity.name}.scan")
        body = self.fn.append_basic_block(f"{ci.entity.name}.compare")
        step = self.fn.append_basic_block(f"{ci.entity.name}.next")
        done = self.fn.append_basic_block(f"{ci.entity.name}.done")
        b.branch(head)
        hb = ir.IRBuilder(head)
        i = hb.phi(I64)
        i.add_incoming(I64(0), start)
        hb.cbranch(hb.icmp_signed("<", i, I64(n)), body, done)
        bb = ir.IRBuilder(body)
        row = bb.load(bb.gep(g, [I32(0), i]))
        field = bb.extract_value(row, 0)
        if isinstance(key.type, ir.LiteralStructType) or key.type == STR:
            eq = bb.call(self.be.callbacks["refined_bytes_equal"],
                         [bb.extract_value(field, 0), bb.extract_value(field, 1),
                          bb.extract_value(key, 0), bb.extract_value(key, 1)])
            same = bb.icmp_signed("!=", eq, I32(0))
        else:
            same = bb.icmp_unsigned("==", field, key)
        bb.cbranch(same, done, step)
        sb = ir.IRBuilder(step)
        i.add_incoming(sb.add(i, I64(1)), step)
        sb.branch(head)
        b.position_at_end(done)
        value = b.phi(rtype)
        value.add_incoming(row, body)
        value.add_incoming(ir.Constant(rtype, None), head)
        found = b.phi(ir.IntType(1))
        found.add_incoming(ir.Constant(ir.IntType(1), 1), body)
        found.add_incoming(ir.Constant(ir.IntType(1), 0), head)
        return value, b.not_(found), ir.Constant(ENUM, [I32(0), I64(0)])

    def _instance(self, inv: str):
        """(module, generic operation, substitution) when `inv` names an `operationInstance`."""
        parts = inv.split(".")
        if len(parts) == 1 and inv in self.m.op_instances:
            return (self.m, *instance_parts(self.world, self.m, self.m.op_instances[inv]))
        if len(parts) == 2 and parts[0] in self.world.modules and parts[1] in self.world.modules[parts[0]].op_instances:
            other = self.world.modules[parts[0]]
            return (other, *instance_parts(self.world, other, other.op_instances[parts[1]]))
        return None

    def _foreign_pairs(self, ci: CallInfo) -> bool:
        """D-175: whether a call through a reference is a foreign function's (an operation type bound with
        ffi.Function) that takes or gives a record of two numbers, which C passes as a struct."""
        canon = self.t(self.info.bindings[ci.reference].type)
        if canon not in self.world.foreign_types:
            return False
        sig = self._ref_sig(ci)
        return bool(pair_record(self.world, sig.output) or any(pair_record(self.world, p.type) for p in sig.inputs))

    def foreign_pair_call(self, b: ir.IRBuilder, ci: CallInfo, args: dict):
        """D-175: call a foreign function passing its records of two numbers as the C ABI passes structs."""
        sig = self._ref_sig(ci)
        fptr = b.load(self.allocas[ci.reference])
        out_kind = pair_record(self.world, sig.output)
        out_struct = self.lt(sig.output) if sig.output else None
        values, types = [], []
        sret = out_kind is not None and self.be.pair_abi(out_kind)[1] == "memory"
        if sret:
            slot = self.fn_alloca(out_struct, f"{ci.entity.name}.result")
            values.append(b.bitcast(slot, PTR))
            types.append(PTR)
        for p in sig.inputs:
            value = args[p.name]
            kind = pair_record(self.world, p.type)
            if kind is None:
                values.append(value)
                types.append(value.type)
                continue
            abi, how = self.be.pair_abi(kind)
            if how == "memory":
                copy = self.fn_alloca(value.type, f"{ci.entity.name}.{p.name}")
                b.store(value, copy)
                values.append(b.bitcast(copy, PTR))
                types.append(PTR)
            else:
                values.append(self.be.pair_to_abi(b, value, kind, value.type))
                types.append(abi)
        if sret:
            ret = PTR
        elif out_kind:
            ret = self.be.pair_abi(out_kind)[0]
        else:
            ret = self.lt(sig.output) if sig.output else ir.VoidType()
        if self.be.module.triple.startswith("x86_64"):
            fty = ir.FunctionType(ret, [], var_arg=True)  # D-158
        else:
            fty = ir.FunctionType(ret, types)
        result = b.call(b.bitcast(fptr, fty.as_pointer()), values)
        if sret:
            return b.load(slot), None, None
        if out_kind:
            return self.be.pair_from_abi(b, result, out_kind, out_struct), None, None
        return (result if sig.output else None), None, None

    def _ref_sig(self, ci: CallInfo):
        t = self.info.bindings[ci.reference].type
        return self.world.type_info(self.t(t)).sig

    def _split(self, b: ir.IRBuilder, res, sig):
        if sig.raises:
            return (b.extract_value(res, 1) if sig.output else None, b.extract_value(res, 0), b.extract_value(res, 2))
        return (res if sig.output else None), None, None

    def ctx(self, ci: CallInfo):
        file, ln = self.where(ci.entity.line)
        s = self.be.string(f"{file}:{ln}: `{ci.entity.name}` in `{self.ent.name}`")
        return s

    def intrinsic(self, b: ir.IRBuilder, inv: str, ci: CallInfo, args: dict, line: int):
        """Library targets and derived targets implemented in the backend."""
        parts = inv.split(".")
        cb = self.be.callbacks
        # derived targets of local or imported types
        if (len(parts) == 2 and S.UPPER.match(parts[0])) or len(parts) == 3:
            return self.derived(b, inv, ci, args, line)
        mod, name = parts
        a = [args[s] for s, *_ in ci.args]
        if mod == "machine":
            return self.machine(b, name, args, ci, line)
        if mod == "system" and name in SYSTEM_CALLS:
            sig = SYSTEM_CALLS[name][1]
            if self.be.os != "windows":
                out = self.be.ltype(sig.output) if sig.output else None
                return self.be.off_target(b, out), None, None
            res = b.call(self.be.system_function(name), [args[p.name] for p in sig.inputs])
            return (res if sig.output else None), None, None
        if mod == "system" and name in LINUX_CALLS:
            number, sig = LINUX_CALLS[name]
            values = [b.ptrtoint(args[p.name], I64) if p.type == "machine.Address" else args[p.name]
                      for p in sig.inputs]
            return self.be.linux_syscall(b, number, values, name), None, None
        if mod == "system" and name == "linux":
            return I1(1 if self.be.os == "linux" else 0), None, None
        if mod == "system" and name == "aarch64":
            return I1(1 if self.be.module.triple.split("-")[0] in ("aarch64", "arm64") else 0), None, None

        def trap_if(cond, message: str) -> None:
            with b.if_then(cond, likely=False):
                self.trap(b, line, message)

        def arith(op: str, x, y, t: str):
            signed = t not in UNSIGNED
            if op in ("add", "subtract", "multiply"):
                fn = ({"add": b.sadd_with_overflow, "subtract": b.ssub_with_overflow, "multiply": b.smul_with_overflow}
                      if signed else
                      {"add": b.uadd_with_overflow, "subtract": b.usub_with_overflow, "multiply": b.umul_with_overflow})[op]
                r = fn(x, y)
                trap_if(b.extract_value(r, 1), f"`{inv}` overflowed `{t}` in `{ci.entity.name}`")
                return b.extract_value(r, 0)
            width = x.type.width
            trap_if(b.icmp_unsigned("==", y, ir.Constant(x.type, 0)), f"`{inv}` divided by zero in `{ci.entity.name}`")
            if not signed:
                return b.udiv(x, y) if op == "divide" else b.urem(x, y)
            trap_if(b.and_(b.icmp_signed("==", x, ir.Constant(x.type, -(1 << (width - 1)))),
                           b.icmp_signed("==", y, ir.Constant(x.type, -1))),
                    f"`{inv}` overflowed `{t}` in `{ci.entity.name}`")
            return b.sdiv(x, y) if op == "divide" else b.srem(x, y)

        def numeric(prefixes: tuple, types) -> Optional[tuple[str, str]]:
            """(operation, type) when `name` is `<operation><type>` for one of them."""
            for t in types:
                if name.endswith(t) and name[:-len(t)] in prefixes:
                    return name[:-len(t)], t
            return None

        if mod == "math":
            # longest type names first, so `addUInt64` is not read as `addUInt6` + ... (and `Int64` not `UInt64`)
            ints = sorted(INTEGER_TARGET_TYPES, key=len, reverse=True)
            hit = numeric(("add", "subtract", "multiply", "divide", "remainder"), ints)
            if hit:
                return arith(hit[0], a[0], a[1], hit[1]), None, None
            hit = numeric(("wrappingAdd", "wrappingSubtract", "wrappingMultiply"), ints)
            if hit:
                fn = {"wrappingAdd": b.add, "wrappingSubtract": b.sub, "wrappingMultiply": b.mul}[hit[0]]
                return fn(a[0], a[1]), None, None
            hit = numeric(("saturatingAdd", "saturatingSubtract", "saturatingMultiply"), ints)
            if hit:
                op, t = hit[0][len("saturating"):], hit[1]
                ty = a[0].type
                if t in UNSIGNED:
                    fn = {"Add": b.uadd_with_overflow, "Subtract": b.usub_with_overflow,
                          "Multiply": b.umul_with_overflow}[op]
                    r = fn(a[0], a[1])
                    # an unsigned result overflows only upward, except a subtract, which overflows below zero
                    clamp = ir.Constant(ty, 0) if op == "Subtract" else ir.Constant(ty, (1 << ty.width) - 1)
                    return b.select(b.extract_value(r, 1), clamp, b.extract_value(r, 0)), None, None
                fn = {"Add": b.sadd_with_overflow, "Subtract": b.ssub_with_overflow, "Multiply": b.smul_with_overflow}[op]
                # on overflow the result clamps to the end of the range the exact result lies past
                r = fn(a[0], a[1])
                overflowed = b.extract_value(r, 1)
                # an add or subtract overflows past the end its left operand's sign points to;
                # a multiply past the end the product's sign points to
                sign_of = b.xor(a[0], a[1]) if op == "Multiply" else a[0]
                negative = b.icmp_signed("<", sign_of, ir.Constant(ty, 0))
                clamp = b.select(negative, ir.Constant(ty, -(1 << (ty.width - 1))),
                                 ir.Constant(ty, (1 << (ty.width - 1)) - 1))
                return b.select(overflowed, clamp, b.extract_value(r, 0)), None, None
            hit = numeric(("negate", "absolute"), sorted(("Int8", "Int16", "Int32", "Int64"), key=len, reverse=True))
            if hit:
                ty = a[0].type
                r = b.ssub_with_overflow(ir.Constant(ty, 0), a[0])
                trap_if(b.extract_value(r, 1), f"`{inv}` overflowed `{hit[1]}` in `{ci.entity.name}`")
                neg = b.extract_value(r, 0)
                if hit[0] == "negate":
                    return neg, None, None
                return b.select(b.icmp_signed("<", a[0], ir.Constant(ty, 0)), neg, a[0]), None, None
            hit = numeric(("add", "subtract", "multiply", "divide"), ("Float64", "Float32"))
            if hit:
                ff = {"add": b.fadd, "subtract": b.fsub, "multiply": b.fmul, "divide": b.fdiv}[hit[0]]
                return ff(a[0], a[1]), None, None
        if mod == "compare":
            ops = {"equal": "==", "notEqual": "!=", "lessThan": "<", "lessOrEqual": "<=", "greaterThan": ">",
                   "greaterOrEqual": ">="}
            hit = numeric(tuple(ops), sorted(INTEGER_TARGET_TYPES + ("Float32", "Float64"), key=len, reverse=True))
            if hit:
                sym, t = ops[hit[0]], hit[1]
                if t in ("Float64", "Float32"):
                    return b.fcmp_ordered(sym, a[0], a[1]), None, None
                if t in UNSIGNED:
                    return b.icmp_unsigned(sym, a[0], a[1]), None, None
                return b.icmp_signed(sym, a[0], a[1]), None, None
        if mod == "logic":
            if name == "and":
                return b.and_(a[0], a[1]), None, None
            if name == "or":
                return b.or_(a[0], a[1]), None, None
            if name == "xor":
                return b.xor(a[0], a[1]), None, None
            if name == "not":
                return b.not_(a[0]), None, None
        if mod == "math" and name == "powerInt64":
            base, exp = a
            trap_if(b.icmp_signed("<", exp, I64(0)), f"`{inv}` with a negative exponent in `{ci.entity.name}`")
            # square-and-multiply: at most 63 rounds whatever the exponent. Squaring happens only while
            # exponent bits remain, so an overflowing square means the exact result overflows too.
            res_ptr = self.fn_alloca(I64, f"{ci.entity.name}.result")
            base_ptr = self.fn_alloca(I64, f"{ci.entity.name}.base")
            exp_ptr = self.fn_alloca(I64, f"{ci.entity.name}.exponent")
            b.store(I64(1), res_ptr)
            b.store(base, base_ptr)
            b.store(exp, exp_ptr)
            head = self.fn.append_basic_block(f"{ci.entity.name}.power")
            body = self.fn.append_basic_block(f"{ci.entity.name}.step")
            done = self.fn.append_basic_block(f"{ci.entity.name}.powered")
            b.branch(head)
            hb = ir.IRBuilder(head)
            hb.cbranch(hb.icmp_signed(">", hb.load(exp_ptr), I64(0)), body, done)
            bb = ir.IRBuilder(body)
            e = bb.load(exp_ptr)
            cur = bb.load(base_ptr)
            odd = bb.icmp_signed("!=", bb.and_(e, I64(1)), I64(0))
            with bb.if_then(odd):
                r = bb.smul_with_overflow(bb.load(res_ptr), cur)
                with bb.if_then(bb.extract_value(r, 1), likely=False):
                    self.trap(bb, line, f"`{inv}` overflowed `Int64` in `{ci.entity.name}`")
                bb.store(bb.extract_value(r, 0), res_ptr)
            rest = bb.ashr(e, I64(1))
            bb.store(rest, exp_ptr)
            with bb.if_then(bb.icmp_signed(">", rest, I64(0))):
                sq = bb.smul_with_overflow(cur, cur)
                with bb.if_then(bb.extract_value(sq, 1), likely=False):
                    self.trap(bb, line, f"`{inv}` overflowed `Int64` in `{ci.entity.name}`")
                bb.store(bb.extract_value(sq, 0), base_ptr)
            bb.branch(head)
            b.position_at_end(done)
            return b.load(res_ptr), None, None
        if mod == "bits":
            hit = numeric(("and", "or", "xor", "not", "shiftLeft", "shiftRight"),
                          sorted(INTEGER_TARGET_TYPES, key=len, reverse=True))
            if hit:
                op, t = hit
                simple = {"and": b.and_, "or": b.or_, "xor": b.xor}
                if op in simple:
                    return simple[op](a[0], a[1]), None, None
                if op == "not":
                    return b.not_(a[0]), None, None
                ty = a[0].type
                bad = b.or_(b.icmp_signed("<", a[1], I64(0)), b.icmp_signed(">=", a[1], I64(ty.width)))
                trap_if(bad, f"`{inv}` shift amount outside 0..{ty.width - 1} in `{ci.entity.name}`")
                amount = b.trunc(a[1], ty) if ty.width < 64 else a[1]
                if op == "shiftLeft":
                    return b.shl(a[0], amount), None, None
                return (b.lshr(a[0], amount) if t in UNSIGNED else b.ashr(a[0], amount)), None, None
        if mod == "convert":
            if name in ("int64BitsToUInt64", "uint64BitsToInt64"):
                return a[0], None, None  # the same 64 bits, read with the other signedness
            if name == "float64BitsToUInt64":
                return b.bitcast(a[0], I64), None, None  # D-127: the same 64 bits, read as an integer
            if name == "uint64BitsToFloat64":
                return b.bitcast(a[0], F64), None, None
            sig = ci.sig
            src, dst = sig.inputs[0].type, sig.output
            if src in INTEGER_RANGES and dst in INTEGER_RANGES:
                return self.convert_integer(b, a[0], src, dst, inv, ci, line), None, None
            if name == "int64ToFloat64":
                return b.sitofp(a[0], F64), None, None
            if name == "float64ToInt64":
                ok = b.and_(b.fcmp_ordered(">=", a[0], F64(-9.223372036854775808e18)),
                            b.fcmp_ordered("<", a[0], F64(9.223372036854775808e18)))
                trap_if(b.not_(ok), f"`{inv}`: value out of range for `Int64` in `{ci.entity.name}`")
                return b.fptosi(a[0], I64), None, None
            if name == "float32ToFloat64":
                return b.fpext(a[0], F64), None, None
            if name == "float64ToFloat32":
                # rounds to the nearest Float32; a finite value too large for Float32 traps
                r = b.fptrunc(a[0], F32)
                inf32 = b.or_(b.fcmp_ordered("==", r, F32(float("inf"))), b.fcmp_ordered("==", r, F32(float("-inf"))))
                inf64 = b.or_(b.fcmp_ordered("==", a[0], F64(float("inf"))),
                              b.fcmp_ordered("==", a[0], F64(float("-inf"))))
                trap_if(b.and_(inf32, b.not_(inf64)), f"`{inv}`: value out of range for `Float32` in `{ci.entity.name}`")
                return r, None, None
        if mod == "console" and name in ("writeLine", "write", "writeError", "writeIntegerLine", "writeFloatLine"):
            fd = I32(2 if name == "writeError" else 1)
            newline = I32(0 if name in ("write",) else 1)
            if name == "writeIntegerLine":
                status = b.call(cb["refined_write_int"], [fd, a[0], newline])
            elif name == "writeFloatLine":
                status = b.call(cb["refined_write_float"], [fd, a[0], newline])
            else:
                status = b.call(cb["refined_write"], [fd, b.extract_value(a[0], 0), b.extract_value(a[0], 1), newline])
            failed = b.icmp_signed("!=", status, I32(0))
            err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.sext(status, I64), 1)
            return None, failed, err
        if mod == "string":
            if name == "byteLength":
                return b.extract_value(a[0], 1), None, None
            if name == "concat":
                l1, l2 = b.extract_value(a[0], 1), b.extract_value(a[1], 1)
                total = b.add(l1, l2)
                dst = b.call(self.be.callbacks["refined_region_alloc"], [a[2], total])
                memcpy = self.be.module.declare_intrinsic("llvm.memcpy", [PTR, PTR, I64])
                b.call(memcpy, [dst, b.extract_value(a[0], 0), l1, I1(0)])
                b.call(memcpy, [b.gep(dst, [l1]), b.extract_value(a[1], 0), l2, I1(0)])
                s = b.insert_value(ir.Constant(STR, ir.Undefined), dst, 0)
                return b.insert_value(s, total, 1), None, None
            if name == "fromInt64":
                len_ptr = self.fn_alloca(I64, f"{ci.entity.name}.len")
                p = b.call(cb["refined_format_int"], [a[0], a[1], len_ptr])
                s = b.insert_value(ir.Constant(STR, ir.Undefined), p, 0)
                return b.insert_value(s, b.load(len_ptr), 1), None, None
            if name == "slice":
                text, start, length = a
                ok = b.and_(b.icmp_signed(">=", start, I64(0)), b.icmp_signed(">=", length, I64(0)))
                # compare without forming start + length, which can overflow and wrap past the check:
                # start <= size and length <= size - start (both sides non-negative when ok)
                size = b.extract_value(text, 1)
                ok = b.and_(ok, b.icmp_signed("<=", start, size))
                ok = b.and_(ok, b.icmp_signed("<=", length, b.sub(size, start)))
                # D-70: a slice keeps characters whole. An offset inside the text splits a character when its
                # byte is a UTF-8 continuation byte (10xxxxxx). Reads stay inside the text: an offset outside it
                # reads a constant zero byte instead.
                zero = b.extract_value(self.be.string(""), 0)

                def splits(i):
                    inside = b.and_(b.icmp_signed(">=", i, I64(0)), b.icmp_signed("<", i, size))
                    at = b.select(inside, b.gep(b.extract_value(text, 0), [b.select(inside, i, I64(0))]), zero)
                    return b.and_(inside, b.icmp_unsigned("==", b.and_(b.load(at), I8(0xC0)), I8(0x80)))
                ok = b.and_(ok, b.not_(b.or_(splits(start), splits(b.add(start, length)))))
                safe_start = b.select(ok, start, I64(0))
                s = b.insert_value(ir.Constant(STR, ir.Undefined), b.gep(b.extract_value(text, 0), [safe_start]), 0)
                s = b.insert_value(s, b.select(ok, length, I64(0)), 1)
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), start, 1)
                return s, b.not_(ok), err
            if name == "contains":
                at = b.call(cb["refined_find"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                 b.extract_value(a[1], 0), b.extract_value(a[1], 1)])
                return b.icmp_signed(">=", at, I64(0)), None, None
            if name == "find":
                at = b.call(cb["refined_find"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                 b.extract_value(a[1], 0), b.extract_value(a[1], 1)])
                return at, b.icmp_signed("<", at, I64(0)), ir.Constant(ENUM, [I32(0), I64(0)])
            if name == "toInt64":
                out_ptr = self.fn_alloca(I64, f"{ci.entity.name}.parsed")
                status = b.call(cb["refined_parse_int"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1), out_ptr])
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.sub(status, I32(1)), 0)
                return b.load(out_ptr), b.icmp_signed("!=", status, I32(0)), err
            if name == "equals":
                eq = b.call(cb["refined_bytes_equal"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                        b.extract_value(a[1], 0), b.extract_value(a[1], 1)])
                return b.icmp_signed("!=", eq, I32(0)), None, None
            if name == "startsWith":
                plen = b.extract_value(a[1], 1)
                long_enough = b.icmp_signed(">=", b.extract_value(a[0], 1), plen)
                eq = b.call(cb["refined_bytes_equal"], [b.extract_value(a[0], 0), b.select(long_enough, plen, I64(0)),
                                                        b.extract_value(a[1], 0), plen])
                return b.and_(long_enough, b.icmp_signed("!=", eq, I32(0))), None, None
            if name == "byteAtOrTrap":
                text, idx = a
                inside = b.and_(b.icmp_signed(">=", idx, I64(0)), b.icmp_signed("<", idx, b.extract_value(text, 1)))
                with b.if_then(b.not_(inside), likely=False):
                    self.trap(b, line, f"`{ci.entity.name}` read byte {'{'}index{'}'} outside its text".replace(
                        "{index}", "an index"))
                return b.load(b.gep(b.extract_value(text, 0), [idx])), None, None
            if name == "byteAt":
                return self.byte_at(b, a[0], a[1], ci)
            if name == "advancePosition":
                return self.advance_position(b, a[0], a[1], ci, line)
            done = self.text_target(b, name, a, ci, line)
            if done is not None:
                return done
        if mod == "bytes":
            if name == "length":
                return b.extract_value(a[0], 1), None, None
            if name == "byteAt":
                return self.byte_at(b, a[0], a[1], ci)
            if name == "equals":
                eq = b.call(cb["refined_bytes_equal"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                        b.extract_value(a[1], 0), b.extract_value(a[1], 1)])
                return b.icmp_signed("!=", eq, I32(0)), None, None
            if name == "slice":
                data, start, length = a
                size = b.extract_value(data, 1)
                ok = b.and_(b.icmp_signed(">=", start, I64(0)), b.icmp_signed(">=", length, I64(0)))
                ok = b.and_(ok, b.icmp_signed("<=", start, size))
                ok = b.and_(ok, b.icmp_signed("<=", length, b.sub(size, start)))
                s = b.insert_value(ir.Constant(STR, ir.Undefined),
                                   b.gep(b.extract_value(data, 0), [b.select(ok, start, I64(0))]), 0)
                s = b.insert_value(s, b.select(ok, length, I64(0)), 1)
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), start, 1)
                return s, b.not_(ok), err
        if mod == "arena":
            left = b.call(cb["refined_region_remaining"], [a[0]])
            if name == "remaining":
                return left, None, None
            if name == "ensure":
                short = b.icmp_signed(">", a[1], left)
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), left, 1)  # exhausted, with what is left
                return None, short, err
        if mod == "byte":
            v = a[0]

            def between(lo: int, hi: int):
                return b.and_(b.icmp_unsigned(">=", v, I8(lo)), b.icmp_unsigned("<=", v, I8(hi)))
            letter = b.or_(between(ord("a"), ord("z")), between(ord("A"), ord("Z")))
            digit = between(ord("0"), ord("9"))
            if name == "isLetter":
                return letter, None, None
            if name == "isDigit":
                return digit, None, None
            if name == "isLetterOrDigit":
                return b.or_(letter, digit), None, None
            if name == "isSpace":
                sp = b.or_(b.icmp_unsigned("==", v, I8(32)), b.icmp_unsigned("==", v, I8(9)))
                sp = b.or_(sp, b.or_(b.icmp_unsigned("==", v, I8(10)), b.icmp_unsigned("==", v, I8(13))))
                return sp, None, None
            if name == "isPunctuation":
                # D-72: the 32 printable ASCII bytes that are neither letters, digits, nor space
                punct = b.or_(between(33, 47), between(58, 64))
                return b.or_(punct, b.or_(between(91, 96), between(123, 126))), None, None
            if name == "equals":
                return b.icmp_unsigned("==", a[0], a[1]), None, None
        if mod == "test":
            c = self.ctx(ci)
            cp, cl = b.extract_value(c, 0), b.extract_value(c, 1)
            if name == "assertEqualInt64":
                b.call(cb["refined_assert_int"], [a[0], a[1], cp, cl])
                return None, None, None
            if name == "assertEqualExitCode":
                b.call(cb["refined_assert_int"], [b.sext(a[0], I64), b.sext(a[1], I64), cp, cl])
                return None, None, None
            if name == "assertTrue":
                b.call(cb["refined_assert_true"], [b.zext(a[0], I32), cp, cl])
                return None, None, None
            if name == "assertEqualString":
                b.call(cb["refined_assert_str"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                  b.extract_value(a[1], 0), b.extract_value(a[1], 1), cp, cl])
                return None, None, None
            if name == "fail":
                b.call(cb["refined_fail"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1), cp, cl])
                return None, None, None
        if mod == "string" and name == "toBytes":
            return a[0], None, None  # the same bytes, viewed as `Bytes` (it borrows `text`)
        if inv in HOST_TARGETS:
            extra = [self.be.string(self.scope_host("listen", "net.tcp"))] if inv == "net.listen" else []
            if ci.sig is not None and ci.sig.scoped:
                extra.append(self.be.string(self.scope_text(ci.sig)))
            return self.host_call(b, inv, ci, args, line, extra)
        self.unsupported(line, f"the library target `{inv}`")

    def machine(self, b: ir.IRBuilder, name: str, args: dict, ci: CallInfo, line: int):
        """D-121: the `machine` targets, each a few instructions: addresses are `i8*`, loads and stores take any
        alignment, and nothing is checked."""
        widths = {"Byte": I8, "Int32": I32, "Int64": I64, "UInt64": I64, "Float64": F64, "Float32": F32, "Address": PTR}
        if name == "zero":
            return ir.Constant(PTR, None), None, None
        if name == "state":
            return b.bitcast(self.be.machine_state(), PTR), None, None
        if name == "stackAddress":
            return self.fn_alloca(I8, f"{ci.entity.name}.here"), None, None
        if name == "offset":
            return b.gep(args["address"], [args["bytes"]]), None, None
        if name == "difference":
            return b.sub(b.ptrtoint(args["left"], I64), b.ptrtoint(args["right"], I64)), None, None
        if name in ("equal", "lessThan"):
            sym = "==" if name == "equal" else "<"
            return b.icmp_unsigned(sym, b.ptrtoint(args["left"], I64), b.ptrtoint(args["right"], I64)), None, None
        if name == "toInt64":
            return b.ptrtoint(args["address"], I64), None, None
        if name == "fromInt64":
            return b.inttoptr(args["value"], PTR), None, None
        if name.startswith("load") and name[4:] in widths:
            t = widths[name[4:]]
            return b.load(b.bitcast(args["address"], t.as_pointer()), align=1), None, None
        if name.startswith("store") and name[5:] in widths:
            t = widths[name[5:]]
            b.store(args["value"], b.bitcast(args["address"], t.as_pointer()), align=1)
            return None, None, None
        if name == "copy":
            move = self.be.module.declare_intrinsic("llvm.memmove", [PTR, PTR, I64])
            b.call(move, [args["target"], args["source"], args["bytes"], I1(0)])
            return None, None, None
        if name == "fill":
            fill = self.be.module.declare_intrinsic("llvm.memset", [PTR, I64])
            b.call(fill, [args["target"], args["value"], args["bytes"], I1(0)])
            return None, None, None
        if name == "compare":
            return self.compare_memory(b, args["left"], args["right"], args["bytes"], ci.entity.name), None, None
        if name in ("addressOfString", "addressOfBytes"):
            return b.extract_value(args["text" if name == "addressOfString" else "data"], 0), None, None
        if name in ("stringAt", "bytesAt"):
            view = b.insert_value(ir.Constant(STR, ir.Undefined), args["address"], 0)
            return b.insert_value(view, args["bytes"], 1), None, None
        if name == "callWithAddress":
            thunk = b.bitcast(args["function"], ir.FunctionType(ir.VoidType(), [PTR]).as_pointer())
            b.call(thunk, [args["argument"]])
            return None, None, None
        if name == "runEntry":
            if not self.be.options.get("runtime_object"):
                self.unsupported(line, "`machine.runEntry` outside the runtime linked with a program (`refined build "
                                       "--kind executable --runtime semanticscript`)")
            entry = self.be.module.globals.get("refined_program_main") or                 ir.Function(self.be.module, ir.FunctionType(I32, []), name="refined_program_main")
            return b.call(entry, []), None, None
        if name in ("switchStack", "startStack", "runEntryOnStack"):
            # D-139: stacks of the runtime's own, switched by a few instructions of assembly
            if name == "runEntryOnStack":
                if not self.be.options.get("runtime_object"):
                    self.unsupported(line, "`machine.runEntryOnStack` outside the runtime linked with a program")
                entry = self.be.module.globals.get("refined_program_main") or \
                    ir.Function(self.be.module, ir.FunctionType(I32, []), name="refined_program_main")
                fn = self.be.stack_routine("refined_run_on_stack", ir.FunctionType(I32, [PTR, PTR]))
                if fn is None:
                    return self.be.off_target(b, I32), None, None
                return b.call(fn, [args["top"], b.bitcast(entry, PTR)]), None, None
            params = ["saveAt", "resume"] if name == "switchStack" else ["saveAt", "top", "function", "argument"]
            symbol = "refined_switch_stack" if name == "switchStack" else "refined_start_stack"
            fn = self.be.stack_routine(symbol, ir.FunctionType(ir.VoidType(), [PTR] * len(params)))
            if fn is None:
                self.be.off_target(b, None)
                return None, None, None
            b.call(fn, [args[p] for p in params])
            return None, None, None
        if name == "interruptHandler":
            # D-147: only the runtime has it, and only for the operation the system calls on an interrupt
            if "refined_interrupt_handler" not in self.be.abi:
                self.unsupported(line, "`machine.interruptHandler` in a program with no `abi c "
                                       "\"refined_interrupt_handler\"` operation")
            mod, op = self.be.abi["refined_interrupt_handler"]
            return b.bitcast(self.be.function_for(mod, op, None, 0), PTR), None, None
        if name == "signalRestorer":
            arch = self.be.linux_arch()
            if not arch:
                return ir.Constant(PTR, None), None, None
            self.be.module.asm_parts["restorer"] = _AARCH64_RESTORER if arch == "aarch64" else _X86_64_RESTORER
            fn = self.be.module.globals.get("refined_signal_restorer") or                 ir.Function(self.be.module, ir.FunctionType(ir.VoidType(), []), name="refined_signal_restorer")
            return b.bitcast(fn, PTR), None, None
        if name == "cLibrary":
            return b.bitcast(self.be.c_library(), PTR), None, None
        if name == "errorMessages":
            return b.bitcast(self.be.error_messages(), PTR), None, None
        if name == "callComparison":
            compare = b.bitcast(args["function"], ir.FunctionType(I32, [PTR, PTR]).as_pointer())
            return b.call(compare, [args["left"], args["right"]]), None, None
        if name == "squareRoot":
            root = self.be.module.declare_intrinsic("llvm.sqrt", [F64])
            return b.call(root, [args["value"]]), None, None
        if name in ("loadFloatControl", "storeFloatControl"):
            # D-167: the floating-point control and status registers of the running thread
            arch = self.be.module.triple.split("-")[0]
            if arch == "x86_64":
                cell = self.fn_alloca(I32, f"{ci.entity.name}.mxcsr")
                if name == "loadFloatControl":
                    save = self.be.module.globals.get("llvm.x86.sse.stmxcsr") or ir.Function(
                        self.be.module, ir.FunctionType(ir.VoidType(), [PTR]), name="llvm.x86.sse.stmxcsr")
                    b.call(save, [b.bitcast(cell, PTR)])
                    return b.zext(b.load(cell), I64), None, None
                b.store(b.trunc(args["value"], I32), cell)
                load = self.be.module.globals.get("llvm.x86.sse.ldmxcsr") or ir.Function(
                    self.be.module, ir.FunctionType(ir.VoidType(), [PTR]), name="llvm.x86.sse.ldmxcsr")
                b.call(load, [b.bitcast(cell, PTR)])
                return None, None, None
            if arch in ("aarch64", "arm64"):
                if name == "loadFloatControl":
                    control = b.asm(ir.FunctionType(I64, []), "mrs $0, fpcr", "=r", [], side_effect=True)
                    status = b.asm(ir.FunctionType(I64, []), "mrs $0, fpsr", "=r", [], side_effect=True)
                    return b.or_(b.and_(control, I64(0xFFFFFFFF)), b.shl(b.and_(status, I64(0xFFFFFFFF)), I64(32))),                         None, None
                value = args["value"]
                b.asm(ir.FunctionType(ir.VoidType(), [I64]), "msr fpcr, $0", "r", [b.and_(value, I64(0xFFFFFFFF))],
                      side_effect=True)
                b.asm(ir.FunctionType(ir.VoidType(), [I64]), "msr fpsr, $0", "r", [b.lshr(value, I64(32))],
                      side_effect=True)
                return None, None, None
            return (I64(0), None, None) if name == "loadFloatControl" else (None, None, None)
        if name in ("fusedMultiplyAdd", "fusedMultiplyAdd32"):
            t = F64 if name == "fusedMultiplyAdd" else F32
            fma = self.be.module.declare_intrinsic("llvm.fma", [t], fnty=ir.FunctionType(t, [t, t, t]))
            if self.be.module.triple.startswith("x86_64"):
                # the operation is compiled for FMA3, so llvm.fma is one instruction rather than a call of libm's fma
                set.add(self.fn.attributes, '"target-features"="+fma"')
            return b.call(fma, [args["left"], args["right"], args["addend"]]), None, None
        if name in ("addLongDouble", "subtractLongDouble", "multiplyLongDouble", "divideLongDouble"):
            op = {"add": b.fadd, "subtract": b.fsub, "multiply": b.fmul, "divide": b.fdiv}[name[:-len("LongDouble")]]
            return op(args["left"], args["right"]), None, None
        if name in ("lessLongDouble", "equalLongDouble"):
            return b.fcmp_ordered("<" if name == "lessLongDouble" else "==", args["left"], args["right"]), None, None
        if name == "longDoubleFromFloat64":
            t = self.be.long_double()
            return (args["value"] if t == F64 else b.fpext(args["value"], t)), None, None
        if name == "longDoubleToFloat64":
            t = self.be.long_double()
            return (args["value"] if t == F64 else b.fptrunc(args["value"], F64)), None, None
        if name == "longDoubleFromInt64":
            return b.sitofp(args["value"], self.be.long_double()), None, None
        if name in ("loadLongDouble", "storeLongDouble"):
            # D-174: a long double moves only through memory, 16 bytes, so the runtime never does its arithmetic
            t = self.be.long_double()
            place = b.bitcast(args["address"], t.as_pointer())
            if name == "loadLongDouble":
                return b.load(place, align=1), None, None
            b.store(args["value"], place, align=1)
            return None, None, None
        if name == "compareExchange32":
            pair = b.cmpxchg(b.bitcast(args["address"], I32.as_pointer()), args["expected"], args["desired"],
                             "seq_cst", "seq_cst")
            return b.extract_value(pair, 0), None, None
        if name in ("threadPointer", "setThreadPointer", "startThread"):
            arch = self.be.linux_arch()
            if name == "threadPointer":
                if arch == "x86_64":
                    return b.inttoptr(b.asm(ir.FunctionType(I64, []), "movq %fs:0, $0", "=r", [], side_effect=True),
                                      PTR), None, None
                if arch == "aarch64":
                    return b.inttoptr(b.asm(ir.FunctionType(I64, []), "mrs $0, tpidr_el0", "=r", [], side_effect=True),
                                      PTR), None, None
                return ir.Constant(PTR, None), None, None
            if name == "setThreadPointer":
                if arch == "aarch64":
                    b.asm(ir.FunctionType(ir.VoidType(), [I64]), "msr tpidr_el0, $0", "r",
                          [b.ptrtoint(args["block"], I64)], side_effect=True)
                return None, None, None
            if not arch:
                return I64(-38), None, None  # ENOSYS: no threads but Linux's here
            self.be.module.asm_parts["thread"] = _THREAD_START[arch]
            if "refined_c_thread_main" not in self.be.abi:
                self.unsupported(line, "`machine.startThread` in a program with no operation exported to C as "
                                       "refined_c_thread_main")
            mod, op = self.be.abi["refined_c_thread_main"]
            main = b.bitcast(self.be.function_for(mod, op, None, 0), PTR)
            fn = self.be.module.globals.get("refined_start_thread") or ir.Function(
                self.be.module, ir.FunctionType(I64, [PTR, PTR, PTR, PTR, PTR]), name="refined_start_thread")
            return b.call(fn, [args["stackTop"], args["block"], args["tidAt"], args["record"], main]), None, None
        if name == "variadicStart":
            # D-157: the operation's own `va_list`, started on the arguments after its fixed ones
            if not self.fn.ftype.var_arg:
                self.unsupported(line, "`machine.variadicStart` outside an `abi library \"<name>\" variadic` operation")
            area = self.fn_alloca(ir.ArrayType(I8, 32), f"{ci.entity.name}.arguments")
            area.align = 16
            start = self.be.module.globals.get("llvm.va_start") or                 ir.Function(self.be.module, ir.FunctionType(ir.VoidType(), [PTR]), name="llvm.va_start")
            place = b.bitcast(area, PTR)
            b.call(start, [place])
            return place, None, None
        if name == "threadEntry":
            # D-168: only the runtime has it: the operation a Windows thread threads.h starts begins in
            if "refined_c_thread_main" not in self.be.abi:
                self.unsupported(line, "`machine.threadEntry` in a program with no operation exported to C as "
                                       "refined_c_thread_main")
            mod, op = self.be.abi["refined_c_thread_main"]
            return b.bitcast(self.be.function_for(mod, op, None, 0), PTR), None, None
        if name == "taskEntry":
            # D-131: only the runtime has it, and only for the operation a task's fiber starts in
            if "refined_task_entry" not in self.be.abi:
                self.unsupported(line, "`machine.taskEntry` in a program with no `abi c \"refined_task_entry\"` "
                                       "operation")
            mod, op = self.be.abi["refined_task_entry"]
            return b.bitcast(self.be.function_for(mod, op, None, 0), PTR), None, None
        self.unsupported(line, f"the library target `machine.{name}`")

    def compare_memory(self, b: ir.IRBuilder, left, right, n, tag: str):
        """-1, 0, or 1: how the first differing byte of two ranges compares, as unsigned bytes."""
        i_ptr, r_ptr = self.fn_alloca(I64, f"{tag}.at"), self.fn_alloca(I32, f"{tag}.order")
        b.store(I64(0), i_ptr)
        b.store(I32(0), r_ptr)
        head, body, out = self.loop(b, tag)
        hb = ir.IRBuilder(head)
        i = hb.load(i_ptr)
        hb.cbranch(hb.icmp_signed("<", i, n), body, out)
        bb = ir.IRBuilder(body)
        x, y = bb.load(bb.gep(left, [i])), bb.load(bb.gep(right, [i]))
        nxt = self.fn.append_basic_block(f"{tag}.next")
        found = self.fn.append_basic_block(f"{tag}.differ")
        bb.cbranch(bb.icmp_unsigned("!=", x, y), found, nxt)
        fb = ir.IRBuilder(found)
        fb.store(fb.select(fb.icmp_unsigned("<", x, y), I32(-1), I32(1)), r_ptr)
        fb.branch(out)
        nb = ir.IRBuilder(nxt)
        nb.store(nb.add(i, I64(1)), i_ptr)
        nb.branch(head)
        b.position_at_end(out)
        return b.load(r_ptr)

    def byte_at(self, b: ir.IRBuilder, text, idx, ci: CallInfo):
        """The byte at a position of a `String` or `Bytes`, or `outOfRange` carrying the position."""
        inside = b.and_(b.icmp_signed(">=", idx, I64(0)), b.icmp_signed("<", idx, b.extract_value(text, 1)))
        start = b.block
        read = self.fn.append_basic_block(f"{ci.entity.name}.read")
        done = self.fn.append_basic_block(f"{ci.entity.name}.done")
        b.cbranch(inside, read, done)
        rb = ir.IRBuilder(read)
        byte = rb.load(rb.gep(rb.extract_value(text, 0), [idx]))
        rb.branch(done)
        b.position_at_end(done)
        phi = b.phi(I8)
        phi.add_incoming(byte, read)
        phi.add_incoming(I8(0), start)
        err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), idx, 1)
        return phi, b.not_(inside), err

    def loop(self, b: ir.IRBuilder, tag: str):
        """Blocks for an inline loop: (head, body, exit). `b` branches to the head; the caller fills the head's
        test, the body, and continues at the exit."""
        head = self.fn.append_basic_block(f"{tag}.head")
        body = self.fn.append_basic_block(f"{tag}.body")
        out = self.fn.append_basic_block(f"{tag}.exit")
        b.branch(head)
        return head, body, out

    def format_unsigned(self, b: ir.IRBuilder, value, region, base: int, room: int, least: int, tag: str):
        """D-91: an unsigned 64-bit value as text in base 10 or 16 (lower-case digits), at least `least` digits,
        written from the end of a `room`-byte block taken from the region."""
        buf = b.call(self.be.callbacks["refined_region_alloc"], [region, I64(room)])
        v_ptr, at_ptr = self.fn_alloca(I64, f"{tag}.value"), self.fn_alloca(I64, f"{tag}.at")
        b.store(value, v_ptr)
        b.store(I64(room), at_ptr)
        head, body, out = self.loop(b, tag)
        hb = ir.IRBuilder(body)
        v = hb.load(v_ptr)
        digit = hb.trunc(hb.urem(v, I64(base)), I8)
        char = hb.select(hb.icmp_unsigned("<", digit, I8(10)), hb.add(digit, I8(ord("0"))),
                         hb.add(digit, I8(ord("a") - 10)))
        at = hb.sub(hb.load(at_ptr), I64(1))
        hb.store(char, hb.gep(buf, [at]))
        hb.store(at, at_ptr)
        rest = hb.udiv(v, I64(base))
        hb.store(rest, v_ptr)
        written = hb.sub(I64(room), at)
        more = hb.or_(hb.icmp_unsigned("!=", rest, I64(0)), hb.icmp_signed("<", written, I64(least)))
        hb.cbranch(more, body, out)
        ir.IRBuilder(head).branch(body)
        b.position_at_end(out)
        at = b.load(at_ptr)
        s = b.insert_value(ir.Constant(STR, ir.Undefined), b.gep(buf, [at]), 0)
        return b.insert_value(s, b.sub(I64(room), at), 1)

    def text_target(self, b: ir.IRBuilder, name: str, a: list, ci: CallInfo, line: int):
        """D-91: the `string` targets a compiler needs beyond D-70 and D-71, lowered inline (the two float
        conversions call the core runtime, as `fromInt64` does)."""
        cb = self.be.callbacks
        tag = ci.entity.name
        zero_enum = ir.Constant(ENUM, [I32(0), I64(0)])
        if name == "endsWith":
            text, suffix = a
            tl, sl = b.extract_value(text, 1), b.extract_value(suffix, 1)
            long_enough = b.icmp_signed(">=", tl, sl)
            at = b.select(long_enough, b.sub(tl, sl), I64(0))
            eq = b.call(cb["refined_bytes_equal"], [b.gep(b.extract_value(text, 0), [at]),
                                                    b.select(long_enough, sl, I64(0)), b.extract_value(suffix, 0), sl])
            return b.and_(long_enough, b.icmp_signed("!=", eq, I32(0))), None, None
        if name == "compare":
            left, right = a
            lp, ll, rp, rl = (b.extract_value(left, 0), b.extract_value(left, 1), b.extract_value(right, 0),
                              b.extract_value(right, 1))
            shorter = b.select(b.icmp_signed("<", ll, rl), ll, rl)
            # by length when one text is a prefix of the other: less (0), equal (1), greater (2)
            by_length = b.select(b.icmp_signed("<", ll, rl), I32(0), b.select(b.icmp_signed("==", ll, rl), I32(1), I32(2)))
            i_ptr, r_ptr = self.fn_alloca(I64, f"{tag}.at"), self.fn_alloca(I32, f"{tag}.order")
            b.store(I64(0), i_ptr)
            b.store(by_length, r_ptr)
            head, body, out = self.loop(b, tag)
            hb = ir.IRBuilder(head)
            i = hb.load(i_ptr)
            hb.cbranch(hb.icmp_signed("<", i, shorter), body, out)
            bb = ir.IRBuilder(body)
            x, y = bb.load(bb.gep(lp, [i])), bb.load(bb.gep(rp, [i]))
            differ = bb.icmp_unsigned("!=", x, y)
            nxt = self.fn.append_basic_block(f"{tag}.next")
            found = self.fn.append_basic_block(f"{tag}.differ")
            bb.cbranch(differ, found, nxt)
            fb = ir.IRBuilder(found)
            fb.store(fb.select(fb.icmp_unsigned("<", x, y), I32(0), I32(2)), r_ptr)
            fb.branch(out)
            nb = ir.IRBuilder(nxt)
            nb.store(nb.add(i, I64(1)), i_ptr)
            nb.branch(head)
            b.position_at_end(out)
            return b.insert_value(zero_enum, b.load(r_ptr), 0), None, None
        if name == "findFrom":
            text, needle, start = a
            size = b.extract_value(text, 1)
            ok = b.and_(b.icmp_signed(">=", start, I64(0)), b.icmp_signed("<=", start, size))
            from_ = b.select(ok, start, I64(0))
            at = b.call(cb["refined_find"], [b.gep(b.extract_value(text, 0), [from_]), b.sub(size, from_),
                                             b.extract_value(needle, 0), b.extract_value(needle, 1)])
            absent = b.icmp_signed("<", at, I64(0))
            # absent (tag 0) when the search ran and found nothing; outOfRange (tag 1, the start) when it could not run
            err = b.insert_value(zero_enum, b.select(ok, I32(0), I32(1)), 0)
            err = b.insert_value(err, b.select(ok, I64(0), start), 1)
            return b.add(at, from_), b.or_(b.not_(ok), absent), err
        if name == "fromByte":
            value, region = a
            ok = b.icmp_unsigned("<", value, I8(0x80))  # one byte is one character only below 128 (UTF-8)
            p_ptr = self.fn_alloca(PTR, f"{tag}.bytes")
            b.store(ir.Constant(PTR, None), p_ptr)
            with b.if_then(ok):
                p = b.call(cb["refined_region_alloc"], [region, I64(1)])
                b.store(value, p)
                b.store(p, p_ptr)
            s = b.insert_value(ir.Constant(STR, ir.Undefined), b.load(p_ptr), 0)
            s = b.insert_value(s, b.select(ok, I64(1), I64(0)), 1)
            return s, b.not_(ok), zero_enum  # invalidAt 0
        if name == "fromUInt64":
            return self.format_unsigned(b, a[0], a[1], 10, 20, 1, tag), None, None
        if name == "fromUInt64Hex":
            return self.format_unsigned(b, a[0], a[1], 16, 16, 1, tag), None, None
        if name == "fromByteHex":
            return self.format_unsigned(b, b.zext(a[0], I64), a[1], 16, 2, 2, tag), None, None
        if name == "toUInt64":
            text = a[0]
            p, n = b.extract_value(text, 0), b.extract_value(text, 1)
            acc, i_ptr = self.fn_alloca(I64, f"{tag}.value"), self.fn_alloca(I64, f"{tag}.at")
            bad, over = self.fn_alloca(I1, f"{tag}.bad"), self.fn_alloca(I1, f"{tag}.over")
            b.store(I64(0), acc)
            b.store(I64(0), i_ptr)
            b.store(b.icmp_signed("==", n, I64(0)), bad)
            b.store(I1(0), over)
            head, body, out = self.loop(b, tag)
            hb = ir.IRBuilder(head)
            i = hb.load(i_ptr)
            hb.cbranch(hb.icmp_signed("<", i, n), body, out)
            bb = ir.IRBuilder(body)
            c = bb.load(bb.gep(p, [i]))
            digit = bb.and_(bb.icmp_unsigned(">=", c, I8(ord("0"))), bb.icmp_unsigned("<=", c, I8(ord("9"))))
            bb.store(bb.or_(bb.load(bad), bb.not_(digit)), bad)
            times = bb.umul_with_overflow(bb.load(acc), I64(10))
            plus = bb.uadd_with_overflow(bb.extract_value(times, 0), bb.zext(bb.sub(c, I8(ord("0"))), I64))
            bb.store(bb.extract_value(plus, 0), acc)
            bb.store(bb.or_(bb.load(over), bb.or_(bb.extract_value(times, 1), bb.extract_value(plus, 1))), over)
            bb.store(bb.add(i, I64(1)), i_ptr)
            bb.branch(head)
            b.position_at_end(out)
            # not a number (tag 0) outranks out of range (tag 1): every byte is read before deciding
            is_bad, is_over = b.load(bad), b.load(over)
            err = b.insert_value(zero_enum, b.select(is_bad, I32(0), I32(1)), 0)
            return b.select(b.or_(is_bad, is_over), I64(0), b.load(acc)), b.or_(is_bad, is_over), err
        if name == "fromFloat64":
            len_ptr = self.fn_alloca(I64, f"{tag}.len")
            p = b.call(cb["refined_format_float"], [a[0], a[1], len_ptr])
            s = b.insert_value(ir.Constant(STR, ir.Undefined), p, 0)
            return b.insert_value(s, b.load(len_ptr), 1), None, None
        if name == "toFloat64":
            out_ptr = self.fn_alloca(F64, f"{tag}.parsed")
            status = b.call(cb["refined_parse_float"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1), out_ptr])
            err = b.insert_value(zero_enum, b.sub(status, I32(1)), 0)
            return b.load(out_ptr), b.icmp_signed("!=", status, I32(0)), err
        return None

    def convert_integer(self, b: ir.IRBuilder, v, src: str, dst: str, inv: str, ci: CallInfo, line: int):
        """D-90: an integer conversion. Each end of the target's range that the source can pass is checked (a
        value past it traps); then the value is cut down or extended by the source's signedness."""
        slo, shi = INTEGER_RANGES[src]
        dlo, dhi = INTEGER_RANGES[dst]
        signed = src not in UNSIGNED
        cmp = b.icmp_signed if signed else b.icmp_unsigned
        bad = I1(0)
        if dlo > slo:
            bad = b.or_(bad, cmp("<", v, ir.Constant(v.type, dlo)))
        if dhi < shi:
            bad = b.or_(bad, cmp(">", v, ir.Constant(v.type, dhi)))
        if dlo > slo or dhi < shi:
            with b.if_then(bad, likely=False):
                self.trap(b, line, f"`{inv}`: value out of range for `{dst}` in `{ci.entity.name}`")
        to = INT_TYPES[dst]
        if to.width < v.type.width:
            return b.trunc(v, to)
        if to.width > v.type.width:
            return b.sext(v, to) if signed else b.zext(v, to)
        return v

    def advance_position(self, b: ir.IRBuilder, text, pos, ci: CallInfo, line: int):
        """D-71: the position after the character at `pos`'s offset. A character is the UTF-8 sequence its lead
        byte announces when that many continuation bytes follow; any other byte is a character of its own. A
        newline byte (10) moves to column 1 of the next line; any other character moves one column right. An
        offset outside the text is `outOfRange` carrying the offset."""
        size = b.extract_value(text, 1)
        offset = b.extract_value(pos, 0)
        inside = b.and_(b.icmp_signed(">=", offset, I64(0)), b.icmp_signed("<", offset, size))
        start = b.block
        read = self.fn.append_basic_block(f"{ci.entity.name}.character")
        done = self.fn.append_basic_block(f"{ci.entity.name}.advanced")
        b.cbranch(inside, read, done)
        rb = ir.IRBuilder(read)
        base = rb.extract_value(text, 0)
        lead = rb.load(rb.gep(base, [offset]))

        def between(v, lo: int, hi: int):
            return rb.and_(rb.icmp_unsigned(">=", v, I8(lo)), rb.icmp_unsigned("<=", v, I8(hi)))
        want = rb.select(between(lead, 0xF0, 0xF4), I64(4), I64(1))
        want = rb.select(between(lead, 0xE0, 0xEF), I64(3), want)
        want = rb.select(between(lead, 0xC2, 0xDF), I64(2), want)
        whole = I1(1)
        for k in (1, 2, 3):
            at = rb.add(offset, I64(k))  # offset < size, so this cannot overflow
            there = rb.icmp_signed("<", at, size)
            byte = rb.load(rb.gep(base, [rb.select(there, at, offset)]))
            follows = rb.and_(there, rb.icmp_unsigned("==", rb.and_(byte, I8(0xC0)), I8(0x80)))
            whole = rb.and_(whole, rb.or_(rb.icmp_signed("<=", want, I64(k)), follows))
        width = rb.select(whole, want, I64(1))
        newline = rb.icmp_unsigned("==", lead, I8(10))
        next_line = rb.sadd_with_overflow(rb.extract_value(pos, 1), I64(1))
        next_column = rb.sadd_with_overflow(rb.extract_value(pos, 2), I64(1))
        overflowed = rb.select(newline, rb.extract_value(next_line, 1), rb.extract_value(next_column, 1))
        with rb.if_then(overflowed, likely=False):
            self.trap(rb, line, f"`string.advancePosition` overflowed `Int64` in `{ci.entity.name}`")
        moved = rb.insert_value(pos, rb.add(offset, width), 0)
        moved = rb.insert_value(moved, rb.select(newline, rb.extract_value(next_line, 0), rb.extract_value(pos, 1)), 1)
        moved = rb.insert_value(moved, rb.select(newline, I64(1), rb.extract_value(next_column, 0)), 2)
        rb.branch(done)
        b.position_at_end(done)
        phi = b.phi(pos.type)
        phi.add_incoming(moved, rb.block)
        phi.add_incoming(pos, start)
        err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), offset, 1)
        return phi, b.not_(inside), err

    def scope_text(self, sig) -> str:
        """D-38: what the runtime checks a scoped argument against before the call happens:
        `<resource>` then each scope of the capabilities this operation uses that grant the call's effect."""
        lines = []
        for verb, res in sorted(sig.effects):
            from .library import SCOPED_RESOURCES
            if res not in SCOPED_RESOURCES:
                continue
            lines.append(f"{verb} {res}")
            for u in self.ent.facts("uses"):
                cap = self.m.capabilities.get(u.text(0))
                if cap is None:
                    continue
                for g in cap.facts("grants"):
                    if g.text(0) == verb and g.text(1) == res and grant_scope(g) is not None:
                        lines.append(grant_scope(g))
        return "\n".join(lines)

    def scope_host(self, verb: str, resource: str) -> str:
        """The host part of the scope of the capability this operation uses for `<verb> <resource>`."""
        for u in self.ent.facts("uses"):
            cap = self.m.capabilities.get(u.text(0))
            if cap is None:
                continue
            for g in cap.facts("grants"):
                if g.text(0) == verb and g.text(1) == resource and grant_scope(g) is not None:
                    return grant_scope(g).rpartition(":")[0]
        return "127.0.0.1"

    # ------------------------------------------------------------ host calls

    def flatten(self, b: ir.IRBuilder, v) -> list:
        """A value as 64-bit slots (see host.py)."""
        t = v.type
        if isinstance(t, ir.IntType):
            if t.width == 64:
                return [v]
            return [b.zext(v, I64) if t.width == 1 else b.sext(v, I64)]
        if isinstance(t, ir.DoubleType):
            return [b.bitcast(v, I64)]
        if isinstance(t, ir.FloatType):
            return [b.bitcast(b.fpext(v, F64), I64)]
        if isinstance(t, ir.PointerType):
            return [b.ptrtoint(v, I64)]
        if isinstance(t, ir.LiteralStructType):
            out = []
            for i in range(len(t.elements)):
                out += self.flatten(b, b.extract_value(v, i))
            return out
        raise AssertionError(f"cannot pass {t} to the host")

    def slot_count(self, t: ir.Type) -> int:
        if isinstance(t, ir.LiteralStructType):
            return sum(self.slot_count(e) for e in t.elements)
        return 1

    def unflatten(self, b: ir.IRBuilder, slots: list, t: ir.Type):
        if isinstance(t, ir.IntType):
            s = slots.pop(0)
            return s if t.width == 64 else b.trunc(s, t)
        if isinstance(t, ir.DoubleType):
            return b.bitcast(slots.pop(0), F64)
        if isinstance(t, ir.FloatType):
            return b.fptrunc(b.bitcast(slots.pop(0), F64), F32)
        if isinstance(t, ir.PointerType):
            return b.inttoptr(slots.pop(0), t)
        if isinstance(t, ir.LiteralStructType):
            agg = ir.Constant(t, ir.Undefined)
            for i, e in enumerate(t.elements):
                agg = b.insert_value(agg, self.unflatten(b, slots, e), i)
            return agg
        raise AssertionError(f"cannot take {t} from the host")

    def host_call(self, b: ir.IRBuilder, name: str, ci: CallInfo, args: dict, line: int, extra=()):
        groups = [self.flatten(b, args[s]) for s, *_ in ci.args] + [self.flatten(b, e) for e in extra]
        sig = ci.sig
        out_t = self.lt(sig.output, line) if sig.output else None
        nres = self.slot_count(out_t) if out_t is not None else 0
        total = sum(len(g) for g in groups)
        argbuf = self.fn_alloca(ir.ArrayType(I64, max(total, 1)), f"{ci.entity.name}.hostArgs")
        resbuf = self.fn_alloca(ir.ArrayType(I64, max(nres, 1)), f"{ci.entity.name}.hostResults")
        payload = self.fn_alloca(I64, f"{ci.entity.name}.hostError")
        at = 0
        for g in groups:
            for s in g:
                b.store(s, b.gep(argbuf, [I32(0), I32(at)]))
                at += 1
        key = self.be.string(f"{name}|{','.join(str(len(g)) for g in groups)}|{nres}")
        status = b.call(self.be.callbacks["refined_host"],
                        [b.extract_value(key, 0), b.extract_value(key, 1), b.gep(argbuf, [I32(0), I32(0)]),
                         b.gep(resbuf, [I32(0), I32(0)]), payload])
        out = None
        if out_t is not None:
            slots = [b.load(b.gep(resbuf, [I32(0), I32(i)])) for i in range(nres)]
            out = self.unflatten(b, slots, out_t)
        if not sig.raises:
            return out, None, None
        err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.sub(status, I32(1)), 0)
        err = b.insert_value(err, b.load(payload), 1)
        return out, b.icmp_signed("!=", status, I32(0)), err

    def host_value(self, b: ir.IRBuilder, name: str, values: list, out_t: ir.Type, tag: str):
        """A host target the compiler calls itself (not a call row): `values` in, one value of `out_t` out."""
        groups = [self.flatten(b, v) for v in values]
        nres = self.slot_count(out_t)
        argbuf = self.fn_alloca(ir.ArrayType(I64, max(sum(len(g) for g in groups), 1)), f"{tag}.hostArgs")
        resbuf = self.fn_alloca(ir.ArrayType(I64, nres), f"{tag}.hostResults")
        payload = self.fn_alloca(I64, f"{tag}.hostError")
        for at, s in enumerate(s for g in groups for s in g):
            b.store(s, b.gep(argbuf, [I32(0), I32(at)]))
        key = self.be.string(f"{name}|{','.join(str(len(g)) for g in groups)}|{nres}")
        b.call(self.be.callbacks["refined_host"], [b.extract_value(key, 0), b.extract_value(key, 1),
                                                   b.gep(argbuf, [I32(0), I32(0)]), b.gep(resbuf, [I32(0), I32(0)]),
                                                   payload])
        return self.unflatten(b, [b.load(b.gep(resbuf, [I32(0), I32(i)])) for i in range(nres)], out_t)

    def derived(self, b: ir.IRBuilder, inv: str, ci: CallInfo, args: dict, line: int):
        parts = inv.split(".")
        type_text, member = ".".join(parts[:-1]), parts[-1]
        canon = self.t(resolve_type(self.world, self.m, type_text, line, self.info.tparams, quiet=True))
        info = self.world.type_info(canon)
        if info is None:
            self.unsupported(line, f"`{inv}`")
        if info.kind in ("opaque", "resource") or (info.kind == "instance" and info.generic in HOST_GENERICS):
            name = f"{info.generic if info.kind == 'instance' else canon}.{member}"
            if name in HOST_TARGETS:
                extra = [self.be.string(self.scope_text(ci.sig))] if ci.sig is not None and ci.sig.scoped else []
                stored = {"map.Map.put": ("value", 1), "set.Set.add": ("item", 0), "channel.Channel.send": ("item", 0)}
                if name in stored and info.args:
                    slot, which = stored[name]
                    held = info.args[which] if which < len(info.args) else info.args[0]
                    if slot in args and self.world.holds(held, lambda c: self.t(c) in ("String", "Bytes")) \
                            and self.t(held) not in ("String", "Bytes"):
                        # D-107: text inside a stored record or enum is copied into the collection's region
                        # (a stored `String` itself is copied by the host)
                        home = b.call(self.be.callbacks["refined_handle_region"], [list(args.values())[0]])
                        args = dict(args, **{slot: self.relocate(b, args[slot], held, home, line)})
                if name in ("map.Map.new", "set.Set.new"):
                    # D-61, D-93: the map or set learns whether its keys are text, compared by content and copied
                    # into it
                    extra.append(I64(1 if self.t(info.args[0]) == "String" else 0))
                if name == "map.Map.new":
                    # D-107: and the map learns whether its values are text, copied into it when they are put
                    extra.append(I64(1 if self.t(info.args[1]) in ("String", "Bytes") else 0))
                if name == "channel.Channel.new":
                    extra.append(I64(1 if self.t(info.args[0]) in ("String", "Bytes") else 0))
                return self.host_call(b, name, ci, args, line, extra)
            self.unsupported(line, f"`{inv}`")
        if info.kind == "instance" and info.generic == "list.List":
            return self.list_member(b, member, info.args[0], args, ci, line)
        if info.kind == "alias" and member == "toInt64":
            # D-100: a position's number is its low bits; the list identity above them is not part of it
            return b.and_(list(args.values())[0], I64((1 << POSITION_BITS) - 1)), None, None
        if info.kind == "record":
            t = self.be.ltype(canon, self.m.file, line)
            names = [n for n, _t in info.fields]
            if member == "new":
                agg = ir.Constant(t, ir.Undefined)
                for i, n in enumerate(names):
                    agg = b.insert_value(agg, args[n], i)
                return agg, None, None
            if member == "with":
                field = [s for s in args if s != "record"][0]
                return b.insert_value(args["record"], args[field], names.index(field)), None, None
            if member in names:
                return b.extract_value(args["record"], names.index(member)), None, None
            if member == "equals":
                return self.equals(b, args["left"], args["right"], canon, line), None, None
        if info.variants:
            names = [n for n, _p in info.variants]
            if member in names:
                payload = info.variants[names.index(member)][1]
                layout = self.be.enum_layout(canon)
                agg = self.be.enum_const(canon, member)
                if payload is not None:
                    if layout is None:
                        agg = b.insert_value(agg, self.widen(b, args["payload"], payload), 1)
                    else:
                        agg = b.insert_value(agg, args["payload"], layout[member])
                return agg, None, None
            if member == "equals":
                return self.equals(b, args["left"], args["right"], canon, line), None, None
        self.unsupported(line, f"`{inv}`")

    def sizeof(self, b: ir.IRBuilder, t: ir.Type):
        return b.ptrtoint(b.gep(ir.Constant(t.as_pointer(), None), [I32(1)]), I64)

    def list_member(self, b: ir.IRBuilder, member: str, item: str, args: dict, ci: CallInfo, line: int):
        """list.List in a region: a header {length, capacity, data, region} and a data block that doubles."""
        et = self.lt(item, line)
        alloc = self.be.callbacks["refined_region_alloc"]
        if member == "new":
            raw = b.call(alloc, [args["region"], self.sizeof(b, LIST_HEADER)])
            hdr = b.bitcast(raw, LIST)
            b.store(ir.Constant(LIST_HEADER, [I64(0), I64(0), ir.Constant(PTR, None), ir.Constant(PTR, None), I64(0)]),
                    hdr)
            b.store(args["region"], b.gep(hdr, [I32(0), I32(3)]))
            identity = b.atomic_rmw("add", self.be.list_counter(), I64(1), "seq_cst")
            b.store(b.add(identity, I64(1)), b.gep(hdr, [I32(0), I32(4)]))
            return hdr, None, None
        hdr = args["list"]
        len_ptr, cap_ptr, data_ptr = (b.gep(hdr, [I32(0), I32(i)]) for i in (0, 1, 2))
        length = b.load(len_ptr)
        if member == "length":
            return length, None, None
        if member == "clear":
            b.store(I64(0), len_ptr)
            return None, None, None
        if member == "truncate":
            want = args["length"]
            ok = b.and_(b.icmp_signed(">=", want, I64(0)), b.icmp_signed("<=", want, length))
            with b.if_then(ok):
                b.store(want, len_ptr)
            return None, b.not_(ok), b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), want, 1)
        if member == "removeLast":
            ok = b.icmp_signed(">", length, I64(0))
            start = b.block
            body = self.fn.append_basic_block(f"{ci.entity.name}.take")
            done = self.fn.append_basic_block(f"{ci.entity.name}.done")
            b.cbranch(ok, body, done)
            ib = ir.IRBuilder(body)
            last = ib.sub(length, I64(1))
            value = ib.load(ib.gep(ib.bitcast(ib.load(data_ptr), et.as_pointer()), [last]))
            ib.store(last, len_ptr)
            ib.branch(done)
            b.position_at_end(done)
            phi = b.phi(et)
            phi.add_incoming(value, body)
            phi.add_incoming(ir.Constant(et, None), start)
            return phi, b.not_(ok), b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), I64(-1), 1)
        if "item" in args and self.world.holds(item, lambda c: self.t(c) in ("String", "Bytes")):
            # D-107: a collection keeps its own copy of the text in what it stores, in its own region, so the
            # text outlives the region it came from
            args = dict(args, item=self.relocate(b, args["item"], item, b.load(b.gep(hdr, [I32(0), I32(3)])), line))
        if member in ("append", "appendIndexed"):
            cap = b.load(cap_ptr)
            with b.if_then(b.icmp_signed("==", length, cap)):
                newcap = b.select(b.icmp_signed("==", cap, I64(0)), I64(4), b.mul(cap, I64(2)))
                size = self.sizeof(b, et)
                fresh = b.call(alloc, [b.load(b.gep(hdr, [I32(0), I32(3)])), b.mul(newcap, size)])
                memcpy = self.be.module.declare_intrinsic("llvm.memcpy", [PTR, PTR, I64])
                b.call(memcpy, [fresh, b.load(data_ptr), b.mul(length, size), I1(0)])
                b.store(fresh, data_ptr)
                b.store(newcap, cap_ptr)
            slot = b.gep(b.bitcast(b.load(data_ptr), et.as_pointer()), [length])
            b.store(args["item"], slot)
            b.store(b.add(length, I64(1)), len_ptr)
            # D-60: `appendIndexed` gives back the new item's position, which is the length before it; D-100: the
            # position also carries the list's identity in its high bits
            if member == "appendIndexed":
                ident = b.load(b.gep(hdr, [I32(0), I32(4)]))
                return b.or_(b.shl(ident, I64(POSITION_BITS)), length), None, None
            return None, None, None
        if member in ("get", "set", "getOrTrap", "replace"):
            idx = args["index"]
            indexed = ci.sig is not None and ci.sig.inputs[1].type != "Int64"
            inside = b.and_(b.icmp_signed(">=", idx, I64(0)), b.icmp_signed("<", idx, length))
            err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), idx, 1)
            if indexed:
                # D-100: a position from another list (or from a list before it was replaced) has another identity
                ident = b.load(b.gep(hdr, [I32(0), I32(4)]))
                mine = b.icmp_signed("==", b.ashr(idx, I64(POSITION_BITS)), ident)
                low = b.and_(idx, I64((1 << POSITION_BITS) - 1))
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), low, 1)
                idx = low
                inside = b.and_(mine, b.icmp_signed("<", idx, length))
            if member == "getOrTrap":
                with b.if_then(b.not_(inside), likely=False):
                    self.trap(b, line, f"`{ci.entity.name}` read a position outside its list")
                return b.load(b.gep(b.bitcast(b.load(data_ptr), et.as_pointer()), [idx])), None, None
            start = b.block
            body = self.fn.append_basic_block(f"{ci.entity.name}.inside")
            done = self.fn.append_basic_block(f"{ci.entity.name}.done")
            b.cbranch(inside, body, done)
            ib = ir.IRBuilder(body)
            slot = ib.gep(ib.bitcast(ib.load(data_ptr), et.as_pointer()), [idx])
            if member == "set":
                ib.store(args["item"], slot)
                ib.branch(done)
                b.position_at_end(done)
                return None, b.not_(inside), err
            if member == "replace":
                if "region" in args:
                    # D-105: the old item is handed back as a value of the region the caller names, which must be
                    # the region the list was made in
                    own = ib.load(ib.gep(hdr, [I32(0), I32(3)]))
                    same = ib.icmp_unsigned("==", ib.ptrtoint(own, I64), ib.ptrtoint(args["region"], I64))
                    with ib.if_then(ib.not_(same), likely=False):
                        self.trap(ib, line, f"`{ci.entity.name}` named a region that is not the list's own")
                old = ib.load(slot)
                ib.store(args["item"], slot)
                after = ib.block
                ib.branch(done)
                b.position_at_end(done)
                phi = b.phi(et)
                phi.add_incoming(old, after)
                phi.add_incoming(ir.Constant(et, None), start)
                return phi, b.not_(inside), err
            value = ib.load(slot)
            ib.branch(done)
            b.position_at_end(done)
            phi = b.phi(et)
            phi.add_incoming(value, body)
            phi.add_incoming(ir.Constant(et, None), start)
            return phi, b.not_(inside), err
        self.unsupported(line, f"`list.List.{member}`")

    def equals(self, b: ir.IRBuilder, x, y, canon: str, line: int):
        """Structural equality: numbers by value, text and bytes by content, records field by field, enums
        by tag and the active payload, lists element by element, host values (handles) by identity."""
        canon = self.t(canon)
        if canon in INT_TYPES or canon == "Bool":
            return b.icmp_unsigned("==", x, y)
        if canon in ("Float64", "Float32"):
            return b.fcmp_ordered("==", x, y)
        if canon in ("String", "Bytes"):
            eq = b.call(self.be.callbacks["refined_bytes_equal"], [b.extract_value(x, 0), b.extract_value(x, 1),
                                                                   b.extract_value(y, 0), b.extract_value(y, 1)])
            return b.icmp_signed("!=", eq, I32(0))
        info = self.world.type_info(canon)
        if info.kind == "alias":
            return self.equals(b, x, y, info.base, line)
        if info.kind == "record":
            acc = I1(1)
            for i, (_n, ft) in enumerate(info.fields):
                acc = b.and_(acc, self.equals(b, b.extract_value(x, i), b.extract_value(y, i), ft, line))
            return acc
        if info.variants and self.be.enum_layout(canon) is None:
            return b.and_(b.icmp_signed("==", b.extract_value(x, 0), b.extract_value(y, 0)),
                          b.icmp_signed("==", b.extract_value(x, 1), b.extract_value(y, 1)))
        if info.variants:
            return self.wide_enum_equals(b, x, y, canon, info, line)
        if info.kind == "instance" and info.generic == "list.List":
            return self.list_equals(b, x, y, info.args[0], line)
        if isinstance(x.type, (ir.IntType, ir.PointerType)):
            return b.icmp_unsigned("==", x, y)  # handles and operation references: the same value
        self.unsupported(line, f"comparing values of `{canon}`")

    def wide_enum_equals(self, b: ir.IRBuilder, x, y, canon: str, info, line: int):
        layout = self.be.enum_layout(canon)
        same_tag = b.icmp_signed("==", b.extract_value(x, 0), b.extract_value(y, 0))
        done = self.fn.append_basic_block("enumEq.done")
        start = b.block
        sw_block = self.fn.append_basic_block("enumEq.payload")
        b.cbranch(same_tag, sw_block, done)
        b.position_at_end(sw_block)
        incoming = [(I1(0), start)]
        sw = b.switch(b.extract_value(x, 0), done)
        incoming.append((I1(1), sw_block))  # a variant without a payload: equal tags are enough
        for tag, (n, p) in enumerate(info.variants):
            if p is None:
                continue
            blk = self.fn.append_basic_block(f"enumEq.{n}")
            sw.add_case(I32(tag), blk)
            b.position_at_end(blk)
            eq = self.equals(b, b.extract_value(x, layout[n]), b.extract_value(y, layout[n]), p, line)
            incoming.append((eq, b.block))
            b.branch(done)
        b.position_at_end(done)
        phi = b.phi(I1)
        for v, blk in incoming:
            phi.add_incoming(v, blk)
        return phi

    def list_equals(self, b: ir.IRBuilder, x, y, item: str, line: int):
        et = self.lt(item, line)
        lx, ly = b.load(b.gep(x, [I32(0), I32(0)])), b.load(b.gep(y, [I32(0), I32(0)]))
        start = b.block
        head = self.fn.append_basic_block("listEq.head")
        body = self.fn.append_basic_block("listEq.body")
        done = self.fn.append_basic_block("listEq.done")
        b.cbranch(b.icmp_signed("==", lx, ly), head, done)
        b.position_at_end(head)
        i = b.phi(I64)
        i.add_incoming(I64(0), start)
        b.cbranch(b.icmp_signed("<", i, lx), body, done)
        b.position_at_end(body)
        dx = b.bitcast(b.load(b.gep(x, [I32(0), I32(2)])), et.as_pointer())
        dy = b.bitcast(b.load(b.gep(y, [I32(0), I32(2)])), et.as_pointer())
        eq = self.equals(b, b.load(b.gep(dx, [i])), b.load(b.gep(dy, [i])), item, line)
        step_end = b.block
        nxt = b.add(i, I64(1))
        i.add_incoming(nxt, step_end)
        b.cbranch(eq, head, done)
        b.position_at_end(done)
        phi = b.phi(I1)
        phi.add_incoming(I1(0), start)  # lengths differ
        phi.add_incoming(I1(1), head)  # every element matched
        phi.add_incoming(I1(0), step_end)  # an element differed
        return phi


def compile_roots(world: World, roots: list[tuple[str, str]],
                  options: Optional[dict] = None) -> tuple[Optional[ir.Module], list[Diagnostic]]:
    """`options`: `trace`, `coverage`, `debug` (instrumented builds). The module carries `refined_blocks`, the
    name of every block compiled, for coverage reports."""
    be = Backend(world, options)
    try:
        module = be.build(roots)
        module.refined_blocks = list(be.block_names)  # type: ignore[attr-defined]
        return module, []
    except Unsupported as exc:
        return None, [Diagnostic("R901", f"the backend does not support {exc.message} yet", exc.file, exc.line)]
