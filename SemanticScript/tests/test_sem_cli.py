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
