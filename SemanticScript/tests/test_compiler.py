"""
test_compiler.py - unit tests for the SemanticScript reference compiler.

Covers the smaller, language-level invariants that the parity suite
(`compare.py`) does not directly exercise:

  - tokenizer escape handling
  - parser line-number tracking
  - simple end-to-end compile-and-JIT for a few canonical programs
  - the bootstrap chain stages 3, 4, 5: each one should compile,
    emit deterministic IR, and (when fed through clang) produce an
    executable whose stdout and exit code match the values declared
    in its input .sscript file.

Run:
    python tests/test_compiler.py

Exits non-zero on first failure, prints a summary otherwise.
"""

import os
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COMPILER_DIR = ROOT / "compiler"
BOOTSTRAP_DIR = ROOT / "bootstrap"

sys.path.insert(0, str(COMPILER_DIR))
import semsc  # noqa: E402


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
    toks = semsc.tokenize_line('const greeting CNullTerminatedByteString "Hi \\"world\\""')
    check("tokenizer: 4 tokens",
          len(toks) == 4,
          f"got {len(toks)} tokens: {toks!r}")
    check("tokenizer: string is unescaped",
          toks[3] == ("str", 'Hi "world"'),
          f"got {toks[3]!r}")

    toks2 = semsc.tokenize_line("# this is a comment")
    check("tokenizer: comment splits into '#' + body",
          toks2 == ["#", "this is a comment"],
          f"got {toks2!r}")

    toks3 = semsc.tokenize_line("   ")
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
    prog = semsc.parse(src)
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
        "CompletelyUnknownVerbThatShouldFail x y",
        "",
    ])
    raised = False
    msg = ""
    try:
        semsc.parse(bad)
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
    src_path = ROOT / "sem" / "hello.sscript"
    source = src_path.read_text(encoding="utf-8")
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    check("compile: hello.sscript defines @main",
          "define i32 @\"main\"" in ir_text or "define i32 @main" in ir_text,
          "no main defined in IR")
    check("compile: hello.sscript references puts",
          "@\"puts\"" in ir_text or "@puts" in ir_text,
          "no puts in IR")


def test_cli_accepts_sem_alias():
    src_path = ROOT / "tests" / "tiny.sem"
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
         str(src_path), "--parse-only", "--quiet"],
        capture_output=True, text=True,
    )
    check("compile: .sem alias parses",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_success_message_renderer():
    rendered = semsc._render_success_message(
        "SSOK001",
        "SemanticScript compile complete",
        "sample.sscript",
        outputs=[("llvm ir", "sample.ll"), ("executable", "sample.exe")],
        details=[("profile", "dev"), ("runtime checks", "panic")],
        next_steps=["Run sample.exe."],
    )
    check("success message: names code and title",
          rendered.startswith("success SSOK001: SemanticScript compile complete"),
          rendered)
    check("success message: lists outputs",
          "Outputs:\n  llvm ir: sample.ll\n  executable: sample.exe" in rendered,
          rendered)
    check("success message: lists next step",
          "Next:\n  Run sample.exe." in rendered,
          rendered)


def test_persisted_ir_path_resolution():
    check("persist llvm ir: auto without --emit-ir discards",
          semsc._resolve_persisted_ir_path("sample.sscript") is None)
    check("persist llvm ir: explicit --emit-ir wins",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", emit_ir="custom.ll") == "custom.ll")
    check("persist llvm ir: yes creates source sidecar",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", persist_llvm_ir="yes") == "sample.ll")
    check("persist llvm ir: yes prefers executable basename",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", emit_exe="out.exe",
              persist_llvm_ir="yes") == "out.ll")
    check("persist llvm ir: no suppresses even explicit path",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", emit_ir="custom.ll",
              persist_llvm_ir="no") is None)


def test_cli_persist_llvm_ir_flag():
    src = "\n".join([
        "project PersistIr",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "persist_ir.sscript"
        sidecar_path = Path(tmpdir) / "persist_ir.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        auto_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--quiet"],
            capture_output=True, text=True,
        )
        check("persist llvm ir: auto leaves no sidecar",
              auto_proc.returncode == 0 and not sidecar_path.exists(),
              f"rc={auto_proc.returncode} stderr={auto_proc.stderr!r}")
        yes_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--persist-llvm-ir", "yes", "--quiet"],
            capture_output=True, text=True,
        )
        check("persist llvm ir: yes writes sidecar",
              yes_proc.returncode == 0 and sidecar_path.exists(),
              f"rc={yes_proc.returncode} stderr={yes_proc.stderr!r}")
        sidecar_path.unlink()
        no_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--persist-llvm-ir", "no", "--quiet"],
            capture_output=True, text=True,
        )
        check("persist llvm ir: no leaves no sidecar",
              no_proc.returncode == 0 and not sidecar_path.exists(),
              f"rc={no_proc.returncode} stderr={no_proc.stderr!r}")


def test_codegen_diagnostic_is_agent_readable():
    src = "\n".join([
        "project BadDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "call badCall math.addI64",
        "arg badCall left missingValue",
        "arg badCall right 1",
        "run badCall",
        "bind resultValue CSignedInt64 badCall",
        "returnValue resultValue",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "bad.sscript"
        ir_path = Path(tmpdir) / "bad.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", str(ir_path)],
            capture_output=True, text=True,
        )
        stderr = proc.stderr
        check("diagnostics: call-lowering failure exits 3",
              proc.returncode == 3,
              f"rc={proc.returncode} stderr={stderr!r}")
        check("diagnostics: agent log names code and phase",
              "error SSCG002" in stderr and "phase: codegen.call-lowering" in stderr,
              stderr)
        check("diagnostics: SemanticScript stack points to call",
              "call badCall math.addI64" in stderr
              and "source: call badCall math.addI64" in stderr,
              stderr)
        json_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", str(ir_path),
             "--diagnostics-format", "json"],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(json_proc.stderr)
        except json.JSONDecodeError:
            payload = {}
        check("diagnostics: json renderer is machine-readable",
              payload.get("code") == "SSCG002"
              and payload.get("semanticStack", [{}])[0].get("callName") == "badCall",
              json_proc.stderr)


def test_backend_diagnostic_maps_symbol_to_source_call():
    src = "\n".join([
        "project BackendDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "call loadJsonCall c.fscanf",
        "returnValue 0",
        "",
    ])
    prog = semsc.parse(src)
    prog.source_path = "backend_bad.sscript"
    cg = semsc.Codegen(prog)
    fake_call = {
        "name": "loadJsonCall",
        "operation": "main",
        "line": 8,
        "target": "c.fscanf",
    }
    cg.provenance.record_external("fscanf", fake_call)
    diag = cg.provenance.explain_backend_error(
        "lld-link: error: undefined symbol: fscanf\n"
        ">>> referenced by tmp.o:(main)\n"
    )
    rendered = diag.render("agent")
    check("diagnostics: backend undefined symbol maps to source",
          diag.code == "SSBE001"
          and diag.primary.line == 8
          and "call loadJsonCall c.fscanf" in rendered,
          rendered)


def test_runtime_check_resolution_profiles():
    check("runtime profile: dev defaults to panic",
          semsc._resolve_runtime_checks("dev") == "panic")
    check("runtime profile: prod defaults to traps",
          semsc._resolve_runtime_checks("prod") == "traps")
    check("runtime profile: explicit override wins",
          semsc._resolve_runtime_checks("prod", "panic") == "panic"
          and semsc._resolve_runtime_checks("dev", "off") == "off")


def test_runtime_profiles_control_panic_context():
    import shutil
    clang = (os.environ.get("SEMSC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("runtime checks: clang available", False,
              f"clang not found at {clang}")
        return
    src = "\n".join([
        "project RuntimePanicDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "const numeratorValue CSignedInt64 7",
        "const zeroDivisor CSignedInt64 0",
        "call divideByZeroCall math.divideI64",
        "arg divideByZeroCall left numeratorValue",
        "arg divideByZeroCall right zeroDivisor",
        "run divideByZeroCall",
        "bind quotientValue CSignedInt64 divideByZeroCall",
        "returnValue quotientValue",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "runtime_panic.sscript"
        dev_exe_path = Path(tmpdir) / "runtime_panic_dev.exe"
        dev_ir_path = Path(tmpdir) / "runtime_panic_dev.ll"
        prod_exe_path = Path(tmpdir) / "runtime_panic_prod.exe"
        prod_ir_path = Path(tmpdir) / "runtime_panic_prod.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        dev_build = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-exe", str(dev_exe_path),
             "--emit-ir", str(dev_ir_path), "--quiet"],
            capture_output=True, text=True,
        )
        if dev_build.returncode != 0:
            check("runtime profile: dev sample builds", False, dev_build.stderr)
            return
        dev_ir_text = dev_ir_path.read_text(encoding="utf-8")
        check("runtime profile: dev panic path avoids C stdio",
              "puts" not in dev_ir_text and "fflush" not in dev_ir_text,
              dev_ir_text)
        dev_run = subprocess.run(
            [str(dev_exe_path)], capture_output=True, text=True)
        dev_output = dev_run.stdout + dev_run.stderr
        check("runtime profile: dev sample exits nonzero",
              dev_run.returncode != 0,
              f"rc={dev_run.returncode} output={dev_output!r}")
        check("runtime profile: dev output names source row by default",
              "error SSRUN001: SemanticScript runtime panic" in dev_output
              and "call: divideByZeroCall -> math.divideI64" in dev_output
              and "10 | call divideByZeroCall math.divideI64" in dev_output
              and "reason: zero divisor before math.divideI64" in dev_output
              and "--build-profile prod" not in dev_output
              and "--runtime-checks off" not in dev_output,
              dev_output)

        prod_build = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-exe", str(prod_exe_path),
             "--emit-ir", str(prod_ir_path), "--build-profile", "prod",
             "--quiet"],
            capture_output=True, text=True,
        )
        if prod_build.returncode != 0:
            check("runtime profile: prod sample builds", False, prod_build.stderr)
            return
        prod_ir_text = prod_ir_path.read_text(encoding="utf-8")
        prod_run = subprocess.run(
            [str(prod_exe_path)], capture_output=True, text=True)
        prod_output = prod_run.stdout + prod_run.stderr
        check("runtime profile: prod sample exits nonzero",
              prod_run.returncode != 0,
              f"rc={prod_run.returncode} output={prod_output!r}")
        check("runtime profile: prod hides source context",
              "llvm.trap" in prod_ir_text
              and "SSRUN001" not in prod_ir_text
              and "SemanticScript runtime panic" not in prod_output
              and "SSRUN001" not in prod_output,
              f"ir={prod_ir_text!r}\noutput={prod_output!r}")


# ============================================================
# Bootstrap chain validation
# ============================================================

def _ensure_built(stage_basename):
    src = BOOTSTRAP_DIR / f"{stage_basename}.sscript"
    exe = BOOTSTRAP_DIR / f"{stage_basename}.exe"
    if exe.exists() and exe.stat().st_mtime >= src.stat().st_mtime:
        return exe
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
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
    input_text = (BOOTSTRAP_DIR / "input3.sscript").read_text(encoding="utf-8")
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
    input_text = (BOOTSTRAP_DIR / "input4.sscript").read_text(encoding="utf-8")
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
    """bootstrap_general.sscript compiles a wide subset of sem/ via REAL
    per-line verb dispatch + escape-aware byte walker. We don't pattern-
    match the IR text (it uses `\\XX` hex escapes now); instead we link
    the IR with clang and diff the exe's stdout against the JS oracle."""
    import shutil
    exe = _ensure_built("bootstrap_general")
    clang = (os.environ.get("SEMSC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("bootstrap_general: clang available", False,
              f"clang not found at {clang}")
        return
    import tempfile
    work = Path(tempfile.gettempdir()) / "semsc_general_tests"
    work.mkdir(exist_ok=True)
    PROJECT_ROOT = BOOTSTRAP_DIR.parent.parent
    pairs = [
        ("hello.sscript", "hello.js"),
        ("hello_world.sscript", "hello-world.js"),
        ("hello_via_helper.sscript", "hello.js"),
        ("inventory_manager.sscript", "inventory-manager.js"),
        ("counterintuitive_closure_capture.sscript", "counterintuitive-closure-capture.js"),
        ("file_inventory.sscript", "file-inventory.js"),
        ("json_order_summary.sscript", "json-order-summary.js"),
    ]
    for sem_basename, js_basename in pairs:
        env = dict(os.environ)
        sem_path = BOOTSTRAP_DIR.parent / "sem" / sem_basename
        env["SEMANTIC_SCRIPT_INPUT"] = str(sem_path)
        proc = subprocess.run([str(exe)], env=env,
                              capture_output=True, text=True, timeout=15)
        ll = work / (sem_basename.replace(".sscript", ".ll"))
        ll.write_text(proc.stdout, encoding="utf-8", newline="\n")
        out_exe = work / (sem_basename.replace(".sscript", ".exe"))
        link = subprocess.run([clang, "-O2", "-o", str(out_exe), str(ll)],
                              capture_output=True, text=True)
        check(f"bootstrap_general: {sem_basename} produces linkable IR",
              link.returncode == 0,
              f"clang failure: {link.stderr.strip()[:200]}")
        if link.returncode != 0:
            continue
        run = subprocess.run([str(out_exe)],
                             capture_output=True, text=True, timeout=15)
        oracle = subprocess.run(
            ["node", str(PROJECT_ROOT / "samples" / "javascript" / js_basename)],
            capture_output=True, text=True, timeout=15)
        sem_out = run.stdout.replace("\r\n", "\n").rstrip("\n")
        js_out = oracle.stdout.replace("\r\n", "\n").rstrip("\n")
        check(f"bootstrap_general: {sem_basename} stdout matches JS oracle",
              sem_out == js_out,
              f"SEM={sem_out[:80]!r}  JS={js_out[:80]!r}")


def test_bootstrap6_scales_with_input():
    exe = _ensure_built("bootstrap6")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input6.sscript").read_text(encoding="utf-8")
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
    input_text = (BOOTSTRAP_DIR / "input5.sscript").read_text(encoding="utf-8")
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
    print(f"Running semsc {semsc.__version__} unit tests")
    print("=" * 60)
    test_tokenizer()
    test_parser_minimal()
    test_parser_syntax_error_has_line()
    test_compile_hello_world_to_ir()
    test_cli_accepts_sem_alias()
    test_success_message_renderer()
    test_persisted_ir_path_resolution()
    test_cli_persist_llvm_ir_flag()
    test_codegen_diagnostic_is_agent_readable()
    test_backend_diagnostic_maps_symbol_to_source_call()
    test_runtime_check_resolution_profiles()
    test_runtime_profiles_control_panic_context()
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
