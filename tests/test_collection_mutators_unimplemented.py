#!/usr/bin/env python3
"""R-061 guard: unimplemented collection mutators fail closed.

The runnable collection surface is list.create/append/length/get/release and
map.create/put/get/size/release. Mutator names kept for iterator-invalidation
analysis (list.set/insert/remove/clear and map.remove/clear) must not pass
`check` as runnable no-ops. They currently have no modeled signature, so SS1198
rejects them before lowering. If a real mutator implementation lands later, this
test should be replaced by a corpus example that proves the mutation behavior.
"""
import importlib
import subprocess
import sys

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__


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
putA discards "put status ignored in mutator probe"
putB is call
putB in main
putB invokes map.put
putB arg map MapHandle theMap
putB arg key String kB
putB arg value Int64 v2
putB discards "put status ignored in mutator probe"
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


def test_map_remove_unimplemented_intrinsic_rejected_at_check(tmp_path):
    p = tmp_path / "rm.sem"
    p.write_text(_PROGRAM, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, SEMANTICSCRIPT, "check", str(p), "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode != 0
    assert '"SS1198"' in proc.stdout
    assert "map.remove" in proc.stdout
