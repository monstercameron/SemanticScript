"""JIT runtime for the refined backend.

Generated code reaches the outside world only through the callbacks declared in
codegen.CALLBACKS. They are implemented here in Python and handed to the JIT
with `add_symbol`, so output, traps, and test assertions behave the same on
every platform and never depend on which C runtime the process loaded.
"""
from __future__ import annotations

import ctypes
import os
import sys
import threading
from dataclasses import dataclass, field

from llvmlite import binding as llvm

TRAP_EXIT_CODE = 70
# Compiled code runs on its own thread with this much stack. Recursive operations trap when fewer than
# STACK_MARGIN_BYTES remain (room for the runtime's callbacks), instead of overflowing the stack.
PROGRAM_STACK_BYTES = 128 * 1024 * 1024  # under the 256 MiB cap Python sets on Windows
STACK_MARGIN_BYTES = 8 * 1024 * 1024
_INITIALIZED = False
# what `process.argumentCount` and `process.argument` read: the words after `--` on the command line
PROGRAM_ARGUMENTS: list[str] = []
# set by the first interrupt (Ctrl-C) while a program that reads `signal` runs; a second one exits
INTERRUPTED = [False]


@dataclass
class Session:
    capture: bool = False
    stdout: list[bytes] = field(default_factory=list)
    stderr: list[bytes] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def write(self, fd: int, data: bytes) -> int:
        if self.capture:
            (self.stdout if fd == 1 else self.stderr).append(data)
            return 0
        try:
            os.write(fd, data)
            return 0
        except OSError as exc:
            return exc.errno or 1


_session = Session()


def _bytes(ptr: int, length: int) -> bytes:
    return ctypes.string_at(ptr, length) if length > 0 else b""


# D-51: what runs after a trap. No program code: deferred cleanups are skipped, since the state that trapped
# may be the state they would act on. The runtime then releases what the program still holds outside the process
# (each hook releases one kind and returns how many it released) before the process exits.
TRAP_RELEASES: list = []


def _release_on_trap() -> int:
    released = 0
    for hook in TRAP_RELEASES:
        try:
            released += hook()
        except Exception:  # noqa: BLE001 - releasing is best effort while the process ends
            pass
    return released


@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64)
def _trap(ptr, length):
    from . import tasks
    trace = tasks.stack_trace()
    msg = b"trap: " + _bytes(ptr, length) + b"\n" + "".join(line + "\n" for line in trace).encode("utf-8", "replace")
    released = _release_on_trap()
    if released:
        msg += (f"the runtime released {released} resource{'s' if released != 1 else ''} the program still held "
                "(files flushed and closed, connections closed, child processes stopped); deferred cleanups do not "
                "run after a trap\n").encode()
    if _session.capture:
        _session.stderr.append(msg)
        out = b"".join(_session.stdout)
        sys.stdout.buffer.write(out)
        sys.stdout.flush()
    os.write(2, msg)
    os._exit(TRAP_EXIT_CODE)


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_int32, ctypes.c_void_p, ctypes.c_int64, ctypes.c_int32)
def _write(fd, ptr, length, newline):
    return _session.write(fd, _bytes(ptr, length) + (b"\n" if newline else b""))


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_int32, ctypes.c_int64, ctypes.c_int32)
def _write_int(fd, value, newline):
    return _session.write(fd, str(value).encode() + (b"\n" if newline else b""))


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _bytes_equal(p1, l1, p2, l2):
    return 1 if l1 == l2 and _bytes(p1, l1) == _bytes(p2, l2) else 0


def _record(ctx: bytes, message: str) -> None:
    _session.failures.append(f"{ctx.decode('utf-8', 'replace')}: {message}")


@ctypes.CFUNCTYPE(None, ctypes.c_int64, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _assert_int(expected, actual, cp, cl):
    if expected != actual:
        _record(_bytes(cp, cl), f"expected {expected}, got {actual}")


@ctypes.CFUNCTYPE(None, ctypes.c_int32, ctypes.c_void_p, ctypes.c_int64)
def _assert_true(value, cp, cl):
    if not value:
        _record(_bytes(cp, cl), "expected true, got false")


@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _assert_str(p1, l1, p2, l2, cp, cl):
    a, b = _bytes(p1, l1), _bytes(p2, l2)
    if a != b:
        _record(_bytes(cp, cl), f"expected {a!r}, got {b!r}")


@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _fail(p, length, cp, cl):
    _record(_bytes(cp, cl), _bytes(p, length).decode("utf-8", "replace"))


class _Region:
    def __init__(self, capacity: int, label: str):
        self.capacity, self.label, self.used, self.blocks = capacity, label, 0, []
        self.handles: list[int] = []  # host objects (maps, channels, ...) released with the region


_regions: dict[int, _Region] = {}


def _trap_now(message: str) -> None:
    data = message.encode()
    _trap(ctypes.cast(ctypes.c_char_p(data), ctypes.c_void_p).value, len(data))


@ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _region_new(capacity, lp, ll):
    anchor = ctypes.create_string_buffer(1)
    addr = ctypes.addressof(anchor)
    reg = _Region(capacity, _bytes(lp, ll).decode("utf-8", "replace"))
    reg.blocks.append(anchor)
    _regions[addr] = reg
    return addr


@ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p)
def _region_remaining(handle):
    reg = _regions.get(handle)
    if reg is None:
        _trap_now("a region was asked how much room it has after it was released")
    return reg.capacity - reg.used


@ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64)
def _region_alloc(handle, size):
    reg = _regions.get(handle)
    if reg is None:
        _trap_now("allocation in a region that was already released")
    if reg.used + size > reg.capacity:
        _trap_now(f"{reg.label} exceeded its capacity of {reg.capacity} bytes")
    reg.used += size
    buf = ctypes.create_string_buffer(max(size, 1))
    reg.blocks.append(buf)
    return ctypes.addressof(buf)


@ctypes.CFUNCTYPE(None, ctypes.c_void_p)
def _region_free(handle):
    reg = _regions.pop(handle, None)
    if reg is not None:
        from . import host, instrument
        instrument.region_released(reg.label, reg.used, reg.capacity)
        for h in reg.handles:
            host.drop(h)


def region_owns(handle: int, obj_handle: int) -> None:
    reg = _regions.get(handle)
    if reg is None:
        _trap_now("allocation in a region that was already released")
    reg.handles.append(obj_handle)


def flush_output() -> None:
    """Before a child process inherits stdout: nothing is buffered here except under capture."""
    if _session.capture:
        sys.stdout.buffer.write(b"".join(_session.stdout))
        sys.stdout.flush()
        _session.stdout.clear()


def read_stdin_line(limit: int) -> bytes | None:
    """One line from standard input, at most `limit` bytes (the caller checks the length); None at end."""
    line = sys.stdin.buffer.readline(limit)
    return line or None


_SHAPES: dict[bytes, tuple[str, list[int], int]] = {}


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_int64, ctypes.POINTER(ctypes.c_int64),
                  ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_int64))
def _host(name_ptr, name_len, args, results, payload):
    """Every host library target (host.py). The name is `<target>|<slots per parameter>|<result slots>`."""
    key = _bytes(name_ptr, name_len)
    shape = _SHAPES.get(key)
    if shape is None:
        name, counts, nres = key.decode().split("|")
        shape = (name, [int(c) for c in counts.split(",") if c], int(nres))
        _SHAPES[key] = shape
    name, counts, nres = shape
    params, at = [], 0
    for c in counts:
        params.append(tuple(args[at + i] for i in range(c)))
        at += c
    from . import host
    try:
        status, slots, err = host.dispatch(name, params)
    except Exception as exc:  # a defect in the runtime must not take the process down silently
        _trap_now(f"`{name}` failed inside the runtime: {exc!r}")
    if status == 0:
        if len(slots) != nres:
            _trap_now(f"`{name}` returned {len(slots)} values where the program expects {nres}")
        for i, v in enumerate(slots):
            results[i] = (int(v) + (1 << 63)) % (1 << 64) - (1 << 63)
    payload[0] = (int(err) + (1 << 63)) % (1 << 64) - (1 << 63)
    return status


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_int32, ctypes.c_double, ctypes.c_int32)
def _write_float(fd, value, newline):
    return _session.write(fd, repr(float(value)).encode() + (b"\n" if newline else b""))


def _region_copy(handle: int, data: bytes) -> int:
    ptr = _region_alloc(handle, len(data))
    if data:
        ctypes.memmove(ptr, data, len(data))
    return ptr


@ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64))
def _format_int(value, region, out_len):
    data = str(value).encode()
    out_len[0] = len(data)
    return _region_copy(region, data)


@ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)
def _find(p1, l1, p2, l2):
    return _bytes(p1, l1).find(_bytes(p2, l2))


@ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_int64, ctypes.POINTER(ctypes.c_int64))
def _parse_int(p, length, out):
    """0 parsed, 1 not a number, 2 out of range. Accepts an optional `-` and ASCII digits only."""
    text = _bytes(p, length)
    body = text[1:] if text[:1] == b"-" else text
    if not body or not body.isdigit():
        out[0] = 0
        return 1
    value = int(text)
    if not -(1 << 63) <= value < (1 << 63):
        out[0] = 0
        return 2
    out[0] = value
    return 0


_CALLBACKS = {
    "refined_trap": _trap, "refined_write": _write, "refined_write_int": _write_int,
    "refined_bytes_equal": _bytes_equal, "refined_assert_int": _assert_int, "refined_assert_true": _assert_true,
    "refined_assert_str": _assert_str, "refined_fail": _fail,
    "refined_region_new": _region_new, "refined_region_alloc": _region_alloc, "refined_region_free": _region_free,
    "refined_region_remaining": _region_remaining,
    "refined_write_float": _write_float, "refined_format_int": _format_int, "refined_find": _find,
    "refined_parse_int": _parse_int, "refined_host": _host,
}


def _init() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    llvm.initialize_native_target()
    llvm.initialize_native_asmprinter()
    from . import instrument, tasks
    for name, cb in {**_CALLBACKS, **tasks.CALLBACKS, **instrument.CALLBACKS}.items():
        llvm.add_symbol(name, ctypes.cast(cb, ctypes.c_void_p).value)
    _INITIALIZED = True


def default_triple() -> str:
    _init()
    return llvm.get_default_triple()


class Engine:
    def __init__(self, ir_text: str):
        _init()
        self.uses_signals = "signal.interrupted|" in ir_text or "signal.waitForInterrupt|" in ir_text
        mod = llvm.parse_assembly(ir_text)
        mod.verify()
        tm = llvm.Target.from_default_triple().create_target_machine()
        self.engine = llvm.create_mcjit_compiler(mod, tm)
        self.engine.finalize_object()
        self.engine.run_static_constructors()

    def address(self, name: str) -> int:
        addr = self.engine.get_function_address(name)
        if not addr:
            raise RuntimeError(f"no function {name!r} was generated")
        return addr

    def _on_program_stack(self, call):
        """Run compiled code on a thread with a known, large stack, and tell the code where that stack
        ends, so deep recursion traps with a message instead of crashing the process."""
        from . import tasks
        result: dict = {}
        tasks.STACK_HERE = ctypes.CFUNCTYPE(ctypes.c_int64)(self.address("refined_stack_here"))
        tasks.start_program()

        def runner() -> None:
            try:
                tasks.enter_program_thread(PROGRAM_STACK_BYTES - STACK_MARGIN_BYTES)
                result["value"] = call()
            except BaseException as exc:  # re-raised on the calling thread
                result["error"] = exc

        if self.uses_signals:
            import signal as _signal

            def on_interrupt(_signum, _frame):
                if INTERRUPTED[0]:
                    os._exit(130)
                INTERRUPTED[0] = True
                tasks.notify()
            _signal.signal(_signal.SIGINT, on_interrupt)
        previous = threading.stack_size(PROGRAM_STACK_BYTES)
        try:
            worker = threading.Thread(target=runner, name="refined-program")
            worker.start()
        finally:
            threading.stack_size(previous)
        while worker.is_alive():  # short joins, so the main thread can take an interrupt
            worker.join(0.1)
        if "error" in result:
            raise result["error"]
        return result.get("value")

    def run_entry(self, name: str, capture: bool = False) -> tuple[int, bytes]:
        _session.capture, _session.stdout = capture, []
        entry = ctypes.CFUNCTYPE(ctypes.c_int32)(self.address(name))
        code = self._on_program_stack(entry)
        return code, b"".join(_session.stdout)

    def run_test(self, name: str) -> tuple[list[str], bytes]:
        _session.capture, _session.stdout, _session.failures = True, [], []
        self._on_program_stack(ctypes.CFUNCTYPE(None)(self.address(name)))
        return list(_session.failures), b"".join(_session.stdout)
