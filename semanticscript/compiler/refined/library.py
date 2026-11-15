"""Standard library signatures (LR-40) for the refined checker.

Each target states its parameters with modes, its output and who owns it, its
error enum, its effects, whether it waits, which parameter its result is a view
of, and which parameter is checked against a capability scope. The checker reads
only this table, so a call can be checked without the library's source.

The table covers the modules LR-40 rule 3 lists. Each module moves to
SemanticScript source and publishes its own signatures as the library is
rewritten (plan step 14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    mode: str  # value | borrowed | borrowedMutable | owned


@dataclass(frozen=True)
class Sig:
    inputs: tuple[Param, ...]
    output: Optional[str] = None
    output_owner: Optional[str] = None  # None, "caller", or the name of a Region parameter
    raises: Optional[str] = None
    effects: frozenset = frozenset()  # {(verb, resource)}
    waits: bool = False
    borrows: Optional[str] = None  # parameter whose value the result is a view of
    scoped: Optional[str] = None  # parameter whose literal value must fall inside the capability's scope


@dataclass
class TypeInfo:
    name: str  # canonical: builtin name or "module.Type"
    kind: str  # builtin | record | enum | opaque | resource | generic | instance | alias | operationType | typeParam
    plain: Optional[bool] = None  # None: computed from contents
    fields: list[tuple[str, str]] = field(default_factory=list)
    variants: list[tuple[str, Optional[str]]] = field(default_factory=list)
    targets: dict[str, Sig] = field(default_factory=dict)
    type_params: list[str] = field(default_factory=list)
    generic: Optional[str] = None  # for instances: canonical generic name
    args: list[str] = field(default_factory=list)  # for instances: type arguments
    sig: Optional[Sig] = None  # for operationType
    base: Optional[str] = None  # for alias
    # D-60: for an alias, the list type it indexes; for a list instance, the alias that indexes it
    index: Optional[str] = None
    # D-92: for an instance stated `in <operation>`, that generic operation
    owner: Optional[str] = None


def P(name: str, type_: str, mode: str) -> Param:
    return Param(name, type_, mode)


def E(*pairs: str) -> frozenset:
    return frozenset(tuple(p.split(" ")) for p in pairs)


BUILTINS = {
    **{t: TypeInfo(t, "builtin", True) for t in
       ("Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64",
        "Float32", "Float64", "Bool", "Byte", "ExitCode", "Region")},
    "String": TypeInfo("String", "builtin", False),
    "Bytes": TypeInfo("Bytes", "builtin", False),
}
INTEGER_RANGES = {
    "Int8": (-2**7, 2**7 - 1), "Int16": (-2**15, 2**15 - 1), "Int32": (-2**31, 2**31 - 1),
    "Int64": (-2**63, 2**63 - 1), "UInt8": (0, 2**8 - 1), "UInt16": (0, 2**16 - 1),
    "UInt32": (0, 2**32 - 1), "UInt64": (0, 2**64 - 1), "Byte": (0, 255),
    "ExitCode": (0, 255),  # what every platform delivers to the parent process
}
FLOAT_TYPES = {"Float32", "Float64"}

# LR-34 rule 5: resources whose capability must state a scope, and how a literal
# argument is compared with it. Every other resource is granted with `none` as its scope.
SCOPED_RESOURCES = {
    "net.tcp": "port",  # scope "<address>:<port>"; the literal is the port
    "net.outbound": "prefix",  # scope "<host>:<port>" prefix; the literal is the address
    "fs.files": "prefix",  # scope is a directory prefix; the literal path starts with it
    "process.programs": "exact",  # scope is the program name; the literal equals it
    "ffi.libraries": "exact",  # scope is the shared library's name; the literal equals it
    "ffi.symbols": "exact",  # scope is one C symbol's name: each foreign function is granted by name (D-41)
}


def path_within(path: str, scope: str, resolve: bool) -> bool:
    """D-41: an `fs.files` scope is a directory (`"data/"`: anything inside it) or a name pattern
    (`"suite-*"`: entries of that directory whose name starts with `suite-`). `resolve` follows `..` and
    links (at run time); without it the path is normalized as written (at check time)."""
    import os
    if not scope.endswith(("/", "*")):
        return False
    norm = (lambda p: os.path.normcase(os.path.realpath(p))) if resolve else \
        (lambda p: os.path.normcase(os.path.abspath(os.path.normpath(p))))
    real = norm(path)
    if scope.endswith("/"):
        base = norm(scope[:-1] or ".")
        return real == base or real.startswith(base.rstrip(os.sep) + os.sep)
    head, tail = os.path.split(scope[:-1])
    base = norm(head or ".")
    if not real.startswith(base.rstrip(os.sep) + os.sep):
        return False
    first = real[len(base.rstrip(os.sep)) + 1:].split(os.sep)[0]
    return first.startswith(os.path.normcase(tail))


def scope_within(resource: str, inner: str, outer: str) -> bool:
    """Whether a capability's scope `inner` is covered by the project's allowed scope `outer`."""
    kind = SCOPED_RESOURCES.get(resource)
    if kind is None:
        return True
    if inner == outer:
        return True
    if resource == "fs.files":
        if outer.endswith("/"):
            return path_within(inner.rstrip("/*") or ".", outer, resolve=False)
        return inner.endswith("*") and inner[:-1].startswith(outer[:-1]) and "/" not in inner[len(outer) - 1:]
    if resource == "net.outbound":
        return inner.startswith(outer) and (outer.endswith((":", "/")) or inner[len(outer)] in ":/")
    return False

# Types that may cross the foreign function interface: numbers and `Bool`, passed by the C ABI as is.
FOREIGN_TYPES = {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64", "Byte", "Float32", "Float64", "Bool"}


def _bin(t: str, out: str) -> Sig:
    return Sig((P("left", t, "copied"), P("right", t, "copied")), out)


def _un(t: str, out: str) -> Sig:
    return Sig((P("value", t, "copied"),), out)


def _compare(t: str) -> dict:
    names = ("equal", "notEqual", "lessThan", "lessOrEqual", "greaterThan", "greaterOrEqual")
    return {f"{n}{t}": _bin(t, "Bool") for n in names}


# D-90: every integer type the language declares has the same arithmetic, comparison, bit, and conversion
# targets, named `<operation><Type>`; checked arithmetic traps, and the wrapping and saturating forms are named.
# `ExitCode` is a status, not a number to compute with: it converts to and from `Int64` only.
INTEGER_TYPES = ("Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64", "Byte")
SIGNED_TYPES = ("Int8", "Int16", "Int32", "Int64")
UNSIGNED_SMALL = ("UInt8", "UInt16", "UInt32", "Byte")  # unsigned types narrower than `UInt64`


def conversion_name(source: str, target: str) -> str:
    """D-90: `convert.<source>To<Target>`; the source's leading capitals are lower case (`uint64ToInt64`)."""
    lead = source[:2].lower() + source[2:] if source.startswith("UInt") else source[0].lower() + source[1:]
    return f"{lead}To{target}"


def _conversions() -> dict:
    """D-90: every integer type to and from `Int64`, the unsigned types to and from `UInt64`, two's-complement
    reinterpretation between `Int64` and `UInt64`, and the float conversions. A conversion that can lose the value
    traps when it would; one that cannot never does."""
    pairs = [(t, "Int64") for t in INTEGER_TYPES if t != "Int64"] + [("Int64", t) for t in INTEGER_TYPES if t != "Int64"]
    pairs += [(t, "UInt64") for t in UNSIGNED_SMALL] + [("UInt64", t) for t in UNSIGNED_SMALL]
    pairs += [("ExitCode", "Int64"), ("Int64", "ExitCode"), ("Int64", "Float64"), ("Float64", "Int64"),
              ("Float32", "Float64"), ("Float64", "Float32")]
    out = {conversion_name(s, t): _un(s, t) for s, t in pairs}
    out["int64BitsToUInt64"] = _un("Int64", "UInt64")
    out["uint64BitsToInt64"] = _un("UInt64", "Int64")
    # D-127: a Float64's IEEE 754 bits as a UInt64 and back, unchanged (a NaN keeps its payload)
    out["float64BitsToUInt64"] = _un("Float64", "UInt64")
    out["uint64BitsToFloat64"] = _un("UInt64", "Float64")
    return out


def _math() -> dict:
    out = {}
    for t in INTEGER_TYPES:
        out.update({f"{op}{t}": _bin(t, t) for op in ("add", "subtract", "multiply", "divide", "remainder")})
        out.update({f"{kind}{op}{t}": _bin(t, t) for kind in ("wrapping", "saturating")
                    for op in ("Add", "Subtract", "Multiply")})
    for t in SIGNED_TYPES:
        out[f"negate{t}"] = _un(t, t)
        out[f"absolute{t}"] = _un(t, t)
    for t in ("Float32", "Float64"):
        out.update({f"{op}{t}": _bin(t, t) for op in ("add", "subtract", "multiply", "divide")})
    out["powerInt64"] = Sig((P("base", "Int64", "copied"), P("exponent", "Int64", "copied")), "Int64")
    return out


def _bits() -> dict:
    out = {}
    for t in INTEGER_TYPES:
        out.update({f"{op}{t}": _bin(t, t) for op in ("and", "or", "xor")})
        out[f"not{t}"] = _un(t, t)
        # the amount is a whole number from 0 to the type's width less one; any other amount traps.
        # `shiftRight` keeps the sign of a signed type and fills with zeros for an unsigned one
        for op in ("shiftLeft", "shiftRight"):
            out[f"{op}{t}"] = Sig((P("value", t, "copied"), P("amount", "Int64", "copied")), t)
    return out


def _generic(name: str, params: list[str], plain: Optional[bool] = False, variants=None) -> TypeInfo:
    return TypeInfo(name, "generic", plain, type_params=params, variants=variants or [])


def _err(name: str, *variants: tuple) -> TypeInfo:
    return TypeInfo(name, "enum", True, variants=list(variants))


_W = E("write console.stdout")
_RG = P("region", "Region", "borrowed")
_DL = P("deadline", "time.Deadline", "copied")

# D-121: the machine, for the runtime only. An address is 64 bits; loads and stores read and write memory as it is,
# with no check, so every target states `use machine.memory`, which build.sem allows and someone approves (D-53).
_MEM = E("use machine.memory")
_A = "machine.Address"
STATE_BYTES = 64 * 1024  # `machine.state`: one zeroed static block for the runtime's process-wide state


def _at(name: str) -> Param:
    return P(name, _A, "copied")


def _machine() -> dict:
    out = {
        "zero": Sig((), _A, effects=_MEM),  # the address 0
        "state": Sig((), _A, effects=_MEM),  # the first byte of the zeroed STATE_BYTES block
        "stackAddress": Sig((), _A, effects=_MEM),  # an address in the calling operation's own stack frame
        "offset": Sig((_at("address"), P("bytes", "Int64", "copied")), _A, effects=_MEM),
        "difference": Sig((_at("left"), _at("right")), "Int64", effects=_MEM),  # left less right, in bytes
        "equal": Sig((_at("left"), _at("right")), "Bool", effects=_MEM),
        "lessThan": Sig((_at("left"), _at("right")), "Bool", effects=_MEM),  # as unsigned numbers
        "toInt64": Sig((_at("address"),), "Int64", effects=_MEM),
        "fromInt64": Sig((P("value", "Int64", "copied"),), _A, effects=_MEM),
        # memmove semantics: the ranges may overlap
        "copy": Sig((_at("target"), _at("source"), P("bytes", "Int64", "copied")), effects=_MEM),
        "fill": Sig((_at("target"), P("value", "Byte", "copied"), P("bytes", "Int64", "copied")), effects=_MEM),
        # -1, 0, or 1: how the first differing byte compares, as unsigned bytes; 0 when none differs
        "compare": Sig((_at("left"), _at("right"), P("bytes", "Int64", "copied")), "Int32", effects=_MEM),
        "addressOfString": Sig((P("text", "String", "borrowed"),), _A, effects=_MEM),
        "addressOfBytes": Sig((P("data", "Bytes", "borrowed"),), _A, effects=_MEM),
        # views of memory the runtime keeps: nothing is copied, and nothing checks that the memory stays valid
        "stringAt": Sig((_at("address"), P("bytes", "Int64", "copied")), "String", effects=_MEM),
        "bytesAt": Sig((_at("address"), P("bytes", "Int64", "copied")), "Bytes", effects=_MEM),
        # `void function(argument)`, for the thunks the compiler hands the runtime when a task starts
        "callWithAddress": Sig((_at("function"), _at("argument")), effects=_MEM),
        # the program linked with the runtime: its entry operation's exit code (D-124)
        "runEntry": Sig((), "Int32", effects=_MEM),
        # D-131: the address of the runtime's `refined_task_entry` operation, where a task's fiber starts
        "taskEntry": Sig((), _A, effects=_MEM),
        # D-147: the address of the runtime's `refined_interrupt_handler` operation, which the operating system calls
        # when an interrupt arrives (SetConsoleCtrlHandler, rt_sigaction), and on Linux the few instructions a signal
        # handler returns through (`rt_sigreturn`, the SA_RESTORER trampoline)
        "interruptHandler": Sig((), _A, effects=_MEM),
        "signalRestorer": Sig((), _A, effects=_MEM),
        # D-139: stacks of the runtime's own on Linux, where there are no fibers: keep the running stack's place at
        # `saveAt` and resume the one kept at `resume`; or keep it and run `function(argument)` on a fresh stack
        # whose top is `top` (it never returns); or run the program's entry on a fresh stack and give its exit code
        "switchStack": Sig((_at("saveAt"), _at("resume")), effects=_MEM),
        "startStack": Sig((_at("saveAt"), _at("top"), _at("function"), _at("argument")), effects=_MEM),
        "runEntryOnStack": Sig((_at("top"),), "Int32", effects=_MEM),
        # D-153: the runtime's C library. `cLibrary` is the address of the table the compiler builds of every
        # `abi library "<name>"` operation: the count, then for each, sorted by name, the name's address, its length,
        # and the function's address. `callComparison` is `int function(left, right)`, the comparison a C caller
        # hands qsort and bsearch. `squareRoot` is the correctly rounded square root, one instruction on x86_64 and
        # AArch64 (llvm.sqrt, which needs no libm there)
        "cLibrary": Sig((), _A, effects=_MEM),
        # D-172: strerror's messages: how many numbers the table has, then for each the address of its message (a C
        # string), or 0 for a number with none; built from the C library of the machine that compiles, when it is
        # glibc (Python's os.strerror is glibc's strerror there), and empty anywhere else
        "errorMessages": Sig((), _A, effects=_MEM),
        "callComparison": Sig((_at("function"), _at("left"), _at("right")), "Int32", effects=_MEM),
        "squareRoot": Sig((P("value", "Float64", "copied"),), "Float64", effects=_MEM),
        # D-157: in an `abi library "<name>" variadic` operation, the address of its `va_list`, started
        # (`llvm.va_start`) on the arguments after its own: 32 bytes the caller of this target reads as the system lays
        # them out (x86_64 Linux, AArch64 Linux, and Windows each have their own)
        "variadicStart": Sig((), _A, effects=_MEM),
        # D-163: setjmp and longjmp. An `abi library` operation whose one call is `saveContext` is emitted as the
        # routine itself: it keeps the caller's callee-saved registers, stack pointer, and return address in the
        # buffer and gives 0; one whose one call is `resumeContext` restores them and returns from that setjmp again
        # with the value (1 for 0). Nothing else may call them: only the routine itself sees its caller's frame
        "saveContext": Sig((_at("buffer"),), "Int32", effects=_MEM),
        "resumeContext": Sig((_at("buffer"), P("value", "Int32", "copied")), effects=_MEM),
        # D-166: threads. `compareExchange32` is an atomic compare-and-exchange of a 32-bit cell (sequentially
        # consistent), giving what the cell held; `threadPointer` reads the running thread's pointer (%fs:0, which a
        # thread block holds itself at, on x86_64; tpidr_el0 on AArch64); `startThread` clones a thread (Linux) on a
        # stack whose top it is given, with a thread block for its thread pointer, its id kept at `tidAt` (cleared and
        # woken when it ends), running `refined_c_thread_main(record)` and ending: the new id, or a negative errno
        "compareExchange32": Sig((_at("address"), P("expected", "Int32", "copied"), P("desired", "Int32", "copied")),
                                 "Int32", effects=_MEM),
        "threadPointer": Sig((), _A, effects=_MEM),
        "setThreadPointer": Sig((_at("block"),), effects=_MEM),
        "startThread": Sig((_at("stackTop"), _at("block"), _at("tidAt"), _at("record")), "Int64", effects=_MEM),
        # D-168: the address of the runtime's `refined_c_thread_main`, where a Windows thread starts (CreateThread)
        "threadEntry": Sig((), _A, effects=_MEM),
        "loadLongDouble": Sig((_at("address"),), "machine.LongDouble", effects=_MEM),
        "storeLongDouble": Sig((_at("address"), P("value", "machine.LongDouble", "copied")), effects=_MEM),
        # arithmetic, each one rounding: x87's instructions on x86_64 Linux, libgcc's soft float (__addtf3, ...) on
        # AArch64 Linux, a double's on Windows; comparisons are ordered (false when either is a NaN)
        "addLongDouble": Sig((P("left", "machine.LongDouble", "copied"), P("right", "machine.LongDouble", "copied")),
                             "machine.LongDouble", effects=_MEM),
        "subtractLongDouble": Sig((P("left", "machine.LongDouble", "copied"),
                                   P("right", "machine.LongDouble", "copied")), "machine.LongDouble", effects=_MEM),
        "multiplyLongDouble": Sig((P("left", "machine.LongDouble", "copied"),
                                   P("right", "machine.LongDouble", "copied")), "machine.LongDouble", effects=_MEM),
        "divideLongDouble": Sig((P("left", "machine.LongDouble", "copied"), P("right", "machine.LongDouble", "copied")),
                                "machine.LongDouble", effects=_MEM),
        "lessLongDouble": Sig((P("left", "machine.LongDouble", "copied"), P("right", "machine.LongDouble", "copied")),
                              "Bool", effects=_MEM),
        "equalLongDouble": Sig((P("left", "machine.LongDouble", "copied"), P("right", "machine.LongDouble", "copied")),
                               "Bool", effects=_MEM),
        "longDoubleFromFloat64": Sig((P("value", "Float64", "copied"),), "machine.LongDouble", effects=_MEM),
        "longDoubleToFloat64": Sig((P("value", "machine.LongDouble", "copied"),), "Float64", effects=_MEM),
        "longDoubleFromInt64": Sig((P("value", "Int64", "copied"),), "machine.LongDouble", effects=_MEM),
        # D-167: fenv.h and fma. `loadFloatControl` is the floating-point control and status (x86_64: MXCSR in the low
        # 32 bits; AArch64: FPCR | FPSR << 32), `storeFloatControl` sets them; `fusedMultiplyAdd` is a * b + c rounded
        # once (llvm.fma: one instruction, FMA3 on x86_64, which every x86_64 processor since 2015 has)
        "loadFloatControl": Sig((), "UInt64", effects=_MEM),
        "storeFloatControl": Sig((P("value", "UInt64", "copied"),), effects=_MEM),
        "fusedMultiplyAdd": Sig((P("left", "Float64", "copied"), P("right", "Float64", "copied"),
                                 P("addend", "Float64", "copied")), "Float64", effects=_MEM),
        "fusedMultiplyAdd32": Sig((P("left", "Float32", "copied"), P("right", "Float32", "copied"),
                                   P("addend", "Float32", "copied")), "Float32", effects=_MEM),
    }
    for t in ("Byte", "Int32", "Int64", "UInt64", "Float64", "Float32", "Address"):
        canon = _A if t == "Address" else t
        out[f"load{t}"] = Sig((_at("address"),), canon, effects=_MEM)
        out[f"store{t}"] = Sig((_at("address"), P("value", canon, "copied")), effects=_MEM)
    return out


# D-122: the operating system's entry points, one typed target each, called directly (Windows: imported from
# kernel32.dll). `system.calls` is granted like `machine.memory`. Each row: target, the function's own name, and
# its signature in the C ABI (a DWORD or BOOL is `Int32`, a HANDLE or pointer `machine.Address`, a SIZE_T `Int64`).
_SYS = E("use system.calls")
SYSTEM_CALLS: dict[str, tuple[str, Sig]] = {
    "getStdHandle": ("GetStdHandle", Sig((P("which", "Int32", "copied"),), _A, effects=_SYS)),
    "writeFile": ("WriteFile", Sig((_at("handle"), _at("buffer"), P("bytes", "Int32", "copied"), _at("written"),
                                    _at("overlapped")), "Int32", effects=_SYS)),
    "readFile": ("ReadFile", Sig((_at("handle"), _at("buffer"), P("bytes", "Int32", "copied"), _at("read"),
                                  _at("overlapped")), "Int32", effects=_SYS)),
    "exitProcess": ("ExitProcess", Sig((P("code", "Int32", "copied"),), effects=_SYS)),
    "virtualAlloc": ("VirtualAlloc", Sig((_at("address"), P("bytes", "Int64", "copied"),
                                          P("allocationType", "Int32", "copied"), P("protection", "Int32", "copied")),
                                         _A, effects=_SYS)),
    "virtualFree": ("VirtualFree", Sig((_at("address"), P("bytes", "Int64", "copied"), P("freeType", "Int32", "copied")),
                                       "Int32", effects=_SYS)),
    "getCommandLineW": ("GetCommandLineW", Sig((), _A, effects=_SYS)),
    "getLastError": ("GetLastError", Sig((), "Int32", effects=_SYS)),
    # D-128: the process heap, for the runtime's memory that grows and is given back piece by piece (host objects)
    "getProcessHeap": ("GetProcessHeap", Sig((), _A, effects=_SYS)),
    "heapAlloc": ("HeapAlloc", Sig((_at("heap"), P("flags", "Int32", "copied"), P("bytes", "Int64", "copied")), _A,
                                   effects=_SYS)),
    "heapReAlloc": ("HeapReAlloc", Sig((_at("heap"), P("flags", "Int32", "copied"), _at("memory"),
                                        P("bytes", "Int64", "copied")), _A, effects=_SYS)),
    "heapFree": ("HeapFree", Sig((_at("heap"), P("flags", "Int32", "copied"), _at("memory")), "Int32", effects=_SYS)),
}


def _sys(symbol: str, params: tuple, output=None) -> tuple[str, Sig]:
    """A `system` row: each parameter `name:Type`, the type `A` for an address (a HANDLE or a pointer)."""
    inputs = []
    for spec in params:
        name, _sep, kind = spec.partition(":")
        inputs.append(_at(name) if kind == "A" else P(name, kind, "copied"))
    return symbol, Sig(tuple(inputs), _A if output == "A" else output, effects=_SYS)


# D-132: stage 3 and 4 of the runtime in SemanticScript: files, paths, text in UTF-16, the environment, child
# processes and pipes, time, and the fibers tasks run on. Every one is kernel32's own.
SYSTEM_CALLS.update({
    "createFileW": _sys("CreateFileW", ("name:A", "access:Int32", "share:Int32", "security:A", "disposition:Int32",
                                        "flags:Int32", "template:A"), "A"),
    "closeHandle": _sys("CloseHandle", ("handle:A",), "Int32"),
    "setFilePointerEx": _sys("SetFilePointerEx", ("handle:A", "distance:Int64", "position:A", "method:Int32"),
                             "Int32"),
    "setEndOfFile": _sys("SetEndOfFile", ("handle:A",), "Int32"),
    "getFileInformationByHandle": _sys("GetFileInformationByHandle", ("handle:A", "information:A"), "Int32"),
    "getFileType": _sys("GetFileType", ("handle:A",), "Int32"),
    "getFileAttributesW": _sys("GetFileAttributesW", ("name:A",), "Int32"),
    "getFullPathNameW": _sys("GetFullPathNameW", ("name:A", "units:Int32", "buffer:A", "filePart:A"), "Int32"),
    "getFinalPathNameByHandleW": _sys("GetFinalPathNameByHandleW", ("handle:A", "buffer:A", "units:Int32",
                                                                    "flags:Int32"), "Int32"),
    "findFirstFileW": _sys("FindFirstFileW", ("name:A", "found:A"), "A"),
    "findNextFileW": _sys("FindNextFileW", ("handle:A", "found:A"), "Int32"),
    "findClose": _sys("FindClose", ("handle:A",), "Int32"),
    "createDirectoryW": _sys("CreateDirectoryW", ("name:A", "security:A"), "Int32"),
    "removeDirectoryW": _sys("RemoveDirectoryW", ("name:A",), "Int32"),
    "deleteFileW": _sys("DeleteFileW", ("name:A",), "Int32"),
    # D-160: stdio's `rename`, which replaces a file that is there as POSIX's rename does
    "moveFileExW": _sys("MoveFileExW", ("existing:A", "replacement:A", "flags:Int32"), "Int32"),
    "lockFile": _sys("LockFile", ("handle:A", "offsetLow:Int32", "offsetHigh:Int32", "bytesLow:Int32",
                                  "bytesHigh:Int32"), "Int32"),
    "unlockFile": _sys("UnlockFile", ("handle:A", "offsetLow:Int32", "offsetHigh:Int32", "bytesLow:Int32",
                                      "bytesHigh:Int32"), "Int32"),
    "multiByteToWideChar": _sys("MultiByteToWideChar", ("codePage:Int32", "flags:Int32", "text:A", "bytes:Int32",
                                                        "wide:A", "units:Int32"), "Int32"),
    "wideCharToMultiByte": _sys("WideCharToMultiByte", ("codePage:Int32", "flags:Int32", "wide:A", "units:Int32",
                                                        "text:A", "bytes:Int32", "defaultCharacter:A",
                                                        "usedDefault:A"), "Int32"),
    "lcMapStringEx": _sys("LCMapStringEx", ("locale:A", "flags:Int32", "source:A", "sourceUnits:Int32", "target:A",
                                            "targetUnits:Int32", "version:A", "reserved:A", "sortHandle:Int64"),
                          "Int32"),
    "getEnvironmentVariableW": _sys("GetEnvironmentVariableW", ("name:A", "buffer:A", "units:Int32"), "Int32"),
    "createProcessW": _sys("CreateProcessW", ("application:A", "commandLine:A", "processSecurity:A",
                                              "threadSecurity:A", "inherit:Int32", "flags:Int32", "environment:A",
                                              "directory:A", "startup:A", "information:A"), "Int32"),
    "createPipe": _sys("CreatePipe", ("readEnd:A", "writeEnd:A", "security:A", "bytes:Int32"), "Int32"),
    "peekNamedPipe": _sys("PeekNamedPipe", ("handle:A", "buffer:A", "bytes:Int32", "read:A", "available:A",
                                            "left:A"), "Int32"),
    "setHandleInformation": _sys("SetHandleInformation", ("handle:A", "mask:Int32", "flags:Int32"), "Int32"),
    "duplicateHandle": _sys("DuplicateHandle", ("sourceProcess:A", "source:A", "targetProcess:A", "target:A",
                                                "access:Int32", "inherit:Int32", "options:Int32"), "Int32"),
    "getCurrentProcess": _sys("GetCurrentProcess", (), "A"),
    "waitForSingleObject": _sys("WaitForSingleObject", ("handle:A", "milliseconds:Int32"), "Int32"),
    "waitForMultipleObjects": _sys("WaitForMultipleObjects", ("count:Int32", "handles:A", "all:Int32",
                                                              "milliseconds:Int32"), "Int32"),
    "getExitCodeProcess": _sys("GetExitCodeProcess", ("process:A", "code:A"), "Int32"),
    "terminateProcess": _sys("TerminateProcess", ("process:A", "code:Int32"), "Int32"),
    "getTickCount64": _sys("GetTickCount64", (), "Int64"),
    "getSystemTimeAsFileTime": _sys("GetSystemTimeAsFileTime", ("time:A",)),
    "getProcessTimes": _sys("GetProcessTimes", ("process:A", "created:A", "exited:A", "kernel:A", "user:A"),
                            "Int32"),
    "getDynamicTimeZoneInformation": _sys("GetDynamicTimeZoneInformation", ("information:A",), "Int32"),
    "sleep": _sys("Sleep", ("milliseconds:Int32",)),
    # D-168: threads.h on Windows: threads, the thread-local slot a thread's block is kept in, and the running thread
    "createThread": _sys("CreateThread", ("security:A", "stackBytes:Int64", "start:A", "parameter:A", "flags:Int32",
                                          "threadId:A"), "A"),
    "exitThread": _sys("ExitThread", ("code:Int32",)),
    "switchToThread": _sys("SwitchToThread", (), "Int32"),
    "getCurrentThreadId": _sys("GetCurrentThreadId", (), "Int32"),
    "tlsAlloc": _sys("TlsAlloc", (), "Int32"),
    "tlsGetValue": _sys("TlsGetValue", ("index:Int32",), "A"),
    "tlsSetValue": _sys("TlsSetValue", ("index:Int32", "value:A"), "Int32"),
    "convertThreadToFiber": _sys("ConvertThreadToFiber", ("parameter:A",), "A"),
    "createFiberEx": _sys("CreateFiberEx", ("commitBytes:Int64", "reserveBytes:Int64", "flags:Int32", "start:A",
                                            "parameter:A"), "A"),
    "switchToFiber": _sys("SwitchToFiber", ("fiber:A",)),
    "deleteFiber": _sys("DeleteFiber", ("fiber:A",)),
    "loadLibraryW": _sys("LoadLibraryW", ("name:A",), "A"),
    "getProcAddress": _sys("GetProcAddress", ("module:A", "name:A"), "A"),
    # D-147: the interrupt handler (signal) and the events that wake the scheduler, kernel32's own
    "setConsoleCtrlHandler": _sys("SetConsoleCtrlHandler", ("handler:A", "add:Int32"), "Int32"),
    "createEventW": _sys("CreateEventW", ("security:A", "manualReset:Int32", "initialState:Int32", "name:A"), "A"),
    "setEvent": _sys("SetEvent", ("event:A",), "Int32"),
    "resetEvent": _sys("ResetEvent", ("event:A",), "Int32"),
})

# D-144: the operating system's interfaces outside kernel32 that the runtime calls where Windows gives no other
# interface: Winsock (ws2_32.dll) for `net`, and the system's random number generator (bcrypt.dll) for `random`.
# Neither is a C library. Each function is imported from the DLL named here; every other row is kernel32's.
SYSTEM_DLLS: dict[str, str] = {}


def _dll(dll: str, rows: dict) -> dict:
    for _name, (symbol, _sig) in rows.items():
        SYSTEM_DLLS[symbol] = dll
    return rows


SYSTEM_CALLS.update(_dll("ws2_32", {
    "wsaStartup": _sys("WSAStartup", ("version:Int32", "data:A"), "Int32"),
    "wsaGetLastError": _sys("WSAGetLastError", (), "Int32"),
    # named `winsock<Name>`: Linux's system calls of the same names are rows of their own (LINUX_CALLS)
    "winsockSocket": _sys("socket", ("family:Int32", "kind:Int32", "protocol:Int32"), "A"),
    "winsockBind": _sys("bind", ("socket:A", "address:A", "bytes:Int32"), "Int32"),
    "winsockListen": _sys("listen", ("socket:A", "backlog:Int32"), "Int32"),
    "winsockAccept": _sys("accept", ("socket:A", "address:A", "bytes:A"), "A"),
    "winsockConnect": _sys("connect", ("socket:A", "address:A", "bytes:Int32"), "Int32"),
    "winsockRecv": _sys("recv", ("socket:A", "buffer:A", "bytes:Int32", "flags:Int32"), "Int32"),
    "winsockSend": _sys("send", ("socket:A", "buffer:A", "bytes:Int32", "flags:Int32"), "Int32"),
    "winsockShutdown": _sys("shutdown", ("socket:A", "how:Int32"), "Int32"),
    "closesocket": _sys("closesocket", ("socket:A",), "Int32"),
    "wsaEventSelect": _sys("WSAEventSelect", ("socket:A", "event:A", "events:Int32"), "Int32"),
    "wsaEnumNetworkEvents": _sys("WSAEnumNetworkEvents", ("socket:A", "event:A", "events:A"), "Int32"),
    "getaddrinfo": _sys("getaddrinfo", ("node:A", "service:A", "hints:A", "result:A"), "Int32"),
    "freeaddrinfo": _sys("freeaddrinfo", ("info:A",)),
}))
SYSTEM_CALLS.update(_dll("bcrypt", {
    "bCryptGenRandom": _sys("BCryptGenRandom", ("algorithm:A", "buffer:A", "bytes:Int32", "flags:Int32"), "Int32"),
}))


def _linux(number: int, params: tuple) -> tuple[int, Sig]:
    """A Linux `system` row: the x86_64 system call number and its parameters, each `name` (an `Int64`) or
    `name:A` (a pointer, `machine.Address`); every call gives the kernel's `Int64` result, a negative errno when it
    fails."""
    inputs = []
    for spec in params:
        name, _sep, kind = spec.partition(":")
        inputs.append(_at(name) if kind == "A" else P(name, "Int64", "copied"))
    return number, Sig(tuple(inputs), "Int64", effects=_SYS)


# D-138: Linux, reached through raw system calls (x86_64 numbers), as the runtime in SemanticScript needs them. Each
# is a `syscall` instruction in the backend; there is no C library to call. Named after the system call.
LINUX_CALLS: dict[str, tuple[int, Sig]] = {
    "read": _linux(0, ("fd", "buffer:A", "bytes")),
    "write": _linux(1, ("fd", "buffer:A", "bytes")),
    "close": _linux(3, ("fd",)),
    "fstat": _linux(5, ("fd", "status:A")),
    "poll": _linux(7, ("fds:A", "count", "milliseconds")),
    "lseek": _linux(8, ("fd", "offset", "whence")),
    "mmap": _linux(9, ("address:A", "bytes", "protection", "flags", "fd", "offset")),
    "munmap": _linux(11, ("address:A", "bytes")),
    "rtSigaction": _linux(13, ("signal", "action:A", "old:A", "maskBytes")),
    "ioctl": _linux(16, ("fd", "request", "argument:A")),
    "dup2": _linux(33, ("fd", "target")),
    "nanosleep": _linux(35, ("duration:A", "left:A")),
    "getpid": _linux(39, ()),
    "fork": _linux(57, ()),
    "execve": _linux(59, ("path:A", "arguments:A", "environment:A")),
    "exit": _linux(60, ("code",)),
    "wait4": _linux(61, ("pid", "status:A", "options", "usage:A")),
    "kill": _linux(62, ("pid", "signal")),
    "fcntl": _linux(72, ("fd", "command", "argument")),
    "flock": _linux(73, ("fd", "operation")),
    "ftruncate": _linux(77, ("fd", "bytes")),
    "getcwd": _linux(79, ("buffer:A", "bytes")),
    "getdents64": _linux(217, ("fd", "buffer:A", "bytes")),
    "clockGettime": _linux(228, ("clock", "time:A")),
    "exitGroup": _linux(231, ("code",)),
    "openat": _linux(257, ("directory", "path:A", "flags", "mode")),
    "mkdirat": _linux(258, ("directory", "path:A", "mode")),
    "newfstatat": _linux(262, ("directory", "path:A", "status:A", "flags")),
    "unlinkat": _linux(263, ("directory", "path:A", "flags")),
    "readlinkat": _linux(267, ("directory", "path:A", "buffer:A", "bytes")),
    "pipe2": _linux(293, ("fds:A", "flags")),
    "pidfdOpen": _linux(434, ("pid", "flags")),
    # D-148, D-149: sockets for `net` and its resolver, and the kernel's random bytes for `random`
    "socket": _linux(41, ("family", "kind", "protocol")),
    "connect": _linux(42, ("fd", "address:A", "bytes")),
    "sendto": _linux(44, ("fd", "buffer:A", "bytes", "flags", "address:A", "addressBytes")),
    "recvfrom": _linux(45, ("fd", "buffer:A", "bytes", "flags", "address:A", "addressBytes:A")),
    "shutdown": _linux(48, ("fd", "how")),
    "bind": _linux(49, ("fd", "address:A", "bytes")),
    "listen": _linux(50, ("fd", "backlog")),
    "setsockopt": _linux(54, ("fd", "level", "option", "value:A", "bytes")),
    "getsockopt": _linux(55, ("fd", "level", "option", "value:A", "bytes:A")),
    "accept4": _linux(288, ("fd", "address:A", "bytes:A", "flags")),
    "getrandom": _linux(318, ("buffer:A", "bytes", "flags")),
    # D-155: the thread pointer a loaded library's code reads (its stack protector's canary at %fs:0x28); x86_64 only
    "archPrctl": _linux(158, ("code", "address:A")),
    # D-160: stdio's `rename`
    "renameat2": _linux(316, ("oldDirectory", "oldPath:A", "newDirectory", "newPath:A", "flags")),
    # D-166: threads.h's mutexes, condition variables, and joins wait on futexes
    "futex": _linux(202, ("address:A", "operation", "value", "timeout:A", "address2:A", "value3")),
    "gettid": _linux(186, ()),
    "schedYield": _linux(24, ()),
}

# D-150: the same system calls on AArch64, by the kernel's generic numbers. AArch64 has no `poll`, `fork`, or `dup2`:
# the backend makes `poll` a `ppoll` (its milliseconds a timespec), `fork` a `clone` of SIGCHLD, and `dup2` a `dup3`.
AARCH64_NUMBERS: dict[str, int] = {
    "read": 63, "write": 64, "close": 57, "fstat": 80, "poll": 73, "lseek": 62, "mmap": 222, "munmap": 215,
    "rtSigaction": 134, "ioctl": 29, "dup2": 24, "nanosleep": 101, "getpid": 172, "fork": 220, "execve": 221,
    "exit": 93, "wait4": 260, "kill": 129, "fcntl": 25, "flock": 32, "ftruncate": 46, "getcwd": 17,
    "getdents64": 61, "clockGettime": 113, "exitGroup": 94, "openat": 56, "mkdirat": 34, "newfstatat": 79,
    "unlinkat": 35, "readlinkat": 78, "pipe2": 59, "pidfdOpen": 434, "socket": 198, "connect": 203, "sendto": 206,
    "recvfrom": 207, "shutdown": 210, "bind": 200, "listen": 201, "setsockopt": 208, "getsockopt": 209,
    "accept4": 242, "getrandom": 278, "renameat2": 276, "futex": 98, "gettid": 178, "schedYield": 124,
}  # D-155: `archPrctl` has no AArch64 number (the thread pointer is a register there); the backend lowers it to a trap

LIBRARY: dict[str, dict] = {
    "machine": {
        # D-174: C's long double, which an `abi library` operation takes and gives as the C ABI passes it: x87's 80
        # bits on x86_64 Linux, binary128 on AArch64 Linux, a double on Windows (the Microsoft ABI's long double);
        # the runtime reads and writes one only through memory (`loadLongDouble`, `storeLongDouble`), 16 bytes
        "types": {"Address": TypeInfo(_A, "opaque", True),
                  "LongDouble": TypeInfo("machine.LongDouble", "opaque", True)},
        "targets": _machine(),
    },
    "system": {
        "types": {},
        "targets": {**{name: sig for name, (_symbol, sig) in SYSTEM_CALLS.items()},
                    **{name: sig for name, (_number, sig) in LINUX_CALLS.items()},
                    # D-138: whether the program is compiled for Linux, a constant of the target
                    "linux": Sig((), "Bool", effects=_SYS),
                    # D-150: whether the program is compiled for AArch64, where some kernel structures differ
                    "aarch64": Sig((), "Bool", effects=_SYS)},
    },
    "console": {
        "types": {
            "WriteError": _err("console.WriteError", ("failed", "Int32")),
            "ReadError": _err("console.ReadError", ("endOfInput", None), ("tooLong", None), ("timedOut", None),
                              ("cancelled", None), ("failed", "Int32")),
        },
        "targets": {
            "writeLine": Sig((P("text", "String", "borrowed"),), raises="console.WriteError", effects=_W),
            "write": Sig((P("text", "String", "borrowed"),), raises="console.WriteError", effects=_W),
            "writeIntegerLine": Sig((P("value", "Int64", "copied"),), raises="console.WriteError", effects=_W),
            "writeFloatLine": Sig((P("value", "Float64", "copied"),), raises="console.WriteError", effects=_W),
            "writeError": Sig((P("text", "String", "borrowed"),), raises="console.WriteError",
                              effects=E("write console.stderr")),
            "readLine": Sig((_RG, P("maxBytes", "Int64", "copied"), _DL), "String", "region", "console.ReadError",
                            E("read console.stdin"), waits=True),
        },
    },
    "math": {
        "types": {},
        "targets": _math(),
    },
    "compare": {
        "types": {},
        "targets": {k: v for t in INTEGER_TYPES + ("Float32", "Float64") for k, v in _compare(t).items()},
    },
    "logic": {
        "types": {},
        "targets": {
            "and": _bin("Bool", "Bool"),
            "or": _bin("Bool", "Bool"),
            "xor": _bin("Bool", "Bool"),
            "not": _un("Bool", "Bool"),
        },
    },
    "bits": {
        "types": {},
        "targets": _bits(),
    },
    "convert": {
        "types": {},
        "targets": _conversions(),
    },
    "string": {
        "types": {
            "StringIndexError": _err("string.StringIndexError", ("outOfRange", "Int64")),
            "ParseError": _err("string.ParseError", ("notANumber", None), ("outOfRange", None)),
            "NotFound": _err("string.NotFound", ("absent", None)),
            "Utf8Error": _err("string.Utf8Error", ("invalidAt", "Int64")),
            # D-91: how two texts order, byte by byte (which is code point order for UTF-8), then by length
            "Ordering": _err("string.Ordering", ("less", None), ("equal", None), ("greater", None)),
            # D-91: a search from an offset: nothing found, or an offset outside the text
            "FindError": _err("string.FindError", ("absent", None), ("outOfRange", "Int64")),
            # D-71: where a character starts in a text: its byte offset, and its line and column (both from 1)
            "Position": TypeInfo("string.Position", "record", True,
                                 fields=[("offset", "Int64"), ("line", "Int64"), ("column", "Int64")]),
        },
        "targets": {
            "byteLength": Sig((P("text", "String", "borrowed"),), "Int64"),
            # D-101: the trapping twin of `byteAt`
            "byteAtOrTrap": Sig((P("text", "String", "borrowed"), P("index", "Int64", "copied")), "Byte"),
            "byteAt": Sig((P("text", "String", "borrowed"), P("index", "Int64", "copied")), "Byte",
                          raises="string.StringIndexError"),
            "equals": Sig((P("left", "String", "borrowed"), P("right", "String", "borrowed")), "Bool"),
            "startsWith": Sig((P("text", "String", "borrowed"), P("prefix", "String", "borrowed")), "Bool"),
            "find": Sig((P("text", "String", "borrowed"), P("needle", "String", "borrowed")), "Int64",
                        raises="string.NotFound"),
            # D-110: whether the needle occurs, as a value rather than an error
            "contains": Sig((P("text", "String", "borrowed"), P("needle", "String", "borrowed")), "Bool"),
            "slice": Sig((P("text", "String", "borrowed"), P("start", "Int64", "copied"), P("length", "Int64", "copied")),
                         "String", raises="string.StringIndexError", borrows="text"),
            "concat": Sig((P("left", "String", "borrowed"), P("right", "String", "borrowed"), _RG), "String",
                          output_owner="region"),
            "fromInt64": Sig((P("value", "Int64", "copied"), _RG), "String", output_owner="region"),
            "toInt64": Sig((P("text", "String", "borrowed"),), "Int64", raises="string.ParseError"),
            "fromBytes": Sig((P("bytes", "Bytes", "borrowed"), _RG), "String", "region", "string.Utf8Error"),
            "toBytes": Sig((P("text", "String", "borrowed"),), "Bytes", borrows="text"),
            # D-71: the position of the character after the one at `position` (a newline starts the next line)
            "advancePosition": Sig((P("text", "String", "borrowed"), P("position", "string.Position", "copied")),
                                   "string.Position", raises="string.StringIndexError"),
            # D-91: text, numbers, and bytes for a compiler, all lowered inline (no host)
            "endsWith": Sig((P("text", "String", "borrowed"), P("suffix", "String", "borrowed")), "Bool"),
            "compare": Sig((P("left", "String", "borrowed"), P("right", "String", "borrowed")), "string.Ordering"),
            "findFrom": Sig((P("text", "String", "borrowed"), P("needle", "String", "borrowed"),
                             P("start", "Int64", "copied")), "Int64", raises="string.FindError"),
            "fromByte": Sig((P("value", "Byte", "copied"), _RG), "String", "region", "string.Utf8Error"),
            "fromUInt64": Sig((P("value", "UInt64", "copied"), _RG), "String", output_owner="region"),
            "toUInt64": Sig((P("text", "String", "borrowed"),), "UInt64", raises="string.ParseError"),
            "fromUInt64Hex": Sig((P("value", "UInt64", "copied"), _RG), "String", output_owner="region"),
            "fromByteHex": Sig((P("value", "Byte", "copied"), _RG), "String", output_owner="region"),
            "fromFloat64": Sig((P("value", "Float64", "copied"), _RG), "String", output_owner="region"),
            "toFloat64": Sig((P("text", "String", "borrowed"),), "Float64", raises="string.ParseError"),
        },
    },
    # D-91: reading bytes. A `Bytes` value is a byte sequence with no encoding; these read it without the host
    "bytes": {
        "types": {"BytesIndexError": _err("bytes.BytesIndexError", ("outOfRange", "Int64"))},
        "targets": {
            "length": Sig((P("bytes", "Bytes", "borrowed"),), "Int64"),
            "byteAt": Sig((P("bytes", "Bytes", "borrowed"), P("index", "Int64", "copied")), "Byte",
                          raises="bytes.BytesIndexError"),
            "slice": Sig((P("bytes", "Bytes", "borrowed"), P("start", "Int64", "copied"), P("length", "Int64", "copied")),
                         "Bytes", raises="bytes.BytesIndexError", borrows="bytes"),
            "equals": Sig((P("left", "Bytes", "borrowed"), P("right", "Bytes", "borrowed")), "Bool"),
        },
    },
    "byte": {
        "types": {},
        "targets": {**{n: _un("Byte", "Bool") for n in ("isLetter", "isDigit", "isLetterOrDigit", "isSpace",
                                                              "isPunctuation")},
                    "equals": _bin("Byte", "Bool")},
    },
    "buffer": {
        "types": {
            "ByteBuffer": TypeInfo("buffer.ByteBuffer", "opaque", False),
        },
        "targets": {
            "new": Sig((_RG,), "buffer.ByteBuffer", "region"),
            "appendString": Sig((P("buffer", "buffer.ByteBuffer", "borrowedMutable"), P("text", "String", "borrowed"))),
            "appendByte": Sig((P("buffer", "buffer.ByteBuffer", "borrowedMutable"), P("value", "Byte", "copied"))),
            "appendInt64": Sig((P("buffer", "buffer.ByteBuffer", "borrowedMutable"), P("value", "Int64", "copied"))),
            "length": Sig((P("buffer", "buffer.ByteBuffer", "borrowed"),), "Int64"),
            "toString": Sig((P("buffer", "buffer.ByteBuffer", "borrowed"), _RG), "String", "region", "string.Utf8Error"),
            "toBytes": Sig((P("buffer", "buffer.ByteBuffer", "borrowed"),), "Bytes", borrows="buffer"),
        },
    },
    "time": {
        "types": {
            "Deadline": TypeInfo("time.Deadline", "opaque", True, targets={
                "never": Sig((), "time.Deadline"),
                "after": Sig((P("milliseconds", "Int64", "copied"),), "time.Deadline"),
            }),
        },
        "targets": {
            "sleep": Sig((P("milliseconds", "Int64", "copied"),), waits=True),
        },
    },
    "clock": {
        "types": {},
        "targets": {
            "now": Sig((), "Int64", effects=E("read clock.wall")),
            "monotonic": Sig((), "Int64", effects=E("read clock.monotonic")),
        },
    },
    "environment": {
        "types": {"MissingError": _err("environment.MissingError", ("missing", None))},
        "targets": {
            "get": Sig((P("name", "String", "borrowed"), _RG), "String", "region", "environment.MissingError",
                       E("read environment.variables")),
        },
    },
    "process": {
        "types": {
            "ArgumentError": _err("process.ArgumentError", ("outOfRange", "Int64")),
            "RunError": _err("process.RunError", ("notFound", None), ("timedOut", None), ("cancelled", None),
                             ("tooLarge", None), ("failed", "Int32")),
            "Arguments": TypeInfo("process.Arguments", "opaque", False),
            "Output": TypeInfo("process.Output", "record", False,
                               fields=[("status", "ExitCode"), ("stdout", "Bytes"), ("stderr", "Bytes")]),
        },
        "targets": {
            "argumentCount": Sig((), "Int64", effects=E("read process.arguments")),
            "argument": Sig((P("index", "Int64", "copied"), _RG), "String", "region", "process.ArgumentError",
                            E("read process.arguments")),
            "newArguments": Sig((_RG,), "process.Arguments", "region"),
            "addArgument": Sig((P("arguments", "process.Arguments", "borrowedMutable"), P("text", "String", "borrowed"))),
            "run": Sig((P("program", "String", "borrowed"), P("arguments", "process.Arguments", "borrowed"), _DL),
                       "ExitCode", raises="process.RunError", effects=E("spawn process.programs"), waits=True,
                       scoped="program"),
            # run a program with `input` on its standard input, collecting what it writes (a pipe each way)
            "runCaptured": Sig((P("program", "String", "borrowed"), P("arguments", "process.Arguments", "borrowed"),
                                P("input", "Bytes", "borrowed"), _RG, P("maxBytes", "Int64", "copied"), _DL),
                               "process.Output", "region", "process.RunError", E("spawn process.programs"),
                               waits=True, scoped="program"),
        },
    },
    "fs": {
        "types": {
            "FileHandle": TypeInfo("fs.FileHandle", "resource", False),
            "FileError": _err("fs.FileError", ("notFound", None), ("denied", None), ("exists", None),
                              ("tooLarge", None), ("timedOut", None), ("cancelled", None), ("busy", None),
                              ("failed", "Int32")),
            "DirectoryListing": TypeInfo("fs.DirectoryListing", "opaque", False),
            "EntryIndexError": _err("fs.EntryIndexError", ("outOfRange", "Int64")),
        },
        "targets": {
            "openRead": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                            E("read fs.files"), scoped="path"),
            "openWrite": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                             E("write fs.files"), scoped="path"),
            "create": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                          E("write fs.files"), scoped="path"),
            "openAppend": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                              E("write fs.files"), scoped="path"),
            "createDirectory": Sig((P("path", "String", "borrowed"),), raises="fs.FileError",
                                   effects=E("write fs.files"), scoped="path"),
            "removeDirectory": Sig((P("path", "String", "borrowed"),), raises="fs.FileError",
                                   effects=E("write fs.files"), scoped="path"),
            "listDirectory": Sig((P("path", "String", "borrowed"), _RG), "fs.DirectoryListing", "region",
                                 "fs.FileError", E("read fs.files"), scoped="path"),
            "entryCount": Sig((P("listing", "fs.DirectoryListing", "borrowed"),), "Int64"),
            # an exclusive advisory lock on an open file, released by `unlock` or by closing the file
            # D-43: a target that changes the state of the handle it is given (its position, its lock, the
            # stream behind it) takes an exclusive loan, so two tasks can never use one handle at once
            "lock": Sig((P("file", "fs.FileHandle", "borrowedMutable"), _DL), raises="fs.FileError",
                        effects=E("write fs.files"), waits=True),
            "unlock": Sig((P("file", "fs.FileHandle", "borrowedMutable"),), raises="fs.FileError",
                          effects=E("write fs.files")),
            "entryName": Sig((P("listing", "fs.DirectoryListing", "borrowed"), P("index", "Int64", "copied"), _RG),
                             "String", "region", "fs.EntryIndexError"),
            "read": Sig((P("file", "fs.FileHandle", "borrowedMutable"), _RG, P("maxBytes", "Int64", "copied"), _DL),
                        "Bytes", "region", "fs.FileError", E("read fs.files"), waits=True),
            "write": Sig((P("file", "fs.FileHandle", "borrowedMutable"), P("bytes", "Bytes", "borrowed"), _DL),
                         raises="fs.FileError", effects=E("write fs.files"), waits=True),
            # closing a handle you own needs no authority beyond holding it
            "close": Sig((P("file", "fs.FileHandle", "owned"),), raises="fs.FileError"),
            "exists": Sig((P("path", "String", "borrowed"),), "Bool", effects=E("read fs.files"), scoped="path"),
            "remove": Sig((P("path", "String", "borrowed"),), raises="fs.FileError", effects=E("write fs.files"),
                          scoped="path"),
            "readAll": Sig((P("path", "String", "borrowed"), _RG, P("maxBytes", "Int64", "copied"), _DL),
                           "Bytes", "region", "fs.FileError", E("read fs.files"), waits=True, scoped="path"),
            "writeAll": Sig((P("path", "String", "borrowed"), P("bytes", "Bytes", "borrowed"), _DL),
                            raises="fs.FileError", effects=E("write fs.files"), waits=True, scoped="path"),
        },
    },
    "net": {
        "types": {
            "TcpListener": TypeInfo("net.TcpListener", "resource", False),
            "TcpConnection": TypeInfo("net.TcpConnection", "resource", False),
            "NetError": _err("net.NetError", ("closed", None), ("timedOut", None), ("refused", None),
                             ("cancelled", None), ("failed", "Int32")),
        },
        "targets": {
            "listen": Sig((P("port", "Int32", "copied"),), "net.TcpListener", "caller", "net.NetError",
                          E("listen net.tcp"), scoped="port"),
            "closeListener": Sig((P("listener", "net.TcpListener", "owned"),), raises="net.NetError",
                                 effects=E("listen net.tcp")),
            "accept": Sig((P("listener", "net.TcpListener", "borrowedMutable"), _DL),
                          "net.TcpConnection", "caller", "net.NetError", E("listen net.tcp"), waits=True),
            "connect": Sig((P("address", "String", "borrowed"), _DL), "net.TcpConnection", "caller", "net.NetError",
                           E("connect net.outbound"), waits=True, scoped="address"),
            "read": Sig((P("connection", "net.TcpConnection", "borrowedMutable"), _RG, P("maxBytes", "Int64", "copied"), _DL),
                        "Bytes", "region", "net.NetError", E("readWrite net.connection"), waits=True),
            "write": Sig((P("connection", "net.TcpConnection", "borrowedMutable"), P("bytes", "Bytes", "borrowed"), _DL),
                         raises="net.NetError", effects=E("readWrite net.connection"), waits=True),
            "close": Sig((P("connection", "net.TcpConnection", "owned"),), raises="net.NetError",
                         effects=E("readWrite net.connection")),
        },
    },
    "http": {
        "types": {
            "HttpMethod": TypeInfo("http.HttpMethod", "enum", True, variants=[
                ("get", None), ("head", None), ("post", None), ("put", None), ("delete", None),
                ("options", None), ("patch", None)]),
            "HttpRequest": TypeInfo("http.HttpRequest", "record", False,
                                    fields=[("method", "http.HttpMethod"), ("path", "String")]),
            "HttpResponse": TypeInfo("http.HttpResponse", "opaque", False),
            "HttpParseError": _err("http.HttpParseError", ("malformed", None), ("tooLarge", None)),
        },
        "targets": {
            "parseRequest": Sig((P("bytes", "Bytes", "borrowed"), _RG), "http.HttpRequest", "region",
                                "http.HttpParseError"),
            "response": Sig((P("status", "Int32", "copied"), P("body", "String", "borrowed"), _RG),
                            "http.HttpResponse", "region"),
            "serializeResponse": Sig((P("response", "http.HttpResponse", "borrowed"), _RG), "Bytes", "region"),
            "header": Sig((P("request", "http.HttpRequest", "borrowed"), P("name", "String", "borrowed")), "String",
                          raises="string.NotFound", borrows="request"),
        },
    },
    "list": {
        "types": {"List": _generic("list.List", ["T@any"]),
                  "IndexOutOfRange": _err("list.IndexOutOfRange", ("outOfRange", "Int64")),
                  # D-111: no row of a table has the key
                  "NotFound": _err("list.NotFound", ("absent", None))},
        "targets": {},
    },
    "map": {
        # D-61: a key is a plain value or a String (compared by content, copied into the map's region)
        "types": {"Map": _generic("map.Map", ["K@key", "V@any"]),
                  "KeyMissing": _err("map.KeyMissing", ("missing", None))},
        "targets": {},
    },
    "set": {
        # D-93: an item is a plain value or a String, like a map's key (D-61)
        "types": {"Set": _generic("set.Set", ["T@key"])},
        "targets": {},
    },
    "option": {
        "types": {"Option": _generic("option.Option", ["T@any"], None,
                                     variants=[("present", "T@any"), ("absent", None)])},
        "targets": {},
    },
    "channel": {
        "types": {"Channel": _generic("channel.Channel", ["T@any"]),
                  "ChannelError": _err("channel.ChannelError", ("closed", None), ("timedOut", None),
                                       ("cancelled", None))},
        "targets": {},
    },
    "ffi": {
        "types": {
            "Library": TypeInfo("ffi.Library", "resource", False),
            "Function": _generic("ffi.Function", ["F@any"]),
            "LoadError": _err("ffi.LoadError", ("notFound", None), ("symbolMissing", None)),
        },
        "targets": {
            # load a shared library by name ("c" is the platform's C runtime); release it with `close`
            "open": Sig((P("name", "String", "borrowed"),), "ffi.Library", "caller", "ffi.LoadError",
                        E("load ffi.libraries"), scoped="name"),
            "close": Sig((P("library", "ffi.Library", "owned"),), effects=E("load ffi.libraries")),
        },
    },
    # D-55: allocation a program can recover from. A region's capacity is still a hard limit (passing it traps,
    # D-49); these let a program ask first and take its own path when the space is not there.
    "arena": {
        "types": {"ArenaError": _err("arena.ArenaError", ("exhausted", "Int64"))},
        "targets": {
            "remaining": Sig((P("region", "Region", "borrowed"),), "Int64"),
            "ensure": Sig((P("region", "Region", "borrowed"), P("bytes", "Int64", "copied")),
                          raises="arena.ArenaError"),
        },
    },
    "random": {
        "types": {
            "Generator": TypeInfo("random.Generator", "opaque", False),
            "RangeError": _err("random.RangeError", ("emptyRange", None)),
        },
        "targets": {
            # a fresh number from the operating system's entropy source, in [low, high]
            "int64Between": Sig((P("low", "Int64", "copied"), P("high", "Int64", "copied")), "Int64",
                                raises="random.RangeError", effects=E("read random.entropy")),
            # a deterministic generator: the same seed gives the same numbers
            "newGenerator": Sig((P("seed", "Int64", "copied"), _RG), "random.Generator", "region"),
            "nextInt64": Sig((P("generator", "random.Generator", "borrowedMutable"), P("low", "Int64", "copied"),
                              P("high", "Int64", "copied")), "Int64", raises="random.RangeError"),
        },
    },
    "crypto": {
        "types": {},
        "targets": {
            "sha256": Sig((P("bytes", "Bytes", "borrowed"), _RG), "Bytes", "region"),
            "hmacSha256": Sig((P("key", "Bytes", "borrowed"), P("message", "Bytes", "borrowed"), _RG), "Bytes",
                              "region"),
            "toHex": Sig((P("bytes", "Bytes", "borrowed"), _RG), "String", "region"),
            "constantTimeEquals": Sig((P("left", "Bytes", "borrowed"), P("right", "Bytes", "borrowed")), "Bool"),
        },
    },
    "log": {
        "types": {"LogError": _err("log.LogError", ("failed", "Int32"))},
        "targets": {
            level: Sig((P("text", "String", "borrowed"),), raises="log.LogError", effects=E("write console.stderr"))
            for level in ("debug", "info", "warn", "error")
        },
    },
    "json": {
        "types": {
            "Value": TypeInfo("json.Value", "opaque", False),
            "Kind": TypeInfo("json.Kind", "enum", True, variants=[
                ("null", None), ("boolean", None), ("number", None), ("text", None), ("array", None),
                ("object", None)]),
            "ParseError": _err("json.ParseError", ("invalidAt", "Int64"), ("tooDeep", None)),
            "AccessError": _err("json.AccessError", ("wrongKind", None), ("missing", None),
                                ("outOfRange", "Int64"), ("notWhole", None)),
        },
        "targets": {
            "parse": Sig((P("text", "String", "borrowed"), _RG), "json.Value", "region", "json.ParseError"),
            "kind": Sig((P("value", "json.Value", "borrowed"),), "json.Kind"),
            "asInt64": Sig((P("value", "json.Value", "borrowed"),), "Int64", raises="json.AccessError"),
            "asBool": Sig((P("value", "json.Value", "borrowed"),), "Bool", raises="json.AccessError"),
            "asText": Sig((P("value", "json.Value", "borrowed"), _RG), "String", "region", "json.AccessError"),
            "length": Sig((P("value", "json.Value", "borrowed"),), "Int64", raises="json.AccessError"),
            "item": Sig((P("value", "json.Value", "borrowed"), P("index", "Int64", "copied"), _RG), "json.Value",
                        "region", "json.AccessError"),
            "field": Sig((P("value", "json.Value", "borrowed"), P("name", "String", "borrowed"), _RG), "json.Value",
                         "region", "json.AccessError"),
            "newObject": Sig((_RG,), "json.Value", "region"),
            "newArray": Sig((_RG,), "json.Value", "region"),
            "setInt64": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                             P("number", "Int64", "copied")), raises="json.AccessError"),
            "setText": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                            P("text", "String", "borrowed")), raises="json.AccessError"),
            "setBool": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                            P("flag", "Bool", "copied")), raises="json.AccessError"),
            "setValue": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                             P("value", "json.Value", "borrowed")), raises="json.AccessError"),
            "appendInt64": Sig((P("array", "json.Value", "borrowedMutable"), P("number", "Int64", "copied")),
                               raises="json.AccessError"),
            "appendText": Sig((P("array", "json.Value", "borrowedMutable"), P("text", "String", "borrowed")),
                              raises="json.AccessError"),
            "stringify": Sig((P("value", "json.Value", "borrowed"), _RG), "String", "region"),
        },
    },
    "secret": {
        "types": {"Secret": TypeInfo("secret.Secret", "opaque", False)},
        "targets": {
            # a Secret has no conversion to text except `reveal`, which needs `read secret.values`
            "fromText": Sig((P("text", "String", "borrowed"), _RG), "secret.Secret", "region"),
            "fromEnvironment": Sig((P("name", "String", "borrowed"), _RG), "secret.Secret", "region",
                                   "environment.MissingError", E("read environment.variables")),
            "reveal": Sig((P("secret", "secret.Secret", "borrowed"), _RG), "String", "region",
                          effects=E("read secret.values")),
            # comparing or measuring a secret reveals something about it, so it needs the same authority
            "matches": Sig((P("secret", "secret.Secret", "borrowed"), P("candidate", "String", "borrowed")), "Bool",
                           effects=E("read secret.values")),
            "length": Sig((P("secret", "secret.Secret", "borrowed"),), "Int64", effects=E("read secret.values")),
        },
    },
    "signal": {
        "types": {"SignalError": _err("signal.SignalError", ("timedOut", None), ("cancelled", None))},
        "targets": {
            "interrupted": Sig((), "Bool", effects=E("read signal.interrupts")),
            "waitForInterrupt": Sig((_DL,), raises="signal.SignalError", effects=E("read signal.interrupts"),
                                    waits=True),
        },
    },
    "test": {
        "types": {},
        "targets": {
            "assertEqualInt64": Sig((P("expected", "Int64", "copied"), P("actual", "Int64", "copied"))),
            "assertEqualExitCode": Sig((P("expected", "ExitCode", "copied"), P("actual", "ExitCode", "copied"))),
            "assertEqualString": Sig((P("expected", "String", "borrowed"), P("actual", "String", "borrowed"))),
            "assertTrue": Sig((P("value", "Bool", "copied"),)),
            "fail": Sig((P("message", "String", "borrowed"),)),
        },
    },
}


def generic_members(generic: str, inst: str, args: list[str], plain, index: Optional[str] = None) -> dict[str, Sig]:
    """Call targets of an instantiated library generic (LR-24, LR-25, LR-33). `index` is the alias that
    indexes a list type (D-60): its positions are then that alias, not `Int64`."""
    def own_mode(t: str) -> str:
        return "copied" if plain(t) else "owned"

    def read_mode(t: str) -> str:
        return "copied" if plain(t) else "borrowed"

    if generic == "list.List":
        item = args[0]
        position = index or "Int64"
        members = {
            "new": Sig((_RG,), inst, "region"),
            "append": Sig((P("list", inst, "borrowedMutable"), P("item", item, own_mode(item)))),
            "get": Sig((P("list", inst, "borrowed"), P("index", position, "copied")), item,
                       raises="list.IndexOutOfRange", borrows=None if plain(item) else "list"),
            "set": Sig((P("list", inst, "borrowedMutable"), P("index", position, "copied"), P("item", item, own_mode(item))),
                       raises="list.IndexOutOfRange"),
            "length": Sig((P("list", inst, "borrowed"),), "Int64"),
            # D-101: the trapping twin of `get`, for an index the program has already proved in range; a bad index
            # is a trap, on the reasoning D-49 uses for region limits
            "getOrTrap": Sig((P("list", inst, "borrowed"), P("index", position, "copied")), item,
                             borrows=None if plain(item) else "list"),
            # D-105: put an item in and take the old one out. For items that are not plain values the old item is
            # handed back owned, as a value of the list's region (named, and checked when the call runs), so a
            # list or record held in a list can be changed: replace it with a fresh one, change it, put it back
            "replace": Sig((P("list", inst, "borrowedMutable"), P("index", position, "copied"),
                            P("item", item, own_mode(item))), item, raises="list.IndexOutOfRange")
            if plain(item) else
            Sig((P("list", inst, "borrowedMutable"), P("index", position, "copied"), P("item", item, own_mode(item)),
                 _RG), item, "region", "list.IndexOutOfRange"),
        }
        if index is not None:
            # D-60: the one source of an index: append an item and receive its position. D-100: an indexed list only
            # grows (no `clear`, `removeLast`, or `truncate`), so a position never names a reused slot
            members["appendIndexed"] = Sig((P("list", inst, "borrowedMutable"), P("item", item, own_mode(item))), index)
        else:
            members["clear"] = Sig((P("list", inst, "borrowedMutable"),))
            # D-102: a list is also a stack: take the last item off, or cut the list to a length
            members["truncate"] = Sig((P("list", inst, "borrowedMutable"), P("length", "Int64", "copied")),
                                      raises="list.IndexOutOfRange")
            if plain(item):
                members["removeLast"] = Sig((P("list", inst, "borrowedMutable"),), item, raises="list.IndexOutOfRange")
        return members
    if generic == "map.Map":
        key, value = args
        kmode = read_mode(key)  # D-61: a String key is lent; `put` copies it into the map's region
        return {
            "new": Sig((_RG,), inst, "region"),
            "put": Sig((P("map", inst, "borrowedMutable"), P("key", key, kmode), P("value", value, own_mode(value)))),
            "get": Sig((P("map", inst, "borrowed"), P("key", key, kmode)), value, raises="map.KeyMissing",
                       borrows=None if plain(value) else "map"),
            "contains": Sig((P("map", inst, "borrowed"), P("key", key, kmode)), "Bool"),
            "remove": Sig((P("map", inst, "borrowedMutable"), P("key", key, kmode)), raises="map.KeyMissing"),
            "length": Sig((P("map", inst, "borrowed"),), "Int64"),
        }
    if generic == "set.Set":
        item = args[0]
        imode = read_mode(item)  # D-93: a String item is lent; `add` copies it into the set's region
        return {
            "new": Sig((_RG,), inst, "region"),
            "add": Sig((P("set", inst, "borrowedMutable"), P("item", item, imode))),
            "contains": Sig((P("set", inst, "borrowed"), P("item", item, imode)), "Bool"),
            "remove": Sig((P("set", inst, "borrowedMutable"), P("item", item, imode))),
            "length": Sig((P("set", inst, "borrowed"),), "Int64"),
        }
    if generic == "option.Option":
        item = args[0]
        return {"present": Sig((P("payload", item, own_mode(item)),), inst), "absent": Sig((), inst)}
    if generic == "ffi.Function":
        # `bind` looks a symbol up in a loaded library and gives it the declared operation type
        return {"bind": Sig((P("library", "ffi.Library", "borrowed"), P("symbol", "String", "borrowed")), args[0],
                            raises="ffi.LoadError", effects=E("load ffi.symbols"), scoped="symbol")}
    if generic == "channel.Channel":
        item = args[0]
        return {
            "new": Sig((P("capacity", "Int64", "copied"), _RG), inst, "region"),
            "send": Sig((P("channel", inst, "borrowed"), P("item", item, own_mode(item)), _DL),
                        raises="channel.ChannelError", waits=True),
            "receive": Sig((P("channel", inst, "borrowed"), _DL), item, "caller" if not plain(item) else None,
                           "channel.ChannelError", waits=True),
            "close": Sig((P("channel", inst, "borrowed"),)),
        }
    return {}


def type_param_name(canon: str) -> str:
    """`T@plain` -> `T`."""
    return canon.split("@", 1)[0]


def fits_constraint(param: str, arg: str, plain) -> bool:
    """Whether type argument `arg` meets the constraint of type parameter `param`: `@plain` admits plain
    values, `@key` (a map's key, D-61) plain values and `String`, `@any` every type."""
    if param.endswith("@plain"):
        return plain(arg)
    if param.endswith("@key"):
        return arg == "String" or plain(arg)
    return True
