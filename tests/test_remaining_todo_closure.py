#!/usr/bin/env python3
"""Regression guards for the final canonical TODO rows.

These tests cover the small compiler/tooling surfaces added while closing the
remaining backlog: cleanup ordering rows, panic tiers, panicmaps, deterministic
collection behavior, causedBy cleanup propagation, and corpus/build metadata.
"""

import json
import os
import subprocess
import sys

import pytest

import semanticscript as ss


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLES = os.path.join(ROOT, "examples")
SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")


def _panic_src(tier=None):
    src = open(os.path.join(EXAMPLES, "panic_div0_report.sem"), encoding="utf-8").read()
    if tier is not None:
        src = src.replace(
            "PanicDiv0Report entry main\n",
            f"PanicDiv0Report entry main\nPanicDiv0Report panic {tier}\n",
        )
    return src


def test_ws1_114_cleanup_order_and_onexit_rows_are_validated():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path m\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "CleanupError is error\n"
        "main is operation\nmain out Result Int32 CleanupError\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let ok immutable Int32 0\nmain do acquire\nmain defer cleanupHandle\n"
        "main return ok nil\n"
        "acquire is call\nacquire in main\nacquire invokes c.acquire\n"
        "acquire out handle OpaquePointer\nacquire owns handle\n"
        "acquire cleanedBy cleanupHandle\n"
        "closeWorker is call\ncloseWorker in main\ncloseWorker invokes c.close\n"
        "closeWorker arg handle OpaquePointer handle\n"
        "closeWorker catch closeErr CleanupError\n"
        "cleanupHandle is cleanup\ncleanupHandle in main\ncleanupHandle call closeWorker\n"
        "cleanupHandle cleans handle\ncleanupHandle order reverseCreation\n"
        "cleanupHandle onExit success error panic\ncleanupHandle onFailure propagate\n"
    )
    program = ss.parse(src)
    cleanup = program.entities["cleanupHandle"]
    assert cleanup.fact("order").payload == ["reverseCreation"]
    assert cleanup.fact("onExit").payload == ["success", "error", "panic"]

    bad_order = src.replace("cleanupHandle order reverseCreation", "cleanupHandle order fifo")
    with pytest.raises(ss.EavError) as exc:
        ss.parse(bad_order)
    assert exc.value.code == "SS1545"

    bad_path = src.replace("cleanupHandle onExit success error panic", "cleanupHandle onExit success retry")
    with pytest.raises(ss.EavError) as exc:
        ss.parse(bad_path)
    assert exc.value.code == "SS1546"


def test_x099_cleanup_propagation_exposes_causedby_chain():
    program = ss.parse(
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path m\nm exports main\nm purpose "p"\nm invariant "i"\n'
        "CleanupError is error\n"
        "main is operation\nmain out Result Int32 CleanupError\nmain async no\n"
        'main purpose "p"\nmain invariant "i"\n'
        "main let ok immutable Int32 0\nmain do acquire\nmain defer cleanupHandle\n"
        "main return ok nil\n"
        "acquire is call\nacquire in main\nacquire invokes c.acquire\n"
        "acquire out handle OpaquePointer\nacquire owns handle\n"
        "acquire cleanedBy cleanupHandle\n"
        "closeWorker is call\ncloseWorker in main\ncloseWorker invokes c.close\n"
        "closeWorker arg handle OpaquePointer handle\n"
        "closeWorker catch closeErr CleanupError\n"
        "cleanupHandle is cleanup\ncleanupHandle in main\ncleanupHandle call closeWorker\n"
        "cleanupHandle cleans handle\ncleanupHandle onFailure propagate\n"
    )
    chains = ss.error_context_chains(program)
    assert chains == [{
        "cleanup": "cleanupHandle",
        "operation": "main",
        "worker": "closeWorker",
        "visibleError": "CleanupError",
        "resultError": "CleanupError",
        "causedBy": "in-flight-error",
        "policy": "wrap",
    }]


def test_ws1_132_133_panic_tiers_change_lowering_and_json_path():
    full_ir = str(ss.lower_to_llvm(ss.parse(_panic_src())))
    assert "ss_panic" in full_ir
    assert "divide-by-zero" in full_ir

    minimal_ir = str(ss.lower_to_llvm(ss.parse(_panic_src("minimal"))))
    assert "ss_panic" in minimal_ir
    assert "site-id" in minimal_ir
    assert "divide-by-zero" not in minimal_ir

    off_ir = str(ss.lower_to_llvm(ss.parse(_panic_src("off"))))
    assert "llvm.trap" in off_ir
    assert "ss_panic" not in off_ir

    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "run", os.path.join(EXAMPLES, "panic_div0_report.sem"), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode != 0
    payload = json.loads(proc.stdout)
    assert payload["status"] == "crashed"
    assert payload["panic"]["path"] == "main"


def test_ws1_134_panicmap_sidecar_and_symbolication(tmp_path, capsys):
    program = ss.parse(_panic_src("minimal"))
    ir_hash = ss._build_identity(program)["irSha256"]
    sidecar = ss._write_panicmap(program, str(tmp_path / "app.exe"), ir_hash)
    data = json.loads(open(sidecar, encoding="utf-8").read())
    assert data["surface"] == "sem.panicmap.v1"
    assert data["irSha256"] == ir_hash
    assert data["panicTier"] == "minimal"
    site = next(s for s in data["sites"] if s["code"] == "SSR0010")
    assert site["op"] == "main"
    assert "Guard the divisor" in site["fixHint"]

    assert ss.main(["explain-panic", sidecar, site["siteId"], "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sem.explainPanic.v1"
    assert payload["site"]["code"] == "SSR0010"


def test_ws1_137_138_panic_examples_are_robust_and_repeatable():
    cases = {
        "panic_div0_report.sem": "SSR0010",
        "panic_narrowing_report.sem": "SSR0012",
        "panic_recursion_report.sem": "SSR0013",
    }
    for filename, code in cases.items():
        path = os.path.join(EXAMPLES, filename)
        for _ in range(2):
            proc = subprocess.run(
                [sys.executable, SEMANTICSCRIPT, "run", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=90,
            )
            assert proc.returncode == 134
            assert f"EAV PANIC {code}" in proc.stderr
            assert "op:" in proc.stderr
            assert "path:" in proc.stderr
            assert "operands:" in proc.stderr


def test_x094_collections_map_is_deterministic_across_runs():
    path = os.path.join(EXAMPLES, "collections_map.sem")
    outs = []
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, SEMANTICSCRIPT, "run", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        assert proc.returncode == 0, proc.stderr
        outs.append(proc.stdout)
    assert outs[0] == outs[1]
    assert "---- 6 passed, 0 failed ----" in outs[0]


def test_x213_x214_x215_corpus_and_build_metadata_are_machine_readable():
    files = [f for f in os.listdir(EXAMPLES) if f.endswith(".sem") and not f.startswith("_")]
    assert len(files) >= 150
    assert any(f.startswith("panic_") for f in files)
    assert any(f.startswith("decimal_") for f in files)
    assert any(f.startswith("async_") for f in files)
    assert any(f.startswith("defer_") for f in files)
    assert ss._default_build_output("hello_world.sem", None, "abc123").endswith("hello_world-abc123.exe")
    identity = ss._build_identity(ss.parse(open(os.path.join(EXAMPLES, "hello_world.sem"), encoding="utf-8").read()))
    assert identity["irSha256"]
