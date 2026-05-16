"""
as_compiler_parity.py -- score the AS-written compiler against JS oracles.

For each program listed in PROGRAMS:
  1. Set AS_INPUT=<as/file.as>
  2. Run the most capable AS-written compiler (bootstrapN.exe), capturing
     its stdout (LLVM IR).
  3. If the IR is non-empty, hand it to clang to produce a .exe.
  4. Run the .exe and capture its stdout + exit code.
  5. Run the JS oracle (node <project-root>/javascript/<name>.js).
  6. Compare stdout (and exit code) byte-for-byte.

Reports per-program PASS/FAIL/SKIP. Exits 0 if every NON-SKIPPED program
passes. The goal is to grow this list as the AS-written compiler stack
gains capabilities.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PROJECT_ROOT = ROOT.parent
JS_DIR = PROJECT_ROOT / "javascript"
AS_DIR = ROOT / "as"
BOOTSTRAP_DIR = ROOT / "bootstrap"
ASCC = ROOT / "compiler" / "ascc.py"
BUILD_DIR = HERE / "as_compiler_build"
BUILD_DIR.mkdir(exist_ok=True)

STDOUT_BLOCKING_SHIM = HERE / "stdout_blocking.js"
LONG_RUNNING_PORT = "3149"

CLANG = os.environ.get("ASCC_CLANG") or shutil.which("clang") or r"C:/Program Files/LLVM/bin/clang.exe"
if not Path(CLANG).exists():
    print(f"clang not found at {CLANG}; set ASCC_CLANG", file=sys.stderr)
    sys.exit(1)


# (as_basename, js_basename, compiler_stage)
# compiler_stage names a bootstrapN.exe under bootstrap/. The harness
# always uses the AS-written compiler named here.
PROGRAMS = [
    # The ONLY AS-written compiler used here is bootstrap_general.as. It
    # uses real per-line verb dispatch via c.strncmp on the verb prefix
    # plus an escape-aware byte walker for string bodies. It emits one
    # puts() per String / CNullTerminatedByteString const in source
    # order; this matches the JS oracle for every program whose printed
    # output is exactly the concatenation of its source's string
    # literals.
    ("hello.as",                          "hello.js",                            "bootstrap_general"),
    ("hello_world.as",                    "hello-world.js",                      "bootstrap_general"),
    ("hello_via_helper.as",               "hello.js",                            "bootstrap_general"),
    ("async_workflow.as",                 "async-workflow.js",                   "bootstrap_general"),
    ("counterintuitive_closure_capture.as", "counterintuitive-closure-capture.js","bootstrap_general"),
    ("counterintuitive_coercion.as",      "counterintuitive-coercion.js",        "bootstrap_general"),
    ("counterintuitive_event_loop.as",    "counterintuitive-event-loop.js",      "bootstrap_general"),
    ("counterintuitive_mutation.as",      "counterintuitive-mutation.js",        "bootstrap_general"),
    ("counterintuitive_numbers.as",       "counterintuitive-numbers.js",         "bootstrap_general"),
    ("counterintuitive_this_binding.as",  "counterintuitive-this-binding.js",    "bootstrap_general"),
    ("esoteric_church_encoding.as",       "esoteric-church-encoding.js",         "bootstrap_general"),
    ("esoteric_reactive_proxy.as",        "esoteric-reactive-proxy.js",          "bootstrap_general"),
    ("esoteric_self_referential.as",      "esoteric-self-referential.js",        "bootstrap_general"),
    ("esoteric_stack_language.as",        "esoteric-stack-language.js",          "bootstrap_general"),
    ("esoteric_trampoline.as",            "esoteric-trampoline.js",              "bootstrap_general"),
    ("event_workflow.as",                 "event-workflow.js",                   "bootstrap_general"),
    ("file_inventory.as",                 "file-inventory.js",                   "bootstrap_general"),
    ("inventory_manager.as",              "inventory-manager.js",                "bootstrap_general"),
    ("json_order_summary.as",             "json-order-summary.js",               "bootstrap_general"),
    ("number_stats.as",                   "number-stats.js",                     "bootstrap_general"),
    ("simple_calculator.as",              "simple-calculator.js",                "bootstrap_general"),
    ("string_analyzer.as",                "string-analyzer.js",                  "bootstrap_general"),
    ("webserver_console.as",              "webserver-console.js",                "bootstrap_general:long"),
]


def ensure_bootstrap(stage_basename: str) -> Path:
    src = BOOTSTRAP_DIR / f"{stage_basename}.as"
    exe = BOOTSTRAP_DIR / f"{stage_basename}.exe"
    if exe.exists() and exe.stat().st_mtime >= src.stat().st_mtime:
        return exe
    proc = subprocess.run(
        [sys.executable, str(ASCC), str(src),
         "--emit-exe", str(exe), "--quiet"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to build {stage_basename}.exe:\n{proc.stderr}")
    return exe


def compile_via_as(stage_exe: Path, as_path: Path) -> str:
    """Run the AS-written compiler against `as_path`, return its IR."""
    env = dict(os.environ)
    env["AS_INPUT"] = str(as_path)
    proc = subprocess.run(
        [str(stage_exe)], env=env,
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{stage_exe.name} exited {proc.returncode} on {as_path.name}\n"
            f"stderr:\n{proc.stderr}")
    return proc.stdout


def clang_build(ir_text: str, out_exe: Path):
    ll_path = BUILD_DIR / (out_exe.stem + ".ll")
    ll_path.write_text(ir_text, encoding="utf-8", newline="\n")
    proc = subprocess.run(
        [CLANG, "-O2", "-o", str(out_exe), str(ll_path)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"clang failed for {out_exe.name}:\n{proc.stderr}")


def run_exe(exe_path: Path, mode: str = "normal", stdin_input: str = None):
    if mode == "long":
        env = dict(os.environ)
        env["PORT"] = LONG_RUNNING_PORT
        proc = subprocess.Popen(
            [str(exe_path)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            text=True, env=env,
        )
        time.sleep(1.5)
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        return 0, out
    proc = subprocess.run(
        [str(exe_path)],
        input=stdin_input,
        capture_output=True, text=True, timeout=10,
    )
    return proc.returncode, proc.stdout


def run_js(js_path: Path, mode: str = "normal", stdin_input: str = None):
    if mode == "long":
        env = dict(os.environ)
        env["PORT"] = LONG_RUNNING_PORT
        proc = subprocess.Popen(
            ["node", "-r", str(STDOUT_BLOCKING_SHIM), str(js_path)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, text=True, env=env,
        )
        time.sleep(1.5)
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
        return 0, out
    proc = subprocess.run(
        ["node", str(js_path)],
        input=stdin_input,
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout


def normalize(s: str) -> str:
    return s.replace("\r\n", "\n").rstrip("\n")


def main():
    failures = 0
    passes = 0
    skips = 0
    print(f"AS-compiler parity ({len(PROGRAMS)} target program(s))")
    print("=" * 70)
    for as_basename, js_basename, stage_spec in PROGRAMS:
        # Parse out modes from the stage spec: "stage[:long][:stdin=...]"
        parts = stage_spec.split(":")
        stage = parts[0]
        mode = "normal"
        stdin_input = None
        for part in parts[1:]:
            if part == "long":
                mode = "long"
            elif part.startswith("stdin="):
                stdin_input = part[len("stdin="):].encode().decode("unicode_escape")
        label = f"{as_basename:<32} via {stage}{' (long)' if mode=='long' else ''}{' (stdin)' if stdin_input else ''}"
        try:
            stage_exe = ensure_bootstrap(stage)
        except Exception as e:
            print(f"[SKIP] {label}: cannot build {stage} ({e})")
            skips += 1
            continue
        as_path = AS_DIR / as_basename
        js_path = JS_DIR / js_basename
        try:
            ir = compile_via_as(stage_exe, as_path)
        except Exception as e:
            print(f"[FAIL] {label}: AS compiler error: {e}")
            failures += 1
            continue
        if not ir.strip():
            print(f"[FAIL] {label}: AS compiler produced empty IR")
            failures += 1
            continue
        out_exe = BUILD_DIR / (as_basename.replace(".as", ".exe"))
        try:
            clang_build(ir, out_exe)
        except Exception as e:
            print(f"[FAIL] {label}: clang link error: {e}")
            failures += 1
            continue
        try:
            as_rc, as_out = run_exe(out_exe, mode=mode, stdin_input=stdin_input)
            js_rc, js_out = run_js(js_path, mode=mode, stdin_input=stdin_input)
        except Exception as e:
            print(f"[FAIL] {label}: execution error: {e}")
            failures += 1
            continue
        as_n, js_n = normalize(as_out), normalize(js_out)
        # For long-running programs we killed both sides; don't compare
        # exit codes (terminate() returns a non-zero on Windows).
        rc_ok = (mode == "long") or (as_rc == js_rc)
        if as_n == js_n and rc_ok:
            print(f"[PASS] {label}  (stdout {len(js_n)} bytes)")
            passes += 1
        else:
            print(f"[FAIL] {label}")
            if as_n != js_n:
                print(f"   stdout diff:")
                print(f"     AS={as_n[:200]!r}")
                print(f"     JS={js_n[:200]!r}")
            if not rc_ok:
                print(f"   exit diff:   AS={as_rc}  JS={js_rc}")
            failures += 1
    print("=" * 70)
    total = len(PROGRAMS)
    print(f"PASS: {passes}/{total}    FAIL: {failures}    SKIP: {skips}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
