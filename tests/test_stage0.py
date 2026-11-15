"""stage0 (docs/refined-examples/stage0): a SemanticScript compiler written in SemanticScript.

stage0 reads a project (its build.sem and the modules it includes), checks that the program is in the stage0 subset,
writes it as C, and builds it with the C compiler through `process.run`, linked with the runtime of refined
executables, the runtime in SemanticScript as an object, and no C library (D-142). Each executable it builds must print what `refined run` prints for the same sample
and exit with the same code, traps included: a loop that passes its bound, a recursion that passes its maxRecursion,
a list read past its end, and a file read outside a capability's scope.

stage0 runs here as the standalone executable the session builds once (conftest.stage0_native); one test runs it
under `refined run` on a few samples and checks it writes the same C, byte for byte."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

SUITE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "suite")
sys.path.insert(0, SUITE)

import caselib  # noqa: E402
from conftest import EXE, LINK, STAGE0, c_compiler  # noqa: E402

# what each sample prints and its exit code, under `refined run` and as an executable
SAMPLES = {
    "hello": ("Hello, world!\n", 0),
    "squares": ("1\n4\n9\n16\n25\n", 0),
    "branch": ("left is smaller\ngap: -19\n", 3),
    "overrun": ("1\n2\n3\n4\n", 70),
    "calls": ("square of 7: 49\n2 to the 10: 1024\nfactorial of 10: 3628800\ngcd of 1071 and 462: 21\n", 0),
    "depth": ("1\n2\n3\n4\n", 70),
    "shapes": ("area: 9\narea: 6\narea: 0\nrefused a side of -2\ncorner: 3\n", 4),
    "lists": ("sum: 14\ncount: 5\nthird: 4\nno item at 9\nalpha\nbeta\ngamma\npoints: 3\nx total: 6\nevens: 4\n", 0),
    "outofrange": ("2\n", 70),
    "strings": ("brown\nbyte: 113\nlength: 19\nquick brown fox 42\nequal: true\nfox at 16\nno cat\nlimit: 3\n", 0),
    "buffers": ("total: 42!\nlength: 10\nparsed: 1234\nnot a number\ndigit, letter\nround trip: abc\n", 0),
    "tables": ("Mercury 0\nVenus 0\nEarth 1\nMars 2\nmoons: 3\nrows: 4\nrocky: Venus\nno row 5\n", 0),
    "maps": ("the: 3\ncat: 1\nkeys: 4\nno dog\ncounted: the cat sat mat\nAda is 36, likes tea\n"
             "Linus is 54, likes coffee\nremoved Ada: 1\nno Ada\n", 0),
    "scanner": ("word ends at 6, line 1, column 6\nnext word at 7, line 1, column 7\nline 2 starts at 14\nvowels: 5\n"
                "counts: 1 5 3\nno slot 7\nbyte after: 195\nnothing after the end\n", 0),
    "modules": ("area: 12\noblong\narea: 25\nsquare\narea: 35\noblong\napp label: app (width 3)\n"
                "shapes label: shapes\napp sides: 3\nshapes sides: 4\n", 0),
    "files": ("wrote 2 lines\nfirst line\nsecond line\n", 70),
    "boundaries": ("lessThan 1\nlessOrEqual 1\ngreaterThan 0\ngreaterOrEqual 0\nequal 0\nnotEqual 1\nlessThan 0\n"
                   "lessOrEqual 1\ngreaterThan 0\ngreaterOrEqual 1\nequal 1\nnotEqual 0\nlessThan 0\n"
                   "lessOrEqual 0\ngreaterThan 1\ngreaterOrEqual 1\nequal 0\nnotEqual 1\nbyte lessThan 1\n"
                   "byte lessOrEqual 1\nbyte greaterThan 0\nbyte greaterOrEqual 0\nbyte equal 0\nbyte notEqual 1\n"
                   "byte lessThan 0\nbyte lessOrEqual 1\nbyte greaterThan 0\nbyte greaterOrEqual 1\nbyte equal 1\n"
                   "byte notEqual 0\nbyte lessThan 0\nbyte lessOrEqual 0\nbyte greaterThan 1\n"
                   "byte greaterOrEqual 1\nbyte equal 0\nbyte notEqual 1\nand 1\nor 1\nxor 0\nnot 0\nand 0\nor 1\n"
                   "xor 1\nnot 0\nand 0\nor 1\nxor 1\nnot 1\nand 0\nor 0\nxor 0\nnot 1\ndivide -3\nremainder -1\n"
                   "subtract -9\nmultiply -14\nnegate 7\nabsolute 7\ndivide 0\nremainder 3\nsubtract 10\n"
                   "multiply -21\nnegate -3\nabsolute 3\n", 0),
    "collatz": ("steps: 0\nsteps: 1\nsteps: 7\nsteps: 2\nsteps: 5\nsteps: 8\nsteps: 16\nsteps: 3\nsteps: 19\n"
                "steps: 6\nsteps: 14\nsteps: 9\ntotal: 90\ndigits: 45\n3^5: 243\nabs: 243\n", 90),
    "divtrap": ("33\n50\n100\n", 70),
    "inventory": ("nails left: 36\ntape left: -1\nnails: 36\n  shelf 0\nscrews: 12\n  shelf 1\nglue: 1\n"
                  "  shelf 2\nglue is stocked\n", 0),
    "ledger": ("balance 50\nbalance 30\nbalance 27\noverdrawn to -73\nnegative deposit -5\nbalance 27\n"
               "balance 34\nAlice done\nrefused: 2\n", 9),
    "overflow": ("4\n16\n64\n256\n1024\n4096\n16384\n65536\n262144\n1048576\n4194304\n16777216\n67108864\n"
                 "268435456\n1073741824\n4294967296\n17179869184\n68719476736\n274877906944\n1099511627776\n"
                 "4398046511104\n17592186044416\n70368744177664\n281474976710656\n1125899906842624\n"
                 "4503599627370496\n18014398509481984\n72057594037927936\n288230376151711744\n"
                 "1152921504606846976\n4611686018427387904\n", 70),
    "words": ("words: 7\nplums-30-pears,-12-and-apples-seven-42\nbuffer: 38\napples at 23\n"
              "starts with plums\nfirst byte: 112\nequal plums-30-pears,-12-and-apples-seven-42\n", 0),
}
OUTSIDE = "samples/outside/outside.sem:12:11: this entity kind is outside the stage0 subset (alias)\n"
# programs `refined check` accepts that are just outside the subset (samples/refused), and where stage0 refuses each
REFUSED = {
    "outEnds": "outEnds.sem:67:15: this call target is outside the stage0 subset (string.endsWith)",
    "outEscape": 'outEscape.sem:33:25: stage0 does not read \\x escapes in text ("A\\x41B")',
    "outInt32": "outInt32.sem:52:16: this call target is outside the stage0 subset (convert.int64ToInt32)",
    "outIntMap": "outIntMap.sem:17:27: this type is outside the stage0 subset (Int64)",
    "outSaturating": "outSaturating.sem:52:13: this call target is outside the stage0 subset (math.saturatingAddInt64)",
    "outSet": "outSet.sem:17:20: this type is outside the stage0 subset (set.Set)",
}
# the samples stage0 also compiles under `refined run`, whose C must equal the executable's byte for byte: a
# map of records holding text, a program of two modules with records, enums, and `with`, every comparison, logic,
# and arithmetic target at its boundaries, and text split with byte tests into a buffer
UNDER_REFINED_RUN = ["maps", "modules", "boundaries", "words"]

CC = c_compiler()


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> str:
    """A copy of stage0 to run in: it writes under build/ in its working directory."""
    dst = str(tmp_path_factory.mktemp("stage0") / "stage0")
    shutil.copytree(STAGE0, dst, ignore=shutil.ignore_patterns("build"))
    return dst


def _native(stage0: str, project: str, *arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([stage0, *arguments], capture_output=True, text=True, cwd=project, timeout=600)


def _executable(folder: str, sample: str) -> str:
    return os.path.join(folder, "build", sample + EXE)


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
@pytest.mark.parametrize("sample", sorted(SAMPLES))
def test_stage0_builds_executables_that_behave_like_refined_run(stage0_native, project, sample):
    built = _native(stage0_native, project, f"samples/{sample}", f"build/{sample}", CC, *LINK)
    assert built.returncode == 0, built.stdout + built.stderr
    assert built.stdout == f"stage0: samples/{sample} -> build/{sample}.c -> build/{sample}\n"
    assert os.path.isfile(os.path.join(project, "build", f"{sample}.c"))
    reference = caselib.refined("run", os.path.join(project, "samples", sample), cwd=project)
    ran = subprocess.run([_executable(project, sample)], capture_output=True, text=True, cwd=project, timeout=60)
    assert (reference.stdout, reference.returncode) == SAMPLES[sample], reference.stderr
    assert (ran.stdout, ran.returncode) == (reference.stdout, reference.returncode), ran.stderr


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
def test_stage0_refuses_a_program_outside_its_subset(stage0_native, project):
    """A refused program is reported as `path:line:column: message (word)`, naming the module's file, with exit code
    1, and nothing is written; no arguments is a usage error, exit code 2; a project with no build.sem is exit 3."""
    proc = _native(stage0_native, project, "samples/outside", "build/outside")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout == ""
    assert proc.stderr == OUTSIDE
    assert not os.path.exists(os.path.join(project, "build", "outside.c"))
    proc = _native(stage0_native, project)
    assert proc.returncode == 2 and proc.stderr.startswith("usage: "), proc.stderr
    proc = _native(stage0_native, project, "samples/missing", "build/missing")
    assert (proc.returncode, proc.stderr) == (3, "samples/missing/build.sem: cannot read the source file\n")


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
@pytest.mark.parametrize("program", sorted(REFUSED))
def test_stage0_refuses_programs_just_outside_its_subset(stage0_native, project, program):
    """Each of these programs passes `refined check`, so the refusal is stage0's own: exit code 1, a located
    `path:line:column: message (word)`, and no C written."""
    checked = caselib.refined("check", os.path.join(project, "samples", "refused", program))
    assert checked.returncode == 0, checked.stdout + checked.stderr
    proc = _native(stage0_native, project, f"samples/refused/{program}", f"build/{program}", CC, *LINK)
    assert (proc.returncode, proc.stdout) == (1, ""), proc.stdout + proc.stderr
    assert proc.stderr == f"samples/refused/{program}/{REFUSED[program]}\n"
    assert not os.path.exists(os.path.join(project, "build", f"{program}.c"))


def test_stage0_module_tests_pass():
    """Every exported invariant of stage0's modules is verified by a test, and every test passes."""
    proc = caselib.refined("test", STAGE0, timeout=1800)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "18 of 18 tests passed" in proc.stdout


@pytest.mark.skipif(CC is None, reason="no C compiler named cc, gcc, or clang on PATH")
def test_stage0_under_refined_run_writes_the_same_c(stage0_native, project, tmp_path):
    """stage0 under `refined run` (the LLVM backend's JIT) and stage0 as a standalone executable (the native host
    library, D-80 to D-85) write the same C, byte for byte, for a representative few samples, and refuse the same
    program with the same diagnostic."""
    jit = str(tmp_path / "jit")
    shutil.copytree(STAGE0, jit, ignore=shutil.ignore_patterns("build"))
    for sample in UNDER_REFINED_RUN:
        native_c = os.path.join(project, "build", f"{sample}.c")
        if not os.path.isfile(native_c):
            assert _native(stage0_native, project, f"samples/{sample}", f"build/{sample}", CC, *LINK).returncode == 0
        proc = caselib.refined("run", jit, "--", f"samples/{sample}", f"build/{sample}", CC, *LINK, cwd=jit,
                               timeout=1800)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert proc.stdout == f"stage0: samples/{sample} -> build/{sample}.c -> build/{sample}\n"
        with open(native_c, "rb") as a, open(os.path.join(jit, "build", f"{sample}.c"), "rb") as b:
            assert a.read() == b.read(), sample
        ran = subprocess.run([_executable(jit, sample)], capture_output=True, text=True, cwd=jit, timeout=60)
        assert (ran.stdout, ran.returncode) == SAMPLES[sample], ran.stderr
    proc = caselib.refined("run", jit, "--", "samples/outside", "build/outside", cwd=jit, timeout=1800)
    assert (proc.returncode, proc.stderr) == (1, OUTSIDE)
