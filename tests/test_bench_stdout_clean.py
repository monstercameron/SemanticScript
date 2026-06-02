#!/usr/bin/env python3
"""A3: `sem bench --json` emits exactly one JSON envelope on stdout.

bench times the JIT'd program in-process and mutes fd 1 around the run. The
program prints through libc `printf` (block-buffered), and an in-process JIT run
never calls `exit()`, so libc never runs its atexit flush — buffered program
output could flush onto the real stdout *after* the mute was lifted and corrupt
the sem.bench.v1 JSON (an intermittent, load-dependent non-JSON envelope that
made bench unusable as a machine surface). cmd_bench now flushes the C runtime's
stdio while fd 1 is still muted, so the program's output is discarded to devnull.

This asserts the stdout is a single clean JSON object with no trailing leaked
bytes, across repeated runs of a print-heavy example.
"""
import importlib
import json
import os
import subprocess
import sys

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
# a print-heavy console example: its loop writes many lines, maximizing the
# chance of buffered libc output the old code would have leaked past the mute.
_EXAMPLE = os.path.join(_REPO, "examples", "module_scope_capture.sem")


def _bench_stdout(runs):
    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "bench", _EXAMPLE, "--runs", str(runs), "--json"],
        capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_bench_json_is_a_single_clean_object():
    for _ in range(8):
        out = _bench_stdout(2)
        # parse the leading JSON object, then assert nothing but whitespace
        # follows it — leaked program output would appear here as trailing bytes
        obj, end = json.JSONDecoder().raw_decode(out.lstrip())
        assert out.lstrip()[end:].strip() == "", repr(out[-120:])
        assert obj["surface"] == "sem.bench.v1"
        assert obj["runStatus"] == "ok"


def test_flush_helper_is_resilient_when_called():
    # the flush is pure hygiene: calling it must never raise, even repeatedly
    semanticscript._flush_c_runtime_stdio()
    semanticscript._flush_c_runtime_stdio()
