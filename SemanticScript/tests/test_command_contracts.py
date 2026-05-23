import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SEM_PATH = REPO_ROOT / "SemanticScript" / "tools" / "sem.py"
TINY_PATH = REPO_ROOT / "SemanticScript" / "tests" / "tiny.sem"
TASKFORGE_PATH = REPO_ROOT / "apps" / "taskforge-web"


def _sem_json(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SEM_PATH), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode, json.loads(proc.stdout)


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
        self.assertIn("aliasIndex", payload)
        self.assertEqual(payload["aliasIndex"]["sem"], "language-core")
        self.assertTrue(any(skill["name"] == "language-core" for skill in payload["skills"]))

    def test_skills_get_alias_contract(self) -> None:
        code, payload = _sem_json("skills", "get", "sem", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.skills.v1")
        self.assertEqual(payload["skills"][0]["name"], "language-core")
        self.assertIn("sem", payload["skills"][0]["aliases"])

    def test_check_json_contract(self) -> None:
        code, payload = _sem_json("check", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.check.v1")
        self.assertIn("diagnostics", payload)
        self.assertIn("summary", payload)
        self.assertIn("targetReadiness", payload)
        self.assertIn(payload["status"], {"ok", "ok-with-warnings", "diagnostics", "compiler-error"})
        if payload["diagnostics"]:
            diagnostic = payload["diagnostics"][0]
            self.assertIn("expected", diagnostic)
            self.assertIn("actual", diagnostic)
            self.assertIn("repair", diagnostic)
            self.assertIn("explain", diagnostic)

    def test_explain_json_contract(self) -> None:
        code, payload = _sem_json("explain", "--json", "SS3104")
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.explain.v1")
        self.assertTrue(payload["found"])
        self.assertIn("whyItMatters", payload)

    def test_graph_json_contract(self) -> None:
        code, payload = _sem_json("graph", "--kind", "calls", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.graph.v1")
        self.assertEqual(payload["kind"], "calls")
        self.assertIn("edges", payload)

    def test_slice_json_contract(self) -> None:
        code, payload = _sem_json("slice", "--operation", "healthHandler", "--json", str(TASKFORGE_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.slice.v1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"]["name"], "healthHandler")

    def test_fix_json_contract(self) -> None:
        code, payload = _sem_json("fix", "--plan", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.fixPlan.v1")
        self.assertIn("repairs", payload)
        self.assertIn("preconditions", payload)

    def test_size_json_contract(self) -> None:
        code, payload = _sem_json("size", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.size.v1")
        self.assertIn("summary", payload)
        self.assertIn("retainedHelpers", payload)

    def test_dev_json_contract(self) -> None:
        code, payload = _sem_json("dev", "--json", str(TINY_PATH))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.dev.v1")
        self.assertEqual(payload["mode"], "watch-plan")
        self.assertIn("watch", payload)

    def test_test_json_contract(self) -> None:
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
            code, payload = _sem_json("test", "--json", str(source))
        self.assertEqual(code, 0)
        self.assertEqual(payload["schemaVersion"], "sem.test.v1")
        self.assertEqual(payload["discoveredTests"], 1)

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


if __name__ == "__main__":
    unittest.main()
