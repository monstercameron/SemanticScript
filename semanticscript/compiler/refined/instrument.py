"""Instrumented runs: tracing, coverage, profiling, and the debugger.

    refined run PATH --trace                 every block entered, on stderr
    refined run PATH --coverage              which blocks ran, reported at the end on stderr
    refined run PATH --profile               calls and time per operation, and region peaks, at the end
    refined run PATH --debug [--break M.OP[:LABEL]]...

The debugger stops at each breakpoint (and after `step`, at the next block) and
reads commands from standard input:

    vars | v        the operation's values (every value starts zeroed in a debug build)
    stack | bt      the operations on the call stack, innermost first
    step | s        stop at the next block entered
    continue | c    run to the next breakpoint
    quit | q        stop the program (exit code 1)

End of input means `continue` with no more stops. Everything the tools print
goes to standard error, so the program's own output is unchanged.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
import threading
import time

from . import runtime as rt

STATE = {"trace": False, "coverage": False, "debug": False, "profile": False}
BREAKPOINTS: set[str] = set()
BLOCKS_RUN: set[str] = set()
ALL_BLOCKS: list[str] = []
_lock = threading.Lock()
_stepping = [False]
_stdin_done = [False]
CALLS: dict[str, int] = {}
TOTAL: dict[str, float] = {}
REGION_PEAKS: dict[str, tuple[int, int]] = {}


def _err(text: str) -> None:
    rt._session.write(2, (text + "\n").encode("utf-8", "replace"))


def _value(addr: int, kind: str) -> str:
    if kind == "i1":
        return "true" if ctypes.c_uint8.from_address(addr).value & 1 else "false"
    if kind.startswith("i"):
        width = int(kind[1:])
        fmt = {8: "b", 16: "h", 32: "i", 64: "q"}.get(width)
        if fmt is None:
            return "?"
        return str(struct.unpack(fmt, ctypes.string_at(addr, width // 8))[0])
    if kind == "f64":
        return repr(ctypes.c_double.from_address(addr).value)
    if kind == "str":
        ptr = ctypes.c_void_p.from_address(addr).value
        length = ctypes.c_int64.from_address(addr + 8).value
        if not ptr or not 0 <= length <= 1 << 20:
            return '""' if not ptr else "<unreadable>"
        return '"' + ctypes.string_at(ptr, length).decode("utf-8", "replace") + '"'
    if kind.startswith("record(") and kind.endswith(")"):
        # D-73: integer and Bool fields in order, each at the next offset its own size aligns to
        shown, offset = [], 0
        for field in kind[7:-1].split(","):
            fname, fkind = field.split(" ")
            size = max(1, int(fkind[1:]) // 8)
            offset = (offset + size - 1) // size * size
            shown.append(f"{fname} {_value(addr + offset, 'i1' if fkind == 'i1' else f'i{size * 8}')}")
            offset += size
        return "{" + ", ".join(shown) + "}"
    if kind.startswith("enum(") and kind.endswith(")"):
        # D-73: the narrow layout {i32 tag, i64 payload}
        variants = kind[5:-1].split(",")
        tag = ctypes.c_int32.from_address(addr).value
        if not 0 <= tag < len(variants):
            return "<unreadable>"
        name = variants[tag]
        if name.endswith("*"):
            return f"{name[:-1]}({ctypes.c_int64.from_address(addr + 8).value})"
        return name
    return "<value>"


def _debug_stop(name: str, values, count: int, desc: str) -> None:
    from . import tasks
    _err(f"debug: stopped at {name}")
    while True:
        if _stdin_done[0]:
            return
        rt.flush_output()
        sys.stderr.write("(debug) ")
        sys.stderr.flush()
        line = sys.stdin.readline()
        if not line:
            _stdin_done[0] = True
            _stepping[0] = False
            return
        cmd = line.strip()
        if cmd in ("vars", "v"):
            parts = [d.split(":", 2) for d in desc.split(";")] if desc else []
            for i, (vname, kind, typ) in enumerate(parts[:count]):
                _err(f"  {vname} {typ} = {_value(values[i], kind)}")
        elif cmd in ("stack", "bt"):
            for line_text in tasks.stack_trace(limit=50):
                _err(line_text)
        elif cmd in ("step", "s"):
            _stepping[0] = True
            return
        elif cmd in ("continue", "c"):
            _stepping[0] = False
            return
        elif cmd in ("quit", "q"):
            _err("debug: stopped by the user")
            os._exit(1)
        elif cmd:
            _err("  commands: vars, stack, step, continue, quit")


@ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int64, ctypes.POINTER(ctypes.c_void_p), ctypes.c_int64,
                  ctypes.c_void_p, ctypes.c_int64)
def _block(name_ptr, name_len, values, count, desc_ptr, desc_len):
    name = rt._bytes(name_ptr, name_len).decode("utf-8", "replace")
    if STATE["trace"]:
        who = threading.current_thread().name
        _err(f"trace: {name}" + ("" if who == "refined-program" else f" [{who}]"))
    if STATE["coverage"]:
        BLOCKS_RUN.add(name)
    if STATE["debug"]:
        op = name.split(":", 1)[0]
        if _stepping[0] or name in BREAKPOINTS or op in BREAKPOINTS:
            with _lock:
                _debug_stop(name, values, count, rt._bytes(desc_ptr, desc_len).decode())


def profile_push(name: str) -> None:
    stack = getattr(_tls, "stack", None)
    if stack is None:
        _tls.stack = stack = []
    stack.append((name, time.perf_counter()))


def profile_pop() -> None:
    name, start = _tls.stack.pop()
    elapsed = time.perf_counter() - start
    with _lock:
        CALLS[name] = CALLS.get(name, 0) + 1
        TOTAL[name] = TOTAL.get(name, 0.0) + elapsed


_tls = threading.local()


def region_released(label: str, used: int, capacity: int) -> None:
    if STATE["profile"]:
        with _lock:
            peak = REGION_PEAKS.get(label, (0, capacity))[0]
            REGION_PEAKS[label] = (max(peak, used), capacity)


def report() -> None:
    if STATE["coverage"]:
        total = sorted(set(ALL_BLOCKS))
        ran = [b for b in total if b in BLOCKS_RUN]
        pct = 100.0 * len(ran) / len(total) if total else 100.0
        _err(f"coverage: {len(ran)} of {len(total)} blocks ran ({pct:.0f}%)")
        for b in total:
            if b not in BLOCKS_RUN:
                _err(f"  never ran: {b}")
    if STATE["profile"]:
        _err("profile: operation, calls, total milliseconds (including what it calls)")
        for name in sorted(TOTAL, key=lambda n: -TOTAL[n]):
            _err(f"  {name}  {CALLS[name]}  {TOTAL[name] * 1000:.3f}")
        for label, (peak, capacity) in sorted(REGION_PEAKS.items()):
            _err(f"  memory: {label} peaked at {peak} of {capacity} bytes")


CALLBACKS = {"refined_block": _block}
