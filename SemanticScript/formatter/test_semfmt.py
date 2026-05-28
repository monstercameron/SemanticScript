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
            'storage   module immutable   modalTopText   String   '
            '"\\n  +----+\\n  | Edit note |"\n'
        )
        expected = (
            'storage module immutable modalTopText String '
            '"\\n  +----+\\n  | Edit note |"\n'
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_hash_inside_string_is_not_an_inline_comment(self) -> None:
        source = 'storage module immutable urlText String "https://example.test/#fragment"   # comment\n'
        expected = 'storage module immutable urlText String "https://example.test/#fragment"  # comment\n'
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
        source = "project Demo\n\n\noperation main\n\n\n\nreturn value zeroValue\n"
        expected = "project Demo\n\noperation main\n\nreturn value zeroValue\n"
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
            semfmt.format_source('storage module immutable bad String "unterminated\n')

    def test_formatting_is_idempotent(self) -> None:
        source = (
            "# # rationale: hello\n"
            "call   writeCall  console.writeLine\n"
            'argument writeCall text String "hello # not comment"\n'
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

    def test_preserves_sql_body_indented_island(self) -> None:
        source = (
            "storage   module immutable selectTodoSql SqlText\n"
            "sql   body   selectTodoSql\n"
            "  SELECT id, title\n"
            "  FROM todos\n"
            "  WHERE user_id = ?\n"
            "operation   main\n"
        )
        expected = (
            "storage module immutable selectTodoSql SqlText\n"
            "sql body selectTodoSql\n"
            "  SELECT id, title\n"
            "  FROM todos\n"
            "  WHERE user_id = ?\n"
            "operation main\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_preserves_html_body_indented_island(self) -> None:
        source = (
            "html   template   CardTemplate\n"
            "html   body   template   CardTemplate\n"
            "  <article class=\"card\">\n"
            "    <h1>{{titleText}}</h1>\n"
            "  </article>\n"
            "operation   main\n"
        )
        expected = (
            "html template CardTemplate\n"
            "html body template CardTemplate\n"
            "  <article class=\"card\">\n"
            "    <h1>{{titleText}}</h1>\n"
            "  </article>\n"
            "operation main\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_formats_webserver_app_rows(self) -> None:
        source = (
            "target   webServer\n"
            "webServer   todoWebServer\n"
            "route   todoWebServer   GET   \"/todos/:id\"   showTodoHandler\n"
            "operation   showTodoHandler\n"
            "input   operation   showTodoHandler   request   HttpRequest\n"
            "input operation showTodoHandler response HttpResponse\n"
            "effect   showTodoHandler   read   http.request.path\n"
            "effect showTodoHandler write http.response\n"
            "call   pathParamCall   http.requestPathParam\n"
            'argument   pathParamCall   name   String   "id"\n'
            "call   responseCall   http.responseText\n"
        )
        expected = (
            "target webServer\n"
            "webServer todoWebServer\n"
            'route todoWebServer GET "/todos/:id" showTodoHandler\n'
            "operation showTodoHandler\n"
            "input operation showTodoHandler request HttpRequest\n"
            "input operation showTodoHandler response HttpResponse\n"
            "effect showTodoHandler read http.request.path\n"
            "effect showTodoHandler write http.response\n"
            "call pathParamCall http.requestPathParam\n"
            'argument pathParamCall name String "id"\n'
            "call responseCall http.responseText\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_formats_new_cutover_row_spacing(self) -> None:
        source = (
            "import   math   standard.math\n"
            "type   SearchResult   result   ok   Int64   error   SearchError\n"
            'purpose   operation   binarySearch   "Return index."\n'
            "input   operation   binarySearch   needle   Int64\n"
            "output   operation   binarySearch   SearchResult\n"
            "storage   module   immutable   target   Int64   42\n"
            "memory   binarySearch   mutable   low   Int64   0\n"
            "memory   binarySearch   heap   no\n"
            "call   elementCall   array.tryGet\n"
            "argument   elementCall   index   Int64   mid\n"
            "run   elementCall\n"
            "bind   value   isMatch   Bool   matchCall\n"
            "bind   ok   midValue   Int64   elementCall\n"
            "bind   error   lookupFailure   SearchError   elementCall\n"
            "jump   target   searchLoop\n"
        )
        expected = (
            "import math standard.math\n"
            "type SearchResult result ok Int64 error SearchError\n"
            'purpose operation binarySearch "Return index."\n'
            "input operation binarySearch needle Int64\n"
            "output operation binarySearch SearchResult\n"
            "storage module immutable target Int64 42\n"
            "memory binarySearch mutable low Int64 0\n"
            "memory binarySearch heap no\n"
            "call elementCall array.tryGet\n"
            "argument elementCall index Int64 mid\n"
            "run elementCall\n"
            "bind value isMatch Bool matchCall\n"
            "bind ok midValue Int64 elementCall\n"
            "bind error lookupFailure SearchError elementCall\n"
            "jump target searchLoop\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_formats_return_ignore_and_bind_variants(self) -> None:
        source = (
            "bind   value   exitCode   ExitCode   exitCall\n"
            "bind   ok   foundIndex   Int64   searchCall\n"
            "bind   error   searchError   SearchError   searchCall\n"
            "return   value   ExitCode.Ok\n"
            "return   ok   foundIndex\n"
            "return   error   searchError\n"
            "return   void\n"
            "ignore   value   source   printCall   type   Int32\n"
            "ignore   ok   source   writeCall   type   Int32\n"
            "ignore   error   source   metricLogCall\n"
            "ignore   void   source   flushCall\n"
        )
        expected = (
            "bind value exitCode ExitCode exitCall\n"
            "bind ok foundIndex Int64 searchCall\n"
            "bind error searchError SearchError searchCall\n"
            "return value ExitCode.Ok\n"
            "return ok foundIndex\n"
            "return error searchError\n"
            "return void\n"
            "ignore value source printCall type Int32\n"
            "ignore ok source writeCall type Int32\n"
            "ignore error source metricLogCall\n"
            "ignore void source flushCall\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_branch_if_pair_moves_separators_after_attached_else(self) -> None:
        source = (
            "branch   if   condition   isMatch   target   found\n"
            "\n"
            "# false path stays documented\n"
            "branch   else   target   checkBelow\n"
            "label   found\n"
        )
        expected = (
            "branch if condition isMatch target found\n"
            "branch else target checkBelow\n"
            "\n"
            "# false path stays documented\n"
            "label found\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_branch_error_pair_moves_comment_after_attached_else(self) -> None:
        source = (
            "branch   error   source   searchCall   target   reportFailure\n"
            "# success path\n"
            "branch   else   target   reportSuccess\n"
        )
        expected = (
            "branch error source searchCall target reportFailure\n"
            "branch else target reportSuccess\n"
            "# success path\n"
        )
        self.assertEqual(semfmt.format_source(source), expected)

    def test_rejects_replaced_old_syntax_rows(self) -> None:
        rows = [
            "importModule math standard.math\n",
            "type SearchResult Result Int64 SearchError\n",
            'purpose binarySearch "Return index."\n',
            "input binarySearch needle Int64\n",
            "output binarySearch SearchResult\n",
            "const target Int64 42\n",
            "let low Int64 0\n",
            "var high Int64 0\n",
            "memoryHeap binarySearch no\n",
            "htmlTemplate CardTemplate\n",
            "htmlArg CardTemplate titleText String\n",
            "htmlBody CardTemplate\n",
            "set local high newHigh\n",
            "set module searchAttempts nextAttempts\n",
            "bind lengthValue Int64 lengthCall\n",
            "bindOk foundIndex Int64 searchCall\n",
            "bindError searchError SearchError searchCall\n",
            "arg elementCall index mid\n",
            "branchIf isMatch found\n",
            "branchIfError searchCall reportFailure\n",
            "branch searchLoop\n",
            "returnValue exitCode\n",
            "returnOk okResponse\n",
            "returnError parseError\n",
            "returnVoid\n",
            "ignoreValue printCall Int32\n",
            "ignoreOk writeCall Int32\n",
            "ignoreError stopServerCall\n",
            "ignore value source flushCall type Void\n",
            "call.fn elementCall array.tryGet\n",
            "argument call=elementCall name=index type=Int64 value=mid\n",
            "@operation binarySearch\n",
        ]
        for row in rows:
            with self.subTest(row=row.strip()):
                with self.assertRaises(semfmt.FormatError):
                    semfmt.format_source(row)

    def test_purpose_accepts_abstraction_subject_kinds(self) -> None:
        # `purpose <abstraction> NAME "..."` must format cleanly: the compiler's
        # missingPurpose advisory demands these rows, so the formatter rejecting
        # them creates an unsatisfiable loop (check wants the row, fmt --check
        # rejects it). Keep in sync with semsc._PURPOSE_SUBJECT_KINDS.
        accepted = [
            'purpose webServer appServer "Serve the dashboard."\n',
            'purpose capability stdoutWriter "Authorize stdout writes."\n',
            'purpose record TaskRow "A task row."\n',
            'purpose resource dbHandle "The database handle."\n',
            'purpose validator inputCheck "Validate input."\n',
            'purpose codec taskCodec "Encode a task."\n',
            'purpose policy retryPolicy "Retry policy."\n',
        ]
        for row in accepted:
            with self.subTest(row=row.strip()):
                # Should not raise; formatting is a no-op for an already-clean row.
                semfmt.format_source(row)

    def test_invariant_still_requires_module_or_operation(self) -> None:
        # invariant accepts only module|operation in the parser, so the formatter
        # must keep rejecting abstraction subjects for invariant.
        with self.assertRaises(semfmt.FormatError):
            semfmt.format_source('invariant webServer appServer "x"\n')


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


class TestCutoverOutput(unittest.TestCase):
    def test_idempotent_cutover_sample_has_no_replaced_row_verbs(self) -> None:
        source = (
            "project   Tiny\n"
            "operation   main\n"
            "input   operation   main   console   Console\n"
            "output   operation   main   ExitCode\n"
            "label   startMain\n"
            "call   flushCall   console.flush\n"
            "run   flushCall\n"
            "ignore   void   source   flushCall\n"
            "return   value   ExitCode.Ok\n"
        )
        once = semfmt.format_source(source)
        twice = semfmt.format_source(once)
        self.assertEqual(once, twice)

        for line in once.splitlines():
            tokens, _ = semfmt.tokenize_code_prefix(line)
            if not tokens:
                continue
            self.assertNotIn(tokens[0].raw, semfmt.REPLACED_ROW_VERBS)


if __name__ == "__main__":
    unittest.main()
