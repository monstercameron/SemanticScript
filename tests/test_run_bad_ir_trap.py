#!/usr/bin/env python3
"""R-232: `run` maps LLVM-rejected IR to the stable SSR0001 trap, not a traceback.

jit_run's parse_assembly/verify raise RuntimeError when LLVM rejects the lowered
IR. The in-process jit branch of cmd_run (the Windows path, and the POSIX
`--_jit-child`) caught only OSError, so a RuntimeError escaped as a raw traceback
on Windows (and made the isolated child exit non-trap on POSIX, so the parent
reported a bare nonzero). cmd_run now routes it through the same _trap_report
path as an OSError guard trap: SSR0001 on stderr, exit 134, no raise.

The fix is the RuntimeError catch, so the test forces jit_run to raise (a
stand-in for an LLVM rejection) rather than fabricating verify-rejected IR.
"""
import argparse
import importlib
import os

ss = importlib.import_module("semanticscript")

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EXAMPLE = os.path.join(_REPO, "examples", "add_two.sem")


def test_run_bad_ir_traps_134_not_traceback(monkeypatch, capsys):
    def _reject(*_a, **_k):
        raise RuntimeError("instruction does not dominate all uses!")
    monkeypatch.setattr(ss, "jit_run", _reject)
    # jit_child=True forces the in-process jit branch on any platform (it is the
    # same branch Windows takes directly).
    args = argparse.Namespace(path=_EXAMPLE, json=False, strict=False,
                              entry=None, jit_child=True)
    rc = ss.cmd_run(args)               # must NOT raise
    err = capsys.readouterr().err
    assert rc == 134
    assert "SSR0001" in err
    assert "LLVM" in err                # the detail names the IR rejection
