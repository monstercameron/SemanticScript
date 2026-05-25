import argparse
import io
import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
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
input operation main count Int64
output operation main ExitCode
effect main write console.stdout
authority main write console.stdout
call writeCall console.writeIntegerLine
argument writeCall value Int64 count
run writeCall
ignore value source writeCall type Int32
call checkedCall math.checkedMultiplyInt64
argument checkedCall left Int64 count
argument checkedCall right Int64 count
run checkedCall
bind ok product Int64 checkedCall
bind error overflow MainError checkedCall
branch error source checkedCall target failed
branch else target done
jump target done
label done
return value product
label failed
return error overflow
"""

REPO_ROOT = Path(__file__).resolve().parents[2]
AUCTION_SERVER_PATH = REPO_ROOT / "experiments" / "realtime-auction-arena" / "server"
AUCTION_SERVER_MAIN_PATH = AUCTION_SERVER_PATH / "src" / "main.sem"


def fake_semantic_embedding(text: str, model_name: str, *, query: bool = False, **kwargs) -> list[float]:
    vector = [0.0] * sem.DOCS_DEFAULT_EMBEDDING_DIMENSIONS
    for token in re.findall(r"[A-Za-z0-9]+", text.lower()):
        bucket = sum(ord(char) for char in token) % sem.DOCS_DEFAULT_EMBEDDING_DIMENSIONS
        vector[bucket] += 1.0
    norm = sum(value * value for value in vector) ** 0.5
    return [value / norm for value in vector] if norm else vector


def load_sem_launcher():
    spec = importlib.util.spec_from_file_location(
        "sem_release_launcher",
        REPO_ROOT / "packaging" / "pyinstaller" / "sem_launcher.py",
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            "type": "Int64",
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

    def test_docs_list_reads_typed_comment_summaries(self) -> None:
        payload = sem._docs_payload("list", module_name="http", summary_tag="rationale")

        self.assertEqual(payload["schemaVersion"], "sem.docs.v1")
        client_get = next(
            operation for operation in payload["operations"]
            if operation["name"] == "clientGet"
        )
        self.assertEqual(client_get["module"], "standard.http")
        self.assertEqual(client_get["summarySource"], "comment:rationale")
        self.assertIn("clientGet fixes the HTTP method to GET", client_get["summary"])
        self.assertIn("host:String", client_get["signature"]["text"])

    def test_docs_get_returns_operation_documentation(self) -> None:
        payload = sem._docs_payload("get", operation_name="http.escapeHtml")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        operation = payload["operation"]
        self.assertEqual(operation["fullName"], "standard.http.escapeHtml")
        self.assertEqual(operation["purpose"], "Escape HTML special characters (& < > \" ') from input into the caller-provided scratch buffer; returns the bounded, null-terminated escaped string.")
        self.assertIn("failure", operation["commentsByTag"])
        self.assertIn("scratch", operation["commentsByTag"]["memory"][0]["text"])
        self.assertEqual(operation["signature"]["outputs"][0]["type"], "String")
        self.assertEqual(operation["capabilityDetails"][0]["resource"], "memory.buffer")
        self.assertEqual(operation["capabilityDetails"][0]["action"], "readWrite")
        self.assertIn("runtimeBindingPrecondition", operation["runtime"])
        self.assertIn("capacity writable bytes", operation["runtime"]["runtimeBindingPrecondition"][0]["text"])
        self.assertIn("call escapeHtmlCall http.escapeHtml", operation["usage"]["call"]["rows"])

    def test_docs_get_includes_failure_and_cleanup_rows(self) -> None:
        payload = sem._docs_payload("get", operation_name="http.clientGet")

        operation = payload["operation"]
        self.assertTrue(operation["usage"]["call"]["requiresFailureHandling"])
        self.assertTrue(operation["usage"]["call"]["requiresCleanup"])
        self.assertIn("branch if condition clientGetIsNull target <failureLabel>", operation["usage"]["failureHandling"]["rows"])
        self.assertIn("argument clientGetNullCheckCall pointer OpaquePointer clientGetResult", operation["usage"]["failureHandling"]["rows"])
        self.assertIn("call clientGetCleanupCall c.free", operation["usage"]["cleanup"]["rows"])
        self.assertIn({"action": "free", "path": "heap"}, operation["usage"]["cleanup"]["requiredCallerEffects"])
        self.assertIn("effect <callerOperation> free heap", operation["usage"]["cleanup"]["authorityRows"])

    def test_docs_get_result_usage_uses_ok_and_error_binds(self) -> None:
        payload = sem._docs_payload("get", operation_name="assert.requireConditionTrue")

        self.assertTrue(payload["ok"])
        rows = payload["operation"]["usage"]["call"]["rows"]
        failure_rows = payload["operation"]["usage"]["failureHandling"]["rows"]
        self.assertIn("bind ok requireConditionTrueResult Int32 requireConditionTrueCall", rows)
        self.assertIn("bind error requireConditionTrueError AssertionError requireConditionTrueCall", failure_rows)
        self.assertIn("branch error source requireConditionTrueCall target <errorLabel>", failure_rows)
        self.assertNotIn("bind value requireConditionTrueResult Result requireConditionTrueCall", rows)

    def test_docs_recommended_rows_do_not_duplicate_result_error_rows(self) -> None:
        payload = sem._docs_payload("get", operation_name="json.createDocument")

        usage = payload["target"]["usage"]
        recommended_rows = usage["call"]["rows"] + usage["failureHandling"]["rows"] + usage["cleanup"]["rows"]
        self.assertEqual(len(recommended_rows), len(set(recommended_rows)))
        self.assertEqual(sum(1 for row in recommended_rows if row.startswith("bind error createDocumentError")), 1)
        self.assertEqual(sum(1 for row in recommended_rows if row.startswith("branch error source createDocumentCall")), 1)

    def test_docs_get_hides_internal_helpers_by_default(self) -> None:
        payload = sem._docs_payload("get", operation_name="http.clientFetchNative")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "not-found")

        internal_payload = sem._docs_payload(
            "get",
            operation_name="http.clientFetchNative",
            include_internal=True,
        )
        self.assertTrue(internal_payload["ok"])
        self.assertTrue(internal_payload["operation"]["visibility"]["internal"])

    def test_docs_list_includes_non_exported_public_operations(self) -> None:
        payload = sem._docs_payload("list", module_name="math", summary_tag="purpose")

        self.assertTrue(payload["ok"])
        self.assertGreater(payload["summary"]["operationCount"], 0)
        self.assertTrue(all(not item["visibility"]["internal"] for item in payload["operations"]))

    def test_docs_next_commands_preserve_std_path(self) -> None:
        std_root = (sem.ROOT / "std").resolve()
        payload = sem._docs_payload("list", module_name="http", std_root=std_root)

        argv = payload["nextCommands"][0]["argv"]
        self.assertIn("--std-path", argv)
        self.assertEqual(Path(argv[argv.index("--std-path") + 1]), std_root)
        self.assertIn("--std-path", payload["nextCommands"][0]["command"])

    def test_docs_invalid_std_path_is_tool_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_root = Path(temp_dir) / "missing-std"
            payload = sem._docs_payload("list", module_name="http", std_root=missing_root)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "tool-error")
        self.assertEqual(payload["operations"], [])
        self.assertIn("standard-library root does not exist", payload["errors"][0])

    def test_docs_module_filter_skips_unrelated_parse_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            std_root = Path(temp_dir)
            http_dir = std_root / "http"
            broken_dir = std_root / "broken"
            http_dir.mkdir()
            broken_dir.mkdir()
            (http_dir / "main.sem").write_text(
                "# rationale: HTTP docs fixture.\n"
                "module standard.http\n"
                "# rationale: Fixture operation.\n"
                "operation fixtureHttpOperation\n"
                "output operation fixtureHttpOperation Int32\n"
                "purpose fixtureHttpOperation \"Return a fixture status\"\n"
                "storage local immutable fixtureStatus Int32 0\n"
                "return value fixtureStatus\n",
                encoding="utf-8",
            )
            (broken_dir / "main.sem").write_text("operation \"unterminated\n", encoding="utf-8")

            payload = sem._docs_payload("list", module_name="http", std_root=std_root)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["modules"], ["standard.http"])
        self.assertEqual(payload["operations"][0]["name"], "fixtureHttpOperation")

    def test_docs_get_reports_ambiguous_operation_names(self) -> None:
        def operation_doc(module_name: str) -> dict:
            module_short_name = module_name.rsplit(".", 1)[-1]
            return {
                "module": module_name,
                "moduleName": module_short_name,
                "name": "sharedName",
                "qualifiedName": f"{module_short_name}.sharedName",
                "fullName": f"{module_name}.sharedName",
                "signature": {"text": "() -> Void", "inputs": [], "outputs": []},
                "summary": "",
                "summarySource": "",
                "location": {},
                "sourceFile": "",
                "visibility": {"public": True, "internal": False, "exported": False, "reason": "operation"},
                "purpose": "",
                "invariants": [],
                "effects": [],
                "capabilityDetails": [],
                "usage": {"failureMode": {}, "cleanup": {}},
            }

        inventory = ([operation_doc("standard.alpha"), operation_doc("standard.beta")], [], [], sem.ROOT / "std")
        with mock.patch.object(sem, "_docs_inventory", return_value=inventory):
            payload = sem._docs_payload("get", operation_name="sharedName")

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "ambiguous")
        self.assertEqual(len(payload["matches"]), 2)
        self.assertEqual(payload["nextCommands"][0]["requiredArgs"][0]["name"], "module")

    def test_docs_get_module_call_target_returns_actionable_payload(self) -> None:
        payload = sem._docs_payload("get", operation_name="gui.applicationCreate")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"]["targetMatchCount"], 1)
        target = payload["target"]
        self.assertEqual(target["target"], "gui.applicationCreate")
        self.assertEqual(target["visibility"]["apiTier"], "compiler-lowered")
        self.assertEqual(target["signature"]["inputs"][0]["name"], "title")
        self.assertIn({"action": "allocate", "path": "gui.application"}, target["usage"]["requiredCallerEffects"])
        self.assertIn("effect <callerOperation> allocate gui.application", target["usage"]["effectRows"])
        self.assertIn("authority <callerOperation> allocate gui.application", target["usage"]["authorityRows"])
        self.assertIn("call applicationCreateCall gui.applicationCreate", target["usage"]["call"]["rows"])
        self.assertIn("branch if condition applicationCreateIsNull target <failureLabel>", target["usage"]["failureHandling"]["rows"])
        self.assertEqual(payload["moduleDocMode"], "compact")
        self.assertNotIn("callTargets", payload["moduleDocs"][0])

    def test_docs_gui_control_on_event_matches_linter_signature(self) -> None:
        payload = sem._docs_payload("get", operation_name="gui.controlOnEvent")
        semlint = sem._load_semlint_module()

        target = payload["target"]
        self.assertIn("argument controlOnEventCall handler GuiEventHandler <handler>", target["usage"]["call"]["rows"])
        self.assertEqual(semlint.BUILTIN_TARGET_SIGNATURES["gui.controlOnEvent"], [
            ("control", "GuiControl"),
            ("eventKind", "GuiEventKind"),
            ("handler", "GuiEventHandler"),
        ])

    def test_docs_static_target_signatures_match_linter(self) -> None:
        _operations, modules, errors, _root = sem._docs_inventory()
        semlint = sem._load_semlint_module()

        self.assertEqual(errors, [])
        docs_by_target = {
            target["target"]: target
            for module in modules
            for target in module.get("callTargets", [])
        }
        for target, expected_signature in semlint.BUILTIN_TARGET_SIGNATURES.items():
            if target not in docs_by_target:
                continue
            expected_inputs = [
                (name, type_name)
                for name, type_name in expected_signature
                if name != "console"
            ]
            actual_inputs = [
                (item["name"], item["type"])
                for item in docs_by_target[target]["signature"]["inputs"]
            ]
            self.assertEqual(actual_inputs, expected_inputs, target)

    def test_docs_get_compiler_owned_targets_returns_actionable_payload(self) -> None:
        console_payload = sem._docs_payload("get", operation_name="console.writeLine")
        math_payload = sem._docs_payload("get", operation_name="math.addInt64")
        pointer_payload = sem._docs_payload("get", operation_name="pointer.isNull")
        malloc_payload = sem._docs_payload("get", operation_name="c.malloc")
        free_payload = sem._docs_payload("get", operation_name="c.free")
        realloc_payload = sem._docs_payload("get", operation_name="c.realloc")

        self.assertTrue(console_payload["ok"])
        console_usage = console_payload["target"]["usage"]
        self.assertFalse(console_usage["importRequired"])
        self.assertEqual(console_usage["importRow"], "")
        self.assertIn("effect <callerOperation> write console.stdout", console_usage["effectRows"])
        self.assertIn("ignore ok source writeLineCall type Void", console_usage["call"]["rows"])
        self.assertIn("bind error writeLineError Int32 writeLineCall", console_usage["failureHandling"]["rows"])

        self.assertTrue(math_payload["ok"])
        self.assertIn("bind value addInt64Result Int64 addInt64Call", math_payload["target"]["usage"]["call"]["rows"])
        self.assertEqual(math_payload["target"]["usage"]["failureMode"], {"kind": "none", "text": "", "source": ""})

        self.assertTrue(pointer_payload["ok"])
        self.assertEqual(pointer_payload["target"]["signature"]["outputs"][0]["type"], "Bool")
        self.assertIn("argument isNullCall pointer OpaquePointer <pointer>", pointer_payload["target"]["usage"]["call"]["rows"])

        self.assertTrue(malloc_payload["ok"])
        malloc_usage = malloc_payload["target"]["usage"]
        self.assertIn({"action": "allocate", "path": "heap"}, malloc_usage["requiredCallerEffects"])
        self.assertIn("branch if condition mallocIsNull target <failureLabel>", malloc_usage["failureHandling"]["rows"])
        self.assertIn("call mallocCleanupCall c.free", malloc_usage["cleanup"]["rows"])
        self.assertIn({"action": "free", "path": "heap"}, malloc_usage["cleanup"]["requiredCallerEffects"])

        self.assertTrue(free_payload["ok"])
        self.assertIn("ignore void source freeCall", free_payload["target"]["usage"]["call"]["rows"])
        self.assertIn("effect <callerOperation> free heap", free_payload["target"]["usage"]["effectRows"])

        self.assertTrue(realloc_payload["ok"])
        self.assertEqual(realloc_payload["target"]["loweringStatus"], "partial")
        self.assertFalse(realloc_payload["target"]["usage"]["availableForCodegen"])

    def test_docs_index_and_search_user_generated_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            source.write_text(
                "# rationale: Task API for creating task records from user text.\n"
                "module examples.tasks\n"
                "# rationale: Create one task and return its identifier.\n"
                "# failure: The caller must validate title text before persisting.\n"
                "operation createTask\n"
                "input operation createTask title String\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task from a title and return its id\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )

            with mock.patch.object(sem, "_docs_sentence_transformer_embedding", side_effect=fake_semantic_embedding):
                index_payload = sem._docs_index_payload(
                    root,
                    db_path=db_path,
                    include_std=False,
                    include_compiler=False,
                )
                search_payload = sem._docs_search_payload("create task from title", db_path=db_path, limit=3)
                full_payload = sem._docs_search_payload("create task from title", db_path=db_path, limit=1, include_docs=True)
            status_payload = sem._docs_index_status_payload(db_path)

        self.assertTrue(index_payload["ok"])
        self.assertEqual(index_payload["schemaVersion"], "sem.docsIndex.v1")
        self.assertTrue(status_payload["ok"])
        self.assertEqual(search_payload["schemaVersion"], "sem.docsSearch.v1")
        self.assertTrue(search_payload["ok"])
        self.assertGreaterEqual(len(search_payload["results"]), 1)
        self.assertEqual(search_payload["results"][0]["qualifiedName"], "examples.tasks.createTask")
        self.assertEqual(search_payload["results"][0]["sourceKind"], "project")
        self.assertEqual(index_payload["features"]["embeddingProvider"], "sentence-transformers")
        self.assertIn(search_payload["results"][0]["confidence"], {"exact", "strong", "medium", "weak"})
        self.assertNotIn("doc", search_payload["results"][0])

        self.assertIn("doc", full_payload["results"][0])

    def test_docs_default_db_path_treats_missing_non_source_path_as_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            missing_project = root / "new-project"
            missing_source = root / "new-project" / "main.sem"

            project_db = sem._docs_default_db_path(missing_project)
            source_db = sem._docs_default_db_path(missing_source)

        self.assertEqual(project_db, (missing_project / ".sem" / "docs.sqlite").resolve())
        self.assertEqual(source_db, (missing_project / ".sem" / "docs.sqlite").resolve())

    def test_docs_index_default_provider_is_real_semantic_embedding(self) -> None:
        parser = sem.build_parser()

        args = parser.parse_args(["docs", "index", "--path", "apps"])

        self.assertEqual(args.embedding_provider, "sentence-transformers")

    def test_docs_index_rejects_removed_hash_embedding_provider(self) -> None:
        parser = sem.build_parser()

        with mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["docs", "index", "--embedding-provider", "hash"])

    def test_docs_index_refresh_prunes_excluded_compiler_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            source.write_text(
                "module examples.tasks\n"
                "# rationale: Create task records.\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )

            first_payload = sem._docs_index_payload(
                root,
                db_path=db_path,
                include_std=False,
                include_compiler=True,
                embedding_provider="none",
            )
            first_search = sem._docs_search_payload("console.writeLine", db_path=db_path, limit=5)
            second_payload = sem._docs_index_payload(
                root,
                db_path=db_path,
                include_std=False,
                include_compiler=False,
                embedding_provider="none",
            )
            second_search = sem._docs_search_payload("console.writeLine", db_path=db_path, limit=5)
            status_payload = sem._docs_index_status_payload(db_path)

        self.assertTrue(first_payload["ok"])
        self.assertTrue(any(result["sourceKind"] == "compiler" for result in first_search["results"]))
        self.assertTrue(second_payload["ok"])
        self.assertEqual(status_payload["summary"]["sourceKinds"], ["project"])
        self.assertEqual(second_search["results"], [])

    def test_docs_search_returns_no_match_for_unrelated_fts_query(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            source.write_text(
                "module examples.tasks\n"
                "# rationale: Create task records.\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )
            sem._docs_index_payload(root, db_path=db_path, include_std=False, include_compiler=False, embedding_provider="none")

            search_payload = sem._docs_search_payload("zzzzqv unrelated phrase", db_path=db_path, limit=5)

        self.assertTrue(search_payload["ok"])
        self.assertEqual(search_payload["results"], [])
        self.assertTrue(search_payload["summary"]["noConfidentMatches"])

    def test_docs_search_validates_and_clamps_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "missing.sqlite"

            invalid_payload = sem._docs_search_payload("anything", db_path=db_path, limit=-1)
            clamped_payload = sem._docs_search_payload("anything", db_path=db_path, limit=999)

        self.assertFalse(invalid_payload["ok"])
        self.assertEqual(invalid_payload["status"], "invalid-arguments")
        self.assertEqual(clamped_payload["status"], "index-missing")
        self.assertEqual(clamped_payload["query"]["limit"], sem.DOCS_SEARCH_MAX_LIMIT)
        self.assertEqual(clamped_payload["query"]["requestedLimit"], 999)

    def test_docs_confidence_does_not_trust_vector_only_matches(self) -> None:
        confidence = sem._docs_result_confidence(
            exact_boost=0.0,
            fts_score=0.0,
            vector_score=0.95,
            structured_boost=3.0,
        )

        self.assertEqual(confidence, "weak")

    def test_docs_status_and_search_report_stale_schema_without_mutating_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "docs.sqlite"
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE docs_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("INSERT INTO docs_meta(key, value) VALUES ('schemaVersion', '1')")
            conn.commit()
            conn.close()

            status_payload = sem._docs_index_status_payload(db_path)
            search_payload = sem._docs_search_payload("anything", db_path=db_path)
            tables = {
                row[0]
                for row in sqlite3.connect(db_path).execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }

        self.assertFalse(status_payload["ok"])
        self.assertEqual(status_payload["status"], "stale-schema")
        self.assertFalse(search_payload["ok"])
        self.assertEqual(search_payload["status"], "stale-schema")
        self.assertEqual(tables, {"docs_meta"})

    def test_docs_embedding_auto_requires_real_provider(self) -> None:
        with mock.patch.object(sem, "_docs_sentence_transformer_embedding", side_effect=ValueError("model unavailable")):
            vector, status, detail = sem._docs_embedding(
                "create task",
                provider="auto",
                model=sem.DOCS_DEFAULT_EMBEDDING_MODEL,
            )
            direct_vector, direct_status, direct_detail = sem._docs_embedding(
                "create task",
                provider="sentence-transformers",
                model=sem.DOCS_DEFAULT_EMBEDDING_MODEL,
            )

        self.assertIsNone(vector)
        self.assertEqual(status, "failed")
        self.assertIn("model unavailable", detail)
        self.assertIsNone(direct_vector)
        self.assertEqual(direct_status, "failed")
        self.assertIn("model unavailable", direct_detail)

    def test_docs_index_reports_missing_real_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            source.write_text(
                "module examples.tasks\n"
                "# rationale: Create task records.\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )
            with mock.patch.object(sem, "_docs_sentence_transformer_embedding", side_effect=ValueError("model unavailable")):
                index_payload = sem._docs_index_payload(root, db_path=db_path, include_std=False, include_compiler=False)

        self.assertFalse(index_payload["ok"])
        self.assertEqual(index_payload["status"], "embedding-error")
        self.assertEqual(index_payload["features"]["embeddingProvider"], "sentence-transformers")
        self.assertIn("real semantic embedding generation failed", index_payload["errors"][0])

    def test_docs_search_uses_indexed_embedding_model_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            source.write_text(
                "module examples.tasks\n"
                "# rationale: Create task records.\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )
            with mock.patch.object(sem, "_docs_sentence_transformer_embedding", side_effect=fake_semantic_embedding):
                sem._docs_index_payload(
                    root,
                    db_path=db_path,
                    include_std=False,
                    include_compiler=False,
                    embedding_model="custom-local-model",
                )

                search_payload = sem._docs_search_payload("create task", db_path=db_path, limit=5)

        self.assertTrue(search_payload["ok"])
        self.assertEqual(search_payload["query"]["embeddingModel"], "custom-local-model")

    def test_docs_search_reports_corrupt_doc_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            source.write_text(
                "module examples.tasks\n"
                "# rationale: Create task records.\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )
            sem._docs_index_payload(root, db_path=db_path, include_std=False, include_compiler=False, embedding_provider="none")
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE docs_entries SET doc_json = '{not json' WHERE qualified_name = 'examples.tasks.createTask'")
            conn.commit()
            conn.close()

            search_payload = sem._docs_search_payload("createTask", db_path=db_path, limit=5)

        self.assertFalse(search_payload["ok"])
        self.assertEqual(search_payload["status"], "corrupt-index")
        self.assertIn("result hydration failed", search_payload["errors"][0])

    def test_docs_index_rebuilds_stale_owned_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            db_path.parent.mkdir()
            source.write_text(
                "module examples.tasks\n"
                "# rationale: Create task records.\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "purpose createTask \"Create a task\"\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )
            conn = sqlite3.connect(db_path)
            conn.execute("CREATE TABLE docs_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("CREATE TABLE docs_entries(id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            conn.execute("CREATE TABLE docs_documents(path TEXT PRIMARY KEY)")
            conn.commit()
            conn.close()

            index_payload = sem._docs_index_payload(root, db_path=db_path, include_std=False, include_compiler=False, embedding_provider="none")
            status_payload = sem._docs_index_status_payload(db_path)
            search_payload = sem._docs_search_payload("create task", db_path=db_path)

        self.assertTrue(index_payload["ok"])
        self.assertTrue(status_payload["ok"])
        self.assertEqual(search_payload["results"][0]["qualifiedName"], "examples.tasks.createTask")

    def test_docs_index_reports_corrupt_db_as_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "tasks.sem"
            db_path = root / ".sem" / "docs.sqlite"
            db_path.parent.mkdir()
            source.write_text(
                "module examples.tasks\n"
                "operation createTask\n"
                "output operation createTask Int32\n"
                "storage local immutable createdTaskId Int32 1\n"
                "return value createdTaskId\n",
                encoding="utf-8",
            )
            db_path.write_text("not sqlite", encoding="utf-8")

            index_payload = sem._docs_index_payload(root, db_path=db_path, include_std=False, include_compiler=False)

        self.assertFalse(index_payload["ok"])
        self.assertEqual(index_payload["status"], "corrupt-index")

    def test_docs_vector_search_falls_back_when_sqlite_vec_table_is_incomplete(self) -> None:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute(
            "CREATE TABLE docs_entries(id INTEGER PRIMARY KEY, embedding_status TEXT, embedding_provider TEXT, embedding_model TEXT, embedding BLOB)"
        )
        conn.execute("CREATE TABLE docs_vec(rowid INTEGER PRIMARY KEY, embedding BLOB)")
        vector = fake_semantic_embedding("alpha task", sem.DOCS_DEFAULT_EMBEDDING_MODEL)
        conn.execute(
            "INSERT INTO docs_entries(id, embedding_status, embedding_provider, embedding_model, embedding) VALUES (1, 'fresh', 'sentence-transformers', ?, ?)",
            (sem.DOCS_DEFAULT_EMBEDDING_MODEL, sem._docs_vector_to_blob(vector)),
        )
        conn.execute("INSERT INTO docs_vec(rowid, embedding) VALUES (999, ?)", (sem._docs_vector_to_blob(vector),))

        with mock.patch.object(sem, "_docs_sentence_transformer_embedding", side_effect=fake_semantic_embedding):
            scores, backend = sem._docs_search_vectors(
                conn,
                "alpha task",
                provider="sentence-transformers",
                model=sem.DOCS_DEFAULT_EMBEDDING_MODEL,
                limit=5,
                sqlite_vec_available=True,
                allow_model_download=False,
            )

        conn.close()
        self.assertIn(1, scores)
        self.assertIn("python cosine fallback", backend)

    def test_docs_get_json_target_returns_cleanup_guidance(self) -> None:
        payload = sem._docs_payload("get", operation_name="json.createDocument")

        self.assertTrue(payload["ok"])
        target = payload["target"]
        self.assertEqual(target["signature"]["outputs"][0]["values"], ["Result", "JsonDocument", "JsonAccessError"])
        self.assertIn("bind ok createDocumentResult JsonDocument createDocumentCall", target["usage"]["call"]["rows"])
        self.assertIn("call createDocumentCleanupCall json.destroyDocument", target["usage"]["cleanup"]["rows"])
        self.assertIn("argument createDocumentCleanupCall document JsonDocument createDocumentResult", target["usage"]["cleanup"]["rows"])
        self.assertIn("ignore value source createDocumentCleanupCall type Int32", target["usage"]["cleanup"]["rows"])

    def test_docs_failure_mode_distinguishes_null_preconditions(self) -> None:
        payload = sem._docs_payload("get", operation_name="string.stringByteLength")

        operation = payload["operation"]
        self.assertEqual(operation["usage"]["failureMode"]["kind"], "caller-precondition")
        self.assertTrue(operation["usage"]["preconditions"]["required"])
        self.assertFalse(operation["usage"]["failureHandling"]["required"])
        self.assertEqual(operation["visibility"]["apiTier"], "helper")
        self.assertTrue(operation["agentWarnings"])

    def test_docs_metadata_ownership_text_becomes_actionable(self) -> None:
        payload = sem._docs_payload("get", operation_name="string.duplicateCStringIntoOwnedMemory")

        usage = payload["operation"]["usage"]
        self.assertEqual(usage["failureMode"]["kind"], "null-sentinel")
        self.assertIn("branch if condition duplicateCStringIntoOwnedMemoryIsNull target <failureLabel>", usage["failureHandling"]["rows"])
        self.assertTrue(usage["cleanup"]["required"])
        self.assertIn("call duplicateCStringIntoOwnedMemoryCleanupCall c.free", usage["cleanup"]["rows"])
        self.assertIn("authority <callerOperation> read memory.buffer", usage["authorityRows"])
        self.assertIn("capability localMemoryBufferReadCapability memory.buffer read", usage["localCapabilityRows"])
        self.assertIn("useCapability <callerOperation> localMemoryBufferReadCapability", usage["localCapabilityRows"])
        self.assertNotIn("useCapability <callerOperation> memoryBufferReadCapability", usage["useCapabilityRows"])

    def test_docs_reports_modules_without_operation_docs(self) -> None:
        payload = sem._docs_payload("list", module_name="json", summary_tag="rationale")

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operations"], [])
        self.assertEqual(payload["nextCommands"][0]["requiredArgs"][0]["name"], "target")
        module_doc = payload["moduleDocs"][0]
        self.assertEqual(module_doc["operationDocStatus"], "no-operation-docs")
        self.assertIn("json.stringify", module_doc["summary"])
        targets = {target["target"] for target in module_doc["callTargets"]}
        self.assertIn("json.createDocument", targets)
        self.assertIn("json.stringify.String", targets)

    def test_docs_module_docs_include_gui_call_targets(self) -> None:
        payload = sem._docs_payload("list", module_name="gui", summary_tag="rationale")

        module_doc = payload["moduleDocs"][0]
        targets = {target["target"] for target in module_doc["callTargets"]}
        self.assertIn("gui.applicationCreate", targets)
        self.assertIn("gui.applicationRun", targets)
        create_target = next(target for target in module_doc["callTargets"] if target["target"] == "gui.applicationCreate")
        self.assertEqual(create_target["signature"]["text"], "(title:GuiText) -> GuiApplication")
        self.assertIn("construction targets create handles", create_target["invariants"][0])
        reserved_target = next(target for target in module_doc["callTargets"] if target["target"] == "gui.eventKeyCode")
        self.assertFalse(reserved_target["usage"]["availableForCodegen"])

    def test_docs_std_library_uses_typed_comment_summaries(self) -> None:
        operations, modules, errors, _root = sem._docs_inventory()

        self.assertEqual(errors, [])
        missing_operations = [
            operation["fullName"]
            for operation in operations
            if operation["visibility"]["public"]
            and not operation.get("summarySource", "").startswith("comment:")
        ]
        missing_modules = [
            module["module"]
            for module in modules
            if not module.get("summarySource", "").startswith("comment:")
        ]
        self.assertEqual(missing_operations, [])
        self.assertEqual(missing_modules, [])

    def test_docs_static_intrinsic_targets_are_actionable(self) -> None:
        sqlite_payload = sem._docs_payload("get", operation_name="sqlite.openDatabase")
        bcrypt_payload = sem._docs_payload("get", operation_name="bcrypt.hashPassword")
        net_payload = sem._docs_payload("get", operation_name="net.fetchText")

        self.assertTrue(sqlite_payload["ok"])
        self.assertEqual(sqlite_payload["target"]["signature"]["outputs"][0]["values"], [
            "Result",
            "SqliteDatabase",
            "SqliteDatabaseOpenFailure",
        ])
        self.assertIn(
            "ignore ok source openDatabaseCleanupCall type Int32",
            sqlite_payload["target"]["usage"]["cleanup"]["rows"],
        )
        self.assertIn(
            "bind error openDatabaseCleanupError SqliteDatabaseCloseFailure openDatabaseCleanupCall",
            sqlite_payload["target"]["usage"]["cleanup"]["rows"],
        )
        self.assertIn(
            "useCapability <callerOperation> sqliteDatabaseReadWriter",
            sqlite_payload["target"]["usage"]["useCapabilityRows"],
        )

        self.assertTrue(bcrypt_payload["ok"])
        self.assertEqual(bcrypt_payload["target"]["usage"]["failureHandling"]["kind"], "status-code")
        self.assertIn(
            "argument hashPasswordCall outBuffer BcryptHashBuffer <outBuffer>",
            bcrypt_payload["target"]["usage"]["call"]["rows"],
        )

        self.assertTrue(net_payload["ok"])
        self.assertIn(
            "fieldGet fetchTextBody HttpClientBodyText fetchTextResult body",
            net_payload["target"]["usage"]["cleanup"]["rows"],
        )
        self.assertIn({"action": "free", "path": "heap"}, net_payload["target"]["usage"]["cleanup"]["requiredCallerEffects"])
        self.assertIn(
            "bind error fetchTextError HttpClientErrorCode fetchTextCall",
            net_payload["target"]["usage"]["failureHandling"]["rows"],
        )

    def test_docs_static_target_coverage_matches_known_runtime_sets(self) -> None:
        _operations, modules, errors, _root = sem._docs_inventory()
        semlint = sem._load_semlint_module()

        self.assertEqual(errors, [])
        targets = {target["target"] for module in modules for target in module.get("callTargets", [])}
        self.assertEqual(sorted(semlint.ALL_NATIVE_HTTP_TARGETS - targets), [])
        self.assertEqual(sorted(semlint.SUPPORTED_JSON_RUNTIME_TARGETS - targets), [])
        self.assertEqual(sorted(semlint.SUPPORTED_JSON_PRIMITIVE_TARGETS - targets), [])
        self.assertIn("bcrypt.hashPassword", targets)
        self.assertIn("net.fetchText", targets)
        self.assertIn("net.fetchBytes", targets)
        self.assertIn("sqlite.openDatabase", targets)

    def test_docs_static_target_edge_rows_are_not_misleading(self) -> None:
        application_run = sem._docs_payload("get", operation_name="gui.applicationRun")["target"]
        verify_password = sem._docs_payload("get", operation_name="bcrypt.verifyPassword")["target"]
        create_builder = sem._docs_payload("get", operation_name="json.createBuilder")["target"]
        response_text = sem._docs_payload("get", operation_name="http.responseText")["target"]
        fetch_bytes = sem._docs_payload("get", operation_name="net.fetchBytes")["target"]

        self.assertEqual(application_run["usage"]["failureHandling"]["kind"], "sentinel-value")
        self.assertFalse(application_run["usage"]["failureHandling"]["required"])
        self.assertEqual(verify_password["usage"]["failureHandling"]["kind"], "negative-status")
        self.assertIn(
            "call verifyPasswordNegativeStatusCheckCall math.lessThanInt32",
            verify_password["usage"]["failureHandling"]["rows"],
        )
        self.assertIn("Legacy builder/finder target", create_builder["agentWarnings"][0])
        self.assertIn(
            "useCapability <callerOperation> httpResponseWriter",
            response_text["usage"]["useCapabilityRows"],
        )
        self.assertFalse(fetch_bytes["usage"]["availableForCodegen"])
        self.assertEqual(fetch_bytes["loweringStatus"], "partial")

    def test_docs_sentinel_value_failure_is_domain_dependent(self) -> None:
        payload = sem._docs_payload("get", operation_name="gui.listBoxSelectedIndex")

        handling = payload["target"]["usage"]["failureHandling"]
        self.assertEqual(handling["kind"], "sentinel-value")
        self.assertFalse(handling["required"])
        self.assertIn("domain-dependent", handling["agentWarnings"][0])
        self.assertIn("domain-dependent", payload["target"]["agentWarnings"][0])

    def test_docs_cli_get_json_uses_parser(self) -> None:
        stdout = io.StringIO()
        with mock.patch("sys.stdout", stdout):
            result = sem.main(["docs", "get", "http.clientGet", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["schemaVersion"], "sem.docs.v1")
        self.assertEqual(payload["operation"]["usage"]["failureMode"]["kind"], "null-sentinel")

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
            payload = sem._build_check_payload(Path("SemanticScript/tests/tiny.sem"), [], include_readiness=True)

        self.assertEqual(payload["schemaVersion"], "sem.check.v1")
        self.assertIn("diagnostics", payload)
        self.assertIn("summary", payload)
        self.assertIn("targetReadiness", payload)
        self.assertIn(payload["targetReadiness"]["status"], {"supported", "partial", "blocked", "source-diagnostics"})
        self.assertIn(payload["status"], {"ok", "ok-with-warnings", "lint-diagnostics"})
        diagnostic = payload["diagnostics"][0]
        self.assertIn("expected", diagnostic)
        self.assertIn("actual", diagnostic)
        self.assertIn("span", diagnostic)
        self.assertIn("repair", diagnostic)
        self.assertTrue(payload["nextCommands"])
        self.assertTrue(any(item["kind"] == "explain" for item in payload["nextCommands"]))
        self.assertTrue(all("argv" in item for item in payload["nextCommands"]))
        self.assertTrue(all("replayable" in item for item in payload["nextCommands"]))

    def test_check_command_with_readiness_fails_when_embedded_readiness_is_not_ok(self) -> None:
        args = argparse.Namespace(json=True, full=False, with_readiness=True, path=".", compiler_args=[])
        payload = {
            "ok": True,
            "status": "ok",
            "targetReadiness": {"ok": False, "status": "partial"},
        }
        with mock.patch.object(sem, "_build_check_payload", return_value=payload), mock.patch.object(
            sem, "_compact_check_payload_for_cli", side_effect=lambda _path, value, full: value
        ), mock.patch("sys.stdout", new=io.StringIO()):
            code = sem.command_check(args)

        self.assertEqual(code, 1)

    def test_check_next_commands_use_include_warnings_for_warning_only_surfaces(self) -> None:
        entries = sem._check_next_commands(
            Path("SemanticScript/tests/tiny.sem"),
            [{"repair": {"id": "inlineAuthority"}}],
            "ok-with-warnings",
            include_readiness=False,
        )

        fix_entry = next(item for item in entries if item["kind"] == "fix")
        self.assertIn("--include-warnings", fix_entry["command"])

    def test_check_next_commands_quote_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="sem space ") as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text(NEW_SYNTAX_SOURCE, encoding="utf-8")
            with mock.patch.object(sem, "_compiler_check_probe", return_value={
                "attempted": True,
                "ok": True,
                "returnCode": 0,
                "stdout": "",
                "stderr": "",
            }):
                payload = sem._build_check_payload(source, [])

        slice_entry = next(item for item in payload["nextCommands"] if item["kind"] == "slice")
        self.assertEqual(slice_entry["argv"][-1], str(source.resolve()))
        self.assertIn(f"\"{source.resolve()}\"", slice_entry["command"])

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
        self.assertIn(payload["status"], {"supported", "partial", "blocked", "source-diagnostics", "quality-diagnostics"})
        self.assertIn("requestedTargets", payload)
        self.assertTrue(any(item["kind"] == "doctor" for item in payload["nextCommands"]))

    def test_readiness_command_returns_nonzero_when_payload_not_ok(self) -> None:
        args = argparse.Namespace(json=True, path=".")
        payload = {"ok": False, "status": "quality-diagnostics", "blockingChecks": [], "partialChecks": [], "requestedTargets": []}
        with mock.patch.object(sem, "_readiness_payload", return_value=payload), mock.patch("sys.stdout", new=io.StringIO()):
            code = sem.command_readiness(args)

        self.assertEqual(code, 1)

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

    def test_help_payload_recommends_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            sem._starter_project_payload(root)
            payload = sem._help_payload(root)
            self.assertEqual(payload["schemaVersion"], "sem.help.v1")
            self.assertTrue(payload["nextCommands"])
            kinds = [item["kind"] for item in payload["nextCommands"]]
            self.assertIn("skills", kinds)
            self.assertIn("check", kinds)
            self.assertEqual(
                payload["state"]["buildTape"], str((root / "build.sem").resolve()))

    def test_package_dependencies_skill_is_discoverable(self) -> None:
        self.assertEqual(sem.SKILL_ALIASES.get("sem-packages"), "package-dependencies")
        self.assertEqual(sem.SKILL_ALIASES.get("sem-deps"), "package-dependencies")
        content = sem._skill_content("package-dependencies", include_full_content=True)
        self.assertIsNotNone(content)
        sources = " ".join(str(content).lower().split())
        self.assertIn("package-management.md", sources)
        self.assertIn("sem deps", sources)

    def test_new_payload_creates_starter_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            payload = sem._starter_project_payload(root)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["schemaVersion"], "sem.newProject.v1")
            self.assertEqual(payload["status"], "created")
            self.assertEqual(payload["project"]["projectName"], "HelloWorld")
            self.assertEqual(payload["project"]["moduleName"], "app.hello_world")
            self.assertTrue((root / "build.sem").is_file())
            self.assertTrue((root / "main.sem").is_file())
            self.assertTrue((root / "main.test.sem").is_file())
            self.assertTrue((root / ".github" / "workflows" / "ci.yml").is_file())
            self.assertTrue((root / ".gitignore").is_file())

            gitignore_text = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".semcache/", gitignore_text)
            self.assertIn(".sem/docs.sqlite", gitignore_text)
            self.assertIn("!sem.lock", gitignore_text)  # lockfile stays committed

            build_text = (root / "build.sem").read_text(encoding="utf-8")
            # build.sem documents the dependency workflow this scaffold aligns with.
            self.assertIn("sem deps sync", build_text)
            self.assertIn("dependencyFetch", build_text)
            main_text = (root / "main.sem").read_text(encoding="utf-8")
            test_text = (root / "main.test.sem").read_text(encoding="utf-8")
            workflow_text = (root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
            self.assertIn("entry console main", build_text)
            self.assertIn(f'projectVersion helloWorld "{sem.STARTER_PROJECT_VERSION}"', build_text)
            self.assertIn("target console", build_text)
            self.assertIn('testPattern helloWorld "*.test.sem"', build_text)
            self.assertIn("call writeGreetingCall console.writeLine", main_text)
            self.assertIn("project HelloWorldSmokeTest", test_text)
            self.assertIn("sem.py test --json . --skip-python-harnesses", workflow_text)
            self.assertIn("sem.py build . -- --emit-exe", workflow_text)
            self.assertTrue(any(item["kind"] == "check" for item in payload["nextCommands"]))
            self.assertTrue(any(item["kind"] == "test" for item in payload["nextCommands"]))
            self.assertTrue(any(item["kind"] == "run" for item in payload["nextCommands"]))
            self.assertFalse(payload["project"]["docsIndex"]["enabled"])

    def test_new_payload_can_opt_in_to_semantic_docs_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            payload = sem._starter_project_payload(root, docs_index_opt_in=True)

            self.assertTrue(payload["ok"])
            self.assertTrue(payload["project"]["docsIndex"]["enabled"])
            self.assertEqual(payload["project"]["docsIndex"]["embeddingProvider"], "sentence-transformers")
            kinds = [item["kind"] for item in payload["nextCommands"]]
            self.assertIn("docs-deps", kinds)
            self.assertIn("docs-index", kinds)
            docs_index_command = next(item for item in payload["nextCommands"] if item["kind"] == "docs-index")
            self.assertIn("--allow-model-download", docs_index_command["argv"])
            for kind in ("docs-deps", "docs-index", "docs-search"):
                command = next(item for item in payload["nextCommands"] if item["kind"] == kind)
                self.assertFalse(command["replayable"])

    def test_new_payload_refuses_nonempty_directory_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            root.mkdir()
            (root / "notes.txt").write_text("keep", encoding="utf-8")

            payload = sem._starter_project_payload(root)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["status"], "path-not-empty")

            forced = sem._starter_project_payload(root, force=True)
            self.assertTrue(forced["ok"])
            self.assertEqual(forced["status"], "created")
            self.assertTrue((root / "build.sem").is_file())
            self.assertTrue((root / "main.sem").is_file())

    def test_new_payload_sanitizes_arbitrary_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "123 weird app!!!"
            payload = sem._starter_project_payload(root)

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["project"]["projectName"], "Project123WeirdApp")
            self.assertEqual(payload["project"]["buildProject"], "project123WeirdApp")
            self.assertEqual(payload["project"]["moduleName"], "app.project_123_weird_app")
            self.assertEqual(payload["project"]["nativeOutput"], "project-123-weird-app.exe")

    def test_new_payload_uses_github_url_for_module_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            payload = sem._starter_project_payload(
                root,
                github_url="https://github.com/acme/hello-world",
            )

            self.assertTrue(payload["ok"])
            self.assertEqual(payload["project"]["modulePath"], "github.com/acme/hello-world")
            self.assertEqual(payload["project"]["githubRepoUrl"], "https://github.com/acme/hello-world")
            self.assertEqual(payload["project"]["githubRepoSlug"], "acme/hello-world")
            build_text = (root / "build.sem").read_text(encoding="utf-8")
            self.assertIn("modulePath helloWorld github.com/acme/hello-world", build_text)

    def test_new_payload_rejects_invalid_github_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            payload = sem._starter_project_payload(
                root,
                github_url="https://gitlab.com/acme/hello-world",
            )

            self.assertFalse(payload["ok"])
            self.assertEqual(payload["status"], "invalid-github-url")

    def test_command_new_prompts_for_github_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            args = argparse.Namespace(
                path=str(root),
                force=False,
                json=False,
                github_url=None,
                enable_docs_index=False,
                no_docs_index=True,
            )
            with mock.patch.object(
                sem,
                "_prompt_for_starter_github_url",
                return_value="https://github.com/acme/hello-world",
            ), mock.patch("sys.stdout", new=io.StringIO()):
                code = sem.command_new(args)

            self.assertEqual(code, 0)
            build_text = (root / "build.sem").read_text(encoding="utf-8")
            self.assertIn("modulePath helloWorld github.com/acme/hello-world", build_text)

    def test_command_new_prompts_for_docs_index_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            args = argparse.Namespace(
                path=str(root),
                force=False,
                json=False,
                github_url="https://github.com/acme/hello-world",
                enable_docs_index=False,
                no_docs_index=False,
            )
            with mock.patch.object(sem, "_prompt_for_starter_docs_index_opt_in", return_value=True) as prompt:
                with mock.patch("sys.stdout", new=io.StringIO()):
                    code = sem.command_new(args)

            self.assertEqual(code, 0)
            prompt.assert_called_once()

    def test_new_starter_project_checks_and_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "hello-world"
            payload = sem._starter_project_payload(root)
            self.assertTrue(payload["ok"])

            check_proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "SemanticScript" / "tools" / "sem.py"), "check", "--json", str(root)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(check_proc.returncode, 0, check_proc.stderr)
            check_payload = json.loads(check_proc.stdout)
            self.assertEqual(check_payload["schemaVersion"], "sem.check.v1")
            self.assertEqual(check_payload["status"], "ok")

            test_proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "SemanticScript" / "tools" / "sem.py"),
                    "test",
                    "--json",
                    str(root),
                    "--skip-python-harnesses",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(test_proc.returncode, 0, test_proc.stderr)
            test_payload = json.loads(test_proc.stdout)
            self.assertEqual(test_payload["schemaVersion"], "sem.test.v1")
            self.assertEqual(test_payload["status"], "passed")
            self.assertEqual(test_payload["discoveredTests"], 1)
            self.assertEqual(test_payload["passedTests"], 1)

            run_proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "SemanticScript" / "tools" / "sem.py"), "run", str(root)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(run_proc.returncode, 0, run_proc.stderr)
            self.assertEqual(run_proc.stdout, "Hello, world!\n")

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

    def test_explain_finds_every_security_rule(self) -> None:
        # Capstone Rec 4: every security rule must be discoverable via
        # `sem explain` (they previously returned "unknown"). Includes the
        # compiler-only SS3911/SS3310, surfaced via docs/reference/security-rules.md.
        for code in ("SS4308", "SS4309", "SS4601", "SS4602",
                     "SS4603", "SS4604", "SS3310", "SS3911"):
            payload = sem._diagnostic_explain_payload(code)
            self.assertTrue(payload["found"], f"{code} not discoverable via sem explain")
            self.assertTrue(payload["title"], f"{code} has no title")
            self.assertTrue(payload["summary"], f"{code} has no summary")
            self.assertTrue(payload["commonFixes"], f"{code} has no fixes")

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
                payload = sem._build_fix_plan_payload(source, [], include_warnings=True)

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
storage module mutable accountLookupRevision Int64 zeroCount
storage module immutable zeroCount Int64 0
storage module immutable nextAccountLookupRevision Int64 1
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
                payload = sem._build_fix_plan_payload(source, [], include_warnings=True)

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
                payload = sem._build_fix_plan_payload(source, [], include_warnings=True)

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
                payload = sem._build_fix_plan_payload(source, [], include_warnings=True)

        self.assertFalse(payload["ok"])
        self.assertFalse(payload["planUsable"])
        self.assertEqual(payload["status"], "blocked")
        self.assertFalse(any(item["kind"] == "patch" for item in payload["nextCommands"]))

    def test_fix_plan_reports_mixed_status_when_only_some_repairs_are_patchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn value nope\n", encoding="utf-8")
            bundle = {"files": [{"path": source}], "semlint": None}
            diagnostics = [
                {"code": "SS3101", "repair": {"id": "addPurpose"}},
                {"code": "SS2506", "repair": {"id": "declareExportedSymbol"}},
            ]
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "status": "diagnostics",
                "scope": {"diagnosticsScope": "file"},
                "diagnostics": diagnostics,
                "summary": {"errors": 2, "warnings": 0},
            }), mock.patch.object(sem, "_collect_facts_bundle", return_value=bundle), mock.patch.object(
                sem,
                "_repair_plan_for_diagnostic",
                side_effect=[
                    {
                        "diagnostic": "SS3101",
                        "subjectName": "main",
                        "edits": [{"op": "insertAfterLine", "file": str(source), "afterLine": 2, "text": 'purpose operation main "demo"'}],
                        "fixSafety": "local-edit",
                    },
                    {
                        "diagnostic": "SS2506",
                        "subjectName": "main",
                        "edits": [],
                        "fixSafety": "requires-human-review",
                    },
                ],
            ):
                payload = sem._build_fix_plan_payload(source, [], include_warnings=True)

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["planUsable"])
        self.assertEqual(payload["status"], "mixed")
        self.assertEqual(payload["patchableRepairCount"], 1)
        self.assertEqual(payload["repairSummary"]["suggestionsOnly"], 1)
        self.assertTrue(any(item["kind"] == "patch" for item in payload["nextCommands"]))
        self.assertFalse(any(item["command"] == "sem patch --apply --json <PLAN.json>" for item in payload["nextCommands"]))

    def test_fix_command_returns_zero_for_plan_usable_mixed_status(self) -> None:
        args = argparse.Namespace(plan=True, json=True, full=False, include_warnings=True, path=".", compiler_args=[])
        payload = {"ok": False, "status": "mixed", "planUsable": True, "repairs": []}
        with mock.patch.object(sem, "_build_fix_plan_payload", return_value=payload), mock.patch.object(
            sem, "_compact_fix_payload_for_cli", side_effect=lambda _path, value, full: value
        ), mock.patch("sys.stdout", new=io.StringIO()):
            code = sem.command_fix(args)

        self.assertEqual(code, 0)

    def test_fix_plan_downgrades_review_only_edits_to_non_patchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn value nope\n", encoding="utf-8")
            bundle = {"files": [{"path": source}], "semlint": None}
            diagnostics = [{"code": "SS3102", "repair": {"id": "addInvariant"}}]
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "status": "diagnostics",
                "scope": {"diagnosticsScope": "file"},
                "diagnostics": diagnostics,
                "summary": {"errors": 1, "warnings": 0},
            }), mock.patch.object(sem, "_collect_facts_bundle", return_value=bundle), mock.patch.object(
                sem,
                "_repair_plan_for_diagnostic",
                return_value={
                    "diagnostic": "SS3102",
                    "subjectName": "main",
                    "edits": [{"op": "insertAfterLine", "file": str(source), "afterLine": 2, "text": 'invariant operation main "<fill me>"'}],
                    "fixSafety": "requires-human-review",
                },
            ):
                payload = sem._build_fix_plan_payload(source, [], include_warnings=True)

        self.assertFalse(payload["planUsable"])
        self.assertEqual(payload["status"], "suggestions-only")
        self.assertEqual(payload["patchableRepairCount"], 0)
        self.assertEqual(payload["repairSummary"]["reviewOnlyEdits"], 1)
        self.assertEqual(payload["repairs"][0]["edits"], [])
        self.assertEqual(len(payload["repairs"][0]["reviewEdits"]), 1)

    def test_fix_plan_hashes_only_machine_patchable_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            other = Path(tmp) / "other.sem"
            source.write_text("module demo.agent\noperation main\nreturn value nope\n", encoding="utf-8")
            other.write_text("module demo.other\noperation nope\nreturn void\n", encoding="utf-8")
            bundle = {"files": [{"path": source}, {"path": other}], "semlint": None}
            diagnostics = [{"code": "SS3104", "repair": {"id": "inlineAuthority"}}]
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "status": "diagnostics",
                "scope": {"diagnosticsScope": "file"},
                "diagnostics": diagnostics,
                "summary": {"errors": 1, "warnings": 0},
            }), mock.patch.object(sem, "_collect_facts_bundle", return_value=bundle), mock.patch.object(
                sem,
                "_repair_plan_for_diagnostic",
                return_value={
                    "diagnostic": "SS3104",
                    "subjectName": "main",
                    "edits": [{"op": "insertAfterLine", "file": str(source), "afterLine": 2, "text": "authority main write console.stdout"}],
                    "fixSafety": "local-edit",
                },
            ):
                payload = sem._build_fix_plan_payload(source, [])

        self.assertEqual(list(payload["preconditions"]["fileHashes"].keys()), [str(source.resolve())])

    def test_compact_fix_payload_surfaces_patchable_repairs_first(self) -> None:
        payload = {
            "schemaVersion": "sem.fixPlan.v1",
            "repairs": [
                {"diagnostic": f"SS{i:04d}", "subjectName": f"item{i}", "edits": [], "fixSafety": "requires-human-review"}
                for i in range(35)
            ],
        }
        payload["repairs"][-1]["edits"] = [{"op": "insertAfterLine", "file": "demo.sem", "afterLine": 1, "text": "purpose operation demo \"x\""}]
        payload["repairs"][-1]["fixSafety"] = "local-edit"

        compacted = sem._compact_fix_payload_for_cli(Path("demo.sem"), payload, full=False)

        self.assertEqual(compacted["repairs"][0]["diagnostic"], "SS0034")
        self.assertIn("repairs", compacted["view"]["truncation"])

    def test_patch_plan_apply_updates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "main.sem"
            source.write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            plan = {
                "schemaVersion": "sem.fixPlan.v1",
                "inputPath": str(source),
                "_inputPlanPath": str(Path(tmp) / "plan.json"),
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
            self.assertTrue(payload["inputPlanPath"].endswith("plan.json"))
            self.assertTrue(any(Path(item).samefile(source) for item in payload["filesChanged"]))
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

    def test_patch_plan_rejects_truncated_fix_payload(self) -> None:
        plan = {
            "schemaVersion": "sem.fixPlan.v1",
            "status": "actionable",
            "planUsable": True,
            "view": {"mode": "compact", "truncation": {"repairs": {"returned": 30, "total": 100, "truncated": 70}}},
            "inputPath": str(Path("SemanticScript/tests/tiny.sem").resolve()),
            "repairs": [],
        }
        payload = sem._execute_patch_plan(plan, "dry-run")
        self.assertFalse(payload["ok"])
        self.assertIn("truncated", payload["details"][0])

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
        self.assertIn("POST:/api/todos", refresh["argv"])

    def test_slice_payload_rejects_conflicting_anchors(self) -> None:
        args = argparse.Namespace(
            operation="healthHandler",
            route="POST:/api/todos",
            symbol=None,
            effect=None,
            capability=None,
            type_name=None,
        )
        payload = sem._slice_payload(Path("apps/taskforge-web"), args)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "error")
        self.assertIn("exactly one anchor", payload["error"])
        self.assertEqual(payload["anchorOptions"], ["operation", "route"])

    def test_route_slice_promotes_source_file_to_project_surface_for_handler_resolution(self) -> None:
        args = argparse.Namespace(
            operation=None,
            route="GET:/api/v1/auctions/:auctionId/events",
            symbol=None,
            effect=None,
            capability=None,
            type_name=None,
        )

        payload = sem._slice_payload(AUCTION_SERVER_MAIN_PATH, args)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["anchor"]["kind"], "route")
        self.assertEqual(payload["operation"]["name"], "auctionEventsHandler")
        self.assertEqual(payload["scope"]["retrievalScope"], "project")
        self.assertEqual(payload["surfaceShift"]["to"], "project")
        self.assertTrue(payload["handlerFile"].endswith("event_context.sem"))

    def test_discover_test_entries_includes_python_harnesses_without_test_prefix(self) -> None:
        entries = sem._discover_test_entries(AUCTION_SERVER_PATH)
        names = {entry["name"] for entry in entries if entry["kind"] == "python"}
        self.assertIn("api_tests", names)
        self.assertIn("enterprise_contract_tests", names)
        self.assertIn("e2e_api_smoke", names)

    def test_test_payload_can_run_python_harnesses_even_when_preflight_is_red(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.sem").write_text("module demo.agent\noperation main\nreturn void\n", encoding="utf-8")
            (root / "marker.txt").write_text("runtime ok\n", encoding="utf-8")
            tests_dir = root / "tests"
            tests_dir.mkdir()
            harness = tests_dir / "runtime_probe.py"
            harness.write_text(
                "from pathlib import Path\n"
                "print(Path('marker.txt').read_text(encoding='utf-8').strip())\n",
                encoding="utf-8",
            )
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": False,
                "status": "lint-diagnostics",
                "summary": {"errors": 1, "warnings": 0},
                "scope": {"diagnosticsScope": "file"},
                "diagnostics": [],
            }):
                payload = sem._run_test_payload(root, allow_red_preflight_harnesses=True)

        self.assertEqual(payload["status"], "diagnostics")
        self.assertEqual(payload["executedTests"], 1)
        self.assertFalse(payload["pythonHarnessesDeferred"])
        self.assertEqual(payload["preflightStatus"], "lint-diagnostics")
        self.assertEqual(payload["runtimeHarnessStatus"], "passed")
        result = payload["results"][0]
        self.assertEqual(result["cwd"], str(root.resolve()))
        self.assertEqual(result["lane"], "runtime-harness")

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
        self.assertEqual(payload["compositeStatus"], "diagnostics/runtime-deferred")
        self.assertEqual(payload["preflightCheck"]["status"], "diagnostics")
        self.assertTrue(any(item["kind"] == "fix" for item in payload["nextCommands"]))

    def test_test_payload_reports_runtime_harness_timeout_structurally(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            harness = root / "tests" / "runtime_probe.py"
            harness.parent.mkdir()
            harness.write_text("print('slow')\n", encoding="utf-8")
            with mock.patch.object(sem, "_build_check_payload", return_value={
                "ok": True,
                "status": "ok",
                "summary": {"errors": 0, "warnings": 0},
                "scope": {"diagnosticsScope": "project"},
                "diagnostics": [],
            }), mock.patch.object(sem, "_discover_test_entries", return_value=[
                {"name": "runtime_probe", "kind": "python", "path": harness}
            ]), mock.patch.object(
                sem.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired(cmd=["python", str(harness)], timeout=600),
            ):
                payload = sem._run_test_payload(root, include_python_harnesses=True)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["runtimeHarnessStatus"], "failed")
        self.assertEqual(payload["coverageSummary"]["runtimeHarnessesFailed"], 1)
        self.assertEqual(payload["results"][0]["status"], "timed-out")

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

    def test_release_launcher_routes_internal_tool_script_paths(self) -> None:
        launcher = load_sem_launcher()
        compiler_path = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
        fake_module = mock.Mock()

        with mock.patch.object(
            launcher.importlib,
            "import_module",
            return_value=fake_module,
        ) as import_mock, mock.patch.object(
            launcher,
            "_run_module_main",
            return_value=0,
        ) as run_mock:
            result = launcher.main([
                str(compiler_path),
                "SemanticScript/tests/tiny.sem",
                "--parse-only",
            ])

        self.assertEqual(result, 0)
        import_mock.assert_called_once_with("SemanticScript.compiler.semsc")
        run_mock.assert_called_once_with(
            fake_module,
            ["SemanticScript/tests/tiny.sem", "--parse-only"],
            passes_argv=False,
        )

    def test_release_launcher_runs_public_sem_cli_by_default(self) -> None:
        launcher = load_sem_launcher()

        with mock.patch.object(sem, "main", return_value=0) as main_mock:
            result = launcher.main(["version", "--json"])

        self.assertEqual(result, 0)
        main_mock.assert_called_once_with(["version", "--json"])


class TestCallContracts(unittest.TestCase):
    def test_call_classes_use_cutover_channel_vocabulary(self) -> None:
        self.assertEqual(call_class("math.addInt64", "Int64"), CALL_CLASS_ORDINARY_VALUE)
        self.assertEqual(call_class("console.writeLine", "Int32"), CALL_CLASS_RESULT)
        self.assertEqual(call_class("c.fopen", "OpaquePointer"), CALL_CLASS_FALLIBLE_ORDINARY)
        self.assertEqual(call_class("user.flush", "Void"), CALL_CLASS_VOID)

    def test_disposition_channels_match_call_class(self) -> None:
        self.assertEqual(disposition_channels_for_call("math.addInt64", "Int64"), frozenset({CALL_CHANNEL_VALUE}))
        self.assertEqual(disposition_channels_for_call("console.writeLine", "Int32"), frozenset({
            CALL_CHANNEL_OK,
            CALL_CHANNEL_ERROR,
        }))
        self.assertEqual(disposition_channels_for_call("c.fopen", "OpaquePointer"), frozenset({
            CALL_CHANNEL_VALUE,
            CALL_CHANNEL_ERROR,
        }))
        self.assertEqual(disposition_channels_for_call("user.flush", "Void"), frozenset({CALL_CHANNEL_VOID}))


if __name__ == "__main__":
    unittest.main()
