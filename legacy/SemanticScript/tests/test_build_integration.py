"""Integration tests for the check -> build pipeline.

Round-2 DevX feedback flagged two gaps:
  * the scaffolded smoke test is a no-op (`return value 0`), so nothing exercises
    codegen, and
  * a green `sem check` did not guarantee a green `sem build` (codegen-only
    failures such as "unsupported const type" surfaced only at build).

These tests exercise the real codegen path (not just parse/lint) and assert the
check<->build verdicts agree. The codegen-level checks need no C toolchain and
run everywhere; the full native exe build+run is gated on a compiler being
available so the lane degrades gracefully.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compiler import semsc  # noqa: E402
from tools import sem  # noqa: E402

SEMSC = ROOT / "compiler" / "semsc.py"

CONSOLE_PROGRAM = "\n".join([
    "project BuildIntegration",
    "target console",
    "runtime native 1",
    "module examples.buildIntegration",
    "entry console main",
    "operation main",
    "output operation main ExitCode",
    "purpose operation main \"return a fixed exit code\"",
    "memory main heap no",
    "async main no",
    "storage local immutable exitCode ExitCode 0",
    "return value exitCode",
])

WEBSERVER_PROGRAM = "\n".join([
    "project RouteServer",
    "target webServer",
    "runtime native 1",
    "module examples.routeServer",
    "webServer routeServer",
    "serverHost routeServer \"127.0.0.1\"",
    "serverPort routeServer 8080",
    "route routeServer GET \"/health\" healthHandler",
    "routeTimeoutOptOut routeServer \"/health\" \"demo: no timeout needed\"",
    "routeMiddlewareOptOut routeServer \"/health\" \"demo: public health probe\"",
    "operation healthHandler",
    "input operation healthHandler request HttpRequest",
    "input operation healthHandler response HttpResponse",
    "output operation healthHandler Int32",
    "effect healthHandler write http.response",
    "memory healthHandler arena request",
    "async healthHandler no",
    "purpose operation healthHandler \"serve a plain-text health response\"",
    "storage local immutable healthBody String \"ok\\n\"",
    "storage local immutable okStatus Int32 200",
    "call writeHealthCall http.responseText",
    "argument writeHealthCall response HttpResponse response",
    "argument writeHealthCall status HttpStatusCode okStatus",
    "argument writeHealthCall body String healthBody",
    "run writeHealthCall",
    "bind value writeStatus Int32 writeHealthCall",
    "return value writeStatus",
])

# A program that PASSES parse/lint but used to fail only at build: an undeclared
# const type. The check-time lowerability gate now rejects it pre-codegen.
UNKNOWN_CONST_PROGRAM = "\n".join([
    "project UnknownConst",
    "target console",
    "runtime native 1",
    "module examples.unknownConst",
    "entry console main",
    "storage module immutable okStatus HttpStatus 200",
    "operation main",
    "output operation main ExitCode",
    "purpose operation main \"x\"",
    "async main no",
    "return value okStatus",
])


def _find_c_compiler() -> str | None:
    if os.environ.get("SEMSC_CLANG"):
        return os.environ["SEMSC_CLANG"]
    for name in ("clang", "zig", "gcc", "cc"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _check_payload(source_text: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "main.sem"
        path.write_text(source_text, encoding="utf-8")
        return sem._build_check_payload(path, [])


class TestCheckBuildConsistency(unittest.TestCase):
    def test_buildable_console_program_lowers_through_codegen(self) -> None:
        payload = _check_payload(CONSOLE_PROGRAM)
        self.assertTrue(payload["buildable"], payload.get("diagnostics"))
        # check said buildable -> codegen must actually succeed.
        prog = semsc.parse(CONSOLE_PROGRAM)
        semsc.Codegen(prog).compile()  # must not raise

    def test_webserver_route_table_generates_native_entry(self) -> None:
        payload = _check_payload(WEBSERVER_PROGRAM)
        self.assertTrue(payload["buildable"], payload.get("diagnostics"))
        prog = semsc.parse(WEBSERVER_PROGRAM)
        module = semsc.Codegen(prog).compile()
        ir_text = str(module)
        # The route table must synthesize the handler and a native entry.
        self.assertIn("healthHandler", ir_text)
        self.assertIn("main", ir_text)

    def test_unknown_const_type_rejected_by_both_check_and_codegen(self) -> None:
        # check must now reject it (no longer a "green check, failed build").
        payload = _check_payload(UNKNOWN_CONST_PROGRAM)
        self.assertFalse(payload["buildable"])
        codes = {d["code"] for d in payload["diagnostics"]}
        self.assertIn("SSCG004", codes)
        # codegen must reject it too (the verdicts agree).
        prog = semsc.parse(UNKNOWN_CONST_PROGRAM)
        with self.assertRaises(Exception):
            semsc.Codegen(prog).compile()


@unittest.skipIf(_find_c_compiler() is None,
                 "no C compiler (clang/zig/gcc/cc / $SEMSC_CLANG) available")
class TestNativeExeBuildAndRun(unittest.TestCase):
    def test_console_program_builds_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "main.sem"
            src.write_text(CONSOLE_PROGRAM, encoding="utf-8")
            exe = Path(tmp) / ("prog.exe" if os.name == "nt" else "prog")
            build = subprocess.run(
                [sys.executable, str(SEMSC), str(src), "--emit-exe", str(exe)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180)
            self.assertEqual(build.returncode, 0,
                             f"build failed:\n{build.stderr}")
            self.assertTrue(exe.exists(), "executable was not produced")
            run = subprocess.run([str(exe)], capture_output=True,
                                 timeout=30)
            self.assertEqual(run.returncode, 0)

    def test_sem_build_standalone_compiles_single_file(self) -> None:
        # `sem build --standalone FILE` compiles a lone source to a native exe
        # without a build.sem project — the single-file native build path the
        # field log asked for (no scaffolding a throwaway project to prove a snippet).
        sem_cli = ROOT / "tools" / "sem.py"
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "snippet.sscript"
            src.write_text(CONSOLE_PROGRAM, encoding="utf-8")
            exe = Path(tmp) / ("prog.exe" if os.name == "nt" else "prog")
            build = subprocess.run(
                [sys.executable, str(sem_cli), "build", "--standalone", str(src),
                 "--", "--emit-exe", str(exe)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=180)
            self.assertEqual(build.returncode, 0, f"standalone build failed:\n{build.stderr}")
            self.assertTrue(exe.exists(), "standalone build produced no executable")
            run = subprocess.run([str(exe)], capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 0)

    def test_sem_build_standalone_rejects_non_file(self) -> None:
        sem_cli = ROOT / "tools" / "sem.py"
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(sem_cli), "build", "--standalone", tmp],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a file", result.stderr)


if __name__ == "__main__":
    unittest.main()
