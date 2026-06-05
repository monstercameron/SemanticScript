from __future__ import annotations

import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPILER = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
LINTER_DIR = REPO_ROOT / "SemanticScript" / "linter"

if str(LINTER_DIR) not in sys.path:
    sys.path.insert(0, str(LINTER_DIR))

import semlint  # noqa: E402


def _emit_ir(source: str, extra_args: list[str] | None = None) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "main.sem"
        ir_path = Path(tmpdir) / "main.ll"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(source_path),
                *(extra_args or []),
                "--emit-ir",
                str(ir_path),
                "--quiet",
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise AssertionError(
                f"compiler failed with {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )
        return ir_path.read_text(encoding="utf-8")


def _lint_source(source: str) -> list[semlint.Diagnostic]:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "main.sem"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        return semlint.lint_path(source_path)


def _diagnostic_codes(source: str) -> list[str]:
    return [diagnostic.code for diagnostic in _lint_source(source)]


def _diagnostic_kinds(source: str) -> list[str]:
    return [diagnostic.kind for diagnostic in _lint_source(source)]


def _assert_fails_with(test: unittest.TestCase, source: str, expected: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "main.sem"
        ir_path = Path(tmpdir) / "main.ll"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(source_path),
                "--emit-ir",
                str(ir_path),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )
    output = proc.stdout + proc.stderr
    test.assertNotEqual(proc.returncode, 0, output)
    test.assertIn(expected, output)


def _assert_strict_fails_with(test: unittest.TestCase, source: str, expected: str) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "main.sem"
        ir_path = Path(tmpdir) / "main.ll"
        source_path.write_text(source, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(COMPILER),
                str(source_path),
                "--strict",
                "--emit-ir",
                str(ir_path),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=60,
        )
    output = proc.stdout + proc.stderr
    test.assertNotEqual(proc.returncode, 0, output)
    test.assertIn(expected, output)


def _user_operation_wait_set_source(
    call_names: Iterable[str],
    *,
    wait_name: str = "nextResult",
    main_async: bool = True,
    include_done: bool = True,
    duplicate_first_case: bool = False,
    start_all: bool = True,
    start_after_wait_set: bool = False,
    unsupported_case: bool = False,
    unknown_case: bool = False,
    done_without_case: bool = False,
    orphan_case: bool = False,
    orphan_done: bool = False,
    two_wait_sets_same_name: bool = False,
    missing_case_label: bool = False,
    missing_done_label: bool = False,
    extra_await_arg: bool = False,
    extra_case_arg: bool = False,
    extra_done_arg: bool = False,
    handler_await: bool = False,
) -> str:
    calls = list(call_names)
    storage_lines = [
        "storage module immutable successfulExitCode ExitCode 0",
        "storage module immutable failedExitCode ExitCode 1",
        "storage module immutable one Int64 1",
        "storage module immutable two Int64 2",
        "storage module immutable three Int64 3",
        "storage module immutable cancellationToken OpaquePointer 0",
    ]
    for index, _call_name in enumerate(calls, start=10):
        storage_lines.append(f"storage module immutable value{index} Int64 {index}")

    lines = [
        "project AsyncWaitSetUserOps",
        "target console",
        "runtime AgentRuntime 1.0",
        "entry console main",
        "import math standard.math",
        "",
        *storage_lines,
        "",
        "operation addPair",
        "input operation addPair left Int64",
        "input operation addPair right Int64",
        "output operation addPair Int64",
        "memory addPair heap no",
        "async addPair no",
        "purpose operation addPair \"Return the sum of two integers.\"",
        "call addCall math.addInt64",
        "argument addCall left Int64 left",
        "argument addCall right Int64 right",
        "run addCall",
        "bind value sum Int64 addCall",
        "return value sum",
        "",
        "operation main",
        "input operation main console Console",
        "output operation main ExitCode",
        "memory main heap no",
        f"async main {'yes' if main_async else 'no'}",
        "purpose operation main \"Exercise await wait-set lowering.\"",
        "label startMain",
    ]
    for index, call_name in enumerate(calls, start=10):
        target = "console.writeLine" if unsupported_case and index == 10 else "addPair"
        lines.extend([
            f"call {call_name} {target}",
        ])
        if target == "addPair":
            lines.extend([
                f"argument {call_name} left Int64 value{index}",
                f"argument {call_name} right Int64 one",
            ])
        else:
            lines.extend([
                f"argument {call_name} console Console console",
                f"argument {call_name} text String one",
            ])
        lines.extend([
            f"timeout {call_name} 3000ms",
            f"cancelOn {call_name} cancellationToken",
        ])
        if start_all and not start_after_wait_set:
            lines.append(f"start {call_name}")

    if orphan_case:
        lines.extend([
            f"case {calls[0]} {calls[0]}Ready",
            "label orphanCaseDone",
            "return value failedExitCode",
        ])
        return "\n".join(lines) + "\n"
    if orphan_done:
        lines.extend([
            "done allDone",
            "label allDone",
            "return value successfulExitCode",
        ])
        return "\n".join(lines) + "\n"

    lines.extend([
        "label waitNextResult",
        (
            f"await {wait_name} unexpectedExtra"
            if extra_await_arg
            else f"await {wait_name}"
        ),
    ])
    if done_without_case:
        lines.append("done allDone")
    else:
        case_targets = calls[:]
        if unknown_case:
            case_targets[0] = "missingCall"
        if duplicate_first_case:
            case_targets.insert(1, case_targets[0])
        for case_call in case_targets:
            if missing_case_label and case_call == case_targets[0]:
                lines.append(f"case {case_call}")
            elif extra_case_arg and case_call == case_targets[0]:
                lines.append(f"case {case_call} {case_call}Ready unexpectedExtra")
            else:
                lines.append(f"case {case_call} {case_call}Ready")
        if include_done:
            if missing_done_label:
                lines.append("done")
            elif extra_done_arg:
                lines.append("done allDone unexpectedExtra")
            else:
                lines.append("done allDone")
    if start_after_wait_set:
        for call_name in calls:
            lines.append(f"start {call_name}")

    for call_name in calls:
        lines.extend([
            f"label {call_name}Ready",
            f"bind ok {call_name}Result Int64 {call_name}",
            "jump target waitNextResult",
        ])
        if handler_await:
            lines.insert(-2, f"await {call_name}")
    lines.extend([
        "label allDone",
        "jump target secondRound" if two_wait_sets_same_name else "return value successfulExitCode",
    ])

    if two_wait_sets_same_name:
        second_calls = ["thirdAddCall", "fourthAddCall"]
        lines.extend([
            "label secondRound",
            "call thirdAddCall addPair",
            "argument thirdAddCall left Int64 two",
            "argument thirdAddCall right Int64 one",
            "timeout thirdAddCall 3000ms",
            "cancelOn thirdAddCall cancellationToken",
            "start thirdAddCall",
            "call fourthAddCall addPair",
            "argument fourthAddCall left Int64 three",
            "argument fourthAddCall right Int64 one",
            "timeout fourthAddCall 3000ms",
            "cancelOn fourthAddCall cancellationToken",
            "start fourthAddCall",
            "label waitNextResultAgain",
            f"await {wait_name}",
        ])
        for call_name in second_calls:
            lines.append(f"case {call_name} {call_name}Ready")
        lines.append("done secondAllDone")
        for call_name in second_calls:
            lines.extend([
                f"label {call_name}Ready",
                f"bind ok {call_name}Result Int64 {call_name}",
                "jump target waitNextResultAgain",
            ])
            if handler_await:
                lines.insert(-2, f"await {call_name}")
        lines.extend([
            "label secondAllDone",
            "return value successfulExitCode",
        ])

    return "\n".join(lines) + "\n"


def _fetch_wait_set_source(case_count: int = 2, *, handler_await: bool = False) -> str:
    urls = [
        ("firstFetchCall", "firstRequest", "firstUrl"),
        ("secondFetchCall", "secondRequest", "secondUrl"),
        ("thirdFetchCall", "thirdRequest", "thirdUrl"),
    ][:case_count]
    lines = [
        "project AsyncWaitSetFetch",
        "target console",
        "runtime AgentRuntime 1.0",
        "entry console main",
        "import net standard.net",
        "",
        "storage module immutable firstUrl Url \"http://127.0.0.1:18090/health\"",
        "storage module immutable secondUrl Url \"http://127.0.0.1:18090/api/version\"",
        "storage module immutable thirdUrl Url \"http://127.0.0.1:18090/api/todos\"",
        "storage module immutable timeoutMillis NetworkTimeoutMilliseconds 3000",
        "storage module immutable maxBodyBytes ResponseBodyLimitBytes 1048576",
        "storage module immutable redirectLimit HttpRedirectLimit 5",
        "storage module immutable cancellationToken OpaquePointer 0",
        "storage module immutable successfulExitCode ExitCode 0",
        "storage module immutable failedExitCode ExitCode 1",
        "",
        "operation main",
        "input operation main console Console",
        "output operation main ExitCode",
        "effect main write network.http.client",
        "memory main heap yes",
        "async main yes",
        "purpose operation main \"Exercise fetch wait-set lowering.\"",
        "label startMain",
    ]
    for call_name, request_name, url_name in urls:
        lines.extend([
            f"new {request_name} HttpGetRequest",
            f"fieldSet {request_name} url {url_name}",
            f"fieldSet {request_name} policy.timeoutMillis timeoutMillis",
            f"fieldSet {request_name} policy.maxBodyBytes maxBodyBytes",
            f"fieldSet {request_name} policy.redirectLimit redirectLimit",
            f"call {call_name} net.fetchText",
            f"argument {call_name} request HttpGetRequest {request_name}",
            f"timeout {call_name} 3000ms",
            f"cancelOn {call_name} cancellationToken",
            f"start {call_name}",
        ])
    lines.extend([
        "label waitNextFetch",
        "await nextFetch",
    ])
    for call_name, _request_name, _url_name in urls:
        lines.append(f"case {call_name} {call_name}Ready")
    lines.append("done allDone")
    for call_name, _request_name, _url_name in urls:
        lines.extend([
            f"label {call_name}Ready",
            f"bind ok {call_name}Response HttpTextResponse {call_name}",
            "jump target waitNextFetch",
        ])
        if handler_await:
            lines.insert(-3, f"await {call_name}")
    lines.extend([
        "label allDone",
        "return value successfulExitCode",
        "label failed",
        "return value failedExitCode",
    ])
    return "\n".join(lines) + "\n"


class TestAsyncWaitSetCompilerPositive(unittest.TestCase):
    def test_user_operation_wait_set_lowers_to_future_readiness_loop(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall", "secondAddCall", "thirdAddCall"])
        ir = _emit_ir(source)

        self.assertEqual(ir.count('call i32 @"ss_async_queue_work"'), 3)
        self.assertEqual(ir.count('call i32 @"ss_async_future_is_ready"'), 3)
        self.assertEqual(ir.count('call i32 @"ss_async_future_await"'), 3)
        self.assertEqual(ir.count('call i32 @"ss_async_loop_run_once"'), 1)
        self.assertIn('%"nextResult_await_poll_error_status"', ir)
        self.assertIn('%"nextResult_await_poll_failed"', ir)
        self.assertIn('nextResult_await_poll_error:', ir)
        for call_name in ("firstAddCall", "secondAddCall", "thirdAddCall"):
            self.assertIn(f'%"nextResult_{call_name}_consumed"', ir)
            self.assertIn(f"nextResult_", ir)
            self.assertIn(f"{call_name}_selected", ir)
            self.assertGreaterEqual(
                ir.count(f'store i8* null, i8** %"{call_name}_future_out"'),
                2,
            )
        self.assertIn('br i1 %"nextResult_thirdAddCall_all_consumed", label %"allDone"', ir)

    def test_fetch_wait_set_lowers_to_fetch_readiness_loop(self) -> None:
        ir = _emit_ir(_fetch_wait_set_source(3))

        self.assertEqual(ir.count('call i32 @"ss_http_client_fetch_text_request_start"'), 3)
        self.assertEqual(ir.count('call i32 @"ss_http_client_fetch_is_ready"'), 3)
        self.assertEqual(ir.count('call i32 @"ss_http_client_fetch_text_await"'), 3)
        self.assertEqual(ir.count('call i32 @"ss_async_loop_run_once"'), 1)
        self.assertNotIn('call i32 @"ss_http_client_fetch_text_request_copy"', ir)
        self.assertIn('%"nextFetch_await_poll_error_status"', ir)
        for call_name in ("firstFetchCall", "secondFetchCall", "thirdFetchCall"):
            self.assertGreaterEqual(
                ir.count(f'store i8* null, i8** %"{call_name}_future_out"'),
                2,
            )

    def test_single_case_wait_set_is_valid(self) -> None:
        ir = _emit_ir(_user_operation_wait_set_source(["onlyAddCall"]))

        self.assertEqual(ir.count('call i32 @"ss_async_queue_work"'), 1)
        self.assertEqual(ir.count('call i32 @"ss_async_future_is_ready"'), 1)
        self.assertIn('br i1 %"nextResult_onlyAddCall_all_consumed", label %"allDone"', ir)

    def test_done_label_can_immediately_follow_done_row(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "done allDone\nlabel firstAddCallReady",
            "\n".join([
                "done allDone",
                "label allDone",
                "return value successfulExitCode",
                "label firstAddCallReady",
            ]),
        ).replace(
            "jump target waitNextResult\nlabel allDone\nreturn value successfulExitCode",
            "jump target waitNextResult",
        )
        ir = _emit_ir(source)

        self.assertIn('br i1 %"nextResult_firstAddCall_all_consumed", label %"allDone"', ir)
        self.assertIn('allDone:', ir)

    def test_repeated_wait_set_names_get_independent_consumed_slots(self) -> None:
        source = _user_operation_wait_set_source(
            ["firstAddCall", "secondAddCall"],
            two_wait_sets_same_name=True,
        )
        ir = _emit_ir(source)

        self.assertIn('%"nextResult_firstAddCall_consumed"', ir)
        self.assertIn('%"nextResult_secondAddCall_consumed"', ir)
        self.assertIn('%"nextResult_1_thirdAddCall_consumed"', ir)
        self.assertIn('%"nextResult_1_fourthAddCall_consumed"', ir)
        self.assertIn('%"nextResult_await_poll_status"', ir)
        self.assertIn('%"nextResult_1_await_poll_status"', ir)

    def test_wait_set_allows_semantic_comments_between_structural_rows(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "await nextResult\ncase firstAddCall firstAddCallReady",
            "\n".join([
                "await nextResult",
                "# rationale: wait for whichever async call finishes first",
                "case firstAddCall firstAddCallReady",
                "# group waitSetDone",
            ]),
        )
        ir = _emit_ir(source)

        self.assertIn('call i32 @"ss_async_future_is_ready"', ir)
        self.assertIn('%"nextResult_firstAddCall_consumed"', ir)

    def test_pre_wait_defer_survives_case_handler_reentry(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall", "secondAddCall"]).replace(
            "label waitNextResult",
            "defer cleanupText net.freeTextBody cancellationToken\nlabel waitNextResult",
        )
        ir = _emit_ir(source)

        self.assertIn("ss_http_client_free_string", ir)

    def test_work_arg_before_work_declaration_is_preserved(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "output operation main ExitCode",
            "output operation main Int64",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "work sumWork target addPair",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        ir = _emit_ir(source)

        self.assertIn('_workSubmit__sumWork', ir)

    def test_non_target_duplicate_work_before_submit_uses_prior_target(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "output operation main ExitCode",
            "output operation main Int64",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "work sumWork",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        ir = _emit_ir(source)

        self.assertIn('_workSubmit__sumWork', ir)

    def test_module_worker_pool_can_back_submit_work(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "entry console main\nimport math standard.math",
            "entry console main\nworkerPool resultPool maxWorkers 4\nimport math standard.math",
        ).replace(
            "output operation main ExitCode",
            "output operation main Int64",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        ir = _emit_ir(source)

        self.assertIn('_workSubmit__sumWork', ir)

    def test_strict_wait_set_handler_fallible_call_can_bind_error_without_branch(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "import math standard.math\n",
            "",
        ).replace(
            "storage module immutable cancellationToken OpaquePointer 0",
            "\n".join([
                "storage module immutable cancellationToken OpaquePointer 0",
                'storage module immutable handlerMessage String "handler"',
            ]),
        ).replace(
            'purpose operation main "Exercise await wait-set lowering."',
            "\n".join([
                'purpose operation main "Exercise await wait-set lowering."',
                'invariant operation main "Handler fallible writes stay local and re-enter the wait set."',
                "effect main write console.stdout",
                "authority main write console.stdout",
            ]),
        ).replace(
            "label waitNextResult",
            "\n".join([
                "call handlerWriteCall console.writeLine",
                "argument handlerWriteCall console Console console",
                "argument handlerWriteCall text String handlerMessage",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "run handlerWriteCall",
                "ignore ok source handlerWriteCall type Int32",
                "bind error handlerWriteError Int32 handlerWriteCall",
                "jump target waitNextResult",
            ]),
        )
        ir = _emit_ir(source, ["--strict"])

        self.assertIn("handlerWriteCall", ir)


class TestAsyncWaitSetCompilerNegative(unittest.TestCase):
    def test_strict_pre_wait_fallible_call_error_ignore_in_handler_still_requires_branch(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "storage module immutable cancellationToken OpaquePointer 0",
            "\n".join([
                "storage module immutable cancellationToken OpaquePointer 0",
                'storage module immutable handlerMessage String "handler"',
            ]),
        ).replace(
            'purpose operation main "Exercise await wait-set lowering."',
            "\n".join([
                'purpose operation main "Exercise await wait-set lowering."',
                'invariant operation main "Pre-wait fallible writes must keep a local error branch."',
                "effect main write console.stdout",
                "authority main write console.stdout",
            ]),
        ).replace(
            "label waitNextResult",
            "\n".join([
                "call handlerWriteCall console.writeLine",
                "argument handlerWriteCall console Console console",
                "argument handlerWriteCall text String handlerMessage",
                "run handlerWriteCall",
                "ignore ok source handlerWriteCall type Int32",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "ignore error source handlerWriteCall",
                "jump target waitNextResult",
            ]),
        )
        _assert_strict_fails_with(self, source, "branch error")

    def test_strict_mixed_run_and_run_checked_same_fallible_call_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "storage module immutable cancellationToken OpaquePointer 0",
            "\n".join([
                "storage module immutable cancellationToken OpaquePointer 0",
                'storage module immutable handlerMessage String "handler"',
            ]),
        ).replace(
            'purpose operation main "Exercise await wait-set lowering."',
            "\n".join([
                'purpose operation main "Exercise await wait-set lowering."',
                'invariant operation main "Fallible writes must use one execution shape."',
                "effect main write console.stdout",
                "authority main write console.stdout",
            ]),
        ).replace(
            "label waitNextResult",
            "\n".join([
                "call handlerWriteCall console.writeLine",
                "argument handlerWriteCall console Console console",
                "argument handlerWriteCall text String handlerMessage",
                "run handlerWriteCall",
                "runChecked handlerWriteCall ok handlerWriteStatus Int32 error handlerWriteError Int32 else handlerWriteFailed",
                "label waitNextResult",
            ]),
        ).replace(
            "label failed\nreturn value failedExitCode",
            "\n".join([
                "label failed",
                "return value failedExitCode",
                "label handlerWriteFailed",
                "return value failedExitCode",
            ]),
        )
        _assert_strict_fails_with(self, source, "mixing unchecked execution with `runChecked`")

    def test_strict_mixed_start_and_run_checked_same_fallible_call_fails(self) -> None:
        source = _fetch_wait_set_source(1).replace(
            "label waitNextFetch",
            "\n".join([
                "runChecked firstFetchCall ok checkedResponse HttpTextResponse error checkedError HttpFetchError else checkedFetchFailed",
                "label waitNextFetch",
            ]),
        ).replace(
            "label failed\nreturn value failedExitCode",
            "\n".join([
                "label failed",
                "return value failedExitCode",
                "label checkedFetchFailed",
                "return value failedExitCode",
            ]),
        )
        _assert_strict_fails_with(self, source, "mixing unchecked execution with `runChecked`")

    def test_strict_mixed_start_in_group_and_run_checked_same_fallible_call_fails(self) -> None:
        source = "\n".join([
            "project StrictStartInGroupRunChecked",
            "target console",
            "runtime AgentRuntime 1.0",
            "entry console main",
            "operation main",
            "input operation main console Console",
            "output operation main ExitCode",
            "effect main write console.stdout",
            "authority main write console.stdout",
            'purpose operation main "Reject mixed checked and grouped execution."',
            'invariant operation main "Fallible grouped calls use one execution shape."',
            "memory main heap no",
            "async main no",
            'storage module immutable message String "hello"',
            "storage module immutable successfulExitCode ExitCode 0",
            "storage module immutable failedExitCode ExitCode 1",
            "label startMain",
            "taskGroup writeGroup",
            "call writeLineCall console.writeLine",
            "argument writeLineCall console Console console",
            "argument writeLineCall text String message",
            "startInGroup writeLineCall writeGroup",
            "runChecked writeLineCall ok writeStatus Int32 error writeError Int32 else writeFailed",
            "awaitGroup writeGroup",
            "return value successfulExitCode",
            "label writeFailed",
            "return value failedExitCode",
            "",
        ])
        _assert_strict_fails_with(self, source, "mixing unchecked execution with `runChecked`")

    def test_strict_fallible_dispositions_must_follow_execution(self) -> None:
        source = "\n".join([
            "project StrictPreRunDisposition",
            "target console",
            "runtime AgentRuntime 1.0",
            "entry console main",
            "error MainError",
            "errorCase MainError WriteFailure",
            "operation main",
            "input operation main console Console",
            "output operation main Result Void MainError",
            "effect main write console.stdout",
            "authority main write console.stdout",
            'purpose operation main "Reject pre-run fallible dispositions."',
            'invariant operation main "Fallible dispositions follow execution."',
            "memory main heap no",
            "async main no",
            'storage module immutable message String "hello"',
            "label startMain",
            "call writeLineCall console.writeLine",
            "argument writeLineCall console Console console",
            "argument writeLineCall text String message",
            "ignore ok source writeLineCall type Int32",
            "bind error writeError MainError writeLineCall",
            "branch error source writeLineCall target writeFailed",
            "run writeLineCall",
            "return ok noResult",
            "label writeFailed",
            "return error writeError",
            "",
        ])
        _assert_strict_fails_with(self, source, "bind ok|ignore ok|ignore void")

    def test_strict_wait_set_fallible_case_requires_success_disposition(self) -> None:
        source = _fetch_wait_set_source(1).replace(
            "bind ok firstFetchCallResponse HttpTextResponse firstFetchCall\njump target waitNextFetch",
            "ignore error source firstFetchCall\njump target waitNextFetch",
        )
        _assert_strict_fails_with(self, source, "bind ok|ignore ok|ignore void")

    def test_strict_wait_set_fallible_case_ignores_only_handler_error_disposition(self) -> None:
        source = _fetch_wait_set_source(1).replace(
            "label waitNextFetch",
            "ignore error source firstFetchCall\nlabel waitNextFetch",
        )
        _assert_strict_fails_with(self, source, "bind error|ignore error")

    def test_strict_wait_set_fallible_case_requires_error_disposition(self) -> None:
        source = _fetch_wait_set_source(1).replace(
            "bind ok firstFetchCallResponse HttpTextResponse firstFetchCall\njump target waitNextFetch",
            "bind ok firstFetchCallResponse HttpTextResponse firstFetchCall\njump target waitNextFetch",
        )
        _assert_strict_fails_with(self, source, "bind error|ignore error")

    def test_done_without_case_after_await_fails_with_specific_error(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], done_without_case=True)
        _assert_fails_with(self, source, "requires at least one following case row")

    def test_missing_done_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], include_done=False)
        _assert_fails_with(self, source, "requires a following done LABEL row")

    def test_duplicate_case_fails(self) -> None:
        source = _user_operation_wait_set_source(
            ["firstAddCall", "secondAddCall"],
            duplicate_first_case=True,
        )
        _assert_fails_with(self, source, "duplicate await case `firstAddCall`")

    def test_unknown_case_call_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], unknown_case=True)
        _assert_fails_with(self, source, "case references unknown call `missingCall`")

    def test_run_checked_unknown_call_fails_with_source_message(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "runChecked missingCall ok missingValue Int64 error missingError Int64 else checkedFailed",
                "return value missingValue",
                "label checkedFailed",
                "return value failedExitCode",
            ]),
        )
        _assert_fails_with(
            self,
            source,
            "runChecked references unknown call `missingCall`",
        )

    def test_case_call_must_have_been_started_as_future(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], start_all=False)
        _assert_fails_with(self, source, "was not started with async lowering")

    def test_case_call_must_be_started_before_wait_set(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], start_all=False).replace(
            "label firstAddCallReady\nbind ok firstAddCallResult Int64 firstAddCall",
            "\n".join([
                "label firstAddCallReady",
                "start firstAddCall",
                "bind ok firstAddCallResult Int64 firstAddCall",
            ]),
        )
        _assert_fails_with(self, source, "was not started with async lowering")

    def test_case_start_must_dominate_wait_set_entry(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "label startMain\njump target waitNextResult\ncall firstAddCall",
        )
        _assert_fails_with(self, source, "does not dominate the wait-set entry")

    def test_case_start_after_return_does_not_dominate_wait_set_entry(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "label startMain\nreturn value successfulExitCode\ncall firstAddCall",
        )
        _assert_fails_with(self, source, "does not dominate the wait-set entry")

    def test_case_start_after_dead_label_does_not_dominate_wait_set_entry(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "\n".join([
                "label startMain",
                "return value successfulExitCode",
                "label deadStart",
                "call firstAddCall",
            ]),
        )
        _assert_fails_with(self, source, "does not dominate the wait-set entry")

    def test_case_call_rejects_multiple_prior_starts(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\nstart firstAddCall\nlabel waitNextResult",
        )
        _assert_fails_with(self, source, "has multiple prior start rows")

    def test_case_call_rejects_branch_skipped_restart(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "\n".join([
                "start firstAddCall",
                "branch if condition successfulExitCode target restartFirstAddCall",
                "branch else target waitNextResult",
                "label restartFirstAddCall",
                "start firstAddCall",
                "jump target waitNextResult",
                "label waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "has multiple prior start rows")

    def test_case_call_rejects_attached_else_bypass_of_start(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "\n".join([
                "label startMain",
                "branch if condition successfulExitCode target doStart",
                "branch else target waitNextResult",
                "label doStart",
                "call firstAddCall",
            ]),
        )
        _assert_fails_with(self, source, "does not dominate the wait-set entry")

    def test_case_call_rejects_attached_else_reentry_to_start(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "label retryStart",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "branch if condition successfulExitCode target earlyExit",
                "branch else target retryStart",
                "label earlyExit",
                "return value successfulExitCode",
            ]),
        )
        _assert_fails_with(self, source, "can be re-entered")

    def test_user_operation_case_requires_async_enclosing_operation(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], main_async=False)
        _assert_fails_with(self, source, "was not started with async lowering")

    def test_unsupported_started_case_target_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], unsupported_case=True)
        _assert_fails_with(self, source, "was not started with async lowering")

    def test_orphan_case_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], orphan_case=True)
        _assert_fails_with(self, source, "must immediately follow an `await NAME` wait-set row")

    def test_orphan_done_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], orphan_done=True)
        _assert_fails_with(self, source, "must immediately follow an `await NAME` wait-set row")

    def test_case_missing_label_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], missing_case_label=True)
        _assert_fails_with(self, source, "case requires: case CALL LABEL")

    def test_case_extra_argument_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], extra_case_arg=True)
        _assert_fails_with(self, source, "case requires: case CALL LABEL")

    def test_done_missing_label_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], missing_done_label=True)
        _assert_fails_with(self, source, "done requires: done LABEL")

    def test_done_extra_argument_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], extra_done_arg=True)
        _assert_fails_with(self, source, "done requires: done LABEL")

    def test_await_wait_set_extra_argument_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], extra_await_arg=True)
        _assert_fails_with(self, source, "await wait set requires: await NAME")

    def test_wait_set_name_cannot_collide_with_call_name(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], wait_name="firstAddCall")
        _assert_fails_with(self, source, "collides with a declared call name")

    def test_case_target_label_must_be_declared(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "case firstAddCall firstAddCallReady",
            "case firstAddCall missingReadyLabel",
        )
        _assert_fails_with(self, source, "target label `missingReadyLabel` is not declared")

    def test_done_target_label_must_be_declared(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "done allDone",
            "done missingDoneLabel",
        )
        _assert_fails_with(self, source, "done label `missingDoneLabel` is not declared")

    def test_case_target_labels_must_be_unique(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "case secondAddCall secondAddCallReady",
            "case secondAddCall firstAddCallReady",
        )
        _assert_fails_with(self, source, "target label `firstAddCallReady` is used by multiple cases")

    def test_case_target_label_must_differ_from_done_label(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "case firstAddCall firstAddCallReady",
            "case firstAddCall allDone",
        )
        _assert_fails_with(self, source, "target label `allDone` must differ from the done label")

    def test_case_target_label_rejects_external_branch_predecessor(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target firstAddCallReady\nlabel waitNextResult",
        )
        _assert_fails_with(self, source, "may only be reached from that case")

    def test_case_target_label_rejects_attached_else_predecessor(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "\n".join([
                "start firstAddCall",
                "branch if condition successfulExitCode target beforeWait",
                "branch else target firstAddCallReady",
                "label beforeWait",
                "label waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "may only be reached from that case")

    def test_case_target_label_rejects_indirect_fallthrough_predecessor(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target strayEntry\nlabel waitNextResult",
        ).replace(
            "done allDone\nlabel firstAddCallReady",
            "done allDone\nlabel strayEntry\nlabel firstAddCallReady",
        )
        _assert_fails_with(self, source, "must not be reachable by fallthrough")

    def test_done_label_rejects_external_branch_predecessor(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target allDone\nlabel waitNextResult",
        )
        _assert_fails_with(self, source, "done label `allDone` may only be reached")

    def test_done_label_rejects_attached_else_predecessor(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "\n".join([
                "start firstAddCall",
                "branch if condition successfulExitCode target beforeWait",
                "branch else target allDone",
                "label beforeWait",
                "label waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "done label `allDone` may only be reached")

    def test_done_label_rejects_indirect_fallthrough_predecessor(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target strayDone\nlabel waitNextResult",
        ).replace(
            "jump target waitNextResult\nlabel allDone",
            "jump target waitNextResult\nlabel strayDone\nlabel allDone",
        )
        _assert_fails_with(self, source, "done label `allDone` must not be reachable by fallthrough")

    def test_done_structural_gap_rejects_executable_rows_before_label(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "done allDone\nlabel firstAddCallReady",
            "done allDone\nreturn value failedExitCode\nlabel firstAddCallReady",
        )
        _assert_fails_with(self, source, "done row must be followed by a label")

    def test_case_result_cannot_be_read_from_another_handler(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok firstAddCallResult Int64 firstAddCall",
                "bind ok stolenSecondResult Int64 secondAddCall",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "result may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_cannot_be_read_from_another_handler(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "call totalCall math.addInt64",
                "argument totalCall left Int64 firstAddCallResult",
                "argument totalCall right Int64 secondAddCallResult",
                "run totalCall",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "firstAddCallResult` value may only be read inside handler label `firstAddCallReady`")

    def test_case_handler_bind_cannot_be_used_by_call_argument_executed_in_done(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call totalCall math.addInt64",
                "argument totalCall left Int64 one",
                "argument totalCall right Int64 secondAddCallResult",
                "label waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "run totalCall",
                "bind value totalResult Int64 totalCall",
                "return value totalResult",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_argument_inside_handler_cannot_be_executed_in_done(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call totalCall math.addInt64",
                "argument totalCall left Int64 one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "argument totalCall right Int64 secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "run totalCall",
                "bind value totalResult Int64 totalCall",
                "return value totalResult",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_cannot_escape_through_mutable_memory(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "memory main mutable leaked Int64 0\nlabel waitNextResult",
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "set memory leaked secondAddCallResult",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "may not be written into non-private state `leaked`")

    def test_case_handler_bind_cannot_escape_through_record_field(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "import math standard.math\n\nstorage module",
            "\n".join([
                "import math standard.math",
                "",
                "record Point layout row align 8",
                "field Point x Int64",
                "field Point y Int64",
                "",
                "storage module",
            ]),
        ).replace(
            "label waitNextResult",
            "\n".join([
                "new leakedPoint Point",
                "fieldSet leakedPoint x one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "fieldSet leakedPoint x secondAddCallResult",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "may not be written into non-private state `leakedPoint`")

    def test_case_handler_bind_cannot_be_used_by_memory_initializer(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "memory main mutable leaked Int64 secondAddCallResult",
                "return value leaked",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_cannot_be_sent_from_done_handler(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "send resultChannel secondAddCallResult",
                "receive leaked Int64 resultChannel",
                "return value leaked",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_cannot_escape_through_channel_send(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "send resultChannel secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "receive leaked Int64 resultChannel",
                "return value leaked",
            ]),
        )
        _assert_fails_with(self, source, "may not be written into non-private state `resultChannel`")

    def test_case_handler_bind_cannot_escape_through_private_channel_receive(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "memory main mutable privateChannel Int64 0",
                "send privateChannel secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "receive leaked Int64 privateChannel",
                "return value leaked",
            ]),
        )
        _assert_fails_with(self, source, "privateChannel` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_cannot_be_used_by_defer_outside_handler(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "defer cleanupAdd addPair secondAddCallResult one",
                "return value successfulExitCode",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_direct_case_call_cannot_be_used_by_defer_outside_handler(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "defer cleanupAdd addPair secondAddCall one",
                "return value successfulExitCode",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCall` value may only be read inside handler label `secondAddCallReady`")

    def test_pre_wait_defer_cannot_capture_future_case_bind(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "defer cleanupFuture addPair secondAddCallResult one\nlabel waitNextResult",
        )
        _assert_fails_with(
            self,
            source,
            "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`",
        )

    def test_pre_wait_defer_cannot_capture_future_case_call(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "defer cleanupFuture addPair secondAddCall one\nlabel waitNextResult",
        )
        _assert_fails_with(
            self,
            source,
            "secondAddCall` value may only be read inside handler label `secondAddCallReady`",
        )

    def test_case_handler_defer_must_not_cross_wait_set_reentry(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "defer cleanupSecondAdd addPair secondAddCallResult one",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "must not register defer cleanup")

    def test_case_handler_bind_cannot_escape_through_storage_read(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "storage local mutable privateStore Int64 0",
                "set storage privateStore secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "read local leaked Int64 privateStore",
                "return value leaked",
            ]),
        )
        _assert_fails_with(self, source, "privateStore` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_bind_cannot_escape_through_work_arg_submit(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork right one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "workArg sumWork left secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_submit_work_requires_declared_work_item(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "submitWork missingWork resultPool",
                "awaitWork missingWork",
                "return value missingWork",
            ]),
        )
        _assert_fails_with(self, source, "submitWork: work `missingWork` is not declared")

    def test_submit_work_requires_user_operation_target(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work missingTargetWork target missingOp",
                "submitWork missingTargetWork resultPool",
                "awaitWork missingTargetWork",
                "return value missingTargetWork",
            ]),
        )
        _assert_fails_with(
            self,
            source,
            "submitWork: work `missingTargetWork` target `missingOp` is not a user operation",
        )

    def test_submit_work_requires_prior_work_args(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "submitWork sumWork resultPool",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        _assert_fails_with(self, source, "_workSubmit__sumWork: missing arg `left`")

    def test_submit_work_requires_declared_worker_pool(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "submitWork sumWork missingPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        _assert_fails_with(
            self,
            source,
            "submitWork: worker pool `missingPool` is not declared",
        )

    def test_case_handler_run_checked_cannot_branch_out_before_reentry(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "call checkedTotalCall math.addInt64",
                "argument checkedTotalCall left Int64 secondAddCallResult",
                "argument checkedTotalCall right Int64 one",
                "runChecked checkedTotalCall ok checkedTotal Int64 error checkedError Int64 else allDone",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "done label `allDone` may only be reached")

    def test_case_handler_argument_cannot_be_used_by_run_checked_in_done(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call checkedTotalCall math.addInt64",
                "argument checkedTotalCall right Int64 one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "argument checkedTotalCall left Int64 secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "runChecked checkedTotalCall ok checkedTotal Int64 error checkedError Int64 else checkedFailed",
                "return value checkedTotal",
                "label checkedFailed",
                "return value failedExitCode",
            ]),
        )
        _assert_fails_with(self, source, "secondAddCallResult` value may only be read inside handler label `secondAddCallReady`")

    def test_await_work_result_inside_handler_cannot_be_read_from_done(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork right one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "workArg sumWork left secondAddCallResult",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "label allDone\nreturn value sumWork",
        )
        _assert_fails_with(self, source, "sumWork` value may only be read inside handler label `secondAddCallReady`")

    def test_case_handler_run_result_cannot_be_read_from_done_handler(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call totalCall math.addInt64",
                "argument totalCall left Int64 one",
                "argument totalCall right Int64 two",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "bind ok secondAddCallResult Int64 secondAddCall\nrun totalCall\njump target waitNextResult",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "label allDone\nbind ok totalResult Int64 totalCall\nreturn value totalResult",
        )
        _assert_fails_with(self, source, "totalCall` value may only be read inside handler label `secondAddCallReady`")

    def test_case_start_allows_exit_to_prior_label_that_cannot_reenter_start(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "\n".join([
                "label entry",
                "jump target startMain",
                "label earlyExit",
                "return value successfulExitCode",
                "label startMain",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "label allDone\njump target earlyExit",
        )
        ir = _emit_ir(source)

        self.assertIn('br label %"earlyExit"', ir)

    def test_case_start_ignores_unreachable_branch_that_bypasses_start(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "\n".join([
                "label entry",
                "jump target startMain",
                "jump target waitNextResult",
                "label startMain",
            ]),
        )
        ir = _emit_ir(source)

        self.assertIn('br label %"waitNextResult"', ir)

    def test_case_start_rejects_backedge_to_start_region(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "label retryStart",
        ).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "bind ok firstAddCallResult Int64 firstAddCall\njump target retryStart",
        )
        _assert_fails_with(self, source, "can be re-entered")

    def test_case_handler_must_reenter_wait_set(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "bind ok firstAddCallResult Int64 firstAddCall\nreturn value successfulExitCode",
        )
        _assert_fails_with(self, source, "must jump back to `waitNextResult`")

    def test_handler_await_after_wait_set_case_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], handler_await=True)
        _assert_fails_with(self, source, "already awaited or consumed by an await wait-set case")

    def test_case_call_cannot_be_restarted_after_consumption(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok firstAddCallResult Int64 firstAddCall",
                "start firstAddCall",
                "jump target waitNextResult",
            ]),
        )
        _assert_fails_with(self, source, "already awaited or consumed by an await wait-set case")

    def test_same_call_in_later_wait_set_fails(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode\n",
            "\n".join([
                "label allDone",
                "jump target secondWait",
                "label secondWait",
                "await secondResult",
                "case firstAddCall firstAddCallAgain",
                "done secondDone",
                "label firstAddCallAgain",
                "bind ok again Int64 firstAddCall",
                "jump target secondWait",
                "label secondDone",
                "return value successfulExitCode",
                "",
            ]),
        )
        _assert_fails_with(self, source, "already awaited or consumed by an earlier wait-set case")


class TestAsyncWaitSetLinter(unittest.TestCase):
    def test_wait_set_name_is_not_treated_as_unresolved_call(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall", "secondAddCall"])
        codes = _diagnostic_codes(source)

        self.assertNotIn("SS4101", codes)
        self.assertNotIn("SS3509", codes)

    def test_wait_set_comments_do_not_hide_shape_from_linter(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "await nextResult\ncase firstAddCall firstAddCallReady",
            "\n".join([
                "await nextResult",
                "# rationale: wait for whichever async call finishes first",
                "case firstAddCall firstAddCallReady",
                "# group waitSetDone",
            ]),
        )
        codes = _diagnostic_codes(source)

        self.assertNotIn("SS4101", codes)
        self.assertNotIn("SS3509", codes)

    def test_case_and_done_labels_are_checked(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "case firstAddCall firstAddCallReady",
            "case firstAddCall missingReadyLabel",
        ).replace(
            "done allDone",
            "done missingDoneLabel",
        )
        codes = _diagnostic_codes(source)
        kinds = _diagnostic_kinds(source)

        self.assertIn("SS4102", codes)
        self.assertIn("referenceIntegrity.unresolvedLabel", kinds)

    def test_run_checked_references_unknown_call(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "runChecked missingCall ok missingValue Int64 error missingError Int64 else checkedFailed",
                "return value missingValue",
                "label checkedFailed",
                "return value failedExitCode",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS4101"
                and diagnostic.subjectName == "missingCall"
                for diagnostic in diagnostics
            )
        )

    def test_wait_set_shape_errors_are_linted(self) -> None:
        malformed_sources = [
            _user_operation_wait_set_source(["firstAddCall"], done_without_case=True),
            _user_operation_wait_set_source(["firstAddCall"], include_done=False),
            _user_operation_wait_set_source(["firstAddCall"], orphan_case=True),
            _user_operation_wait_set_source(["firstAddCall"], orphan_done=True),
            _user_operation_wait_set_source(
                ["firstAddCall", "secondAddCall"],
                duplicate_first_case=True,
            ),
        ]
        for source in malformed_sources:
            with self.subTest(source=source.splitlines()[-12:]):
                diagnostics = _lint_source(source)
                self.assertIn("SS3509", [diagnostic.code for diagnostic in diagnostics])
                self.assertIn(
                    "concurrencyDiscipline.awaitWaitSetMalformed",
                    [diagnostic.kind for diagnostic in diagnostics],
                )
                self.assertTrue(
                    any(diagnostic.blocksCompile for diagnostic in diagnostics if diagnostic.code == "SS3509")
                )

    def test_done_without_case_does_not_treat_wait_set_name_as_call(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], done_without_case=True)
        codes = _diagnostic_codes(source)

        self.assertIn("SS3509", codes)
        self.assertNotIn("SS4101", codes)

    def test_case_consumes_future_and_counts_as_completion_boundary(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"])
        codes = _diagnostic_codes(source)

        self.assertNotIn("SS3512", codes)

    def test_handler_await_after_wait_set_case_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], handler_await=True)
        diagnostics = _lint_source(source)

        self.assertIn("SS3509", [diagnostic.code for diagnostic in diagnostics])
        self.assertTrue(
            any(diagnostic.blocksCompile for diagnostic in diagnostics if diagnostic.code == "SS3509")
        )

    def test_fallible_call_declared_before_wait_set_runs_in_handler_context(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call handlerWriteCall console.writeLine",
                "argument handlerWriteCall console Console console",
                "argument handlerWriteCall text String one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "run handlerWriteCall",
                "ignore ok source handlerWriteCall type Int32",
                "bind error handlerWriteError Int32 handlerWriteCall",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            [
                diagnostic for diagnostic in diagnostics
                if diagnostic.code == "SS3106"
                and diagnostic.subjectName == "handlerWriteCall"
            ],
            diagnostics,
        )

    def test_fallible_handler_call_with_only_ignored_error_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call handlerWriteCall console.writeLine",
                "argument handlerWriteCall console Console console",
                "argument handlerWriteCall text String one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "run handlerWriteCall",
                "ignore error source handlerWriteCall",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3106"
                and diagnostic.subjectName == "handlerWriteCall"
                and "bind/ignore ok" in diagnostic.gapEdge
                for diagnostic in diagnostics
            ),
            diagnostics,
        )

    def test_pre_wait_fallible_call_error_ignore_inside_handler_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "storage module immutable cancellationToken OpaquePointer 0",
            "\n".join([
                "storage module immutable cancellationToken OpaquePointer 0",
                'storage module immutable handlerMessage String "handler"',
            ]),
        ).replace(
            "label waitNextResult",
            "\n".join([
                "call handlerWriteCall console.writeLine",
                "argument handlerWriteCall console Console console",
                "argument handlerWriteCall text String handlerMessage",
                "run handlerWriteCall",
                "ignore ok source handlerWriteCall type Int32",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "ignore error source handlerWriteCall",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3106"
                and diagnostic.subjectName == "handlerWriteCall"
                and "branch error" in diagnostic.gapEdge
                for diagnostic in diagnostics
            ),
            diagnostics,
        )

    def test_restart_after_wait_set_case_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok firstAddCallResult Int64 firstAddCall",
                "start firstAddCall",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startAfterCaseCompletion"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_run_checked_known_call_is_not_unknown_verb_or_unused_label(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "call checkedTotalCall math.addInt64",
                "argument checkedTotalCall left Int64 one",
                "argument checkedTotalCall right Int64 two",
                "runChecked checkedTotalCall ok checkedTotal Int64 error checkedError Int64 else checkedFailed",
                "return value checkedTotal",
                "label checkedFailed",
                "return value failedExitCode",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            [
                diagnostic for diagnostic in diagnostics
                if diagnostic.code == "SS0001"
                and diagnostic.subjectName == "runChecked"
            ],
            diagnostics,
        )
        self.assertFalse(
            [
                diagnostic for diagnostic in diagnostics
                if diagnostic.code == "SS0102"
                and diagnostic.subjectName == "checkedFailed"
            ],
            diagnostics,
        )

    def test_same_call_in_multiple_wait_sets_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode\n",
            "\n".join([
                "label allDone",
                "jump target secondWait",
                "label secondWait",
                "await secondResult",
                "case firstAddCall firstAddCallAgain",
                "done secondDone",
                "label firstAddCallAgain",
                "bind ok again Int64 firstAddCall",
                "jump target secondWait",
                "label secondDone",
                "return value successfulExitCode",
                "",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertIn("SS3509", [diagnostic.code for diagnostic in diagnostics])
        self.assertTrue(
            any(
                diagnostic.gapEdge == "singleCompletionEdge"
                for diagnostic in diagnostics
                if diagnostic.code == "SS3509"
            )
        )

    def test_case_and_done_arity_errors_are_linted(self) -> None:
        malformed_sources = [
            _user_operation_wait_set_source(["firstAddCall"], missing_case_label=True),
            _user_operation_wait_set_source(["firstAddCall"], missing_done_label=True),
            _user_operation_wait_set_source(["firstAddCall"], extra_await_arg=True),
            _user_operation_wait_set_source(["firstAddCall"], extra_case_arg=True),
            _user_operation_wait_set_source(["firstAddCall"], extra_done_arg=True),
        ]
        for source in malformed_sources:
            with self.subTest(source=source.splitlines()[-12:]):
                diagnostics = _lint_source(source)
                self.assertTrue(
                    {"SS0002", "SS3509"} & {diagnostic.code for diagnostic in diagnostics}
                )
                self.assertTrue(
                    any(
                        diagnostic.blocksCompile
                        for diagnostic in diagnostics
                        if diagnostic.code in {"SS0002", "SS3509"}
                    )
                )

    def test_wait_set_name_collision_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], wait_name="firstAddCall")
        diagnostics = _lint_source(source)

        self.assertIn("SS3509", [diagnostic.code for diagnostic in diagnostics])
        self.assertTrue(
            any(
                diagnostic.gapEdge == "waitSetNameCallCollision"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
                if diagnostic.code == "SS3509"
            )
        )

    def test_case_target_label_collisions_are_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "case secondAddCall secondAddCallReady",
            "case secondAddCall firstAddCallReady",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "uniqueCaseLabel"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_done_label_collision_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "case firstAddCall firstAddCallReady",
            "case firstAddCall allDone",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseDoneLabelDisjoint"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_target_external_branch_predecessor_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target firstAddCallReady\nlabel waitNextResult",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseLabelPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_target_attached_else_predecessor_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "\n".join([
                "start firstAddCall",
                "branch if condition successfulExitCode target beforeWait",
                "branch else target firstAddCallReady",
                "label beforeWait",
                "label waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseLabelPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_target_indirect_fallthrough_predecessor_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target strayEntry\nlabel waitNextResult",
        ).replace(
            "done allDone\nlabel firstAddCallReady",
            "done allDone\nlabel strayEntry\nlabel firstAddCallReady",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseLabelPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_done_label_external_branch_predecessor_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target allDone\nlabel waitNextResult",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "doneLabelPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_done_label_attached_else_predecessor_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "\n".join([
                "start firstAddCall",
                "branch if condition successfulExitCode target beforeWait",
                "branch else target allDone",
                "label beforeWait",
                "label waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "doneLabelPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_done_label_indirect_fallthrough_predecessor_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\njump target strayDone\nlabel waitNextResult",
        ).replace(
            "jump target waitNextResult\nlabel allDone",
            "jump target waitNextResult\nlabel strayDone\nlabel allDone",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "doneLabelPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_unqualified_unknown_case_target_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "call firstAddCall addPair",
            "call firstAddCall missingOp",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "asyncFutureCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_unsupported_started_case_target_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], unsupported_case=True)
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "asyncFutureCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_user_operation_case_in_non_async_operation_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], main_async=False)
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "asyncFutureCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_without_start_is_still_flagged(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"], start_all=False)
        diagnostics = _lint_source(source)

        self.assertIn("SS3511", [diagnostic.code for diagnostic in diagnostics])
        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_start_after_wait_set_is_linted(self) -> None:
        source = _user_operation_wait_set_source(
            ["firstAddCall"],
            start_after_wait_set=True,
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_start_that_does_not_dominate_wait_set_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "label startMain\njump target waitNextResult\ncall firstAddCall",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_start_after_return_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "label startMain\nreturn value successfulExitCode\ncall firstAddCall",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_start_after_dead_label_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "\n".join([
                "label startMain",
                "return value successfulExitCode",
                "label deadStart",
                "call firstAddCall",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_done_structural_gap_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "done allDone\nlabel firstAddCallReady",
            "done allDone\nreturn value failedExitCode\nlabel firstAddCallReady",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "doneStructuralGap"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_done_label_after_done_row_is_linted_as_valid(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "done allDone\nlabel firstAddCallReady",
            "\n".join([
                "done allDone",
                "label allDone",
                "return value successfulExitCode",
                "label firstAddCallReady",
            ]),
        ).replace(
            "jump target waitNextResult\nlabel allDone\nreturn value successfulExitCode",
            "jump target waitNextResult",
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "doneLabelPrivateEntry"
                for diagnostic in diagnostics
            ),
            diagnostics,
        )

    def test_case_result_read_from_other_handler_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok firstAddCallResult Int64 firstAddCall",
                "bind ok stolenSecondResult Int64 secondAddCall",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_read_from_other_handler_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "call totalCall math.addInt64",
                "argument totalCall left Int64 firstAddCallResult",
                "argument totalCall right Int64 secondAddCallResult",
                "run totalCall",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_call_argument_executed_in_done_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call totalCall math.addInt64",
                "argument totalCall left Int64 one",
                "argument totalCall right Int64 secondAddCallResult",
                "label waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "run totalCall",
                "bind value totalResult Int64 totalCall",
                "return value totalResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_argument_inside_handler_run_in_done_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call totalCall math.addInt64",
                "argument totalCall left Int64 one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "argument totalCall right Int64 secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "run totalCall",
                "bind value totalResult Int64 totalCall",
                "return value totalResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_mutable_memory_escape_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "memory main mutable leaked Int64 0\nlabel waitNextResult",
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "set memory leaked secondAddCallResult",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEscape"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_record_field_escape_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "import math standard.math\n\nstorage module",
            "\n".join([
                "import math standard.math",
                "",
                "record Point layout row align 8",
                "field Point x Int64",
                "field Point y Int64",
                "",
                "storage module",
            ]),
        ).replace(
            "label waitNextResult",
            "\n".join([
                "new leakedPoint Point",
                "fieldSet leakedPoint x one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "fieldSet leakedPoint x secondAddCallResult",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEscape"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_memory_initializer_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "memory main mutable leaked Int64 secondAddCallResult",
                "return value leaked",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_send_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "send resultChannel secondAddCallResult",
                "receive leaked Int64 resultChannel",
                "return value leaked",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_channel_send_escape_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "send resultChannel secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "receive leaked Int64 resultChannel",
                "return value leaked",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEscape"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_private_channel_receive_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "memory main mutable privateChannel Int64 0",
                "send privateChannel secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "receive leaked Int64 privateChannel",
                "return value leaked",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_defer_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "defer cleanupAdd addPair secondAddCallResult one",
                "return value successfulExitCode",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_direct_case_call_defer_outside_handler_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "defer cleanupAdd addPair secondAddCall one",
                "return value successfulExitCode",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_pre_wait_defer_future_case_bind_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "defer cleanupFuture addPair secondAddCallResult one\nlabel waitNextResult",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_pre_wait_defer_future_case_call_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "defer cleanupFuture addPair secondAddCall one\nlabel waitNextResult",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_defer_before_reentry_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "defer cleanupSecondAdd addPair secondAddCallResult one",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseHandlerDefer"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_bind_storage_read_escape_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "storage local mutable privateStore Int64 0",
                "set storage privateStore secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "read local leaked Int64 privateStore",
                "return value leaked",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_missing_declaration_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "submitWork missingWork resultPool",
                "awaitWork missingWork",
                "return value missingWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3514"
                and diagnostic.gapEdge == "workDeclaration"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_missing_target_operation_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work missingTargetWork target missingOp",
                "submitWork missingTargetWork resultPool",
                "awaitWork missingTargetWork",
                "return value missingTargetWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3514"
                and diagnostic.gapEdge == "workTarget"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_missing_worker_pool_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "submitWork sumWork missingPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3514"
                and diagnostic.gapEdge == "workerPool"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_missing_required_work_arg_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3514"
                and diagnostic.gapEdge == "workArg"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_requires_work_args_before_submit(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "submitWork sumWork resultPool",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3514"
                and diagnostic.gapEdge == "workArg"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_requires_work_before_submit(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "submitWork sumWork resultPool",
                "work sumWork target addPair",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3514"
                and diagnostic.gapEdge == "workDeclaration"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_submit_work_late_duplicate_work_after_valid_declaration_is_not_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "output operation main ExitCode",
            "output operation main Int64",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "submitWork sumWork resultPool",
                "work sumWork target addPair",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            [
                diagnostic for diagnostic in diagnostics
                if diagnostic.code == "SS3514"
                and diagnostic.subjectName == "sumWork"
            ],
            diagnostics,
        )

    def test_submit_work_late_duplicate_arg_after_valid_arg_is_not_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "output operation main ExitCode",
            "output operation main Int64",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "submitWork sumWork resultPool",
                "workArg sumWork left three",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            [
                diagnostic for diagnostic in diagnostics
                if diagnostic.code == "SS3514"
                and diagnostic.subjectName == "sumWork"
            ],
            diagnostics,
        )

    def test_submit_work_non_target_duplicate_before_submit_is_not_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "output operation main ExitCode",
            "output operation main Int64",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork left one",
                "workArg sumWork right two",
                "work sumWork",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            [
                diagnostic for diagnostic in diagnostics
                if diagnostic.code == "SS3514"
                and diagnostic.subjectName == "sumWork"
            ],
            diagnostics,
        )

    def test_case_handler_bind_work_arg_submit_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork right one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "workArg sumWork left secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "return value sumWork",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_run_checked_branch_out_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "call checkedTotalCall math.addInt64",
                "argument checkedTotalCall left Int64 secondAddCallResult",
                "argument checkedTotalCall right Int64 one",
                "runChecked checkedTotalCall ok checkedTotal Int64 error checkedError Int64 else allDone",
                "jump target waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseHandlerReentry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_argument_run_checked_in_done_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call checkedTotalCall math.addInt64",
                "argument checkedTotalCall right Int64 one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "argument checkedTotalCall left Int64 secondAddCallResult",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "runChecked checkedTotalCall ok checkedTotal Int64 error checkedError Int64 else checkedFailed",
                "return value checkedTotal",
                "label checkedFailed",
                "return value failedExitCode",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_await_work_result_inside_handler_read_from_done_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "workerPool resultPool maxWorkers 4",
                "work sumWork target addPair",
                "workArg sumWork right one",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "\n".join([
                "bind ok secondAddCallResult Int64 secondAddCall",
                "workArg sumWork left secondAddCallResult",
                "submitWork sumWork resultPool",
                "awaitWork sumWork",
                "jump target waitNextResult",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "label allDone\nreturn value sumWork",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_run_result_read_from_done_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "label waitNextResult",
            "\n".join([
                "call totalCall math.addInt64",
                "argument totalCall left Int64 one",
                "argument totalCall right Int64 two",
                "label waitNextResult",
            ]),
        ).replace(
            "bind ok secondAddCallResult Int64 secondAddCall\njump target waitNextResult",
            "bind ok secondAddCallResult Int64 secondAddCall\nrun totalCall\njump target waitNextResult",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "label allDone\nbind ok totalResult Int64 totalCall\nreturn value totalResult",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseResultPrivateEntry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_start_exit_to_non_reentering_prior_label_is_linted_as_valid(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "\n".join([
                "label entry",
                "jump target startMain",
                "label earlyExit",
                "return value successfulExitCode",
                "label startMain",
            ]),
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "label allDone\njump target earlyExit",
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "singleStartExecution"
                for diagnostic in diagnostics
            ),
            diagnostics,
        )

    def test_case_start_unreachable_bypass_branch_is_linted_as_valid(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "\n".join([
                "label entry",
                "jump target startMain",
                "jump target waitNextResult",
                "label startMain",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertFalse(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                for diagnostic in diagnostics
            ),
            diagnostics,
        )

    def test_case_start_backedge_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "label retryStart",
        ).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "bind ok firstAddCallResult Int64 firstAddCall\njump target retryStart",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "singleStartExecution"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_case_handler_exit_before_reentry_is_linted(self) -> None:
        source = _user_operation_wait_set_source([
            "firstAddCall",
            "secondAddCall",
        ]).replace(
            "bind ok firstAddCallResult Int64 firstAddCall\njump target waitNextResult",
            "bind ok firstAddCallResult Int64 firstAddCall\nreturn value successfulExitCode",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "caseHandlerReentry"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_multiple_prior_case_starts_are_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "start firstAddCall\nstart firstAddCall\nlabel waitNextResult",
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "singlePriorStart"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_branch_skipped_restart_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "start firstAddCall\nlabel waitNextResult",
            "\n".join([
                "start firstAddCall",
                "branch if condition successfulExitCode target restartFirstAddCall",
                "branch else target waitNextResult",
                "label restartFirstAddCall",
                "start firstAddCall",
                "jump target waitNextResult",
                "label waitNextResult",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "singlePriorStart"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_attached_else_bypass_of_start_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain\ncall firstAddCall",
            "\n".join([
                "label startMain",
                "branch if condition successfulExitCode target doStart",
                "branch else target waitNextResult",
                "label doStart",
                "call firstAddCall",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "startBeforeCase"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )

    def test_attached_else_reentry_to_start_is_linted(self) -> None:
        source = _user_operation_wait_set_source(["firstAddCall"]).replace(
            "label startMain",
            "label retryStart",
        ).replace(
            "label allDone\nreturn value successfulExitCode",
            "\n".join([
                "label allDone",
                "branch if condition successfulExitCode target earlyExit",
                "branch else target retryStart",
                "label earlyExit",
                "return value successfulExitCode",
            ]),
        )
        diagnostics = _lint_source(source)

        self.assertTrue(
            any(
                diagnostic.code == "SS3509"
                and diagnostic.gapEdge == "singleStartExecution"
                and diagnostic.blocksCompile
                for diagnostic in diagnostics
            )
        )


class TestAsyncWaitSetFuzz(unittest.TestCase):
    def test_generated_user_operation_wait_sets_keep_ir_invariants(self) -> None:
        rng = random.Random(20260522)
        for iteration in range(20):
            case_count = rng.randint(1, 7)
            call_names = [f"call{iteration}_{index}Call" for index in range(case_count)]
            rng.shuffle(call_names)
            wait_name = f"nextGenerated{iteration}Result"
            source = _user_operation_wait_set_source(call_names, wait_name=wait_name)
            with self.subTest(iteration=iteration, case_count=case_count):
                ir = _emit_ir(source)
                self.assertEqual(ir.count('call i32 @"ss_async_queue_work"'), case_count)
                self.assertEqual(ir.count('call i32 @"ss_async_future_is_ready"'), case_count)
                self.assertEqual(ir.count('call i32 @"ss_async_future_await"'), case_count)
                self.assertEqual(ir.count('call i32 @"ss_async_loop_run_once"'), 1)
                self.assertEqual(ir.count("_consumed\" = alloca i1"), case_count)
                for index, call_name in enumerate(call_names):
                    self.assertIn(f'{wait_name}_{index}_{call_name}_case_check', ir)
                    self.assertIn(f'{wait_name}_{index}_{call_name}_selected', ir)


if __name__ == "__main__":
    unittest.main()
