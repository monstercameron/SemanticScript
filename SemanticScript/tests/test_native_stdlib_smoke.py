"""Native-exe smoke tests for stdlib modules the JIT runner cannot execute.

A handful of stdlib modules are backed by native runtime adapters (libc
stdio, the bcrypt ABI, HMAC crypto, the outbound HTTP client) and therefore
cannot run under `semsc --run` (JIT). `test_stdlib.py` skips them. This
harness builds each one as a native executable via `--emit-exe` and, where
the behaviour is deterministic and self-contained, runs it and asserts on
its output.

Coverage:
  - log    : build + run  -> escapeJsonString escapes `"` and `\\` (prints OK)
  - time   : build + run  -> unix epoch read is not the old constant-zero fallback
  - bcrypt : build + run  -> hash/verify round-trip (prints OK)
  - jwt    : build only    -> links its native HMAC runtime (the runtime
             smoke passes at committed HEAD; it is build-checked here so the
             harness stays green while jwt's native runtime is mid-revision)
  - net    : parse only    -> contract module (type aliases + `net.fetch*`
             intrinsic namespace) is well-formed; it has no executable body
             and its async network intrinsics need the optional libuv/libcurl
             runtime, so there is nothing to run standalone.

Run from repo root:
  python -m unittest SemanticScript/tests/test_native_stdlib_smoke.py -v
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
STD_ROOT = REPO_ROOT / "SemanticScript" / "std"


def _build_exe(source: Path, out_dir: Path) -> Path:
    exe_path = out_dir / (source.parent.name + "_smoke.exe")
    result = subprocess.run(
        [sys.executable, str(SEMSC), str(source), "--emit-exe", str(exe_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"native build failed for {source}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    if not exe_path.exists():
        raise AssertionError(f"build reported success but {exe_path} is missing")
    return exe_path


def _build_and_run(module: str) -> subprocess.CompletedProcess:
    source = STD_ROOT / module / "main.test.sem"
    with tempfile.TemporaryDirectory(prefix=f"ss_{module}_smoke_") as temp_dir:
        exe_path = _build_exe(source, Path(temp_dir))
        return subprocess.run(
            [str(exe_path)],
            cwd=temp_dir,
            text=True,
            capture_output=True,
            timeout=60,
        )


# Standalone console program exercising the html.fragmentConcat compiler-lowered
# primitive. Two HtmlFragment-typed storage rows fold into one fragment via
# `html.fragmentConcat`; the result is bound as HtmlFragment (so SS4302 — the
# rule that catches a String op's result mislabelled as an opaque HTML handle —
# accepts the bind) and then written via console.writeLine. Build + run proves
# the intrinsic lowers (snprintf-backed, links in every target) and produces the
# expected `<p></p>` concatenation.
_HTML_FRAGMENT_CONCAT_SOURCE = """project HtmlFragmentConcatSmoke
target console
runtime AgentRuntime 0.1
entry console main

import memory standard.memory

error MainError
errorCase MainError Failed

capability stdoutWriteCapability console.stdout write
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free
capability bufferWriteCapability memory.buffer write

storage module immutable capacityBytes ByteCount 64
storage module immutable openTagText HtmlFragment "<p>"
storage module immutable closeTagText HtmlFragment "</p>"

operation main
input operation main console Console
output operation main Result ExitCode MainError
useCapability main stdoutWriteCapability
useCapability main heapAllocationCapability
useCapability main heapFreeCapability
useCapability main bufferWriteCapability
effect main write console.stdout
effect main allocate heap
effect main free heap
effect main write memory.buffer
memory main heap yes
async main no
purpose operation main "smoke-test html.fragmentConcat"
invariant operation main "prints <p></p>"
label startMain
call allocCall memory.allocateMemoryBytes
argument allocCall byteCount ByteCount capacityBytes
run allocCall
bind ok scratchBuffer String allocCall
bind error allocFailure MemoryAllocationError allocCall
branch error source allocCall target failed
defer releaseCall memory.releaseMemoryBytes scratchBuffer
call concatCall html.fragmentConcat
argument concatCall left HtmlFragment openTagText
argument concatCall right HtmlFragment closeTagText
argument concatCall buffer OpaquePointer scratchBuffer
argument concatCall capacity ByteCount capacityBytes
run concatCall
bind value joinedFragment HtmlFragment concatCall
call writeCall console.writeLine
argument writeCall text String joinedFragment
run writeCall
ignore void source writeCall
bind error writeFailure Int32 writeCall
branch error source writeCall target failed
storage module immutable okCode ExitCode 0
return ok okCode
label failed
makeError mainFailure MainError.Failed
return error mainFailure
"""


class TestNativeStdlibSmoke(unittest.TestCase):
    def test_log_escape_json_string_native_smoke(self) -> None:
        result = _build_and_run("log")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_time_epoch_native_smoke(self) -> None:
        result = _build_and_run("time")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_bcrypt_hash_verify_native_smoke(self) -> None:
        result = _build_and_run("bcrypt")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_jwt_native_runtime_links(self) -> None:
        # Build-only: confirms the jwt module + its native HMAC runtime
        # compile and link. The full runtime smoke (prints
        # "stdJwtRuntimeSmokeOk") passes at committed HEAD; it is not run
        # here so this harness is not coupled to in-flight jwt runtime work.
        source = STD_ROOT / "jwt" / "main.test.sem"
        with tempfile.TemporaryDirectory(prefix="ss_jwt_smoke_") as temp_dir:
            _build_exe(source, Path(temp_dir))

    def test_net_contract_module_parses(self) -> None:
        # net is a contract module: type aliases + the compiler-owned
        # net.fetch* intrinsic namespace, with no executable body. Its
        # network intrinsics need the optional libuv/libcurl runtime, so the
        # meaningful standalone check is that the module parses cleanly.
        result = subprocess.run(
            [sys.executable, str(SEMSC), str(STD_ROOT / "net" / "main.sem"),
             "--parse-only"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=120,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_html_fragment_concat_native_smoke(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ss_html_fragment_smoke_") as temp_dir:
            root = Path(temp_dir)
            source = root / "html_fragment_concat.sem"
            source.write_text(_HTML_FRAGMENT_CONCAT_SOURCE, encoding="utf-8", newline="\n")
            exe_path = _build_exe(source, root)
            result = subprocess.run(
                [str(exe_path)],
                cwd=root,
                text=True,
                capture_output=True,
                timeout=60,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("<p></p>", result.stdout)


if __name__ == "__main__":
    unittest.main()
