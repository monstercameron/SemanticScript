import argparse
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from SemanticScript.shared.call_contracts import (
    CALL_CHANNEL_ERROR,
    CALL_CHANNEL_OK,
    CALL_CHANNEL_VALUE,
    CALL_CHANNEL_VOID,
    CALL_CLASS_FALLIBLE_ORDINARY,
    CALL_CLASS_ORDINARY_VALUE,
    CALL_CLASS_RESULT,
    CALL_CLASS_VOID,
    call_class,
    disposition_channels_for_call,
)
from SemanticScript.tools import sem


NEW_SYNTAX_SOURCE = """\
module demo.agent
operation main
input operation main count I64
output operation main ExitCode
effect main write console.stdout
authority main write console.stdout
call writeCall console.writeIntegerLine
argument writeCall value I64 count
run writeCall
ignore value source writeCall type I32
call checkedCall math.checkedMultiplyI64
argument checkedCall left I64 count
argument checkedCall right I64 count
run checkedCall
bind ok product I64 checkedCall
bind error overflow MainError checkedCall
branch error source checkedCall target failed
branch else target done
jump target done
label done
return value product
label failed
return error overflow
"""


class TestSemAgentPayloads(unittest.TestCase):
    def test_symbols_payload_uses_cutover_row_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")

            payload = sem._symbol_graph_payload(source)

        self.assertEqual(payload["schemaVersion"], "sem.symbols.v1")
        self.assertFalse(payload["syntax"]["normalCommandsAutoMigrateOldSyntax"])
        operation = payload["files"][0]["operations"][0]
        self.assertEqual(operation["inputs"][0]["subjectKind"], "operation")
        self.assertEqual(operation["effects"][0]["action"], "write")
        self.assertEqual(operation["authorities"][0]["action"], "write")

        write_call = operation["calls"][0]
        self.assertIn("arguments", write_call)
        self.assertNotIn("args", write_call)
        self.assertEqual(write_call["arguments"][0], {
            "parameter": "value",
            "type": "I64",
            "value": "count",
            "location": write_call["arguments"][0]["location"],
        })
        self.assertEqual(write_call["disposition"]["ignore"]["value"][0]["source"], "writeCall")
        self.assertNotIn("ignoreValue", write_call["disposition"])

        checked_call = operation["calls"][1]
        self.assertEqual(
            [item["name"] for item in checked_call["disposition"]["bind"]["ok"]],
            ["product"],
        )
        self.assertEqual(
            [item["name"] for item in checked_call["disposition"]["bind"]["error"]],
            ["overflow"],
        )
        self.assertEqual(
            checked_call["disposition"]["branchError"][0]["kind"],
            "branch error",
        )
        self.assertNotIn("bindOk", checked_call["disposition"])
        self.assertNotIn("branchIfError", checked_call["disposition"])
        self.assertEqual(
            [edge["kind"] for edge in operation["controlFlow"]],
            ["branch error", "branch else", "jump"],
        )
        self.assertEqual(
            [ret["variant"] for ret in operation["returns"]],
            ["value", "error"],
        )

    def test_context_payload_declares_no_implicit_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")

            payload = sem._build_context_payload(source)

        self.assertEqual(payload["schemaVersion"], "sem.context.v1")
        self.assertFalse(payload["supportedSyntax"]["normalCommandsAutoMigrateOldSyntax"])
        self.assertEqual(
            payload["supportedSyntax"]["currentRows"]["argument"],
            "argument CALL PARAM TYPE VALUE",
        )

    def test_check_command_delegates_without_migration_flag(self) -> None:
        args = argparse.Namespace(path="example.sem", compiler_args=[])
        with mock.patch.object(sem, "_run_compiler", return_value=0) as run_compiler:
            result = sem.command_check(args)

        self.assertEqual(result, 0)
        compiler_args = run_compiler.call_args.args[1]
        self.assertEqual(compiler_args[:2], ["--parse-only", "--lint"])
        self.assertNotIn("migrate", " ".join(compiler_args).lower())
        self.assertNotIn("convert", " ".join(compiler_args).lower())

    def test_check_payload_is_machine_readable(self) -> None:
        with mock.patch.object(sem, "_compiler_check_probe", return_value={
            "attempted": True,
            "ok": True,
            "returnCode": 0,
            "stdout": "",
            "stderr": "",
        }):
            payload = sem._build_check_payload(Path("SemanticScript/tests/tiny.sem"), [])

        self.assertEqual(payload["schemaVersion"], "sem.check.v1")
        self.assertIn("diagnostics", payload)
        self.assertIn("summary", payload)
        self.assertIn("targetReadiness", payload)
        self.assertIn(payload["targetReadiness"]["status"], {"supported", "partial", "blocked"})
        self.assertIn(payload["status"], {"ok", "ok-with-warnings"})
        diagnostic = payload["diagnostics"][0]
        self.assertIn("expected", diagnostic)
        self.assertIn("actual", diagnostic)
        self.assertIn("span", diagnostic)
        self.assertIn("repair", diagnostic)
        self.assertTrue(payload["nextCommands"])
        self.assertTrue(any(item["kind"] == "explain" for item in payload["nextCommands"]))

    def test_graph_payload_calls_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")

            payload = sem._graph_payload(source, "calls")

        self.assertEqual(payload["schemaVersion"], "sem.graph.v1")
        self.assertEqual(payload["kind"], "calls")
        self.assertEqual(payload["summary"]["edgeCount"], 2)
        self.assertEqual(payload["edges"][0]["fromOperation"], "main")

    def test_graph_payload_auth_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")

            payload = sem._graph_payload(source, "auth")

        self.assertEqual(payload["schemaVersion"], "sem.graph.v1")
        self.assertEqual(payload["kind"], "auth")
        edge_kinds = {edge["kind"] for edge in payload["edges"]}
        self.assertIn("authority", edge_kinds)

    def test_readiness_payload_reports_status(self) -> None:
        payload = sem._readiness_payload(Path("SemanticScript/tests/tiny.sem"))
        self.assertEqual(payload["schemaVersion"], "sem.readiness.v1")
        self.assertIn(payload["status"], {"supported", "partial", "blocked"})
        self.assertIn("requestedTargets", payload)
        self.assertTrue(any(item["kind"] == "doctor" for item in payload["nextCommands"]))

    def test_dev_payload_is_watch_plan(self) -> None:
        payload = sem._dev_payload(Path("SemanticScript/tests/tiny.sem"), trace=True)
        self.assertEqual(payload["schemaVersion"], "sem.dev.v1")
        self.assertEqual(payload["mode"], "watch-plan")
        self.assertTrue(payload["watch"]["planOnly"])
        self.assertTrue(payload["trace"]["requested"])

    def test_slice_operation_payload_includes_neighborhood(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")

            payload = sem._slice_operation_payload(source, "main")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["anchor"]["kind"], "operation")
        self.assertEqual(payload["operation"]["name"], "main")
        self.assertGreaterEqual(len(payload["calledOperations"]), 2)
        self.assertIn("purposes", payload)
        self.assertIn("invariants", payload)

    def test_skill_registry_is_version_matched(self) -> None:
        payload = sem._skill_registry_payload()
        names = {item["name"] for item in payload}
        self.assertIn("language-core", names)
        self.assertIn("errors-effects-capabilities", names)
        language_skill = next(item for item in payload if item["name"] == "language-core")
        self.assertIn("sem", language_skill["aliases"])
        skill = sem._skill_content("language-core")
        self.assertIsNotNone(skill)
        self.assertIn("sem", skill["aliases"])
        self.assertIn("program-structure", skill["content"])

    def test_explain_payload_finds_linter_codes(self) -> None:
        payload = sem._diagnostic_explain_payload("SS3104")
        self.assertTrue(payload["found"])
        self.assertEqual(payload["code"], "SS3104")
        self.assertTrue(payload["references"])
        self.assertTrue(payload["whyItMatters"])
        self.assertTrue(payload["commonFixes"])
        self.assertTrue(payload["nextCommands"])

    def test_fix_plan_generates_inline_authority_edit(self) -> None:
        source_text = """\
module demo.agent
operation main
input operation main request Console
output operation main ExitCode
effect main write console.stdout
memory main heap no
async main no
return value request
"""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(source_text, encoding="utf-8")
            with mock.patch.object(sem, "_compiler_check_probe", return_value={
                "attempted": True,
                "ok": True,
                "returnCode": 0,
                "stdout": "",
                "stderr": "",
            }):
                payload = sem._build_fix_plan_payload(source, [])

        repairs = [repair for repair in payload["repairs"] if repair["diagnostic"] == "SS3104"]
        self.assertTrue(repairs)
        authority_edit = repairs[0]["edits"][0]
        self.assertEqual(authority_edit["op"], "insertAfterLine")
        self.assertIn("authority main write console.stdout", authority_edit["text"])
        self.assertTrue(any(item["kind"] == "patch" for item in payload["nextCommands"]))

    def test_fix_plan_marks_metadata_repairs_as_human_review(self) -> None:
        source_text = """\
module demo.agent
storage module mutable accountLookupRevision I64 zeroCount
storage module immutable zeroCount I64 0
storage module immutable nextAccountLookupRevision I64 1
operation main
output operation main ExitCode
memory main heap no
async main no
set module accountLookupRevision nextAccountLookupRevision
return value 0
"""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(source_text, encoding="utf-8")
            with mock.patch.object(sem, "_compiler_check_probe", return_value={
                "attempted": True,
                "ok": True,
                "returnCode": 0,
                "stdout": "",
                "stderr": "",
            }):
                payload = sem._build_fix_plan_payload(source, [])

        repair_by_code = {repair["diagnostic"]: repair for repair in payload["repairs"]}
        self.assertEqual(repair_by_code["SS3101"]["fixSafety"], "requires-human-review")
        self.assertEqual(repair_by_code["SS3102"]["fixSafety"], "requires-human-review")

    def test_patch_plan_apply_updates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            plan = {
                "schemaVersion": "sem.fixPlan.v1",
                "inputPath": str(source),
                "repairs": [
                    {
                        "diagnostic": "SSTEST",
                        "edits": [
                            {
                                "op": "insertAfterLine",
                                "file": str(source),
                                "afterLine": 2,
                                "text": 'purpose operation main "demo"',
                            }
                        ],
                    }
                ],
            }
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": True,
                "summary": {"errors": 0, "warnings": 0},
            }):
                payload = sem._execute_patch_plan(plan, "apply")

            self.assertEqual(payload["schemaVersion"], "sem.patch.v1")
            self.assertEqual(payload["mode"], "apply")
            self.assertIn(str(source), payload["filesChanged"])
            self.assertTrue(any(item["kind"] == "test" for item in payload["nextCommands"]))
            updated = source.read_text(encoding="utf-8")
            self.assertIn('purpose operation main "demo"', updated)

    def test_patch_plan_rejects_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            original_hash = sem._file_sha256(source)
            plan = {
                "schemaVersion": "sem.fixPlan.v1",
                "inputPath": str(source),
                "preconditions": {"fileHashes": {str(source): original_hash}},
                "repairs": [
                    {
                        "diagnostic": "SSTEST",
                        "edits": [
                            {
                                "op": "insertAfterLine",
                                "file": str(source),
                                "afterLine": 2,
                                "text": 'purpose operation main "demo"',
                            }
                        ],
                    }
                ],
            }
            source.write_text("module demo.agent\noperation main\nreturn value changed\n", encoding="utf-8")
            payload = sem._execute_patch_plan(plan, "apply")
            self.assertFalse(payload["ok"])
            self.assertTrue(payload["staleFiles"])
            self.assertTrue(any(item["kind"] == "fix" for item in payload["nextCommands"]))

    def test_size_payload_reports_source_and_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")
            payload = sem._size_payload(source)

        self.assertEqual(payload["schemaVersion"], "sem.size.v1")
        self.assertEqual(payload["summary"]["operationCount"], 1)
        self.assertEqual(payload["summary"]["callCount"], 2)
        self.assertGreater(payload["summary"]["sourceBytes"], 0)

    def test_test_payload_runs_semantic_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "demo.test.sem"
            source.write_text(
                "project DemoTest\n"
                "target console\n"
                "runtime AgentRuntime 0.1\n"
                "entry console main\n"
                "operation main\n"
                "output operation main ExitCode\n"
                "memory main heap no\n"
                "async main no\n"
                "purpose operation main \"demo test\"\n"
                "invariant operation main \"returns zero\"\n"
                "return value 0\n",
                encoding="utf-8",
            )
            payload = sem._run_test_payload(source, include_python_harnesses=False)
        self.assertEqual(payload["schemaVersion"], "sem.test.v1")
        self.assertEqual(payload["discoveredTests"], 1)
        self.assertEqual(payload["failedTests"], 0)
        self.assertTrue(any(item["kind"] == "check" for item in payload["nextCommands"]))

    def test_main_supports_version_json(self) -> None:
        with mock.patch("sys.stdout") as stdout:
            result = sem.main(["version", "--json"])
        self.assertEqual(result, 0)
        self.assertTrue(stdout.write.called)

        with mock.patch("sys.stdout") as stdout:
            result = sem.main(["--version", "--json"])
        self.assertEqual(result, 0)
        self.assertTrue(stdout.write.called)


class TestCallContracts(unittest.TestCase):
    def test_call_classes_use_cutover_channel_vocabulary(self) -> None:
        self.assertEqual(call_class("math.addI64", "I64"), CALL_CLASS_ORDINARY_VALUE)
        self.assertEqual(call_class("console.writeLine", "I32"), CALL_CLASS_RESULT)
        self.assertEqual(call_class("c.fopen", "COpaqueMemoryAddress"), CALL_CLASS_FALLIBLE_ORDINARY)
        self.assertEqual(call_class("user.flush", "Void"), CALL_CLASS_VOID)

    def test_disposition_channels_match_call_class(self) -> None:
        self.assertEqual(disposition_channels_for_call("math.addI64", "I64"), frozenset({CALL_CHANNEL_VALUE}))
        self.assertEqual(disposition_channels_for_call("console.writeLine", "I32"), frozenset({
            CALL_CHANNEL_OK,
            CALL_CHANNEL_ERROR,
        }))
        self.assertEqual(disposition_channels_for_call("c.fopen", "COpaqueMemoryAddress"), frozenset({
            CALL_CHANNEL_VALUE,
            CALL_CHANNEL_ERROR,
        }))
        self.assertEqual(disposition_channels_for_call("user.flush", "Void"), frozenset({CALL_CHANNEL_VOID}))


if __name__ == "__main__":
    unittest.main()
