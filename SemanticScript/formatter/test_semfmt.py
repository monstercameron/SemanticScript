"""Tests for the SemanticScript formatter.

Run from repo root:
    python -m unittest SemanticScript/formatter/test_semfmt.py -v
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_FORMATTER_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
if _FORMATTER_DIRECTORY not in sys.path:
    sys.path.insert(0, _FORMATTER_DIRECTORY)

import semfmt  # noqa: E402


class TestFormatSource(unittest.TestCase):
    def test_normalizes_code_token_spacing(self) -> None:
        source = "call   writeHelloGreetingCall     console.writeLine\n"
        expected = "call writeHelloGreetingCall console.writeLine\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_preserves_quoted_string_spelling_byte_for_byte(self) -> None:
        source = (
            'storage   local immutable   modalTopText   CNullTerminatedByteString   '
            '"\\n  +----+\\n  | Edit note |"\n'
        )
        expected = (
            'storage local immutable modalTopText CNullTerminatedByteString '
            '"\\n  +----+\\n  | Edit note |"\n'
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_hash_inside_string_is_not_an_inline_comment(self) -> None:
        source = 'const urlText String "https://example.test/#fragment"   # comment\n'
        expected = 'const urlText String "https://example.test/#fragment"  # comment\n'
        self.assertEqual(semfmt.format_source(source), expected)

    def test_inline_comment_is_separated_from_code_by_two_spaces(self) -> None:
        source = "run   writeCall#no space\n"
        expected = "run writeCall  #no space\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_trims_trailing_whitespace(self) -> None:
        source = "project Demo   \n# note   \n"
        expected = "project Demo\n# note\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_collapses_blank_line_runs(self) -> None:
        source = "project Demo\n\n\noperation main\n\n\n\nreturnValue zeroValue\n"
        expected = "project Demo\n\noperation main\n\nreturnValue zeroValue\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_removes_leading_and_trailing_blank_runs(self) -> None:
        source = "\n\nproject Demo\n\n\n"
        expected = "project Demo\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_normalizes_nested_typed_comment_heading(self) -> None:
        source = "# # rationale: explain the operation\n#   continuation remains aligned\n"
        expected = "# rationale: explain the operation\n#   continuation remains aligned\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_can_preserve_nested_typed_comment_heading_when_disabled(self) -> None:
        source = "# # rationale: explain the operation\n"
        self.assertEqual(
            semfmt.format_source(source, normalize_comment_headings=False),
            source,
        )

    def test_crlf_input_keeps_crlf_output(self) -> None:
        source = "project   Demo\r\n\r\noperation   main\r\n"
        expected = "project Demo\r\n\r\noperation main\r\n"
        self.assertEqual(semfmt.format_source(source), expected)

    def test_unterminated_string_raises_format_error(self) -> None:
        with self.assertRaises(semfmt.FormatError):
            semfmt.format_source('const bad String "unterminated\n')

    def test_formatting_is_idempotent(self) -> None:
        source = (
            "# # rationale: hello\n"
            "call   writeCall  console.writeLine\n"
            'arg writeCall text "hello # not comment"\n'
            "\n\n"
            "run writeCall\n"
        )
        once = semfmt.format_source(source)
        twice = semfmt.format_source(once)
        self.assertEqual(once, twice)

    def test_preserves_json_body_indented_island(self) -> None:
        source = (
            "storage   module immutable payloadJsonText JsonText\n"
            "jsonBody   payloadJsonText\n"
            "  {\n"
            '    "message": "keep  spaces",\n'
            '    "items": [1, 2, 3]\n'
            "  }\n"
            "operation   main\n"
        )
        formatted = semfmt.format_source(source)
        expected = (
            "storage module immutable payloadJsonText JsonText\n"
            "jsonBody payloadJsonText\n"
            "  {\n"
            '    "message": "keep  spaces",\n'
            '    "items": [1, 2, 3]\n'
            "  }\n"
            "operation main\n"
        )
        self.assertEqual(formatted, expected)
        island = "\n".join(formatted.splitlines()[2:6])
        self.assertEqual(json.loads(island)["message"], "keep  spaces")

    def test_formats_webserver_app_rows(self) -> None:
        source = (
            "target   webServer\n"
            "webServer   todoWebServer\n"
            "route   todoWebServer   GET   \"/todos/:id\"   showTodoHandler\n"
            "operation   showTodoHandler\n"
            "input   showTodoHandler   request   HttpRequest\n"
            "input showTodoHandler response HttpResponse\n"
            "effect   showTodoHandler   read   http.request.path\n"
            "effect showTodoHandler write http.response\n"
            "call   pathParamCall   http.requestPathParam\n"
            'arg   pathParamCall   name   "id"\n'
            "call   responseCall   http.responseText\n"
        )
        expected = (
            "target webServer\n"
            "webServer todoWebServer\n"
            'route todoWebServer GET "/todos/:id" showTodoHandler\n'
            "operation showTodoHandler\n"
            "input showTodoHandler request HttpRequest\n"
            "input showTodoHandler response HttpResponse\n"
            "effect showTodoHandler read http.request.path\n"
            "effect showTodoHandler write http.response\n"
            "call pathParamCall http.requestPathParam\n"
            'arg pathParamCall name "id"\n'
            "call responseCall http.responseText\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)


class TestCollectPaths(unittest.TestCase):
    def test_collects_supported_files_from_directory_and_skips_third_party(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "main.sem"
            second = root / "lib.sscript"
            ignored = root / "third_party" / "vendor.sem"
            ignored.parent.mkdir()
            first.write_text("project Demo\n", encoding="utf-8")
            second.write_text("project Lib\n", encoding="utf-8")
            ignored.write_text("project Vendor\n", encoding="utf-8")

            paths = {path.name for path in semfmt.collect_paths([str(root)])}

        self.assertEqual(paths, {"main.sem", "lib.sscript"})

    def test_collects_glob_matches(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.sem").write_text("project A\n", encoding="utf-8")
            (root / "b.sscript").write_text("project B\n", encoding="utf-8")
            (root / "notes.txt").write_text("ignored\n", encoding="utf-8")

            paths = {path.name for path in semfmt.collect_paths([str(root / "*.s*")])}

        self.assertEqual(paths, {"a.sem", "b.sscript"})


class TestCli(unittest.TestCase):
    def test_check_mode_reports_drift_without_writing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.sem"
            path.write_text("project   Demo\n", encoding="utf-8")
            stderr = io.StringIO()

            exit_code = semfmt.run(["--check", str(path)], stderr=stderr)

            self.assertEqual(exit_code, 1)
            self.assertIn("would reformat", stderr.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), "project   Demo\n")

    def test_default_mode_writes_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.sem"
            path.write_text("project   Demo\n", encoding="utf-8")

            exit_code = semfmt.run([str(path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), "project Demo\n")

    def test_diff_mode_prints_unified_diff_without_writing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.sem"
            path.write_text("project   Demo\n", encoding="utf-8")
            stdout = io.StringIO()

            exit_code = semfmt.run(["--diff", str(path)], stdout=stdout)

            self.assertEqual(exit_code, 0)
            self.assertIn("-project   Demo", stdout.getvalue())
            self.assertIn("+project Demo", stdout.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), "project   Demo\n")

    def test_stdin_mode_writes_formatted_source_to_stdout(self) -> None:
        stdout = io.StringIO()
        exit_code = semfmt.run(
            ["--stdin-file-name", "stdin.sem"],
            stdin=io.StringIO("project   Demo\n"),
            stdout=stdout,
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.getvalue(), "project Demo\n")

    def test_stdin_check_mode_reports_drift(self) -> None:
        stderr = io.StringIO()
        exit_code = semfmt.run(
            ["--check", "--stdin-file-name", "stdin.sem"],
            stdin=io.StringIO("project   Demo\n"),
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("would reformat stdin.sem", stderr.getvalue())


class TestCompilerCompatibility(unittest.TestCase):
    def test_formatted_tiny_fixture_still_parses(self) -> None:
        root = Path(__file__).resolve().parents[1]
        compiler_dir = root / "compiler"
        if str(compiler_dir) not in sys.path:
            sys.path.insert(0, str(compiler_dir))
        import semsc  # noqa: E402

        source = (root / "tests" / "tiny.sscript").read_text(encoding="utf-8")
        formatted = semfmt.format_source(source)
        program = semsc.parse(formatted)
        self.assertEqual(program.project_name, "Tiny")


if __name__ == "__main__":
    unittest.main()
