#!/usr/bin/env python3
"""BIN-4 / BIN-9: backend output equivalence (JIT ≡ native) as a codegen conformance gate.

The check ⊇ codegen contract has a second half: the two backends must AGREE. A
check-clean program run through the in-process JIT and built to a native exe must
produce identical stdout and exit code — otherwise one backend is unsound. This is
the codegen conformance gate (BIN-9): it runs a representative slice of the
check-clean console corpus through both backends and asserts equivalence.

C-compiler-gated: skipped (not failed) when no clang/zig is available to build the
native exe.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A representative slice of deterministic, check-clean console examples spanning
# value/IO, integer math, control flow, records, and string output.
CONFORMANCE_EXAMPLES = [
    "hello_world.sem",
    "add_two.sem",
    "abs_difference.sem",
    "record_demo.sem",
    "module_storage.sem",
]


def _jit_run(source):
    return semanticscript._record_run(source)  # (stdout, exitCode)


def _native_run(source, tmp_path):
    program = semanticscript.parse(source)
    exe = semanticscript.build_executable(program, str(tmp_path / "prog"))
    proc = subprocess.run([exe], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=60)
    return proc.stdout, proc.returncode


@pytest.mark.parametrize("name", CONFORMANCE_EXAMPLES)
def test_bin4_jit_native_output_equivalence(name, tmp_path):
    if semanticscript._find_c_compiler() is None:
        pytest.skip("no C compiler to build the native exe for JIT≡native conformance")
    path = os.path.join(ROOT, "examples", name)
    if not os.path.exists(path):
        pytest.skip(f"{name} not present")
    source = open(path, encoding="utf-8").read()

    # Both backends must agree the program is check-clean before we compare output.
    prog = semanticscript.parse(source)
    errs = [d for d in semanticscript.lint(prog) if d.severity == "error"]
    assert not errs, f"{name} is not check-clean: {[d.code for d in errs]}"

    jit_out, jit_code = _jit_run(source)
    nat_out, nat_code = _native_run(source, tmp_path)
    assert jit_out == nat_out, (
        f"{name}: JIT≢native stdout\n--- JIT ---\n{jit_out!r}\n--- native ---\n{nat_out!r}")
    assert jit_code == nat_code, (
        f"{name}: JIT exit {jit_code} != native exit {nat_code}")
