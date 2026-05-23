import argparse
import json
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

    def test_check_payload_normalizes_compiler_diagnostic(self) -> None:
        compiler_json = json.dumps({
            "schema": "semsc.diagnostic.v1",
            "code": "SSCG001",
            "phase": "codegen.lower",
            "severity": "error",
            "message": "unresolved symbol: 'nope'",
            "blocksCompile": True,
            "primary": {
                "path": "SemanticScript/tests/tiny.sem",
                "line": 7,
                "column": 1,
                "raw": "return error nope",
                "role": "compilerError",
            },
            "semanticStack": [],
            "loweringTrace": [],
            "direction": "resolve the source symbol before lowering",
            "suggestedFixes": ["Declare or bind the missing value before returning it."],
            "backendExcerpt": "",
            "agentHint": "Prefer source edits over LLVM edits.",
        })
        with mock.patch.object(sem, "_compiler_check_probe", return_value={
            "attempted": True,
            "ok": False,
            "returnCode": 3,
            "stdout": "",
            "stderr": compiler_json,
        }):
            payload = sem._build_check_payload(Path("SemanticScript/tests/tiny.sem"), [])

        compiler_diags = [item for item in payload["diagnostics"] if item["source"] == "compiler"]
        self.assertTrue(compiler_diags)
        self.assertEqual(payload["status"], "compiler-error")
        self.assertEqual(compiler_diags[0]["code"], "SSCG001")

    def test_check_payload_normalizes_compiler_ndjson(self) -> None:
        compiler_json = "\n".join([
            json.dumps({
                "schema": "semsc.diagnostic.v1",
                "code": "SSCG001",
                "phase": "codegen.lower",
                "severity": "error",
                "message": "first compiler issue",
                "blocksCompile": True,
                "primary": {"path": "SemanticScript/tests/tiny.sem", "line": 7, "column": 1, "role": "compilerError"},
            }),
            json.dumps({
                "schema": "semsc.diagnostic.v1",
                "code": "SSCG002",
                "phase": "codegen.lower",
                "severity": "error",
                "message": "second compiler issue",
                "blocksCompile": True,
                "primary": {"path": "SemanticScript/tests/tiny.sem", "line": 8, "column": 1, "role": "compilerError"},
            }),
        ])
        with mock.patch.object(sem, "_compiler_check_probe", return_value={
            "attempted": True,
            "ok": False,
            "returnCode": 3,
            "stdout": "",
            "stderr": compiler_json,
        }):
            payload = sem._build_check_payload(Path("SemanticScript/tests/tiny.sem"), [])

        compiler_diags = [item for item in payload["diagnostics"] if item["source"] == "compiler"]
        self.assertEqual([item["code"] for item in compiler_diags], ["SSCG001", "SSCG002"])

    def test_check_payload_normalizes_parse_error(self) -> None:
        with mock.patch.object(sem, "_compiler_check_probe", return_value={
            "attempted": True,
            "ok": False,
            "returnCode": 2,
            "stdout": "",
            "stderr": "semsc: parse error in SemanticScript/tests/tiny.sem: line 3: unknown verb: 'bogus'",
        }):
            payload = sem._build_check_payload(Path("SemanticScript/tests/tiny.sem"), [])

        compiler_diags = [item for item in payload["diagnostics"] if item["source"] == "compiler"]
        self.assertTrue(compiler_diags)
        self.assertEqual(compiler_diags[0]["code"], "SEMSC_PARSE")

    def test_check_payload_omits_test_command_when_no_tests_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(
                "module demo.agent\n"
                "operation main\n"
                "output operation main ExitCode\n"
                "memory main heap no\n"
                "async main no\n"
                "purpose operation main \"demo\"\n"
                "invariant operation main \"returns zero\"\n"
                "return value 0\n",
                encoding="utf-8",
            )
            with mock.patch.object(sem, "_compiler_check_probe", return_value={
                "attempted": True,
                "ok": True,
                "returnCode": 0,
                "stdout": "",
                "stderr": "",
            }):
                payload = sem._build_check_payload(source, [])

        self.assertFalse(any(item["kind"] == "test" for item in payload["nextCommands"]))

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

    def test_slice_route_next_commands_preserve_route_anchor(self) -> None:
        args = argparse.Namespace(
            operation=None,
            route="POST:/api/todos",
            symbol=None,
            effect=None,
            capability=None,
            type_name=None,
        )
        payload = sem._slice_payload(Path("apps/taskforge-web"), args)
        self.assertTrue(payload["ok"])
        refresh = next(item for item in payload["nextCommands"] if item["kind"] == "slice")
        self.assertIn("--route POST:/api/todos", refresh["command"])

    def test_skill_registry_is_version_matched(self) -> None:
        payload = sem._skill_registry_payload()
        names = {item["name"] for item in payload}
        self.assertIn("language-core", names)
        self.assertIn("errors-effects-capabilities", names)
        language_skill = next(item for item in payload if item["name"] == "language-core")
        self.assertIn("sem", language_skill["aliases"])
        skill = sem._skill_content("language-core", include_full_content=True)
        self.assertIsNotNone(skill)
        self.assertIn("sem", skill["aliases"])
        self.assertIn("program-structure", skill["content"])

    def test_skill_content_defaults_to_summary_index(self) -> None:
        skill = sem._skill_content("language-core")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["contentMode"], "summary")
        self.assertNotIn("content", skill)
        self.assertTrue(skill["fileSummaries"])
        self.assertTrue(skill["sectionIndex"])

    def test_markdown_heading_index_ignores_indented_example_comments(self) -> None:
        headings = sem._markdown_heading_index(
            "# Real Heading\n"
            "  # example comment inside a semantic snippet\n"
            "## Another Heading\n"
        )
        self.assertEqual(
            headings,
            [
                {"line": 1, "level": 1, "title": "Real Heading"},
                {"line": 3, "level": 2, "title": "Another Heading"},
            ],
        )

    def test_compact_check_payload_limits_large_lists(self) -> None:
        payload = {
            "diagnostics": [{"code": f"SS{i:04d}"} for i in range(120)],
            "toolErrors": [{"message": str(i)} for i in range(25)],
            "errors": [{"message": str(i)} for i in range(25)],
            "unresolvedReferences": [{"name": f"ref{i}"} for i in range(70)],
        }
        compacted = sem._compact_check_payload_for_cli(Path("apps/taskforge-web"), payload, full=False)
        self.assertEqual(compacted["view"]["mode"], "compact")
        self.assertEqual(len(compacted["diagnostics"]), sem.CHECK_DIAGNOSTIC_WINDOW)
        self.assertEqual(compacted["view"]["truncation"]["diagnostics"]["total"], 120)
        self.assertEqual(len(compacted["toolErrors"]), sem.CHECK_TOOL_ERROR_WINDOW)
        self.assertEqual(len(compacted["unresolvedReferences"]), sem.CHECK_REFERENCE_WINDOW)

    def test_compact_fix_payload_limits_repairs(self) -> None:
        payload = {"repairs": [{"diagnostic": f"SS{i:04d}", "edits": []} for i in range(90)]}
        compacted = sem._compact_fix_payload_for_cli(Path("apps/taskforge-web"), payload, full=False)
        self.assertEqual(compacted["view"]["mode"], "compact")
        self.assertEqual(len(compacted["repairs"]), sem.FIX_REPAIR_WINDOW)
        self.assertEqual(compacted["view"]["truncation"]["repairs"]["total"], 90)

    def test_compact_graph_payload_limits_nodes_and_edges(self) -> None:
        payload = {
            "nodes": [{"name": f"n{i}"} for i in range(180)],
            "edges": [{"from": f"n{i}", "to": f"n{i+1}"} for i in range(260)],
        }
        compacted = sem._compact_graph_payload_for_cli(Path("apps/taskforge-web"), payload, full=False)
        self.assertEqual(compacted["view"]["mode"], "compact")
        self.assertEqual(len(compacted["nodes"]), sem.GRAPH_NODE_WINDOW)
        self.assertEqual(len(compacted["edges"]), sem.GRAPH_EDGE_WINDOW)

    def test_compact_slice_payload_limits_operation_neighborhood(self) -> None:
        payload = {
            "calledOperations": [{"target": f"op{i}"} for i in range(70)],
            "callers": [{"operation": f"caller{i}"} for i in range(50)],
            "operation": {
                "calls": [{"target": f"op{i}"} for i in range(70)],
                "controlFlow": [{"target": f"label{i}"} for i in range(60)],
                "returns": [{"value": f"v{i}"} for i in range(30)],
            },
        }
        compacted = sem._compact_slice_payload_for_cli(Path("apps/taskforge-web"), payload, full=False)
        self.assertEqual(compacted["view"]["mode"], "compact")
        self.assertEqual(len(compacted["calledOperations"]), sem.SLICE_CALL_WINDOW)
        self.assertEqual(len(compacted["callers"]), sem.SLICE_CALLER_WINDOW)
        self.assertEqual(len(compacted["operation"]["calls"]), sem.SLICE_CALL_WINDOW)
        self.assertEqual(len(compacted["operation"]["controlFlow"]), sem.SLICE_CONTROL_FLOW_WINDOW)
        self.assertEqual(len(compacted["operation"]["returns"]), sem.SLICE_RETURN_WINDOW)

    def test_skill_registry_keeps_experimental_research_opt_in(self) -> None:
        payload = sem._skill_registry_payload()
        graph_skill = next(item for item in payload if item["name"] == "graph-and-slice")
        self.assertTrue(all("experiments" not in path for path in graph_skill["files"]))
        self.assertTrue(any(item["name"] == "agent-tooling-research" for item in payload))

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
        inline_authority = next(
            suggestion for suggestion in repairs[0]["suggestions"]
            if suggestion["name"] == "inlineAuthority"
        )
        self.assertEqual(inline_authority["shape"], "authority main write console.stdout")
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

    def test_fix_plan_reports_no_repairs_when_source_is_clean(self) -> None:
        source_text = """\
module demo.agent
operation main
output operation main ExitCode
memory main heap no
async main no
purpose operation main "demo"
invariant operation main "returns zero"
return value 0
"""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(source_text, encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "status": "ok",
                "diagnostics": [],
                "summary": {"errors": 0, "warnings": 0},
            }):
                payload = sem._build_fix_plan_payload(source, [])

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no-repairs")
        self.assertEqual(payload["repairCount"], 0)
        self.assertIn("no actionable machine repair", payload["blockingReason"])

    def test_fix_plan_reports_suggestions_only_when_no_patchable_edits_exist(self) -> None:
        source_text = """\
module demo.agent
error MainError
errorCase MainError Placeholder
operation main
output operation main ExitCode
memory main heap no
async main no
purpose operation main "demo"
invariant operation main "returns zero"
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

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "suggestions-only")
        self.assertEqual(payload["patchableRepairCount"], 0)
        self.assertFalse(any(item["kind"] == "patch" for item in payload["nextCommands"]))

    def test_fix_plan_blocked_does_not_advertise_patch_application(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn value nope\n", encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "status": "compiler-error",
                "scope": {"diagnosticsScope": "file"},
                "diagnostics": [{"code": "SEMSC_PARSE"}],
                "summary": {"errors": 1, "warnings": 0},
            }):
                payload = sem._build_fix_plan_payload(source, [])

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["planUsable"])
        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(any(item["kind"] == "patch" for item in payload["nextCommands"]))

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
            self.assertTrue(any(item["kind"] == "graph" for item in payload["nextCommands"]))
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

    def test_patch_plan_deleted_target_returns_structured_error(self) -> None:
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
            source.unlink()
            payload = sem._execute_patch_plan(plan, "dry-run")

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["staleFiles"])
        self.assertIn("detail", payload["staleFiles"][0])

    def test_patch_plan_apply_reports_failed_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            original_text = "module demo.agent\noperation main\nreturn void\n"
            source.write_text(original_text, encoding="utf-8")
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
                "ok": False,
                "summary": {"errors": 1, "warnings": 0},
            }):
                payload = sem._execute_patch_plan(plan, "apply")

            self.assertFalse(payload["ok"])
            self.assertFalse(payload["applied"])
            self.assertTrue(payload["rolledBack"])
            self.assertFalse(payload["verification"]["checkOk"])
            self.assertEqual(source.read_text(encoding="utf-8"), original_text)
            self.assertTrue(any(item["kind"] == "fix" for item in payload["nextCommands"]))

    def test_patch_plan_rejects_unknown_edit_ops(self) -> None:
        plan = {
            "schemaVersion": "sem.fixPlan.v1",
            "inputPath": str(Path("SemanticScript/tests/tiny.sem").resolve()),
            "repairs": [
                {
                    "diagnostic": "SSTEST",
                    "edits": [
                        {
                            "op": "deleteUniverse",
                            "file": str(Path("SemanticScript/tests/tiny.sem").resolve()),
                        }
                    ],
                }
            ],
        }
        payload = sem._execute_patch_plan(plan, "dry-run")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["details"])
        self.assertIn("unsupported op", payload["details"][0])

    def test_patch_plan_rejects_out_of_range_replace_coordinates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            plan = {
                "schemaVersion": "sem.fixPlan.v1",
                "status": "actionable",
                "planUsable": True,
                "inputPath": str(source),
                "repairs": [
                    {
                        "diagnostic": "SSTEST",
                        "edits": [
                            {
                                "op": "replaceLine",
                                "file": str(source),
                                "line": 999,
                                "text": "return value 0",
                            }
                        ],
                    }
                ],
            }
            payload = sem._execute_patch_plan(plan, "dry-run")

        self.assertFalse(payload["ok"])
        self.assertIn("coordinates", payload["error"])
        self.assertIn("outside", payload["details"][0])

    def test_load_plan_accepts_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps({"schemaVersion": "sem.fixPlan.v1", "repairs": []}), encoding="utf-8-sig")

            payload = sem._load_plan(plan_path)

        self.assertEqual(payload["schemaVersion"], "sem.fixPlan.v1")

    def test_size_payload_reports_source_and_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")
            payload = sem._size_payload(source)

        self.assertEqual(payload["schemaVersion"], "sem.size.v1")
        self.assertEqual(payload["summary"]["operationCount"], 1)
        self.assertEqual(payload["summary"]["callCount"], 2)
        self.assertGreater(payload["summary"]["sourceBytes"], 0)

    def test_slice_symbol_payload_handles_storage_symbols(self) -> None:
        payload = sem._slice_symbol_payload(Path("SemanticScript/tests/tiny.sem"), "successfulExitCode")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["anchor"]["resolvedKind"], "storage")
        self.assertEqual(payload["declarations"][0]["kind"], "storage")
        self.assertTrue(all(not item.endswith(".py") for item in payload["relatedDocs"]))
        self.assertTrue(all(item.endswith((".py", ".test.sem", ".test.sscript")) for item in payload["relatedTests"]))

    def test_slice_route_refresh_command_preserves_route_anchor(self) -> None:
        args = argparse.Namespace(
            operation=None,
            route="POST:/api/todos",
            symbol=None,
            effect=None,
            capability=None,
            type=None,
        )
        payload = sem._slice_payload(Path("apps/taskforge-web"), args)
        self.assertTrue(payload["ok"])
        refresh = next(item for item in payload["nextCommands"] if item["kind"] == "slice")
        self.assertIn("--route POST:/api/todos", refresh["command"])

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
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["discoveredTests"], 1)
        self.assertEqual(payload["failedTests"], 0)
        self.assertEqual(payload["executedTests"], 1)
        self.assertTrue(any(item["kind"] == "check" for item in payload["nextCommands"]))

    def test_test_payload_tracks_selected_and_skipped_harnesses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            semantic_test = root / "demo.test.sem"
            semantic_test.write_text(
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
            tests_dir = root / "tests"
            tests_dir.mkdir()
            (tests_dir / "test_demo.py").write_text("print('ok')\n", encoding="utf-8")
            payload = sem._run_test_payload(root, include_python_harnesses=False)

        self.assertEqual(payload["discoveredTests"], 2)
        self.assertEqual(payload["selectedTests"], 1)
        self.assertEqual(payload["executedTests"], 1)
        self.assertEqual(payload["skippedTests"], 1)

    def test_test_payload_reports_no_tests_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            payload = sem._run_test_payload(source, include_python_harnesses=False)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "no-tests")
        self.assertEqual(payload["selectedTests"], 0)

    def test_test_payload_reports_preflight_diagnostics_for_project_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / "tests" / "test_demo.py"
            harness.parent.mkdir()
            harness.write_text("print('ok')\n", encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": False,
                "status": "diagnostics",
                "summary": {"errors": 1, "warnings": 0},
                "scope": {"diagnosticsScope": "project"},
            }), mock.patch.object(sem, "_discover_test_entries", return_value=[
                {"kind": "python", "path": harness, "name": "test_demo"}
            ]), mock.patch("subprocess.run") as run_mock:
                run_mock.return_value = mock.Mock(returncode=0, stdout="ok\n", stderr="")
                payload = sem._run_test_payload(root, include_python_harnesses=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "diagnostics")
        self.assertEqual(payload["preflightCheck"]["status"], "diagnostics")
        self.assertTrue(any(item["kind"] == "fix" for item in payload["nextCommands"]))

    def test_dev_payload_omits_test_action_when_no_tests_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(
                "module demo.agent\n"
                "operation main\n"
                "output operation main ExitCode\n"
                "memory main heap no\n"
                "async main no\n"
                "purpose operation main \"demo\"\n"
                "invariant operation main \"returns zero\"\n"
                "return value 0\n",
                encoding="utf-8",
            )
            payload = sem._dev_payload(source, trace=False)

        self.assertFalse(any(item.get("kind") == "test" for item in payload["actions"]))

    def test_dev_payload_marks_invalid_source_not_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": False,
                "status": "diagnostics",
                "summary": {"errors": 1, "warnings": 0},
                "scope": {"diagnosticsScope": "file"},
            }):
                payload = sem._dev_payload(source, trace=False)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["sourceStatus"], "diagnostics")
        self.assertFalse(any(item.get("kind") == "test" for item in payload["actions"]))

    def test_test_payload_prefers_preflight_diagnostics_over_no_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": False,
                "status": "diagnostics",
                "summary": {"errors": 1, "warnings": 0},
                "scope": {"diagnosticsScope": "file"},
            }):
                payload = sem._run_test_payload(source, include_python_harnesses=False)

        self.assertEqual(payload["status"], "diagnostics")
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["selectedTests"], 0)
        self.assertTrue(any(item["kind"] == "fix" for item in payload["nextCommands"]))

    def test_test_payload_skips_python_harnesses_when_preflight_is_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "project"
            source.mkdir()
            harness = source / "test_app.py"
            harness.write_text("print('should not run')\n", encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": False,
                "status": "diagnostics",
                "summary": {"errors": 1, "warnings": 0},
                "scope": {"diagnosticsScope": "project"},
            }), mock.patch.object(sem, "_discover_test_entries", return_value=[
                {"name": "test_app", "kind": "python", "path": harness}
            ]), mock.patch.object(sem.subprocess, "run") as run_mock:
                payload = sem._run_test_payload(source, include_python_harnesses=True)

        self.assertEqual(payload["status"], "diagnostics")
        self.assertEqual(payload["executedTests"], 0)
        self.assertEqual(payload["skippedTests"], 1)
        self.assertEqual(payload["results"][0]["status"], "skipped")
        self.assertIn("semantic preflight", payload["results"][0]["reason"])
        run_mock.assert_not_called()

    def test_graph_payload_includes_uniform_status_fields(self) -> None:
        payload = sem._graph_payload(Path("SemanticScript/tests/tiny.sem"), "calls")
        self.assertIn("ok", payload)
        self.assertIn("status", payload)
        self.assertIn("completeContext", payload)

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
