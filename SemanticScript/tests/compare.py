"""
compare.py - parity test harness.

For each (js_basename, sem_basename, stdin_input) row in PROGRAMS this script:
  1. runs <project root>/samples/javascript/<js>.js with Node (passing any stdin)
  2. compiles SemanticScript/sem/<sem>.sscript with semsc and JIT-runs main
  3. compares stdout byte-for-byte and exit codes

Long-running programs (the webserver) are run via a port-pinned smoke harness
so the test does not block.

Exits non-zero if any pair diverges.
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(ROOT)
JS_DIR = os.path.join(PROJECT_ROOT, "samples", "javascript")
SEM_DIR = os.path.join(ROOT, "sem")
COMPILER = os.path.join(ROOT, "compiler", "semsc.py")
LONG_RUNNING_PORT = "3149"


# (js_basename, sem_basename, stdin_input, mode)
# mode: "normal" = run JS to completion; "long" = capture banner only
PROGRAMS = [
    ("hello.js",                              "hello.sscript",                              "",       "normal"),
    ("hello-world.js",                        "hello_world.sscript",                        "",       "normal"),
    ("countdown.js",                          "countdown.sscript",                          "",       "normal"),
    ("fizzbuzz.js",                           "fizzbuzz.sscript",                           "",       "normal"),
    ("factorial.js",                          "factorial.sscript",                          "",       "normal"),
    ("sum_of_squares.js",                     "sum_of_squares.sscript",                     "",       "normal"),
    ("simple-calculator.js",                  "simple_calculator.sscript",                  "",       "normal"),
    ("number-stats.js",                       "number_stats.sscript",                       "",       "normal"),
    ("string-analyzer.js",                    "string_analyzer.sscript",                    "",       "normal"),
    ("json-order-summary.js",                 "json_order_summary.sscript",                 "",       "normal"),
    ("inventory-manager.js",                  "inventory_manager.sscript",                  "",       "normal"),
    ("event-workflow.js",                     "event_workflow.sscript",                     "",       "normal"),
    ("async-workflow.js",                     "async_workflow.sscript",                     "",       "normal"),
    ("complex-checkout-saga.js",              "complex_checkout_saga.sscript",              "",       "normal"),
    ("esoteric-church-encoding.js",           "esoteric_church_encoding.sscript",           "",       "normal"),
    ("esoteric-reactive-proxy.js",            "esoteric_reactive_proxy.sscript",            "",       "normal"),
    ("esoteric-self-referential.js",          "esoteric_self_referential.sscript",          "",       "normal"),
    ("esoteric-stack-language.js",            "esoteric_stack_language.sscript",            "",       "normal"),
    ("esoteric-trampoline.js",                "esoteric_trampoline.sscript",                "",       "normal"),
    ("counterintuitive-closure-capture.js",   "counterintuitive_closure_capture.sscript",   "",       "normal"),
    ("counterintuitive-coercion.js",          "counterintuitive_coercion.sscript",          "",       "normal"),
    ("counterintuitive-event-loop.js",        "counterintuitive_event_loop.sscript",        "",       "normal"),
    ("counterintuitive-mutation.js",          "counterintuitive_mutation.sscript",          "",       "normal"),
    ("counterintuitive-numbers.js",           "counterintuitive_numbers.sscript",           "",       "normal"),
    ("counterintuitive-this-binding.js",      "counterintuitive_this_binding.sscript",      "",       "normal"),
    ("file-inventory.js",                     "file_inventory.sscript",                     "",       "normal"),
    ("todos-list.js",                         "todos_list.sscript",                         "1\n7\n", "normal"),
    ("webserver-console.js",                  "webserver_console.sscript",                  "",       "long"),
]


def run_js(js_basename, stdin, mode):
    js_path = os.path.join(JS_DIR, js_basename)
    if mode == "long":
        # Node's stdout is block-buffered when piped, so the listen-banner
        # stays trapped in libuv's async write queue and is lost when we
        # force-terminate. Preload a tiny shim that switches process.stdout
        # into synchronous (blocking) mode so the banner flushes as soon as
        # it is written, before the server starts blocking on accept.
        # Port 3000 is reserved on this host; use a high free port that
        # Node will print in the banner, and pin both the JS-side and the
        # SemanticScript side to the same port via the LONG_RUNNING_PORT env var below.
        shim = os.path.join(HERE, "stdout_blocking.js")
        env = dict(os.environ)
        env["PORT"] = LONG_RUNNING_PORT
        proc = subprocess.Popen(
            ["node", "-r", shim, js_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            text=True,
            env=env,
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
        ["node", js_path],
        input=stdin,
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout


def run_sem(sem_basename):
    sem_path = os.path.join(SEM_DIR, sem_basename)
    proc = subprocess.run(
        [sys.executable, COMPILER, sem_path, "--run"],
        capture_output=True, text=True, timeout=30,
    )
    return proc.returncode, proc.stdout


def normalize(s):
    return s.replace("\r\n", "\n").rstrip("\n")


def main():
    failures = 0
    for js_basename, sem_basename, stdin, mode in PROGRAMS:
        try:
            js_rc, js_out = run_js(js_basename, stdin, mode)
        except Exception as e:
            print(f"[ERR ] {sem_basename}: failed to run JS: {e}")
            failures += 1
            continue
        try:
            sem_rc, sem_out = run_sem(sem_basename)
        except Exception as e:
            print(f"[ERR ] {sem_basename}: failed to run SemanticScript: {e}")
            failures += 1
            continue
        js_n, sem_n = normalize(js_out), normalize(sem_out)
        out_ok = js_n == sem_n
        # For long-running programs we don't check JS exit code (we killed it)
        rc_ok = (mode == "long") or (js_rc == sem_rc)
        ok = out_ok and rc_ok
        status = "OK  " if ok else "FAIL"
        print(f"[{status}] {sem_basename}: rc js={js_rc} sem={sem_rc}; out_equal={out_ok}")
        if not ok:
            failures += 1
            print("  --- JS stdout ---")
            print(js_n)
            print("  --- SemanticScript stdout ---")
            print(sem_n)
    total = len(PROGRAMS)
    if failures:
        print(f"\n{failures} / {total} failure(s).")
        sys.exit(1)
    print(f"\nAll {total} programs match.")


if __name__ == "__main__":
    main()
