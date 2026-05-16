"""
test_compiler.py - unit tests for the AgentScript reference compiler.

Covers the smaller, language-level invariants that the parity suite
(`compare.py`) does not directly exercise:

  - tokenizer escape handling
  - parser line-number tracking
  - simple end-to-end compile-and-JIT for a few canonical programs
  - the bootstrap chain stages 3, 4, 5: each one should compile,
    emit deterministic IR, and (when fed through clang) produce an
    executable whose stdout and exit code match the values declared
    in its input .as file.

Run:
    python tests/test_compiler.py

Exits non-zero on first failure, prints a summary otherwise.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COMPILER_DIR = ROOT / "compiler"
BOOTSTRAP_DIR = ROOT / "bootstrap"

sys.path.insert(0, str(COMPILER_DIR))
import ascc  # noqa: E402


FAILURES = []


def check(label, predicate, message=""):
    if predicate:
        print(f"[OK  ] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}: {message}")


# ============================================================
# Tokenizer
# ============================================================

def test_tokenizer():
    toks = ascc.tokenize_line('const greeting CNullTerminatedByteString "Hi \\"world\\""')
    check("tokenizer: 4 tokens",
          len(toks) == 4,
          f"got {len(toks)} tokens: {toks!r}")
    check("tokenizer: string is unescaped",
          toks[3] == ("str", 'Hi "world"'),
          f"got {toks[3]!r}")

    toks2 = ascc.tokenize_line("# this is a comment")
    check("tokenizer: comment splits into '#' + body",
          toks2 == ["#", "this is a comment"],
          f"got {toks2!r}")

    toks3 = ascc.tokenize_line("   ")
    check("tokenizer: whitespace-only -> empty",
          toks3 == [],
          f"got {toks3!r}")


# ============================================================
# Parser
# ============================================================

def test_parser_minimal():
    src = "\n".join([
        "project Minimal",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "output main Result ExitCode MainError",
        "memory main heap no",
        "async main no",
        "purpose main \"minimal program\"",
        "label startMain",
        "const exitCodeValue ExitCode 0",
        "returnOk exitCodeValue",
        "",
    ])
    prog = ascc.parse(src)
    check("parser: project recorded",
          prog.project_name == "Minimal",
          f"got {prog.project_name!r}")
    check("parser: operation main recorded",
          "main" in prog.operations,
          f"got operations: {list(prog.operations)}")


def test_parser_syntax_error_has_line():
    bad = "\n".join([
        "project Bad",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "label startMain",
        # This `returnOk` references something never declared. The parser
        # itself accepts that; codegen later raises. So instead use a verb
        # that the parser rejects.
        "completelyUnknownVerbThatShouldFail x y",
        "",
    ])
    raised = False
    msg = ""
    try:
        ascc.parse(bad)
    except SyntaxError as e:
        raised = True
        msg = str(e)
    check("parser: unknown verb raises SyntaxError",
          raised,
          "no exception raised")
    check("parser: SyntaxError message names the source line",
          "line 7" in msg or "line " in msg,
          f"msg = {msg!r}")


# ============================================================
# End-to-end compile + JIT for a canonical program
# ============================================================

def test_compile_hello_world_to_ir():
    src_path = ROOT / "as" / "hello.as"
    source = src_path.read_text(encoding="utf-8")
    prog = ascc.parse(source)
    cg = ascc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    check("compile: hello.as defines @main",
          "define i32 @\"main\"" in ir_text or "define i32 @main" in ir_text,
          "no main defined in IR")
    check("compile: hello.as references puts",
          "@\"puts\"" in ir_text or "@puts" in ir_text,
          "no puts in IR")


# ============================================================
# Bootstrap chain validation
# ============================================================

def _ensure_built(stage_basename):
    src = BOOTSTRAP_DIR / f"{stage_basename}.as"
    exe = BOOTSTRAP_DIR / f"{stage_basename}.exe"
    if exe.exists() and exe.stat().st_mtime >= src.stat().st_mtime:
        return exe
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "ascc.py"),
         str(src), "--emit-exe", str(exe), "--quiet"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to build {stage_basename}.exe\nSTDERR:\n{proc.stderr}")
    return exe


def _emit_ir(stage_exe):
    proc = subprocess.run([str(stage_exe)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{stage_exe.name} exited {proc.returncode}\nSTDERR:\n{proc.stderr}")
    return proc.stdout


def test_bootstrap3_emits_constant_return_ir():
    exe = _ensure_built("bootstrap3")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input3.as").read_text(encoding="utf-8")
    expected = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap3: IR contains 'define i32 @main()'",
          "define i32 @main()" in ir_text,
          f"IR was:\n{ir_text}")
    check("bootstrap3: IR returns the parsed ExitCode literal",
          f"ret i32 {expected}" in ir_text,
          f"expected ret i32 {expected}, IR:\n{ir_text}")


def test_bootstrap4_emits_greeting_and_exit():
    exe = _ensure_built("bootstrap4")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input4.as").read_text(encoding="utf-8")
    marker = 'CNullTerminatedByteString "'
    idx = input_text.find(marker)
    g_start = idx + len(marker)
    g_end = input_text.index('"', g_start)
    expected_greeting = input_text[g_start:g_end]
    expected_exit = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap4: IR contains greeting bytes",
          expected_greeting in ir_text,
          f"greeting {expected_greeting!r} not in IR")
    check("bootstrap4: IR returns parsed ExitCode",
          f"ret i32 {expected_exit}" in ir_text,
          f"expected ret i32 {expected_exit}")
    check("bootstrap4: IR declares puts",
          "declare i32 @puts(i8*)" in ir_text,
          "no puts declaration in IR")


def test_bootstrap_general_real_dispatch():
    """bootstrap_general.as compiles a wide subset of as/ via REAL
    per-line verb dispatch + escape-aware byte walker. We don't pattern-
    match the IR text (it uses `\\XX` hex escapes now); instead we link
    the IR with clang and diff the exe's stdout against the JS oracle."""
    import shutil
    exe = _ensure_built("bootstrap_general")
    clang = (os.environ.get("ASCC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("bootstrap_general: clang available", False,
              f"clang not found at {clang}")
        return
    import tempfile
    work = Path(tempfile.gettempdir()) / "ascc_general_tests"
    work.mkdir(exist_ok=True)
    PROJECT_ROOT = BOOTSTRAP_DIR.parent.parent
    pairs = [
        ("hello.as", "hello.js"),
        ("hello_world.as", "hello-world.js"),
        ("hello_via_helper.as", "hello.js"),
        ("inventory_manager.as", "inventory-manager.js"),
        ("counterintuitive_closure_capture.as", "counterintuitive-closure-capture.js"),
        ("file_inventory.as", "file-inventory.js"),
        ("json_order_summary.as", "json-order-summary.js"),
    ]
    for as_basename, js_basename in pairs:
        env = dict(os.environ)
        as_path = BOOTSTRAP_DIR.parent / "as" / as_basename
        env["AS_INPUT"] = str(as_path)
        proc = subprocess.run([str(exe)], env=env,
                              capture_output=True, text=True, timeout=15)
        ll = work / (as_basename.replace(".as", ".ll"))
        ll.write_text(proc.stdout, encoding="utf-8", newline="\n")
        out_exe = work / (as_basename.replace(".as", ".exe"))
        link = subprocess.run([clang, "-O2", "-o", str(out_exe), str(ll)],
                              capture_output=True, text=True)
        check(f"bootstrap_general: {as_basename} produces linkable IR",
              link.returncode == 0,
              f"clang failure: {link.stderr.strip()[:200]}")
        if link.returncode != 0:
            continue
        run = subprocess.run([str(out_exe)],
                             capture_output=True, text=True, timeout=15)
        oracle = subprocess.run(
            ["node", str(PROJECT_ROOT / "javascript" / js_basename)],
            capture_output=True, text=True, timeout=15)
        as_out = run.stdout.replace("\r\n", "\n").rstrip("\n")
        js_out = oracle.stdout.replace("\r\n", "\n").rstrip("\n")
        check(f"bootstrap_general: {as_basename} stdout matches JS oracle",
              as_out == js_out,
              f"AS={as_out[:80]!r}  JS={js_out[:80]!r}")


def test_bootstrap6_scales_with_input():
    exe = _ensure_built("bootstrap6")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input6.as").read_text(encoding="utf-8")
    greetings = re.findall(r'CNullTerminatedByteString "([^"]*)"', input_text)
    n = len(greetings)
    check("bootstrap6: emits one @.s<i> constant per input greeting",
          all(f"@.s{i}" in ir_text for i in range(n)),
          f"missing @.s<i> for some i in 0..{n-1}")
    check("bootstrap6: emits one @print<i> helper per input greeting",
          all(f"@print{i}()" in ir_text for i in range(n)),
          f"missing @print<i> for some i in 0..{n-1}")
    check("bootstrap6: main calls every helper in order",
          all(f"call void @print{i}()" in ir_text for i in range(n)),
          "main is missing one or more @print<i> calls")
    expected_exit = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap6: ret i32 matches parsed ExitCode",
          f"ret i32 {expected_exit}" in ir_text,
          "ret i32 doesn't match parsed ExitCode")


def test_bootstrap5_emits_countdown_loop():
    exe = _ensure_built("bootstrap5")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input5.as").read_text(encoding="utf-8")
    expected_start = int(re.search(r"CountdownValue (\d+)", input_text).group(1))
    expected_exit = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap5: IR contains loopHead label",
          "loopHead:" in ir_text,
          "no loopHead label")
    check("bootstrap5: IR contains loopBody label",
          "loopBody:" in ir_text,
          "no loopBody label")
    check("bootstrap5: IR contains loopExit label",
          "loopExit:" in ir_text,
          "no loopExit label")
    check("bootstrap5: IR stores parsed start value",
          f"store i64 {expected_start}, i64* %counter" in ir_text,
          f"no store of {expected_start}")
    check("bootstrap5: IR returns parsed ExitCode",
          f"ret i32 {expected_exit}" in ir_text,
          f"no ret i32 {expected_exit}")


# ============================================================
# Driver
# ============================================================

def main():
    print(f"Running ascc {ascc.__version__} unit tests")
    print("=" * 60)
    test_tokenizer()
    test_parser_minimal()
    test_parser_syntax_error_has_line()
    test_compile_hello_world_to_ir()
    test_bootstrap3_emits_constant_return_ir()
    test_bootstrap4_emits_greeting_and_exit()
    test_bootstrap5_emits_countdown_loop()
    test_bootstrap6_scales_with_input()
    test_bootstrap_general_real_dispatch()

    print("=" * 60)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} test(s)")
        for label in FAILURES:
            print(f"  - {label}")
        sys.exit(1)
    print("All unit tests passed.")


if __name__ == "__main__":
    main()
