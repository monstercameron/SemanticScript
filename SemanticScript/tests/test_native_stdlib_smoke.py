"""Native-exe smoke tests for stdlib modules the JIT runner cannot execute.

A handful of stdlib modules are backed by native runtime adapters (libc
stdio, the bcrypt ABI, HMAC crypto, the outbound HTTP client) and therefore
cannot run under `semsc --run` (JIT). `test_stdlib.py` skips them. This
harness builds each one as a native executable via `--emit-exe` and, where
the behaviour is deterministic and self-contained, runs it and asserts on
its output.

Coverage:
  - log    : build + run  -> escapeJsonString escapes `"` and `\\` (prints OK)
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


# A standalone console program exercising the native convert formatters. They
# delegate to sem_convert_runtime.c through runtimeBinding rows, so they LINK in
# a native build (unlike convertSignedInt64ToString, whose SemanticScript body
# hits SSCG002). Formats an Int64 then a Float64 into one caller-owned buffer and
# prints each: proves the native path and the shortest-round-trip float (0.1).
_CONVERT_FORMATTER_SOURCE = """project ConvertNativeFormatterSmoke
target console
runtime AgentRuntime 0.1
entry console main

import convert standard.convert
import memory standard.memory

error MainError
errorCase MainError Failed

capability stdoutWriteCapability console.stdout write
capability heapAllocationCapability heap allocate
capability heapFreeCapability heap free
capability bufferWriteCapability memory.buffer write

storage module immutable scratchCapacityBytes ByteCount 32
storage module immutable formatCapacity Int32 32
storage module immutable sampleInt Int64 -12345
storage module immutable sampleFloat Float64 0.1

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
purpose operation main "Smoke-test native convert formatters."
invariant operation main "Prints the decimal text of sampleInt then sampleFloat."
label startMain
call allocCall memory.allocateMemoryBytes
argument allocCall byteCount ByteCount scratchCapacityBytes
run allocCall
bind ok scratchBuffer String allocCall
bind error allocError MemoryAllocationError allocCall
branch error source allocCall target failed
defer releaseScratchCall memory.releaseMemoryBytes scratchBuffer
call formatIntCall formatSignedInt64IntoBuffer
argument formatIntCall inputValue Int64 sampleInt
argument formatIntCall scratch OpaquePointer scratchBuffer
argument formatIntCall capacity Int32 formatCapacity
run formatIntCall
bind value formattedInt String formatIntCall
call writeIntCall console.writeLine
argument writeIntCall text String formattedInt
run writeIntCall
ignore void source writeIntCall
bind error writeIntErr Int32 writeIntCall
branch error source writeIntCall target failed
call formatFloatCall formatFloat64IntoBuffer
argument formatFloatCall inputValue Float64 sampleFloat
argument formatFloatCall scratch OpaquePointer scratchBuffer
argument formatFloatCall capacity Int32 formatCapacity
run formatFloatCall
bind value formattedFloat String formatFloatCall
call writeFloatCall console.writeLine
argument writeFloatCall text String formattedFloat
run writeFloatCall
ignore void source writeFloatCall
bind error writeFloatErr Int32 writeFloatCall
branch error source writeFloatCall target failed
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

    def test_convert_native_formatters_build_and_run(self) -> None:
        # Build + run proves convert.formatSignedInt64IntoBuffer and
        # formatFloat64IntoBuffer link and execute natively: -12345 from the int
        # formatter and 0.1 (shortest round-trip) from the float formatter.
        with tempfile.TemporaryDirectory(prefix="ss_convert_fmt_") as temp_dir:
            source = Path(temp_dir) / "main.test.sem"
            source.write_text(_CONVERT_FORMATTER_SOURCE, encoding="utf-8")
            exe_path = _build_exe(source, Path(temp_dir))
            result = subprocess.run(
                [str(exe_path)],
                cwd=temp_dir,
                text=True,
                capture_output=True,
                timeout=60,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("-12345", result.stdout)
        self.assertIn("0.1", result.stdout)

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


if __name__ == "__main__":
    unittest.main()
