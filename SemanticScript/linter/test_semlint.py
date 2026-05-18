"""Focused regression tests for the stable semlint.py surface.

Run from repo root: `python -m unittest SemanticScript/linter/test_semlint.py -v`
"""

from pathlib import Path
import sys
import tempfile
import unittest


LINTER_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(LINTER_DIR))

import semlint  # noqa: E402


def _lint_source(source_text: str):
    with tempfile.TemporaryDirectory() as temp_dir:
        fixture_path = Path(temp_dir) / "fixture.sscript"
        fixture_path.write_text(source_text, encoding="utf-8")
        return semlint.lint_program(semlint.parse_file(fixture_path))


def _lint_source_at(relative_path: str, source_text: str):
    with tempfile.TemporaryDirectory() as temp_dir:
        fixture_path = Path(temp_dir) / relative_path
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(source_text, encoding="utf-8")
        return semlint.lint_program(semlint.parse_file(fixture_path))


def _rules(diagnostics):
    return [diagnostic.rule for diagnostic in diagnostics]


class StableSemlintTests(unittest.TestCase):
    def test_hierarchical_capability_covers_request_method(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

capability httpRequestReader http.request read

operation methodEchoHandler
input methodEchoHandler request HttpRequest
output methodEchoHandler CSignedInt32
effect methodEchoHandler read http.request.method
memory methodEchoHandler arena request
async methodEchoHandler no
useCapability methodEchoHandler httpRequestReader
purpose methodEchoHandler "Read the method"

label startMethodEchoHandler

call methodReadCall http.requestMethod
arg methodReadCall request request
run methodReadCall
ignoreValue methodReadCall CNullTerminatedByteString
const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        rules = _rules(diagnostics)
        self.assertNotIn("missingCapabilityUse", rules)
        self.assertNotIn("overdeclaredEffect", rules)

    def test_http_request_readers_cover_specific_effects(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

capability httpRequestReader http.request read

operation debugHandler
input debugHandler request HttpRequest
output debugHandler CSignedInt32
effect debugHandler read http.request.header
effect debugHandler read http.request.query
effect debugHandler read http.request.body
memory debugHandler arena request
async debugHandler no
useCapability debugHandler httpRequestReader
purpose debugHandler "Read debug request surfaces"

label startDebugHandler

const headerName CNullTerminatedByteString "x-sem-test"
const queryName CNullTerminatedByteString "name"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name headerName
run headerReadCall
ignoreValue headerReadCall CNullTerminatedByteString
call queryReadCall http.requestQueryParam
arg queryReadCall request request
arg queryReadCall name queryName
run queryReadCall
ignoreValue queryReadCall CNullTerminatedByteString
call bodyReadCall http.requestBodyText
arg bodyReadCall request request
run bodyReadCall
ignoreValue bodyReadCall CNullTerminatedByteString
const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertNotIn("overdeclaredEffect", _rules(diagnostics))

    def test_effect_without_used_capability_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

capability httpResponseWriter http.response write

operation writeTextResponse
output writeTextResponse CSignedInt32
effect writeTextResponse write http.response
memory writeTextResponse arena request
async writeTextResponse no
purpose writeTextResponse "Write a response"

label startWriteTextResponse

const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("missingCapabilityUse", _rules(diagnostics))

    def test_imported_capability_use_is_not_reported_as_missing_local_declaration(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1
module fixture

importModule stdio

operation main
output main CSignedInt32
effect main write console.stdout
memory main arena request
async main no
useCapability main stdoutWriteCapability
purpose main "Use an imported stdio capability"

label startMain

const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        rules = _rules(diagnostics)
        self.assertNotIn("unknownCapabilityReference", rules)
        self.assertNotIn("missingCapabilityUse", rules)

    def test_unknown_imported_capability_name_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1
module fixture

importModule stdio

operation main
output main CSignedInt32
effect main write console.stdout
memory main arena request
async main no
useCapability main stdoutWriteCapabilty
purpose main "Typo an imported stdio capability"

label startMain

const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        rules = _rules(diagnostics)
        self.assertIn("unknownCapabilityReference", rules)
        self.assertIn("missingCapabilityUse", rules)

    def test_response_json_and_cancellation_token_effects_are_recognized(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

capability httpRequestReader http.request read
capability httpResponseWriter http.response write

operation jsonHandler
input jsonHandler request HttpRequest
input jsonHandler response HttpResponse
output jsonHandler CSignedInt32
effect jsonHandler read http.request.cancellationToken
effect jsonHandler write http.response
memory jsonHandler arena request
async jsonHandler no
useCapability jsonHandler httpRequestReader
useCapability jsonHandler httpResponseWriter
purpose jsonHandler "Read cancellation and write JSON"

label startJsonHandler

call cancellationReadCall http.requestCancellationToken
arg cancellationReadCall request request
run cancellationReadCall
ignoreValue cancellationReadCall CancellationToken

const okStatus CSignedInt32 200
call responseWriteCall http.responseJson
arg responseWriteCall response response
arg responseWriteCall status okStatus
arg responseWriteCall body "{}"
run responseWriteCall
bind responseStatus CSignedInt32 responseWriteCall
returnValue responseStatus
""".strip()
        )

        rules = _rules(diagnostics)
        self.assertNotIn("missingEffectDeclaration", rules)
        self.assertNotIn("missingCapabilityUse", rules)

    def test_overdeclared_http_request_read_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

operation homeHandler
input homeHandler request HttpRequest
output homeHandler CSignedInt32
effect homeHandler read http.request.path
memory homeHandler arena request
async homeHandler no
purpose homeHandler "Static route"

label startHomeHandler

const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("overdeclaredEffect", _rules(diagnostics))

    def test_dangling_route_metadata_selector_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
purpose fixtureServer "Serve routes"
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/" homeHandler
timeoutBudget requestTimeoutBudget DurationMilliseconds 2000
purpose requestTimeoutBudget "Bound requests"
routeTimeout fixtureServer homeRoute requestTimeoutBudget

operation homeHandler
output homeHandler CSignedInt32
memory homeHandler arena request
async homeHandler no
purpose homeHandler "Static route"

label startHomeHandler

const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("danglingRouteMetadata", _rules(diagnostics))

    def test_routed_handler_native_http_abi_is_checked_in_relaxed_sem_profile(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/health" healthHandler

operation healthHandler
input healthHandler request HttpRequest
output healthHandler HttpResponse
memory healthHandler arena request
async healthHandler no
purpose healthHandler "Wrong handler ABI"

label startHealthHandler

const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("webRouteHandlerAbi", _rules(diagnostics))

    def test_native_http_response_calls_require_explicit_response_status_and_body(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/health" healthHandler

operation healthHandler
input healthHandler request HttpRequest
input healthHandler response HttpResponse
output healthHandler CSignedInt32
memory healthHandler arena request
async healthHandler no
purpose healthHandler "Missing explicit response handle"

label startHealthHandler

const okStatus CSignedInt32 200
const healthBody CNullTerminatedByteString "ok"
call responseWriteCall http.responseText
arg responseWriteCall status okStatus
arg responseWriteCall body healthBody
run responseWriteCall
bind responseStatus CSignedInt32 responseWriteCall
returnValue responseStatus
""".strip()
        )

        self.assertIn("httpResponseCallAbi", _rules(diagnostics))

    def test_native_http_response_header_requires_response_name_and_value(self):
        diagnostics = _lint_source_at(
            "SemanticScript/sem/feature_tests/fixture.sscript",
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/health" healthHandler

operation healthHandler
input healthHandler request HttpRequest
input healthHandler response HttpResponse
output healthHandler CSignedInt32
memory healthHandler arena request
async healthHandler no
purpose healthHandler "Missing response header value"

label startHealthHandler

const headerName CNullTerminatedByteString "X-Test"
call responseHeaderCall http.responseHeader
arg responseHeaderCall response response
arg responseHeaderCall name headerName
run responseHeaderCall
const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("httpResponseCallAbi", _rules(diagnostics))

    def test_native_http_response_bytes_requires_explicit_length(self):
        diagnostics = _lint_source_at(
            "SemanticScript/sem/feature_tests/fixture.sscript",
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer POST "/bytes" bytesHandler

operation bytesHandler
input bytesHandler request HttpRequest
input bytesHandler response HttpResponse
output bytesHandler CSignedInt32
memory bytesHandler arena request
async bytesHandler no
purpose bytesHandler "Missing explicit binary response length"

label startBytesHandler

const okStatus CSignedInt32 200
call requestBodyCall http.requestBodyBytes
arg requestBodyCall request request
run requestBodyCall
bind requestBody COpaqueMemoryAddress requestBodyCall
call responseBytesCall http.responseBytes
arg responseBytesCall response response
arg responseBytesCall status okStatus
arg responseBytesCall body requestBody
run responseBytesCall
bind responseStatus CSignedInt32 responseBytesCall
returnValue responseStatus
""".strip()
        )

        self.assertIn("httpResponseCallAbi", _rules(diagnostics))

    def test_native_http_request_header_requires_request_and_name(self):
        diagnostics = _lint_source_at(
            "SemanticScript/sem/feature_tests/fixture.sscript",
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/header" headerHandler

operation headerHandler
input headerHandler request HttpRequest
input headerHandler response HttpResponse
output headerHandler CSignedInt32
memory headerHandler arena request
async headerHandler no
purpose headerHandler "Missing header name argument"

label startHeaderHandler

call headerReadCall http.requestHeader
arg headerReadCall request request
run headerReadCall
const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("httpRequestCallAbi", _rules(diagnostics))

    def test_native_http_multipart_part_requires_request_and_name(self):
        diagnostics = _lint_source_at(
            "SemanticScript/sem/feature_tests/fixture.sscript",
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer POST "/upload" uploadHandler

operation uploadHandler
input uploadHandler request HttpRequest
input uploadHandler response HttpResponse
output uploadHandler CSignedInt32
memory uploadHandler arena request
async uploadHandler no
purpose uploadHandler "Missing multipart part name"

label startUploadHandler

call uploadReadCall http.multipartPartBytes
arg uploadReadCall request request
run uploadReadCall
const okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("httpRequestCallAbi", _rules(diagnostics))

    def test_nullable_http_reader_flow_to_response_is_reported_without_guard_note(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/header" headerHandler

operation headerHandler
input headerHandler request HttpRequest
input headerHandler response HttpResponse
output headerHandler CSignedInt32
memory headerHandler arena request
async headerHandler no
purpose headerHandler "Reflect a header"

label startHeaderHandler

const headerName CNullTerminatedByteString "x-test"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name headerName
run headerReadCall
bind headerValue CNullTerminatedByteString headerReadCall
const okStatus CSignedInt32 200
call responseWriteCall http.responseText
arg responseWriteCall response response
arg responseWriteCall status okStatus
arg responseWriteCall body headerValue
run responseWriteCall
bind responseStatus CSignedInt32 responseWriteCall
returnValue responseStatus
""".strip()
        )

        self.assertIn("nullableHttpValueFlow", _rules(diagnostics))

    def test_nullable_http_reader_flow_with_branch_guard_is_not_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/header" headerHandler

operation headerHandler
input headerHandler request HttpRequest
input headerHandler response HttpResponse
output headerHandler CSignedInt32
memory headerHandler arena request
async headerHandler no
purpose headerHandler "Reflect a header safely"

label startHeaderHandler

const headerName CNullTerminatedByteString "x-test"
const okStatus CSignedInt32 200
const badStatus CSignedInt32 400
const fallbackBody CNullTerminatedByteString "required x-test header"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name headerName
run headerReadCall
bind headerValue CNullTerminatedByteString headerReadCall
call headerNullCheckCall pointer.isNull
arg headerNullCheckCall pointer headerValue
run headerNullCheckCall
bind headerIsNull Bool headerNullCheckCall
branchIf headerIsNull headerAbsent
call responseWriteCall http.responseText
arg responseWriteCall response response
arg responseWriteCall status okStatus
arg responseWriteCall body headerValue
run responseWriteCall
bind responseStatus CSignedInt32 responseWriteCall
returnValue responseStatus
label headerAbsent
call fallbackResponseCall http.responseText
arg fallbackResponseCall response response
arg fallbackResponseCall status badStatus
arg fallbackResponseCall body fallbackBody
run fallbackResponseCall
bind fallbackStatus CSignedInt32 fallbackResponseCall
returnValue fallbackStatus
""".strip()
        )

        self.assertNotIn("nullableHttpValueFlow", _rules(diagnostics))

    def test_nullable_http_reader_flow_can_be_documented_as_negative_behavior(self):
        diagnostics = _lint_source(
            """
project Fixture
target webServer
runtime native 1
module fixture

webServer fixtureServer
serverHost fixtureServer "127.0.0.1"
serverPort fixtureServer 18081
route fixtureServer GET "/header" headerHandler

operation headerHandler
input headerHandler request HttpRequest
input headerHandler response HttpResponse
output headerHandler CSignedInt32
memory headerHandler arena request
async headerHandler no
purpose headerHandler "Reflect a header"
warning headerHandler "Missing x-test intentionally exercises the null-body failure path."

label startHeaderHandler

const headerName CNullTerminatedByteString "x-test"
call headerReadCall http.requestHeader
arg headerReadCall request request
arg headerReadCall name headerName
run headerReadCall
bind headerValue CNullTerminatedByteString headerReadCall
const okStatus CSignedInt32 200
call responseWriteCall http.responseText
arg responseWriteCall response response
arg responseWriteCall status okStatus
arg responseWriteCall body headerValue
run responseWriteCall
bind responseStatus CSignedInt32 responseWriteCall
returnValue responseStatus
""".strip()
        )

        self.assertNotIn("nullableHttpValueFlow", _rules(diagnostics))

    def test_raw_json_string_interpolation_is_reported(self):
        diagnostics = _lint_source(
            r"""
project Fixture
target console
runtime native 1

operation saveTitle
output saveTitle CSignedInt32
memoryHeap saveTitle no
async saveTitle no
purpose saveTitle "Save a title"
invariant saveTitle "Fixture"

label startSaveTitle
storage local immutable itemFormatText CNullTerminatedByteString "{\"title\":\"%s\"}\n"
storage local immutable okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertIn("rawJsonStringInterpolation", _rules(diagnostics))

    def test_split_json_prefix_with_escaping_is_not_reported(self):
        diagnostics = _lint_source(
            r"""
project Fixture
target console
runtime native 1

operation saveTitle
output saveTitle CSignedInt32
memoryHeap saveTitle no
async saveTitle no
purpose saveTitle "Save a title"
invariant saveTitle "Title bytes pass through JSON escaping"

label startSaveTitle
storage local immutable itemPrefixText CNullTerminatedByteString "{\"title\":\""
storage local immutable rawCharacterFormatText CNullTerminatedByteString "%c"
storage local immutable okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertNotIn("rawJsonStringInterpolation", _rules(diagnostics))

    def test_fixed_offset_parser_without_contract_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation loadFixedLine
output loadFixedLine CSignedInt64
effect loadFixedLine read memory.buffer
memoryHeap loadFixedLine no
async loadFixedLine no
purpose loadFixedLine "Load a line"

label startLoadFixedLine
storage local immutable titleValueOffset CSignedInt64 30
storage local immutable zeroValue CSignedInt64 0
returnValue zeroValue
""".strip()
        )

        self.assertIn("fixedOffsetParserContract", _rules(diagnostics))

    def test_fixed_offset_parser_with_exact_contract_is_not_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation loadFixedLine
output loadFixedLine CSignedInt64
effect loadFixedLine read memory.buffer
memoryHeap loadFixedLine no
async loadFixedLine no
purpose loadFixedLine "Load a line"
invariant loadFixedLine "Accepts only the exact object key order emitted by saveFixedLine."

label startLoadFixedLine
storage local immutable titleValueOffset CSignedInt64 30
storage local immutable zeroValue CSignedInt64 0
returnValue zeroValue
""".strip()
        )

        self.assertNotIn("fixedOffsetParserContract", _rules(diagnostics))

    def test_implicit_scalar_width_drift_is_reported_on_set(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation copyFlag
output copyFlag CSignedInt64
memoryHeap copyFlag no
async copyFlag no
purpose copyFlag "Copy a flag"
invariant copyFlag "Fixture"

label startCopyFlag
storage local mutable wideFlag CSignedInt64 0
storage local immutable narrowFlag CSignedInt32 1
set local wideFlag narrowFlag
returnValue wideFlag
""".strip()
        )

        self.assertIn("implicitScalarWidthDrift", _rules(diagnostics))

    def test_bound_resource_with_explicit_close_is_not_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation readFile
output readFile CSignedInt32
effect readFile read filesystem
effect readFile open file
effect readFile close file
memoryHeap readFile no
async readFile no
purpose readFile "Open and close a file"
invariant readFile "The opened handle is passed to fclose before return."

label startReadFile
storage local immutable dataFilePath CNullTerminatedByteString "todos.json"
storage local immutable readMode CNullTerminatedByteString "r"
call openCall c.fopen
arg openCall filename dataFilePath
arg openCall mode readMode
run openCall
bind fileHandle CFileHandle openCall
call closeCall c.fclose
arg closeCall stream fileHandle
run closeCall
ignoreValue closeCall CSignedInt32
storage local immutable okStatus CSignedInt32 0
returnValue okStatus
""".strip()
        )

        self.assertNotIn("cleanupNotProven", _rules(diagnostics))

    def test_relaxed_sem_profile_skips_operation_style_checks(self):
        diagnostics = _lint_source_at(
            "SemanticScript/sem/feature_tests/fixture.sscript",
            """
project Fixture
target console
runtime native 1

operation math.addI64
output math.addI64 CSignedInt64
call writeLine console.writeLine
run writeLine
storage local immutable value CSignedInt64 0
returnValue value
""".strip()
        )

        rules = _rules(diagnostics)
        self.assertNotIn("operationNameCase", rules)
        self.assertNotIn("vagueCallName", rules)
        self.assertNotIn("hiddenFailure", rules)

    def test_nonreturning_process_contract_satisfies_missing_return(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation terminateNow
output terminateNow Void
memoryHeap terminateNow no
async terminateNow no
purpose terminateNow "Terminate the process. Does not return."
invariant terminateNow "Control flow does not return."

label startTerminateNow
call exitCall c.exit
arg exitCall code exitCode
run exitCall
storage local immutable exitCode CSignedInt32 0
""".strip()
        )

        self.assertNotIn("missingReturn", _rules(diagnostics))

    def test_fopen_mode_rejects_over_authorized_filesystem_effect(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation loadTodos
output loadTodos CSignedInt32
effect loadTodos read filesystem
effect loadTodos write filesystem
effect loadTodos open file
effect loadTodos close file
memoryHeap loadTodos no
async loadTodos no
purpose loadTodos "Load a file"

label startLoadTodos
storage local immutable dataFilePath CNullTerminatedByteString "todos.json"
storage local immutable readMode CNullTerminatedByteString "r"
storage local immutable okStatus CSignedInt32 0
call openCall c.fopen
arg openCall filename dataFilePath
arg openCall mode readMode
run openCall
bind fileHandle CFileHandle openCall
call closeCall c.fclose
arg closeCall stream fileHandle
run closeCall
ignoreValue closeCall CSignedInt32
returnValue okStatus
""".strip()
        )

        self.assertIn("overAuthorizedEffect", _rules(diagnostics))

    def test_fopen_write_mode_satisfies_filesystem_write_effect(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation saveTodos
output saveTodos CSignedInt32
effect saveTodos write filesystem
effect saveTodos open file
effect saveTodos close file
memoryHeap saveTodos no
async saveTodos no
purpose saveTodos "Save a file"

label startSaveTodos
storage local immutable dataFilePath CNullTerminatedByteString "todos.json"
storage local immutable writeMode CNullTerminatedByteString "w"
storage local immutable okStatus CSignedInt32 0
call openCall c.fopen
arg openCall filename dataFilePath
arg openCall mode writeMode
run openCall
bind fileHandle CFileHandle openCall
call closeCall c.fclose
arg closeCall stream fileHandle
run closeCall
ignoreValue closeCall CSignedInt32
returnValue okStatus
""".strip()
        )

        self.assertNotIn("overAuthorizedEffect", _rules(diagnostics))

    def test_fopen_without_open_file_effect_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation saveTodos
output saveTodos CSignedInt32
effect saveTodos write filesystem
effect saveTodos close file
memoryHeap saveTodos no
async saveTodos no
purpose saveTodos "Save a file"

label startSaveTodos
storage local immutable dataFilePath CNullTerminatedByteString "todos.json"
storage local immutable writeMode CNullTerminatedByteString "w"
storage local immutable okStatus CSignedInt32 0
call openCall c.fopen
arg openCall filename dataFilePath
arg openCall mode writeMode
run openCall
bind fileHandle CFileHandle openCall
call closeCall c.fclose
arg closeCall stream fileHandle
run closeCall
ignoreValue closeCall CSignedInt32
returnValue okStatus
""".strip()
        )

        self.assertIn("missingEffectDeclaration", _rules(diagnostics))

    def test_result_void_error_without_return_error_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation copyBuffer
output copyBuffer Result CSignedInt64 Void
memoryHeap copyBuffer no
async copyBuffer no
purpose copyBuffer "Copy bytes"

label startCopyBuffer
storage local immutable copiedLength CSignedInt64 0
returnOk copiedLength
""".strip()
        )

        self.assertIn("resultVoidErrorWithoutFailurePath", _rules(diagnostics))

    def test_printf_long_long_with_i32_arg_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation writeDone
output writeDone CSignedInt32
effect writeDone write filesystem
memoryHeap writeDone no
async writeDone no
purpose writeDone "Write a done flag"

label startWriteDone
storage local immutable itemPrefixFormatText CNullTerminatedByteString "{\\"done\\":%lld}"
storage local immutable doneValue CSignedInt32 1
storage local immutable okStatus CSignedInt32 0
call writeCall c.fprintf
arg writeCall stream fileHandle
arg writeCall format itemPrefixFormatText
arg writeCall done doneValue
run writeCall
ignoreValue writeCall CSignedInt32
returnValue okStatus
""".strip()
        )

        self.assertIn("printfFormatWidthMismatch", _rules(diagnostics))

    def test_hide_cursor_without_show_cursor_is_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation runTui
output runTui CSignedInt32
effect runTui write console.stdout
memoryHeap runTui no
async runTui no
purpose runTui "Run terminal UI"

label startRunTui
storage local immutable okStatus CSignedInt32 0
call hideCursorCall hideCursor
run hideCursorCall
ignoreValue hideCursorCall CSignedInt32
returnValue okStatus
""".strip()
        )

        self.assertIn("terminalStateCleanup.missing", _rules(diagnostics))

    def test_hide_cursor_with_show_cursor_defer_is_not_reported(self):
        diagnostics = _lint_source(
            """
project Fixture
target console
runtime native 1

operation runTui
output runTui CSignedInt32
effect runTui write console.stdout
memoryHeap runTui no
async runTui no
purpose runTui "Run terminal UI"
defer restoreCursorOnExit showCursor
deferRunOn restoreCursorOnExit all

label startRunTui
storage local immutable okStatus CSignedInt32 0
call hideCursorCall hideCursor
run hideCursorCall
ignoreValue hideCursorCall CSignedInt32
returnValue okStatus
""".strip()
        )

        self.assertNotIn("terminalStateCleanup.missing", _rules(diagnostics))


if __name__ == "__main__":
    unittest.main()
