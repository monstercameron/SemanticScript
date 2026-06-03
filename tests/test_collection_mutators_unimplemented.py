#!/usr/bin/env python3
"""Tripwire: collection mutators that lint accepts but the runtime silently drops.

Six collection intrinsics — list.set, list.insert, list.remove, list.clear,
map.remove, map.clear — appear in the iteration-invalidation mutator set
(semanticscript.py `_COLLECTION_MUTATORS`) so a program that calls them passes
`check` clean. But none of them is in its module's `.semsig` and none is lowered,
so at runtime they are NO-OPS: a `map.remove` leaves the entry in place, a
`map.clear` leaves the map full. The program looks green up to the point an
assertion actually observes the (non-)mutation. This is the DX-11 species —
silently wrong with no diagnostic — applied to collections.

The test below encodes the CORRECT behavior (remove drops the size by one) and is
marked xfail: today it fails because remove no-ops, so the suite stays green. When
the runtime gains a real `map.remove` (or a `check`-time SS#### diagnostic rejects
the unimplemented intrinsic), this XPASSes / changes shape and flags that the mark
should be removed and the example promoted into the corpus.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__

# minimal: two puts -> size 2, remove one -> size SHOULD be 1.
_PROGRAM = """\
P is project
P module m
P target console
P entry main
m is module
m path a.b
m exports main
m purpose "p"
m invariant "i"
ExitCode is alias
ExitCode for Int32
MapHandle is alias
MapHandle for OpaquePointer
stdoutWriter is capability
stdoutWriter grants write console.stdout
main is operation
main out ExitCode
main effect write console.stdout
main uses stdoutWriter
main async no
main purpose "remove one of two keys; size should be 1"
main invariant "i"
main let kA immutable String "a"
main let kB immutable String "b"
main let v1 immutable Int64 1
main let v2 immutable Int64 2
main let one immutable Int64 1
main let nm immutable String "size is 1 after removing one of two keys"
main do mk
main do putA
main do putB
main do rm
main do sz
main do chk
main do rep
main return code
mk is call
mk in main
mk invokes map.create
mk out theMap MapHandle
putA is call
putA in main
putA invokes map.put
putA arg map MapHandle theMap
putA arg key String kA
putA arg value Int64 v1
putB is call
putB in main
putB invokes map.put
putB arg map MapHandle theMap
putB arg key String kB
putB arg value Int64 v2
rm is call
rm in main
rm invokes map.remove
rm arg map MapHandle theMap
rm arg key String kA
sz is call
sz in main
sz invokes map.size
sz arg map MapHandle theMap
sz out mapSize Int64
chk is call
chk in main
chk invokes test.assertEqualInt64
chk arg name String nm
chk arg expected Int64 one
chk arg actual Int64 mapSize
rep is call
rep in main
rep invokes test.summary
rep out code ExitCode
"""


def test_map_remove_decrements_size_checks_clean(tmp_path):
    # the gap is specifically that this CHECKS clean — lint does not warn that
    # map.remove will no-op. That clean check is the trap.
    p = tmp_path / "rm.sem"
    p.write_text(_PROGRAM, encoding="utf-8")
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "check", str(p), "--json"],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode in (0, 0), proc.stderr
    assert '"status"' in proc.stdout


@pytest.mark.xfail(reason="map.remove has no runtime lowering — silently no-ops; "
                          "implement it (or emit a check-time diagnostic) then "
                          "drop this mark and promote to a corpus example",
                   strict=False)
def test_map_remove_actually_removes(tmp_path):
    p = tmp_path / "rm.sem"
    p.write_text(_PROGRAM, encoding="utf-8")
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", str(p)],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    # CORRECT behavior: removing one of two keys leaves size 1, all green.
    assert "PASS" in proc.stdout and "FAIL" not in proc.stdout, proc.stdout
    assert "1 passed, 0 failed" in proc.stdout, proc.stdout
