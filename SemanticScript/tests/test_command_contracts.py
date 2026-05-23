import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from functools import lru_cache
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SEM_PATH = REPO_ROOT / "SemanticScript" / "tools" / "sem.py"
TINY_PATH = REPO_ROOT / "SemanticScript" / "tests" / "tiny.sem"
AGENT_DEMO_TEST_PATH = REPO_ROOT / "SemanticScript" / "tests" / "agent_cli_demo.test.sem"
TASKFORGE_PATH = REPO_ROOT / "apps" / "taskforge-web"
TASKFORGE_MAIN_PATH = TASKFORGE_PATH / "main.sem"
AUCTION_SERVER_PATH = REPO_ROOT / "experiments" / "realtime-auction-arena" / "server"
AUCTION_SERVER_MAIN_PATH = AUCTION_SERVER_PATH / "src" / "main.sem"


@lru_cache(maxsize=256)
def _sem_json_cached(*args: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(SEM_PATH), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
    )
    return proc.returncode, proc.stdout


def _sem_json(*args: str) -> tuple[int, dict]:
    code, stdout = _sem_json_cached(*args)
    return code, copy.deepcopy(json.loads(stdout))


class TestSemCommandContracts(unittest.TestCase):
    def test_version_json_contract(self) -> None:
        code, payload = _sem_json("--version", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.version.v1")
        self.assertIn("runtimeFeatureFlags", payload)
        self.assertIn("syntax", payload)

    def test_doctor_json_contract(self) -> None:
        code, payload = _sem_json("doctor", "--json")
        self.assertIn(code, {0, 1})
        self.assertEqual(payload["schemaVersion"], "sem.doctor.v0")
        self.assertIn("checks", payload)

    def test_readiness_json_contract(self) -> None:
        code, payload = _sem_json("readiness", "--json", str(TINY_PATH))
        self.assertIn(code, {0, 1})
        self.assertEqual(payload["schemaVersion"], "sem.readiness.v1")
        self.assertIn("status", payload)

    def test_skills_json_contract(self) -> None:
        code, payload = _sem_json("skills", "list", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.skills.v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertIn("aliasIndex", payload)
        self.assertEqual(payload["aliasIndex"]["sem"], "language-core")
        self.assertTrue(any(skill["name"] == "language-core" for skill in payload["skills"]))

    def test_skills_get_alias_contract(self) -> None:
        code, payload = _sem_json("skills", "get", "sem", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.skills.v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["skills"][0]["name"], "language-core")
        self.assertIn("sem", payload["skills"][0]["aliases"])
        self.assertEqual(payload["contentMode"], "summary")
        self.assertEqual(payload["skills"][0]["contentMode"], "summary")
        self.assertIn("sectionIndex", payload["skills"][0])
        self.assertNotIn("content", payload["skills"][0])
        self.assertFalse(payload["nextCommands"][0]["replayable"])
        self.assertIn("requiredArgs", payload["nextCommands"][0])

    def test_skills_get_full_contract(self) -> None:
        code, payload = _sem_json("skills", "get", "sem", "--full", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["contentMode"], "full")
        self.assertIn("content", payload["skills"][0])

    def test_skills_get_reports_missing_names(self) -> None:
        code, payload = _sem_json("skills", "get", "sem", "nope", "--json")
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "partial")
        self.assertIn("nope", payload["missingNames"])

    def test_check_json_contract(self) -> None:
        code, payload = _sem_json("check", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.check.v1")
        self.assertIn("diagnostics", payload)
        self.assertIn("nextCommands", payload)
        self.assertTrue(all("argv" in item for item in payload["nextCommands"]))
        self.assertTrue(all("replayable" in item for item in payload["nextCommands"]))
        self.assertIn("summary", payload)
        self.assertNotIn("targetReadiness", payload)
        self.assertIn(payload["status"], {"ok", "ok-with-warnings", "lint-diagnostics", "compiler-error", "tool-error"})
        if payload["diagnostics"]:
            diagnostic = payload["diagnostics"][0]
            self.assertIn("expected", diagnostic)
            self.assertIn("actual", diagnostic)
            self.assertIn("repair", diagnostic)
            self.assertIn("explain", diagnostic)

    def test_check_with_readiness_json_contract(self) -> None:
        code, payload = _sem_json("check", "--json", "--with-readiness", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertIn("targetReadiness", payload)

    def test_replayable_next_command_argv_executes_from_payload(self) -> None:
        code, payload = _sem_json("check", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        replayable = next(item for item in payload["nextCommands"] if item["kind"] == "graph" and item["replayable"])
        proc = subprocess.run(
            replayable["argv"],
            cwd=replayable["cwd"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertIn(proc.returncode, {0, 1})
        self.assertTrue(proc.stdout.strip())
        followup_payload = json.loads(proc.stdout)
        self.assertIn("schemaVersion", followup_payload)

    def test_check_accepts_trailing_json_flag_after_path(self) -> None:
        code, payload = _sem_json("check", str(AGENT_DEMO_TEST_PATH), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.check.v1")
        self.assertEqual(payload["status"], "ok")

    def test_taskforge_check_json_compacts_project_payload(self) -> None:
        code, payload = _sem_json("check", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 1)
        self.assertEqual(payload["view"]["mode"], "compact")
        self.assertIn("diagnostics", payload["view"]["truncation"])
        self.assertGreater(
            payload["view"]["truncation"]["diagnostics"]["total"],
            payload["view"]["truncation"]["diagnostics"]["returned"],
        )

    def test_explain_json_contract(self) -> None:
        code, payload = _sem_json("explain", "--json", "SS3104")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.explain.v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["found"])
        self.assertIn("whyItMatters", payload)
        self.assertIn("nextCommands", payload)

    def test_graph_json_contract(self) -> None:
        code, payload = _sem_json("graph", "--kind", "calls", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.graph.v1")
        self.assertEqual(payload["kind"], "calls")
        self.assertIn("edges", payload)
        self.assertIn("nextCommands", payload)
        self.assertFalse(any("<" in item["command"] for item in payload["nextCommands"]))

    def test_graph_summary_next_commands_are_concrete(self) -> None:
        code, payload = _sem_json("graph", "--kind", "summary", "--json", str(TASKFORGE_MAIN_PATH))
        self.assertEqual(code, 0)
        self.assertFalse(any("<" in item["command"] for item in payload["nextCommands"]))

    def test_auction_server_source_graph_followup_uses_project_surface(self) -> None:
        code, payload = _sem_json("graph", "--kind", "summary", "--json", str(AUCTION_SERVER_MAIN_PATH))
        self.assertEqual(code, 0)
        followup = next(item for item in payload["nextCommands"] if item["kind"] == "graph")
        self.assertIn(str(AUCTION_SERVER_PATH), followup["command"])
        self.assertNotIn(str(AUCTION_SERVER_MAIN_PATH), followup["command"])

    def test_auction_server_routes_graph_has_nodes(self) -> None:
        code, payload = _sem_json("graph", "--kind", "routes", "--json", str(AUCTION_SERVER_PATH))
        self.assertEqual(code, 0)
        self.assertGreater(payload["summary"]["nodeCount"], 0)
        self.assertTrue(any(node["kind"] == "route" for node in payload["nodes"]))

    def test_slice_json_contract(self) -> None:
        code, payload = _sem_json("slice", "--operation", "healthHandler", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.slice.v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"]["name"], "healthHandler")
        self.assertIn("inputPath", payload)
        self.assertIn("nextCommands", payload)
        self.assertTrue(all("argv" in item for item in payload["nextCommands"]))

    def test_slice_rejects_conflicting_anchors(self) -> None:
        code, payload = _sem_json("slice", "--operation", "healthHandler", "--route", "POST:/api/todos", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 1)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["anchorOptions"], ["operation", "route"])

    def test_readme_route_slice_example_is_valid(self) -> None:
        code, payload = _sem_json("slice", "--route", "POST:/api/todos", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["route"]["path"], "/api/todos")

    def test_readme_symbol_slice_example_is_valid(self) -> None:
        code, payload = _sem_json("slice", "--symbol", "serverPortNumber", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["symbolType"], "storage")

    def test_auction_server_route_slice_from_source_file_resolves_handler(self) -> None:
        code, payload = _sem_json("slice", "--route", "GET:/api/v1/auctions/:auctionId/events", "--json", str(AUCTION_SERVER_MAIN_PATH))
        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["scope"]["retrievalScope"], "project")
        self.assertEqual(payload["operation"]["name"], "auctionEventsHandler")
        self.assertTrue(payload["handlerFile"].endswith("event_context.sem"))

    def test_fix_json_contract(self) -> None:
        code, payload = _sem_json("fix", "--plan", "--json", str(TINY_PATH))
        self.assertEqual(code, 1)
        self.assertEqual(payload["schemaVersion"], "sem.fixPlan.v1")
        self.assertEqual(payload["status"], "no-repairs")
        self.assertFalse(payload["planUsable"])
        self.assertIn("repairs", payload)
        self.assertIn("preconditions", payload)
        self.assertIn("nextCommands", payload)
        self.assertEqual(payload["patchableRepairCount"], 0)

    def test_fix_include_warnings_json_contract(self) -> None:
        code, payload = _sem_json("fix", "--plan", "--json", "--include-warnings", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.fixPlan.v1")
        self.assertEqual(payload["status"], "mixed")
        self.assertTrue(payload["planUsable"])
        self.assertTrue(any(not item["replayable"] and item.get("artifactInputs") for item in payload["nextCommands"]))

    def test_fix_accepts_trailing_flags_after_path(self) -> None:
        code, payload = _sem_json("fix", str(TINY_PATH), "--plan", "--json", "--include-warnings")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.fixPlan.v1")
        self.assertEqual(payload["status"], "mixed")

    def test_taskforge_fix_json_compacts_project_payload(self) -> None:
        code, payload = _sem_json("fix", "--plan", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 1)
        self.assertEqual(payload["view"]["mode"], "compact")
        self.assertIn("repairs", payload["view"]["truncation"])

    def test_auction_server_fix_reports_mixed_status(self) -> None:
        code, payload = _sem_json("fix", "--plan", "--json", str(AUCTION_SERVER_PATH))
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "suggestions-only")
        self.assertFalse(payload["planUsable"])
        self.assertEqual(payload["patchableRepairCount"], 0)
        self.assertIn("focusAnchors", payload)
        self.assertGreater(len(payload["focusAnchors"]["topFiles"]), 0)
        self.assertFalse(any(item["kind"] == "patch" for item in payload["nextCommands"]))

    def test_size_json_contract(self) -> None:
        code, payload = _sem_json("size", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.size.v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertIn("scope", payload)
        self.assertIn("summary", payload)
        self.assertIn("retainedHelpers", payload)
        self.assertIn("nextCommands", payload)

    def test_context_json_contract(self) -> None:
        code, payload = _sem_json("context", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.context.v1")
        self.assertIn("project", payload)

    def test_symbols_json_contract(self) -> None:
        code, payload = _sem_json("symbols", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.symbols.v1")
        self.assertIn("summary", payload)

    def test_fmt_check_contract(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SEM_PATH), "fmt", "--check", str(AGENT_DEMO_TEST_PATH)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_dev_json_contract(self) -> None:
        code, payload = _sem_json("dev", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.dev.v1")
        self.assertEqual(payload["mode"], "watch-plan")
        self.assertIn("watch", payload)
        self.assertIn("nextCommands", payload)

    def test_taskforge_dev_reports_blocked_project_watch_plan(self) -> None:
        code, payload = _sem_json("dev", "--json", str(TASKFORGE_MAIN_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.dev.v1")
        self.assertEqual(payload["status"], "quality-diagnostics")
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["buildableSource"])
        normalized_watch_files = "\n".join(path.replace("\\", "/") for path in payload["watch"]["files"])
        self.assertIn("components/main.sem", normalized_watch_files)
        self.assertIn("pages/main.sem", normalized_watch_files)
        self.assertEqual(payload["surfaceShift"]["from"], "source-file")
        self.assertEqual(payload["surfaceShift"]["to"], "project")
        graph_action = next(item for item in payload["actions"] if item["kind"] == "graph")
        self.assertIn("graph --kind routes", graph_action["command"])
        self.assertIn("routes are present", payload["restart"]["reason"])

    def test_taskforge_check_and_dev_surface_shift_agree(self) -> None:
        _, check_payload = _sem_json("check", "--json", str(TASKFORGE_MAIN_PATH))
        _, dev_payload = _sem_json("dev", "--json", str(TASKFORGE_MAIN_PATH))
        self.assertEqual(check_payload["surfaceShift"]["from"], "source-file")
        self.assertEqual(check_payload["surfaceShift"]["to"], "project")
        self.assertEqual(dev_payload["surfaceShift"]["from"], "source-file")
        self.assertEqual(dev_payload["surfaceShift"]["to"], "project")

    def test_test_json_contract(self) -> None:
        code, payload = _sem_json("test", "--json", str(AGENT_DEMO_TEST_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.test.v1")
        self.assertEqual(payload["status"], "passed")
        self.assertEqual(payload["discoveredTests"], 1)
        self.assertIn("nextCommands", payload)

    def test_test_json_contract_reports_no_tests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            code, payload = _sem_json("test", "--json", str(source))
            self.assertEqual(code, 1)
            self.assertEqual(payload["schemaVersion"], "sem.test.v1")
            self.assertEqual(payload["status"], "no-tests")
            self.assertEqual(payload["selectedTests"], 0)

    def test_patch_dry_run_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            plan = Path(tmp) / "plan.json"
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            plan.write_text(json.dumps({
                "schemaVersion": "sem.fixPlan.v1",
                "inputPath": str(source),
                "preconditions": {"fileHashes": {str(source): source_hash}},
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
            }), encoding="utf-8")
            code, payload = _sem_json("patch", "--dry-run", "--json", str(plan))
            self.assertEqual(code, 0)
            self.assertEqual(payload["schemaVersion"], "sem.patch.v1")
            self.assertEqual(payload["mode"], "dry-run")
            self.assertEqual(payload["inputPlanPath"], str(plan.resolve()))
            self.assertFalse(payload["applied"])
            self.assertIn("nextCommands", payload)
            apply_entry = next(item for item in payload["nextCommands"] if item["kind"] == "patch")
            self.assertEqual(apply_entry["argv"][-1], str(plan.resolve()))
            self.assertTrue(apply_entry["replayable"])

    def test_patch_accepts_utf8_bom_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps({
                "schemaVersion": "sem.fixPlan.v1",
                "status": "actionable",
                "planUsable": True,
                "inputPath": str(source),
                "preconditions": {"fileHashes": {}},
                "repairs": [{"diagnostic": "SSTEST", "edits": []}],
            }), encoding="utf-8-sig")
            code, payload = _sem_json("patch", "--dry-run", "--json", str(plan))

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])

    def test_patch_dry_run_stale_contract_is_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            plan = Path(tmp) / "plan.json"
            plan.write_text(json.dumps({
                "schemaVersion": "sem.fixPlan.v1",
                "inputPath": str(source),
                "preconditions": {"fileHashes": {str(source): source_hash}},
                "repairs": [],
            }), encoding="utf-8")
            source.write_text("module demo.agent\noperation main\nreturn value changed\n", encoding="utf-8")
            code, payload = _sem_json("patch", "--dry-run", "--json", str(plan))
            self.assertEqual(code, 1)
            self.assertFalse(payload["ok"])

    def test_patch_missing_plan_returns_structured_error(self) -> None:
        missing = str((REPO_ROOT / "missing-plan.json").resolve())
        proc = subprocess.run(
            [sys.executable, str(SEM_PATH), "patch", "--dry-run", "--json", missing],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 1)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["schemaVersion"], "sem.patch.v1")
        self.assertFalse(payload["ok"])

    def test_agent_demo_fixture_check_and_test_are_green(self) -> None:
        check_code, check_payload = _sem_json("check", "--json", str(AGENT_DEMO_TEST_PATH))
        test_code, test_payload = _sem_json("test", "--json", str(AGENT_DEMO_TEST_PATH))
        self.assertEqual(check_code, 0)
        self.assertEqual(check_payload["status"], "ok")
        self.assertEqual(test_code, 0)
        self.assertEqual(test_payload["status"], "passed")

    def test_taskforge_test_reports_preflight_diagnostics(self) -> None:
        check_code, check_payload = _sem_json("check", "--json", str(TASKFORGE_PATH))
        test_code, test_payload = _sem_json("test", "--json", str(TASKFORGE_PATH))
        self.assertEqual(check_code, 1)
        self.assertIn(check_payload["status"], {"lint-diagnostics", "compiler-error", "tool-error"})
        self.assertEqual(test_code, 1)
        self.assertEqual(test_payload["status"], "diagnostics")
        self.assertFalse(test_payload["ok"])
        self.assertFalse(test_payload["preflightCheck"]["ok"])
        self.assertEqual(test_payload["executedTests"], 0)
        self.assertEqual(test_payload["skippedTests"], 1)
        self.assertIn("semantic preflight", test_payload["results"][0]["reason"])

    def test_taskforge_test_skip_python_harnesses_still_reports_preflight_diagnostics(self) -> None:
        test_code, test_payload = _sem_json("test", "--json", "--skip-python-harnesses", str(TASKFORGE_PATH))
        self.assertEqual(test_code, 1)
        self.assertEqual(test_payload["status"], "diagnostics")
        self.assertFalse(test_payload["ok"])
        self.assertEqual(test_payload["executedTests"], 0)
        self.assertEqual(test_payload["skippedTests"], 1)
        self.assertFalse(test_payload["preflightCheck"]["ok"])

    def test_auction_server_test_discovers_python_harnesses_when_runtime_harnesses_are_disabled(self) -> None:
        test_code, test_payload = _sem_json("test", "--json", "--skip-python-harnesses", str(AUCTION_SERVER_PATH))
        self.assertEqual(test_code, 0)
        self.assertEqual(test_payload["status"], "passed")
        self.assertGreater(test_payload["discoveredTests"], 26)
        self.assertTrue(test_payload["preflightCheck"]["ok"])
        self.assertIn(test_payload["preflightStatus"], {"ok", "ok-with-warnings"})
        self.assertTrue(any(result["name"] == "api_tests" for result in test_payload["results"]))
        self.assertTrue(any(result["status"] == "skipped" and result["kind"] == "python" for result in test_payload["results"]))
        self.assertEqual(test_payload["coverageSummary"]["runtimeHarnessesExecuted"], 0)
        self.assertEqual(test_payload["coverageSummary"]["runtimeSignalStatus"], "not-requested")
        self.assertEqual(test_payload["runtimeHarnessStatus"], "not-requested")

    def test_auction_server_test_allow_red_preflight_flag_still_runs_runtime_harnesses(self) -> None:
        test_code, test_payload = _sem_json("test", "--json", "--allow-red-preflight-harnesses", str(AUCTION_SERVER_PATH))
        self.assertEqual(test_code, 0)
        self.assertEqual(test_payload["status"], "passed")
        self.assertTrue(test_payload["preflightCheck"]["ok"])
        self.assertIn(test_payload["preflightStatus"], {"ok", "ok-with-warnings"})
        self.assertGreater(test_payload["coverageSummary"]["runtimeHarnessesExecuted"], 0)
        self.assertEqual(test_payload["coverageSummary"]["runtimeSignalStatus"], "executed")
        self.assertEqual(test_payload["compositeStatus"], "ok/runtime-passed")
        self.assertEqual(test_payload["runtimeHarnessStatus"], "passed")
        self.assertGreater(test_payload["coverageSummary"]["semanticContractsExecuted"], 0)


if __name__ == "__main__":
    unittest.main()
