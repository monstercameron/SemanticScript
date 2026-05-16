"""
run_bootstrap_chain.py -- end-to-end verification of the AgentScript
self-hosting bootstrap.

This script demonstrates that AgentScript can compile AgentScript by
walking the full chain. The bootstrap ladder grows the parser one rung
at a time; each stage's output executable is produced by code written
entirely in AgentScript.

    Stage 1 (bootstrap.as):   Python `ascc.py` compiles `bootstrap.as`
                              into native `bootstrap.exe`. The .as file
                              hand-emits the LLVM IR for `Hello, World!`
                              line by line.

    Stage 2 (bootstrap2.as):  Reads `input.as`, finds its first quoted
                              greeting, emits LLVM IR that prints those
                              exact bytes when compiled.

    Stage 3 (bootstrap3.as):  Reads `input3.as`, finds the first
                              `ExitCode <N>` declaration whose value is
                              a decimal-digit literal, and emits LLVM IR
                              for a program that returns N from main().

    Stage 4 (bootstrap4.as):  Reads `input4.as`, finds both a greeting
                              string and an `ExitCode` integer, and
                              emits a complete LLVM module that prints
                              the greeting with puts and exits with the
                              integer.

    Stage 5 (bootstrap5.as):  Reads `input5.as`, finds the
                              `CountdownValue <N>` start and the
                              `ExitCode <M>` return code, and emits LLVM
                              IR with real basic-block control flow
                              (entry / loopHead / loopBody / loopExit
                              joined by a conditional branch). The
                              resulting executable prints N..1 one per
                              line, then exits M.

The script fails (exit 1) if any stage produces unexpected output.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASCC = HERE.parent / "compiler" / "ascc.py"
CLANG = os.environ.get("ASCC_CLANG") or shutil.which("clang") or r"C:/Program Files/LLVM/bin/clang.exe"

if not Path(CLANG).exists():
    print(f"clang not found at {CLANG}; set ASCC_CLANG", file=sys.stderr)
    sys.exit(1)


def step(title: str):
    print()
    print(f"=== {title} ===")


def run(cmd, allow_nonzero=False, **kwargs):
    proc = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
    if proc.returncode != 0 and not allow_nonzero:
        print(f"FAIL: {' '.join(str(c) for c in cmd)}", file=sys.stderr)
        if proc.stdout:
            print("--- stdout ---", file=sys.stderr)
            print(proc.stdout, file=sys.stderr)
        if proc.stderr:
            print("--- stderr ---", file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
        sys.exit(1)
    return proc


def assert_output(actual: str, expected: str, label: str):
    actual_norm = actual.replace("\r\n", "\n").rstrip("\n")
    if actual_norm != expected:
        print(f"FAIL ({label}):\n  expected: {expected!r}\n  got:      {actual_norm!r}",
              file=sys.stderr)
        sys.exit(1)
    print(f"  matched expected: {expected!r}")


def assert_exit(actual: int, expected: int, label: str):
    if actual != expected:
        print(f"FAIL ({label}): expected exit {expected}, got {actual}", file=sys.stderr)
        sys.exit(1)
    print(f"  matched expected exit code: {expected}")


def compile_as(source: str, exe_name: str):
    run([sys.executable, str(ASCC), str(HERE / source),
         "--emit-exe", str(HERE / exe_name)])
    print(f"  built: {HERE / exe_name}")


def emit_ir(exe_name: str, ll_name: str) -> str:
    result = run([str(HERE / exe_name)])
    out = result.stdout
    (HERE / ll_name).write_text(out, newline="\n")
    print(f"  emitted: {HERE / ll_name} ({len(out)} bytes)")
    return out


def clang_build(ll_name: str, exe_name: str):
    run([CLANG, "-O2", "-o", str(HERE / exe_name), str(HERE / ll_name)])
    print(f"  built: {HERE / exe_name}")


# ---------------------------------------------------------------- Stage 1
step("Stage 1 -- Python ascc.py compiles bootstrap.as -> bootstrap.exe")
compile_as("bootstrap.as", "bootstrap.exe")

step("Stage 2 -- bootstrap.exe emits LLVM IR for hello-world")
emit_ir("bootstrap.exe", "hello_self.ll")

step("Stage 3 -- clang compiles the AgentScript-emitted IR -> hello_self.exe")
clang_build("hello_self.ll", "hello_self.exe")

step("Stage 4 -- hello_self.exe runs (AgentScript program compiled by AgentScript)")
result = run([str(HERE / "hello_self.exe")])
print(f"  output: {result.stdout!r}")
assert_output(result.stdout, "Hello, World!", "stage 1-4")

# ---------------------------------------------------------------- Stage 2
step("Stage 5 -- Python ascc.py compiles bootstrap2.as -> bootstrap2.exe")
compile_as("bootstrap2.as", "bootstrap2.exe")

step("Stage 6 -- bootstrap2.exe reads input.as, extracts its first quoted greeting, emits IR")
emit_ir("bootstrap2.exe", "stage2_hello.ll")

step("Stage 7 -- clang compiles bootstrap2-emitted IR -> stage2_hello.exe")
clang_build("stage2_hello.ll", "stage2_hello.exe")

step("Stage 8 -- stage2_hello.exe runs (AgentScript greeting parsed from .as source)")
result = run([str(HERE / "stage2_hello.exe")])
print(f"  output: {result.stdout!r}")
input_text = (HERE / "input.as").read_text(encoding="utf-8")
first_quote = input_text.index('"')
second_quote = input_text.index('"', first_quote + 1)
expected_greeting = input_text[first_quote + 1:second_quote]
assert_output(result.stdout, expected_greeting, "stage 5-8")

# ---------------------------------------------------------------- Stage 3
step("Stage 9 -- Python ascc.py compiles bootstrap3.as -> bootstrap3.exe")
compile_as("bootstrap3.as", "bootstrap3.exe")

step("Stage 10 -- bootstrap3.exe parses input3.as's ExitCode literal, emits IR")
emit_ir("bootstrap3.exe", "stage3.ll")

step("Stage 11 -- clang compiles bootstrap3-emitted IR -> stage3_const.exe")
clang_build("stage3.ll", "stage3_const.exe")

step("Stage 12 -- stage3_const.exe exits with the parsed integer")
result = run([str(HERE / "stage3_const.exe")], allow_nonzero=True)
print(f"  exit code: {result.returncode}")
input3_text = (HERE / "input3.as").read_text(encoding="utf-8")
# Mirror bootstrap3's parser: find first 'ExitCode ' followed by a digit.
import re as _re
match = _re.search(r"ExitCode (\d+)", input3_text)
expected_exit = int(match.group(1))
assert_exit(result.returncode, expected_exit, "stage 9-12")

# ---------------------------------------------------------------- Stage 4
step("Stage 13 -- Python ascc.py compiles bootstrap4.as -> bootstrap4.exe")
compile_as("bootstrap4.as", "bootstrap4.exe")

step("Stage 14 -- bootstrap4.exe parses greeting + ExitCode from input4.as, emits IR")
emit_ir("bootstrap4.exe", "stage4.ll")

step("Stage 15 -- clang compiles bootstrap4-emitted IR -> stage4_greet.exe")
clang_build("stage4.ll", "stage4_greet.exe")

step("Stage 16 -- stage4_greet.exe prints greeting and exits with parsed code")
result = run([str(HERE / "stage4_greet.exe")], allow_nonzero=True)
print(f"  output: {result.stdout!r}  exit: {result.returncode}")
input4_text = (HERE / "input4.as").read_text(encoding="utf-8")
# Find the first `CNullTerminatedByteString "..."` declaration
marker = 'CNullTerminatedByteString "'
idx = input4_text.find(marker)
greet_start = idx + len(marker)
greet_end = input4_text.index('"', greet_start)
expected_greeting4 = input4_text[greet_start:greet_end]
match4 = _re.search(r"ExitCode (\d+)", input4_text)
expected_exit4 = int(match4.group(1))
assert_output(result.stdout, expected_greeting4, "stage 13-16 greeting")
assert_exit(result.returncode, expected_exit4, "stage 13-16 exit")

# ---------------------------------------------------------------- Stage 5
step("Stage 17 -- Python ascc.py compiles bootstrap5.as -> bootstrap5.exe")
compile_as("bootstrap5.as", "bootstrap5.exe")

step("Stage 18 -- bootstrap5.exe parses CountdownValue + ExitCode from input5.as, emits IR")
emit_ir("bootstrap5.exe", "stage5.ll")

step("Stage 19 -- clang compiles bootstrap5-emitted IR -> stage5_countdown.exe")
clang_build("stage5.ll", "stage5_countdown.exe")

step("Stage 20 -- stage5_countdown.exe runs the countdown loop")
result = run([str(HERE / "stage5_countdown.exe")], allow_nonzero=True)
print(f"  output: {result.stdout!r}  exit: {result.returncode}")
input5_text = (HERE / "input5.as").read_text(encoding="utf-8")
match_count = _re.search(r"CountdownValue (\d+)", input5_text)
expected_start = int(match_count.group(1))
match_exit = _re.search(r"ExitCode (\d+)", input5_text)
expected_exit5 = int(match_exit.group(1))
expected_output5 = "\n".join(str(i) for i in range(expected_start, 0, -1))
assert_output(result.stdout, expected_output5, "stage 17-20 countdown")
assert_exit(result.returncode, expected_exit5, "stage 17-20 exit")

print()
print("=" * 60)
print("ALL STAGES OK -- AgentScript has compiled AgentScript end-to-end.")
print("Bootstrap chain: hello -> parsed-greeting -> constant-return ->")
print("                 greeting+exit -> countdown-with-branches")
print("=" * 60)
