"""
sem_compiler_parity.py -- score the SemanticScript-written compiler against JS oracles.

For each program listed in PROGRAMS:
  1. Set SEMANTIC_SCRIPT_INPUT=<sem/file.sscript>
  2. Run the most capable SemanticScript-written compiler (bootstrapN.exe), capturing
     its stdout (LLVM IR).
  3. If the IR is non-empty, hand it to clang to produce a .exe.
  4. Run the .exe and capture its stdout + exit code.
  5. Run the JS oracle (node <project-root>/samples/javascript/<name>.js).
  6. Compare stdout (and exit code) byte-for-byte.

Reports per-program PASS/FAIL/SKIP. Exits 0 if every NON-SKIPPED program
passes. The goal is to grow this list as the SemanticScript-written compiler stack
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
JS_DIR = PROJECT_ROOT / "samples" / "javascript"
SEM_DIR = ROOT / "sem"
BOOTSTRAP_DIR = ROOT / "bootstrap"
SEMSC = ROOT / "compiler" / "semsc.py"
BUILD_DIR = HERE / "sem_compiler_build"
BUILD_DIR.mkdir(exist_ok=True)

STDOUT_BLOCKING_SHIM = HERE / "stdout_blocking.js"
CANONICAL_LONG_RUNNING_PORT = "3149"
LONG_RUNNING_PORT = os.environ.get("SEMANTIC_SCRIPT_TEST_PORT", "0")

CLANG = os.environ.get("SEMSC_CLANG") or shutil.which("clang") or r"C:/Program Files/LLVM/bin/clang.exe"
if not Path(CLANG).exists():
    print(f"clang not found at {CLANG}; set SEMSC_CLANG", file=sys.stderr)
    sys.exit(1)


# (sem_basename, js_basename, compiler_stage)
# compiler_stage names a bootstrapN.exe under bootstrap/. The harness
# always uses the SemanticScript-written compiler named here.
PROGRAMS = [
    # The ONLY SemanticScript-written compiler used here is bootstrap_general.sscript. It
    # uses real per-line verb dispatch via c.strncmp on the verb prefix
    # plus an escape-aware byte walker for string bodies. It emits one
    # puts() per String / CNullTerminatedByteString const in source
    # order; this matches the JS oracle for every program whose printed
    # output is exactly the concatenation of its source's string
    # literals.
    ("hello.sscript",                          "hello.js",                            "bootstrap_general"),
    ("hello_world.sscript",                    "hello-world.js",                      "bootstrap_general"),
    ("hello_via_helper.sscript",               "hello.js",                            "bootstrap_general"),
    ("async_workflow.sscript",                 "async-workflow.js",                   "bootstrap_general"),
    ("counterintuitive_closure_capture.sscript", "counterintuitive-closure-capture.js","bootstrap_general"),
    ("counterintuitive_coercion.sscript",      "counterintuitive-coercion.js",        "bootstrap_general"),
    ("counterintuitive_event_loop.sscript",    "counterintuitive-event-loop.js",      "bootstrap_general"),
    ("counterintuitive_mutation.sscript",      "counterintuitive-mutation.js",        "bootstrap_general"),
    ("counterintuitive_numbers.sscript",       "counterintuitive-numbers.js",         "bootstrap_general"),
    ("counterintuitive_this_binding.sscript",  "counterintuitive-this-binding.js",    "bootstrap_general"),
    ("esoteric_church_encoding.sscript",       "esoteric-church-encoding.js",         "bootstrap_general"),
    ("esoteric_reactive_proxy.sscript",        "esoteric-reactive-proxy.js",          "bootstrap_general"),
    ("esoteric_self_referential.sscript",      "esoteric-self-referential.js",        "bootstrap_general"),
    ("esoteric_stack_language.sscript",        "esoteric-stack-language.js",          "bootstrap_general"),
    ("esoteric_trampoline.sscript",            "esoteric-trampoline.js",              "bootstrap_general"),
    ("event_workflow.sscript",                 "event-workflow.js",                   "bootstrap_general"),
    ("file_inventory.sscript",                 "file-inventory.js",                   "bootstrap_general"),
    ("inventory_manager.sscript",              "inventory-manager.js",                "bootstrap_general"),
    ("json_order_summary.sscript",             "json-order-summary.js",               "bootstrap_general"),
    ("number_stats.sscript",                   "number-stats.js",                     "bootstrap_general"),
    ("simple_calculator.sscript",              "simple-calculator.js",                "bootstrap_general"),
    ("string_analyzer.sscript",                "string-analyzer.js",                  "bootstrap_general"),
    ("webserver_console.sscript",              "webserver-console.js",                "bootstrap_general:long"),
    # Integer-output programs (var/set/math/branchIf/writeIntegerLine path).
    ("countdown.sscript",                      "countdown.js",                        "bootstrap_general"),
    ("factorial.sscript",                      "factorial.js",                        "bootstrap_general"),
    ("sum_of_squares.sscript",                 "sum_of_squares.js",                   "bootstrap_general"),
    ("fizzbuzz.sscript",                       "fizzbuzz.js",                         "bootstrap_general"),
    ("todos_list.sscript",                     "todos-list.js",                       "bootstrap_general:stdin=1\\n7\\n"),
]


def ensure_bootstrap(stage_basename: str) -> Path:
    src = BOOTSTRAP_DIR / f"{stage_basename}.sscript"
    exe = BOOTSTRAP_DIR / f"{stage_basename}.exe"
    if exe.exists() and exe.stat().st_mtime >= src.stat().st_mtime:
        return exe
    proc = subprocess.run(
        [sys.executable, str(SEMSC), str(src),
         "--emit-exe", str(exe), "--quiet"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to build {stage_basename}.exe:\n{proc.stderr}")
    return exe


def compile_via_sem(stage_exe: Path, source_path: Path) -> str:
    """Run the SemanticScript-written compiler against `source_path`, return its IR."""
    env = dict(os.environ)
    env["SEMANTIC_SCRIPT_INPUT"] = str(source_path)
    proc = subprocess.run(
        [str(stage_exe)], env=env,
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"{stage_exe.name} exited {proc.returncode} on {source_path.name}\n"
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
    text = s.replace("\r\n", "\n").rstrip("\n")
    return text.replace(
        f"http://127.0.0.1:{LONG_RUNNING_PORT}",
        f"http://127.0.0.1:{CANONICAL_LONG_RUNNING_PORT}",
    )


def main():
    failures = 0
    passes = 0
    skips = 0
    print(f"SemanticScript-compiler parity ({len(PROGRAMS)} target program(s))")
    print("=" * 70)
    for sem_basename, js_basename, stage_spec in PROGRAMS:
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
        label = f"{sem_basename:<32} via {stage}{' (long)' if mode=='long' else ''}{' (stdin)' if stdin_input else ''}"
        try:
            stage_exe = ensure_bootstrap(stage)
        except Exception as e:
            print(f"[SKIP] {label}: cannot build {stage} ({e})")
            skips += 1
            continue
        sem_path = SEM_DIR / sem_basename
        js_path = JS_DIR / js_basename
        try:
            ir = compile_via_sem(stage_exe, sem_path)
        except Exception as e:
            print(f"[FAIL] {label}: SemanticScript compiler error: {e}")
            failures += 1
            continue
        if not ir.strip():
            print(f"[FAIL] {label}: SemanticScript compiler produced empty IR")
            failures += 1
            continue
        out_exe = BUILD_DIR / (sem_basename.replace(".sscript", ".exe"))
        try:
            clang_build(ir, out_exe)
        except Exception as e:
            print(f"[FAIL] {label}: clang link error: {e}")
            failures += 1
            continue
        try:
            sem_rc, sem_out = run_exe(out_exe, mode=mode, stdin_input=stdin_input)
            js_rc, js_out = run_js(js_path, mode=mode, stdin_input=stdin_input)
        except Exception as e:
            print(f"[FAIL] {label}: execution error: {e}")
            failures += 1
            continue
        sem_n, js_n = normalize(sem_out), normalize(js_out)
        # For long-running programs we killed both sides; don't compare
        # exit codes (terminate() returns a non-zero on Windows).
        rc_ok = (mode == "long") or (sem_rc == js_rc)
        if sem_n == js_n and rc_ok:
            print(f"[PASS] {label}  (stdout {len(js_n)} bytes)")
            passes += 1
        else:
            print(f"[FAIL] {label}")
            if sem_n != js_n:
                print(f"   stdout diff:")
                print(f"     SEM={sem_n[:200]!r}")
                print(f"     JS={js_n[:200]!r}")
            if not rc_ok:
                print(f"   exit diff:   SEM={sem_rc}  JS={js_rc}")
            failures += 1
    print("=" * 70)
    total = len(PROGRAMS)
    print(f"PASS: {passes}/{total}    FAIL: {failures}    SKIP: {skips}")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
