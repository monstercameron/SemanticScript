"""Tests for the `sem eval` JIT eval surface (sem.eval.v1).

These exercise the full wrap -> compile -> JIT-run -> capture path through the
real compiler, so they assert on observable program output, execution metrics,
and diagnostic remapping rather than on a mocked lowering.
"""

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from SemanticScript.tools import sem

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC_PATH = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
HELLO_WORLD_PATH = REPO_ROOT / "SemanticScript" / "sem" / "hello_world.sem"

PRINT_SNIPPET = (
    'storage local immutable greeting String "hi from eval"\n'
    "call printCall console.writeLine\n"
    "argument printCall text String greeting\n"
    "run printCall\n"
)

INTEGER_SNIPPET = (
    "storage local immutable answer Int64 42\n"
    "call printCall console.writeIntegerLine\n"
    "argument printCall value Int64 answer\n"
    "run printCall\n"
)

NONZERO_EXIT_SNIPPET = (
    "storage local immutable code ExitCode 7\n"
    "return value code\n"
)


def _eval(text: str, **kwargs) -> dict:
    params = dict(max_output_bytes=sem.EVAL_DEFAULT_MAX_OUTPUT_BYTES,
                  timeout=sem.EVAL_DEFAULT_TIMEOUT_SECONDS,
                  show_source=False)
    params.update(kwargs)
    return sem._eval_payload(text, **params)


class EvalSnippetTests(unittest.TestCase):
    def test_print_snippet_captures_stdout_and_metrics(self) -> None:
        payload = _eval(PRINT_SNIPPET)

        self.assertEqual(payload["schemaVersion"], "sem.eval.v1")
        self.assertEqual(payload["mode"], "snippet")
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["ok"])

        output = payload["output"]
        self.assertEqual(output["stdout"], "hi from eval\n")
        self.assertEqual(output["stdoutLines"], ["hi from eval"])
        self.assertFalse(output["truncated"])
        # The metrics sentinel must never leak into captured streams.
        self.assertNotIn("__SEM_RUN_METRICS__", output["stdout"])
        self.assertNotIn("__SEM_RUN_METRICS__", output["stderr"])

        execution = payload["execution"]
        self.assertTrue(execution["ran"])
        self.assertEqual(execution["exitCode"], 0)
        self.assertIsInstance(execution["timing"]["executeNs"], int)
        self.assertGreater(execution["timing"]["executeNs"], 0)
        self.assertEqual(execution["timing"]["executeUs"],
                         round(execution["timing"]["executeNs"] / 1000, 3))
        self.assertGreaterEqual(execution["timing"]["totalNs"],
                                execution["timing"]["executeNs"])

        memory = execution["memory"]
        self.assertIn(memory["source"],
                      {"GetProcessMemoryInfo", "getrusage", "unavailable"})
        if memory["source"] != "unavailable":
            self.assertIsInstance(memory["peakWorkingSetBytes"], int)
            self.assertGreater(memory["peakWorkingSetBytes"], 0)
            self.assertEqual(memory["peakWorkingSetKib"],
                             round(memory["peakWorkingSetBytes"] / 1024))

    def test_integer_line_snippet(self) -> None:
        payload = _eval(INTEGER_SNIPPET)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["output"]["stdout"], "42\n")
        self.assertEqual(payload["output"]["stdoutLines"], ["42"])

    def test_intentional_nonzero_exit_is_not_a_harness_failure(self) -> None:
        payload = _eval(NONZERO_EXIT_SNIPPET)
        # The program chose exit 7; the eval harness still succeeded.
        self.assertEqual(payload["status"], "nonzero-exit")
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["execution"]["ran"])
        self.assertEqual(payload["execution"]["exitCode"], 7)

    def test_compile_blocking_input_does_not_run(self) -> None:
        payload = _eval("this is not valid semanticscript\n")
        self.assertEqual(payload["status"], "compile-failed")
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["execution"]["ran"])
        self.assertIsNone(payload["execution"]["exitCode"])
        self.assertTrue(payload["diagnostics"])

    def test_native_runtime_intrinsics_are_refused_before_jit_run(self) -> None:
        payload = _eval(
            'storage local immutable dbPath String "demo.db"\n'
            "storage local immutable mode Int32 6\n"
            "call openDatabaseCall sqlite.openDatabase\n"
            "argument openDatabaseCall path String dbPath\n"
            "argument openDatabaseCall mode Int32 mode\n"
            "run openDatabaseCall\n"
        )
        self.assertEqual(payload["status"], "native-runtime-unavailable")
        self.assertFalse(payload["ok"])
        self.assertFalse(payload["execution"]["ran"])
        self.assertIn("sqlite.openDatabase", payload["nativeRuntimeTargets"])
        self.assertTrue(any(note["code"] == "SSEVAL002" for note in payload["notes"]["linter"]))

    def test_full_program_is_passed_through(self) -> None:
        source = HELLO_WORLD_PATH.read_text(encoding="utf-8")
        payload = _eval(source)
        self.assertEqual(payload["mode"], "program")
        self.assertEqual(payload["lineOffset"], 0)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("Hello, world!", payload["output"]["stdout"])

    def test_diagnostics_are_remapped_to_snippet_lines(self) -> None:
        # An un-disposed fallible console.writeLine raises SS3106 on the `call`
        # row, which is snippet line 2 here.
        payload = _eval(PRINT_SNIPPET)
        ss3106 = [d for d in payload["diagnostics"] if d.get("code") == "SS3106"]
        self.assertTrue(ss3106, "expected an SS3106 advisory for the fallible call")
        span = ss3106[0]["span"]
        self.assertIn("wrappedLine", span)
        self.assertIn("snippetLine", span)
        self.assertEqual(span["snippetLine"], 2)
        self.assertGreater(span["wrappedLine"], span["snippetLine"])

    def test_module_declaration_is_hoisted(self) -> None:
        snippet = (
            'storage module immutable bannerText String "hoisted"\n'
            "call printCall console.writeLine\n"
            "argument printCall text String bannerText\n"
            "run printCall\n"
        )
        payload = _eval(snippet, show_source=True)
        wrapped = payload["wrappedSource"]
        # The module-level storage must land before `operation main`.
        self.assertLess(wrapped.index("storage module immutable bannerText"),
                        wrapped.index("operation main"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["output"]["stdout"], "hoisted\n")

    def test_notes_are_split_by_origin(self) -> None:
        payload = _eval(PRINT_SNIPPET)
        self.assertIn("notes", payload)
        self.assertIn("linter", payload["notes"])
        self.assertIn("compiler", payload["notes"])
        # Every note in a group carries the matching source.
        self.assertTrue(all(n.get("source") == "linter"
                            for n in payload["notes"]["linter"]))
        self.assertTrue(all(n.get("source") == "compiler"
                            for n in payload["notes"]["compiler"]))
        # The split partitions the merged diagnostics stream exactly.
        self.assertEqual(
            len(payload["notes"]["linter"]) + len(payload["notes"]["compiler"]),
            len([d for d in payload["diagnostics"]
                 if d.get("source") in {"linter", "compiler"}]))

    def test_nonstrict_run_executes_despite_blocking_notes(self) -> None:
        # hello_world.sem trips strict-blocking linter notes (deprecated rows)
        # that the backend tolerates. Non-strict eval must still run it and
        # surface the notes rather than refusing to execute.
        source = HELLO_WORLD_PATH.read_text(encoding="utf-8")
        payload = _eval(source)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["execution"]["ran"])
        self.assertIn("Hello, world!", payload["output"]["stdout"])
        blocking = [n for n in payload["notes"]["linter"] if n.get("blocksCompile")]
        self.assertTrue(blocking, "expected strict-blocking linter notes to be surfaced")

    def test_output_is_capped(self) -> None:
        # Print a line, but cap the byte budget below its length.
        payload = _eval(PRINT_SNIPPET, max_output_bytes=4)
        self.assertTrue(payload["output"]["truncated"])
        self.assertLessEqual(len(payload["output"]["stdout"].encode("utf-8")), 4)
        # byteCount reports the true (pre-cap) size.
        self.assertGreater(payload["output"]["byteCount"], 4)

    def test_multibyte_output_is_capped_on_a_character_boundary(self) -> None:
        # "é" is two UTF-8 bytes; a 3-byte cap must not split it.
        snippet = (
            'storage local immutable s String "ééé"\n'
            "call printCall console.writeLine\n"
            "argument printCall text String s\n"
            "run printCall\n"
        )
        payload = _eval(snippet, max_output_bytes=3)
        self.assertTrue(payload["output"]["truncated"])
        # Whatever survived must be valid UTF-8 (no broken trailing byte).
        payload["output"]["stdout"].encode("utf-8")
        self.assertLessEqual(len(payload["output"]["stdout"].encode("utf-8")), 3)

    def test_runtime_crash_is_classified(self) -> None:
        # A dynamically-computed zero divisor traps at runtime (not statically),
        # so the program launches but never returns: status "crashed".
        snippet = (
            "storage local immutable a Int64 10\n"
            "call sub math.subtractInt64\n"
            "argument sub left Int64 a\n"
            "argument sub right Int64 a\n"
            "run sub\n"
            "bind value z Int64 sub\n"
            "call d math.divideInt64\n"
            "argument d left Int64 a\n"
            "argument d right Int64 z\n"
            "run d\n"
            "bind value q Int64 d\n"
        )
        payload = _eval(snippet)
        self.assertEqual(payload["status"], "crashed")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["execution"]["ran"])

    def test_library_mode_full_program_is_flagged(self) -> None:
        # An `operation` with no `entry`: full-program mode, library compile,
        # stub main returns 0. Must not be a silent empty success.
        program = (
            "operation helper\n"
            "output operation helper Int64\n"
            "storage local immutable v Int64 5\n"
            "return value v\n"
        )
        payload = _eval(program)
        self.assertEqual(payload["mode"], "program")
        self.assertTrue(payload["libraryMode"])
        self.assertEqual(payload["status"], "ok")
        codes = [n["code"] for n in payload["notes"]["linter"]]
        self.assertIn("SSEVAL001", codes)
        self.assertTrue(payload["nextCommands"])

    def test_compile_failed_has_next_commands(self) -> None:
        payload = _eval("this is not valid semanticscript\n")
        self.assertEqual(payload["status"], "compile-failed")
        intents = " ".join(c.get("command", "") for c in payload["nextCommands"])
        self.assertIn("sem check", intents)
        # nextCommands must follow the repo-wide shape: kind/reason/command and
        # an always-present replayable bool.
        for entry in payload["nextCommands"]:
            self.assertIn("kind", entry)
            self.assertIn("reason", entry)
            self.assertIn("command", entry)
            self.assertIsInstance(entry["replayable"], bool)


class RuntimeEntrypointDetectionTests(unittest.TestCase):
    """Library-mode detection must mirror the compiler's entrypoint decision."""

    def test_operation_without_entry_is_library_mode(self) -> None:
        self.assertFalse(sem._program_has_runtime_entrypoint(
            "operation helper\noutput operation helper Int64\n"))

    def test_explicit_entry_is_an_entrypoint(self) -> None:
        self.assertTrue(sem._program_has_runtime_entrypoint(
            "project P\ntarget console\nentry console main\noperation main\n"))

    def test_routed_webserver_is_an_entrypoint(self) -> None:
        # A route emits a native HTTP entrypoint, so it is NOT library mode even
        # without an `entry` row — mirroring the compiler, which keys on routes
        # independent of the `target` row (here `target console`).
        self.assertTrue(sem._program_has_runtime_entrypoint(
            "project P\ntarget console\nroute get / homeHandler\n"))

    def test_webserver_without_route_is_library_mode(self) -> None:
        self.assertFalse(sem._program_has_runtime_entrypoint(
            "project P\ntarget webServer\noperation helper\n"))


class ExtractRunMetricsTests(unittest.TestCase):
    def test_matching_nonce_is_accepted_and_stripped(self) -> None:
        stderr = ('program line\n'
                  '__SEM_RUN_METRICS__ {"executeNs": 99, "nonce": "good"}\n')
        metrics, remaining = sem._extract_run_metrics(stderr, "good")
        self.assertEqual(metrics["executeNs"], 99)
        self.assertNotIn("__SEM_RUN_METRICS__", remaining)
        self.assertIn("program line", remaining)

    def test_spoofed_nonce_is_rejected_and_preserved(self) -> None:
        # A program writing a look-alike line cannot forge completion metrics;
        # the unauthenticated line stays in the reported stream as its output.
        stderr = '__SEM_RUN_METRICS__ {"executeNs": 5, "nonce": "bad"}\n'
        metrics, remaining = sem._extract_run_metrics(stderr, "good")
        self.assertIsNone(metrics)
        self.assertIn("__SEM_RUN_METRICS__", remaining)

    def test_last_genuine_sentinel_wins(self) -> None:
        stderr = ('__SEM_RUN_METRICS__ {"executeNs": 1, "nonce": "good"}\n'
                  '__SEM_RUN_METRICS__ {"executeNs": 2, "nonce": "good"}\n')
        metrics, _ = sem._extract_run_metrics(stderr, "good")
        self.assertEqual(metrics["executeNs"], 2)


class EvalCommandTests(unittest.TestCase):
    def _run_command(self, **kwargs) -> tuple[int, dict | None, str]:
        import argparse
        ns = argparse.Namespace(
            path=kwargs.get("path"),
            code=kwargs.get("code"),
            human=kwargs.get("human", False),
            show_source=kwargs.get("show_source", False),
            max_output_bytes=kwargs.get("max_output_bytes",
                                        sem.EVAL_DEFAULT_MAX_OUTPUT_BYTES),
            timeout=kwargs.get("timeout", sem.EVAL_DEFAULT_TIMEOUT_SECONDS),
            json=kwargs.get("json", False),
        )
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            rc = sem.command_eval(ns)
        stdout = out.getvalue()
        try:
            payload = json.loads(stdout) if stdout.strip() else None
        except json.JSONDecodeError:
            payload = None
        return rc, payload, err.getvalue()

    def test_json_is_default_output(self) -> None:
        rc, payload, _ = self._run_command(code=PRINT_SNIPPET)
        self.assertEqual(rc, 0)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["schemaVersion"], "sem.eval.v1")

    def test_human_mode_emits_program_output(self) -> None:
        rc, payload, stderr = self._run_command(code=PRINT_SNIPPET, human=True)
        self.assertEqual(rc, 0)
        self.assertIsNone(payload)  # human mode is not JSON
        self.assertIn("[ok]", stderr)

    def test_compile_failure_returns_nonzero(self) -> None:
        rc, payload, _ = self._run_command(code="not valid\n")
        self.assertEqual(rc, 1)
        self.assertEqual(payload["status"], "compile-failed")

    def test_missing_file_is_input_error(self) -> None:
        rc, payload, _ = self._run_command(path="does-not-exist.sem")
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "input-error")

    def test_nonpositive_timeout_is_rejected(self) -> None:
        rc, payload, _ = self._run_command(code=PRINT_SNIPPET, timeout=0)
        self.assertEqual(rc, 2)
        self.assertEqual(payload["status"], "input-error")

    def test_timeout_status_when_run_exceeds_budget(self) -> None:
        # Simulate a run that never finishes within the wall-clock bound.
        with mock.patch.object(
                sem, "_capture_compiler",
                side_effect=subprocess.TimeoutExpired(cmd="semsc", timeout=1)):
            payload = sem._eval_payload(
                PRINT_SNIPPET, max_output_bytes=65536, timeout=1,
                show_source=False)
        self.assertEqual(payload["status"], "timeout")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["execution"]["timeoutSeconds"], 1)
        self.assertTrue(payload["nextCommands"])


class RunMetricsFlagTests(unittest.TestCase):
    """The compiler's `--run-metrics` flag is the source of execution metrics."""

    def test_metrics_sentinel_is_emitted_on_stderr(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SEMSC_PATH), str(HELLO_WORLD_PATH),
             "--run", "--run-metrics", "--quiet", "--persist-llvm-ir", "no"],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0)
        # Program output stays on stdout, clean of the sentinel.
        self.assertIn("Hello, world!", proc.stdout)
        self.assertNotIn("__SEM_RUN_METRICS__", proc.stdout)
        sentinel_lines = [ln for ln in proc.stderr.splitlines()
                          if ln.startswith("__SEM_RUN_METRICS__ ")]
        self.assertEqual(len(sentinel_lines), 1)
        metrics = json.loads(sentinel_lines[0][len("__SEM_RUN_METRICS__ "):])
        self.assertIsInstance(metrics["executeNs"], int)
        self.assertGreater(metrics["executeNs"], 0)
        self.assertEqual(metrics["exitCode"], 0)
        self.assertIn(metrics["memorySource"],
                      {"GetProcessMemoryInfo", "getrusage", "unavailable"})

    def test_peak_working_set_helper(self) -> None:
        from SemanticScript.compiler import semsc
        peak, source = semsc._peak_working_set_bytes()
        self.assertIn(source, {"GetProcessMemoryInfo", "getrusage", "unavailable"})
        if source != "unavailable":
            self.assertIsInstance(peak, int)
            self.assertGreater(peak, 0)


if __name__ == "__main__":
    unittest.main()
