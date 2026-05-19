"""
test_compiler.py - unit tests for the SemanticScript reference compiler.

Covers the smaller, language-level invariants that the parity suite
(`compare.py`) does not directly exercise:

  - tokenizer escape handling
  - parser line-number tracking
  - simple end-to-end compile-and-JIT for a few canonical programs
  - the bootstrap chain stages 3, 4, 5: each one should compile,
    emit deterministic IR, and (when fed through clang) produce an
    executable whose stdout and exit code match the values declared
    in its input .sscript file.

Run:
    python tests/test_compiler.py

Exits non-zero on first failure, prints a summary otherwise.
"""

import os
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
COMPILER_DIR = ROOT / "compiler"
BOOTSTRAP_DIR = ROOT / "bootstrap"
APP_DIR = ROOT.parent / "app"
HELLO_GUI_DIR = APP_DIR / "hello-gui"

sys.path.insert(0, str(COMPILER_DIR))
import semsc  # noqa: E402


FAILURES = []


def check(label, predicate, message=""):
    if predicate:
        print(f"[OK  ] {label}")
    else:
        FAILURES.append(label)
        print(f"[FAIL] {label}: {message}")


def run_semsc_source(source, *args, suffix=".sscript"):
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / f"sample{suffix}"
        src_path.write_text(source, encoding="utf-8", newline="\n")
        return subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), *args],
            capture_output=True, text=True,
        )


def _gui_support_pending_message(message):
    """Return true for the current pre-GUI compiler diagnostics.

    These checks let this test file carry the GUI contract before the parser,
    build tape, and codegen land. As soon as those phases accept the sample,
    the tests below switch from pending checks to concrete model/IR asserts.
    """
    pending_fragments = (
        "targetRuntime value `windowsGui` is invalid",
        "unknown top-level declaration: gui",
        "unknown build-tape row `gui",
        "standard.gui",
        "gui.runWindow",
        "unknown call target",
        "not a declared operation",
        "_GUI_CONTROL_KINDS",
        "_compile_gui_program",
        "entry mode `windowsGui`",
        "windowsGui` is spec-defined",
        "not been wired into this compiler",
        "not implemented",
    )
    return any(fragment in message for fragment in pending_fragments)


# ============================================================
# Tokenizer
# ============================================================

def test_tokenizer():
    toks = semsc.tokenize_line('const greeting CNullTerminatedByteString "Hi \\"world\\""')
    check("tokenizer: 4 tokens",
          len(toks) == 4,
          f"got {len(toks)} tokens: {toks!r}")
    check("tokenizer: string is unescaped",
          toks[3] == ("str", 'Hi "world"'),
          f"got {toks[3]!r}")

    toks2 = semsc.tokenize_line("# this is a comment")
    check("tokenizer: comment splits into '#' + body",
          toks2 == ["#", "this is a comment"],
          f"got {toks2!r}")

    toks3 = semsc.tokenize_line("   ")
    check("tokenizer: whitespace-only -> empty",
          toks3 == [],
          f"got {toks3!r}")


# ============================================================
# Parser
# ============================================================

def test_parser_minimal():
    src = "\n".join([
        "project Minimal",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "output main Result ExitCode MainError",
        "memory main heap no",
        "async main no",
        "purpose main \"minimal program\"",
        "label startMain",
        "const exitCodeValue ExitCode 0",
        "returnOk exitCodeValue",
        "",
    ])
    prog = semsc.parse(src)
    check("parser: project recorded",
          prog.project_name == "Minimal",
          f"got {prog.project_name!r}")
    check("parser: operation main recorded",
          "main" in prog.operations,
          f"got operations: {list(prog.operations)}")


def test_parser_syntax_error_has_line():
    bad = "\n".join([
        "project Bad",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "label startMain",
        # This `returnOk` references something never declared. The parser
        # itself accepts that; codegen later raises. So instead use a verb
        # that the parser rejects.
        "CompletelyUnknownVerbThatShouldFail x y",
        "",
    ])
    raised = False
    msg = ""
    try:
        semsc.parse(bad)
    except SyntaxError as e:
        raised = True
        msg = str(e)
    check("parser: unknown verb raises SyntaxError",
          raised,
          "no exception raised")
    check("parser: SyntaxError message names the source line",
          "line 7" in msg or "line " in msg,
          f"msg = {msg!r}")


def test_parser_module_namespace_contract():
    prog = semsc.parse("\n".join([
        "project ModuleOk",
        "module examples.valid_module",
        "",
    ]))
    check("parser: module namespace recorded",
          prog.module_name == "examples.valid_module",
          f"got {prog.module_name!r}")

    raised = False
    msg = ""
    try:
        semsc.parse("\n".join([
            "project ModuleBad",
            "module examples.one",
            "module examples.two",
            "",
        ]))
    except SyntaxError as e:
        raised = True
        msg = str(e)
    check("parser: conflicting module namespaces rejected",
          raised and "conflicting module declarations" in msg,
          f"raised={raised} msg={msg!r}")


def test_parser_language_mode_strict_executable():
    strict_source = "\n".join([
        "languageMode strictExecutable",
        "project StrictMode",
        "operation main",
        "output main Result ExitCode MainError",
        "precondition main \"caller validates inputs\"",
        "label startMain",
        "const exitCodeValue ExitCode 0",
        "returnOk exitCodeValue",
        "",
    ])
    prog = semsc.parse(strict_source)
    check("parser: strictExecutable language mode recorded",
          prog.language_modes == ["strictExecutable"],
          f"got {prog.language_modes!r}")
    main_op = prog.operations.get("main")
    check("parser: documented strict body metadata still parses",
          main_op is not None
          and any(verb == "precondition" for verb, _args, _line in main_op.lines),
          f"lines = {main_op.lines if main_op is not None else None!r}")

    permissive_source = "\n".join([
        "project NonStrictMode",
        "misspelledTopLevel Row",
        "operation main",
        "misspelledBody row",
        "",
    ])
    prog = semsc.parse(permissive_source)
    main_op = prog.operations.get("main")
    check("parser: non-strict keeps permissive top-level metadata",
          "Row" in prog.hard_metadata
          and "misspelledTopLevel" in prog.hard_metadata["Row"],
          f"metadata = {prog.hard_metadata!r}")
    check("parser: non-strict keeps permissive body metadata",
          main_op is not None
          and any(verb == "misspelledBody" for verb, _args, _line in main_op.lines),
          f"lines = {main_op.lines if main_op is not None else None!r}")

    refined_source = "\n".join([
        "languageMode refinedSyntax",
        "project RefinedMode",
        "researchTop Row \"metadata\"",
        "operation main",
        "researchBody row",
        "",
    ])
    prog = semsc.parse(refined_source)
    main_op = prog.operations.get("main")
    check("parser: refinedSyntax language mode recorded",
          prog.language_modes == ["refinedSyntax"],
          f"got {prog.language_modes!r}")
    check("parser: refinedSyntax preserves permissive top-level metadata",
          "Row" in prog.hard_metadata
          and "researchTop" in prog.hard_metadata["Row"],
          f"metadata = {prog.hard_metadata!r}")
    check("parser: refinedSyntax preserves permissive body metadata",
          main_op is not None
          and any(verb == "researchBody" for verb, _args, _line in main_op.lines),
          f"lines = {main_op.lines if main_op is not None else None!r}")

    bad_mode_raised = False
    bad_mode_msg = ""
    try:
        semsc.parse("languageMode strictExecutabel\n")
    except SyntaxError as e:
        bad_mode_raised = True
        bad_mode_msg = str(e)
    check("parser: unknown languageMode is rejected",
          bad_mode_raised and "not a known language mode value" in bad_mode_msg,
          f"msg = {bad_mode_msg!r}")

    incompatible_raised = False
    incompatible_msg = ""
    try:
        semsc.parse("languageMode strictExecutable\nlanguageMode refinedSyntax\n")
    except SyntaxError as e:
        incompatible_raised = True
        incompatible_msg = str(e)
    check("parser: incompatible language modes are rejected",
          incompatible_raised and "cannot be combined" in incompatible_msg,
          f"msg = {incompatible_msg!r}")

    bad_top = "\n".join([
        "languageMode strictExecutable",
        "project BadTop",
        "misspelledTopLevel Row",
        "",
    ])
    proc = run_semsc_source(bad_top, "--parse-only", "--quiet")
    check("parser: strictExecutable rejects unknown lowercase top-level verb without lint",
          proc.returncode == 2
          and "misspelledTopLevel" in proc.stderr
          and "languageMode refinedSyntax" in proc.stderr,
          f"returncode={proc.returncode} stderr={proc.stderr!r}")

    bad_body = "\n".join([
        "languageMode strictExecutable",
        "project BadBody",
        "operation main",
        "label startMain",
        "misspelledBody row",
        "",
    ])
    proc = run_semsc_source(bad_body, "--parse-only", "--quiet")
    check("parser: strictExecutable rejects unknown lowercase body verb without lint",
          proc.returncode == 2
          and "misspelledBody" in proc.stderr
          and "operation-body" in proc.stderr,
          f"returncode={proc.returncode} stderr={proc.stderr!r}")


def test_build_registry_imports_registered_module():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        module_path = root / "main.sem"
        build_path.write_text("\n".join([
            "buildProject registrySmoke",
            "project RegistrySmoke",
            "modulePath registrySmoke github.com/example/registry-smoke",
            "languageVersion registrySmoke \"1.0\"",
            "projectVersion registrySmoke \"1.0.0\"",
            "projectLicense registrySmoke MIT",
            "sourceRoot registrySmoke \".\"",
            "targetRuntime registrySmoke nativeExe",
            "buildProfile registrySmoke dev",
            "optLevel registrySmoke 2",
            "runtimeChecks registrySmoke panic",
            "persistLlvmIr registrySmoke auto",
            "target console",
            "runtime native 1",
            "entry console main",
            "registerModule registrySmoke app.todo \".\"",
            "mainFile registrySmoke \"main.sem\"",
            "mainOperation registrySmoke main",
            "importModule app.todo",
            "",
        ]), encoding="utf-8", newline="\n")
        module_path.write_text("\n".join([
            "module app.todo",
            "exportOperation app.todo main",
            "operation main",
            "output main ExitCode",
            "memory main heap no",
            "async main no",
            "purpose main \"registry import smoke\"",
            "returnValue 0",
            "",
        ]), encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--emit-ir", "--quiet"],
            capture_output=True, text=True,
        )
    check("build registry: importModule resolves registered module",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_build_registry_qualified_import_call_lowers():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        module_path = root / "main.sem"
        provider_path = root / "provider.sem"
        build_path.write_text("\n".join([
            "buildProject importQualified",
            "project ImportQualified",
            "modulePath importQualified github.com/example/import-qualified",
            "languageVersion importQualified \"1.0\"",
            "projectVersion importQualified \"1.0.0\"",
            "projectLicense importQualified MIT",
            "sourceRoot importQualified \".\"",
            "targetRuntime importQualified nativeExe",
            "buildProfile importQualified dev",
            "optLevel importQualified 2",
            "runtimeChecks importQualified panic",
            "persistLlvmIr importQualified auto",
            "target console",
            "runtime native 1",
            "entry console main",
            "registerModule importQualified app.consumer \"main.sem\"",
            "registerModule importQualified app.provider \"provider.sem\"",
            "mainFile importQualified \"main.sem\"",
            "mainOperation importQualified main",
            "importModule app.consumer",
            "",
        ]), encoding="utf-8", newline="\n")
        provider_path.write_text("\n".join([
            "module app.provider",
            "exportOperation app.provider providerAnswer",
            "operation providerAnswer",
            "output providerAnswer ExitCode",
            "purpose providerAnswer \"answer\"",
            "returnValue 42",
            "",
        ]), encoding="utf-8", newline="\n")
        module_path.write_text("\n".join([
            "module app.consumer",
            "importModule provider app.provider",
            "operation main",
            "output main ExitCode",
            "purpose main \"consumer\"",
            "call answerCall provider.providerAnswer",
            "run answerCall",
            "bind answer ExitCode answerCall",
            "returnValue answer",
            "",
        ]), encoding="utf-8", newline="\n")
        ir_path = root / "qualified.ll"
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--emit-ir", str(ir_path), "--quiet"],
            capture_output=True, text=True,
        )
        ir_text = ir_path.read_text(encoding="utf-8") if ir_path.exists() else ""
    check("build registry: qualified import call lowers",
          proc.returncode == 0 and "providerAnswer" in ir_text,
          f"rc={proc.returncode} stderr={proc.stderr!r} ir={ir_text!r}")


def test_build_registry_singular_import_call_lowers():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        module_path = root / "main.sem"
        provider_path = root / "provider.sem"
        build_path.write_text("\n".join([
            "buildProject importSingular",
            "project ImportSingular",
            "modulePath importSingular github.com/example/import-singular",
            "languageVersion importSingular \"1.0\"",
            "projectVersion importSingular \"1.0.0\"",
            "projectLicense importSingular MIT",
            "sourceRoot importSingular \".\"",
            "targetRuntime importSingular nativeExe",
            "buildProfile importSingular dev",
            "optLevel importSingular 2",
            "runtimeChecks importSingular panic",
            "persistLlvmIr importSingular auto",
            "target console",
            "runtime native 1",
            "entry console main",
            "registerModule importSingular app.consumer \"main.sem\"",
            "registerModule importSingular app.provider \"provider.sem\"",
            "mainFile importSingular \"main.sem\"",
            "mainOperation importSingular main",
            "importModule app.consumer",
            "",
        ]), encoding="utf-8", newline="\n")
        provider_path.write_text("\n".join([
            "module app.provider",
            "exportOperation app.provider providerAnswer",
            "operation providerAnswer",
            "output providerAnswer ExitCode",
            "purpose providerAnswer \"answer\"",
            "returnValue 42",
            "",
        ]), encoding="utf-8", newline="\n")
        module_path.write_text("\n".join([
            "module app.consumer",
            "importModule provider app.provider",
            "importOperation answer provider providerAnswer",
            "operation main",
            "output main ExitCode",
            "purpose main \"consumer\"",
            "call answerCall answer",
            "run answerCall",
            "bind answerValue ExitCode answerCall",
            "returnValue answerValue",
            "",
        ]), encoding="utf-8", newline="\n")
        ir_path = root / "singular.ll"
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--emit-ir", str(ir_path), "--quiet"],
            capture_output=True, text=True,
        )
        ir_text = ir_path.read_text(encoding="utf-8") if ir_path.exists() else ""
    check("build registry: singular import call lowers",
          proc.returncode == 0 and "providerAnswer" in ir_text,
          f"rc={proc.returncode} stderr={proc.stderr!r} ir={ir_text!r}")


def test_build_registry_missing_source_is_error():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        build_path.write_text("\n".join([
            "buildProject registryBad",
            "project RegistryBad",
            "modulePath registryBad github.com/example/registry-bad",
            "languageVersion registryBad \"1.0\"",
            "projectVersion registryBad \"1.0.0\"",
            "projectLicense registryBad MIT",
            "sourceRoot registryBad \".\"",
            "targetRuntime registryBad nativeExe",
            "buildProfile registryBad dev",
            "optLevel registryBad 2",
            "runtimeChecks registryBad panic",
            "persistLlvmIr registryBad auto",
            "target console",
            "runtime native 1",
            "entry console main",
            "registerModule registryBad app.missing \"missing\"",
            "mainFile registryBad \"main.sem\"",
            "mainOperation registryBad main",
            "importModule app.missing",
            "",
        ]), encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--parse-only", "--quiet"],
            capture_output=True, text=True,
        )
    check("build registry: missing registered module source fails parse",
          proc.returncode == 2 and "registered module `app.missing`" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_rejects_missing_output_contract():
    src = "\n".join([
        "project MissingOutput",
        "entry console main",
        "operation main",
        "purpose main \"exercise missing output diagnostics\"",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict lint: missing output is fatal",
          proc.returncode == 2 and "missingOutputContract" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_rejects_unknown_output_contract_type():
    src = "\n".join([
        "project UnknownOutput",
        "entry console main",
        "operation main",
        "output main MysteryReturnType",
        "purpose main \"exercise unknown output diagnostics\"",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict lint: unknown output type is fatal",
          proc.returncode == 2 and "unknownOutputType" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_requires_effect_capability_or_authority():
    src = "\n".join([
        "project MissingAuthority",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "purpose main \"exercise capability diagnostics\"",
        "invariant main \"Effect is intentionally declared for lint coverage.\"",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict lint: effect without authority is fatal",
          proc.returncode == 2 and "missingCapabilityUse" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")

    authorized_src = "\n".join([
        "project InlineAuthority",
        "entry console main",
        "authority main console.stdout write",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "purpose main \"exercise inline authority coverage\"",
        "invariant main \"Inline authority covers the declared effect.\"",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    authorized = run_semsc_source(
        authorized_src, "--parse-only", "--strict", "--quiet")
    check("strict lint: inline authority covers effect",
          authorized.returncode == 0,
          f"rc={authorized.returncode} stderr={authorized.stderr!r}")


def _strict_http_route_source(
        route_method="GET",
        handler_inputs=None,
        middleware_output="MiddlewareControl",
        middleware_return="continueMiddlewareControl",
        wrapper_forwarder_line="responseBodyForwarder writeTextResponse body",
        handler_body=None):
    if handler_inputs is None:
        handler_inputs = [
            "input healthHandler request HttpRequest",
            "input healthHandler response HttpResponse",
        ]
    if handler_body is None:
        handler_body = [
            "const okStatus CSignedInt32 200",
            "const okBody CNullTerminatedByteString \"ok\\n\"",
            "call wrapperCall writeTextResponse",
            "arg wrapperCall response response",
            "arg wrapperCall status okStatus",
            "arg wrapperCall body okBody",
            "run wrapperCall",
            "bind responseStatus CSignedInt32 wrapperCall",
            "returnValue responseStatus",
        ]
    wrapper_forwarder_lines = (
        [wrapper_forwarder_line] if wrapper_forwarder_line else []
    )
    return "\n".join([
        "languageMode strictExecutable",
        "project StrictHttpContracts",
        "target webServer",
        "runtime native 1",
        "webServer strictServer",
        "purpose strictServer \"strict HTTP fixture server\"",
        "serverHost strictServer \"127.0.0.1\"",
        "serverPort strictServer 18083",
        f"route strictServer {route_method} \"/health\" healthHandler",
        "routeMiddleware strictServer \"/health\" auditMiddleware",
        "authority auditMiddleware http.response write",
        "authority writeTextResponse http.response write",
        "authority healthHandler http.response write",
        "authority healthHandler http.request read",
        "",
        "operation auditMiddleware",
        "input auditMiddleware request HttpRequest",
        "input auditMiddleware response HttpResponse",
        f"output auditMiddleware {middleware_output}",
        "effect auditMiddleware write http.response",
        "purpose auditMiddleware \"strict middleware ABI fixture\"",
        "invariant auditMiddleware \"middleware output shape is explicit\"",
        "memory auditMiddleware arena request",
        "async auditMiddleware no",
        "label startAuditMiddleware",
        f"returnValue {middleware_return}",
        "",
        "operation writeTextResponse",
        "input writeTextResponse response HttpResponse",
        "input writeTextResponse status CSignedInt32",
        "input writeTextResponse body CNullTerminatedByteString",
        "output writeTextResponse CSignedInt32",
        "effect writeTextResponse write http.response",
        "purpose writeTextResponse \"strict response wrapper fixture\"",
        "invariant writeTextResponse \"wrapper forwards body explicitly\"",
        "memory writeTextResponse arena request",
        "async writeTextResponse no",
        *wrapper_forwarder_lines,
        "label startWriteTextResponse",
        "call writeCall http.responseText",
        "arg writeCall response response",
        "arg writeCall status status",
        "arg writeCall body body",
        "run writeCall",
        "bindOk writeStatus CSignedInt32 writeCall",
        "bindError writeCallError CSignedInt32 writeCall",
        "branchIfError writeCall writeFailed",
        "returnValue writeStatus",
        "label writeFailed",
        "returnValue writeCallError",
        "",
        "operation healthHandler",
        *handler_inputs,
        "output healthHandler CSignedInt32",
        "effect healthHandler read http.request",
        "effect healthHandler write http.response",
        "purpose healthHandler \"strict route handler ABI fixture\"",
        "invariant healthHandler \"route handler writes exactly one response\"",
        "memory healthHandler arena request",
        "async healthHandler no",
        "label startHealthHandler",
        *handler_body,
        "",
    ])


def test_strict_web_contracts_reject_invalid_route_method():
    src = _strict_http_route_source(route_method="CONNECT")
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: invalid route method is compile-blocking without lint",
          proc.returncode == 3 and "SS3601" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_accept_lowercase_route_method():
    src = _strict_http_route_source(route_method="get")
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict HTTP: supported route methods are case-insensitive",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_mode_rejects_http_contracts_without_lint_flag():
    src = _strict_http_route_source(route_method="CONNECT")
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable HTTP: invalid route method blocks compile",
          proc.returncode == 3
          and "SS3601" in proc.stderr
          and "semantic.strictExecutable" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_reject_middleware_i32_output():
    src = _strict_http_route_source(
        middleware_output="CSignedInt32",
        middleware_return="0",
    )
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: middleware return is compile-blocking without lint",
          proc.returncode == 3 and "SS3610" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_reject_handler_input_name_mismatch():
    src = _strict_http_route_source(handler_inputs=[
        "input healthHandler req HttpRequest",
        "input healthHandler res HttpResponse",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: route handler names are compile-blocking without lint",
          proc.returncode == 3 and "SS3609" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_reject_missing_response_forwarder():
    src = _strict_http_route_source(wrapper_forwarder_line=None)
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: missing forwarder is compile-blocking without lint",
          proc.returncode == 3 and "SS3615" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_reject_wrong_response_forwarder():
    src = _strict_http_route_source(
        wrapper_forwarder_line="responseBodyForwarder writeTextResponse wrongBody")
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: wrong forwarder is compile-blocking without lint",
          proc.returncode == 3 and "SS3607" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_reject_nullable_header_response_body():
    handler_body = [
        "const okStatus CSignedInt32 200",
        "const tokenHeaderName CNullTerminatedByteString \"X-Token\"",
        "call headerReadCall http.requestHeader",
        "arg headerReadCall request request",
        "arg headerReadCall name tokenHeaderName",
        "run headerReadCall",
        "bind maybeToken CNullTerminatedByteString headerReadCall",
        "call writeCall http.responseText",
        "arg writeCall response response",
        "arg writeCall status okStatus",
        "arg writeCall body maybeToken",
        "run writeCall",
        "bind responseStatus CSignedInt32 writeCall",
        "returnValue responseStatus",
    ]
    src = _strict_http_route_source(handler_body=handler_body)
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: nullable request header is compile-blocking without lint",
          proc.returncode == 3 and "SS3603" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_web_contracts_accept_valid_route_middleware_and_forwarder():
    src = _strict_http_route_source()
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strict HTTP: valid route/middleware/forwarder contract passes without lint",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_rejects_plain_run_for_fallible_heap_allocation():
    src = "\n".join([
        "project StrictUncheckedMalloc",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "authority main heap allocate",
        "operation main",
        "output main Result Void MainError",
        "effect main allocate heap",
        "purpose main \"exercise strict fallible call diagnostics\"",
        "invariant main \"heap allocation failure must be explicit\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call mallocCall c.malloc",
        "arg mallocCall size allocationSize",
        "run mallocCall",
        "returnOk noResult",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict checked calls: c.malloc plain run is fatal",
          proc.returncode == 3
          and "uncheckedFallibleCall" in proc.stderr
          and "c.malloc" in proc.stderr
          and "bind|ignoreValue" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_accepts_complete_legacy_checked_fallible_call_pattern():
    src = "\n".join([
        "project StrictCheckedMalloc",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "authority main heap allocate",
        "authority main heap free",
        "operation main",
        "output main Result Void MainError",
        "effect main allocate heap",
        "effect main free heap",
        "purpose main \"exercise accepted legacy checked call pattern\"",
        "invariant main \"heap allocation failure branches before use\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call mallocCall c.malloc",
        "arg mallocCall size allocationSize",
        "run mallocCall",
        "bindOk heapBuffer COpaqueMemoryAddress mallocCall",
        "bindError mallocCallError MainError mallocCall",
        "branchIfError mallocCall allocationFailed",
        "call freeCall c.free",
        "arg freeCall ptr heapBuffer",
        "run freeCall",
        "returnOk noResult",
        "label allocationFailed",
        "returnError mallocCallError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict checked calls: complete legacy pattern is accepted",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_run_checked_heap_allocation_lowers():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictRunCheckedMalloc",
        "target console",
        "runtime native 1",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "authority main heap allocate",
        "authority main heap free",
        "operation main",
        "output main Result Void MainError",
        "effect main allocate heap",
        "effect main free heap",
        "purpose main \"exercise source-level checked heap allocation\"",
        "invariant main \"allocation failure and cleanup are executable\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call mallocCall c.malloc",
        "arg mallocCall size allocationSize",
        "runChecked mallocCall ok heapBuffer COpaqueMemoryAddress error mallocStatus MainError else allocationFailed",
        "call freeCall c.free",
        "arg freeCall ptr heapBuffer",
        "run freeCall",
        "returnVoid",
        "label allocationFailed",
        "makeError allocationFailure MainError.OutOfMemory",
        "returnError allocationFailure",
        "",
    ])
    proc = run_semsc_source(src, "--emit-ir", "--quiet")
    check("strict checked calls: runChecked malloc compiles without lint flag",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_rejects_plain_run_for_fallible_sqlite_prepare():
    src = "\n".join([
        "project StrictUncheckedSqlitePrepare",
        "entry console main",
        "error MainError",
        "errorCase MainError PrepareFailed",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"exercise strict sqlite fallible call diagnostics\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const database SqliteDatabase 0",
        "const sqlText CNullTerminatedByteString \"select 1\"",
        "call prepareStatementCall sqlite.prepareStatement",
        "arg prepareStatementCall database database",
        "arg prepareStatementCall sql sqlText",
        "run prepareStatementCall",
        "bindOk statement SqliteStatement prepareStatementCall",
        "returnOk noResult",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict checked calls: sqlite.prepareStatement plain run is fatal",
          proc.returncode == 3
          and "uncheckedFallibleCall" in proc.stderr
          and "sqlite.prepareStatement" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_rejects_missing_status_for_fallible_http_response_write():
    src = "\n".join([
        "project StrictUncheckedHttpResponseWrite",
        "entry console main",
        "error MainError",
        "errorCase MainError ResponseWriteFailed",
        "authority main http.response write",
        "operation main",
        "input main response HttpResponse",
        "output main Result Void MainError",
        "effect main write http.response",
        "purpose main \"exercise strict HTTP response status diagnostics\"",
        "invariant main \"response write failure must branch explicitly\"",
        "memory main heap no",
        "async main no",
        "label start",
        "const okStatus CSignedInt32 200",
        "const bodyText CNullTerminatedByteString \"ok\"",
        "const plainType CNullTerminatedByteString \"text/plain\"",
        "call writeResponseCall http.responseText",
        "arg writeResponseCall response response",
        "arg writeResponseCall status okStatus",
        "arg writeResponseCall body bodyText",
        "arg writeResponseCall contentType plainType",
        "run writeResponseCall",
        "returnOk noResult",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--strict", "--quiet")
    check("strict checked calls: missing HTTP response status disposition is fatal",
          proc.returncode == 3
          and "uncheckedFallibleCall" in proc.stderr
          and "http.responseText" in proc.stderr
          and "bind|ignoreValue" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_rejects_heap_allocation_without_oom_branch():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictOwnedHeapUnchecked",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"strict heap allocation must branch on OOM\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call allocationCall c.malloc",
        "arg allocationCall size allocationSize",
        "run allocationCall",
        "bindOk heapBuffer COpaqueMemoryAddress allocationCall",
        "returnOk noResult",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: unchecked heap allocation fails",
          proc.returncode == 3
          and "SS3305" in proc.stderr
          and "allocationCall" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_rejects_heap_allocation_without_free():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictOwnedHeapMissingFree",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"strict heap allocation must have executable free\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call allocationCall c.malloc",
        "arg allocationCall size allocationSize",
        "run allocationCall",
        "bindOk heapBuffer COpaqueMemoryAddress allocationCall",
        "bindError allocationError MainError allocationCall",
        "branchIfError allocationCall allocationFailed",
        "returnOk noResult",
        "label allocationFailed",
        "returnError allocationError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: missing heap free fails",
          proc.returncode == 3
          and "SS3303" in proc.stderr
          and "c.free" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_rejects_double_heap_free():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictOwnedHeapDoubleFree",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"strict heap cleanup must not double free\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call allocationCall c.malloc",
        "arg allocationCall size allocationSize",
        "run allocationCall",
        "bindOk heapBuffer COpaqueMemoryAddress allocationCall",
        "bindError allocationError MainError allocationCall",
        "branchIfError allocationCall allocationFailed",
        "call firstFreeCall c.free",
        "arg firstFreeCall ptr heapBuffer",
        "run firstFreeCall",
        "call secondFreeCall c.free",
        "arg secondFreeCall ptr heapBuffer",
        "run secondFreeCall",
        "returnOk noResult",
        "label allocationFailed",
        "returnError allocationError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: double heap free fails",
          proc.returncode == 3
          and "SS3307" in proc.stderr
          and "heapBuffer" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_accepts_explicit_heap_free():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictOwnedHeapExplicitFree",
        "entry console main",
        "error MainError",
        "errorCase MainError OutOfMemory",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"strict heap cleanup is executable\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const allocationSize CByteCount 8",
        "call allocationCall c.malloc",
        "arg allocationCall size allocationSize",
        "run allocationCall",
        "bindOk heapBuffer COpaqueMemoryAddress allocationCall",
        "bindError allocationError MainError allocationCall",
        "branchIfError allocationCall allocationFailed",
        "call freeCall c.free",
        "arg freeCall ptr heapBuffer",
        "run freeCall",
        "returnOk noResult",
        "label allocationFailed",
        "returnError allocationError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: explicit heap free passes",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_rejects_sqlite_open_setup_failure_without_close():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictSqliteOpenCleanupMissing",
        "entry console main",
        "error MainError",
        "errorCase MainError OpenFailed",
        "errorCase MainError SchemaFailed",
        "storage module immutable schemaSql CNullTerminatedByteString \"create table t(id integer)\"",
        "operation main",
        "output main Result SqliteDatabase MainError",
        "purpose main \"SQLite setup failure must close fresh handle\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const databasePath CNullTerminatedByteString \":memory:\"",
        "call openCall sqlite.openDatabase",
        "arg openCall path databasePath",
        "arg openCall mode inMemorySqliteOpenMode",
        "run openCall",
        "bindOk database SqliteDatabase openCall",
        "bindError openError MainError openCall",
        "branchIfError openCall openFailed",
        "call schemaCall sqlite.exec",
        "arg schemaCall database database",
        "arg schemaCall sql schemaSql",
        "run schemaCall",
        "ignoreOk schemaCall Void",
        "bindError schemaError MainError schemaCall",
        "branchIfError schemaCall schemaFailed",
        "returnOk database",
        "label openFailed",
        "returnError openError",
        "label schemaFailed",
        "returnError schemaError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: sqlite setup failure without close fails",
          proc.returncode == 3
          and "SS3905" in proc.stderr
          and "schemaFailed" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_accepts_sqlite_open_setup_failure_close():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictSqliteOpenCleanup",
        "entry console main",
        "error MainError",
        "errorCase MainError OpenFailed",
        "errorCase MainError SchemaFailed",
        "storage module immutable schemaSql CNullTerminatedByteString \"create table t(id integer)\"",
        "operation main",
        "output main Result SqliteDatabase MainError",
        "purpose main \"SQLite setup failure closes fresh handle\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const databasePath CNullTerminatedByteString \":memory:\"",
        "call openCall sqlite.openDatabase",
        "arg openCall path databasePath",
        "arg openCall mode inMemorySqliteOpenMode",
        "run openCall",
        "bindOk database SqliteDatabase openCall",
        "bindError openError MainError openCall",
        "branchIfError openCall openFailed",
        "call schemaCall sqlite.exec",
        "arg schemaCall database database",
        "arg schemaCall sql schemaSql",
        "run schemaCall",
        "ignoreOk schemaCall Void",
        "bindError schemaError MainError schemaCall",
        "branchIfError schemaCall schemaFailed",
        "returnOk database",
        "label openFailed",
        "returnError openError",
        "label schemaFailed",
        "call closeAfterSchemaFailureCall sqlite.closeDatabase",
        "arg closeAfterSchemaFailureCall database database",
        "run closeAfterSchemaFailureCall",
        "ignoreOk closeAfterSchemaFailureCall Void",
        "bindError closeError MainError closeAfterSchemaFailureCall",
        "branchIfError closeAfterSchemaFailureCall closeFailed",
        "returnError schemaError",
        "label closeFailed",
        "returnError closeError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: sqlite setup failure close passes",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_rejects_sqlite_prepare_without_finalize():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictSqlitePrepareMissingFinalize",
        "entry console main",
        "error MainError",
        "errorCase MainError PrepareFailed",
        "storage module immutable selectSql CNullTerminatedByteString \"select 1\"",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"SQLite statements must be finalized\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const database SqliteDatabase 0",
        "call prepareCall sqlite.prepareStatement",
        "arg prepareCall database database",
        "arg prepareCall sql selectSql",
        "run prepareCall",
        "bindOk statement SqliteStatement prepareCall",
        "bindError prepareError MainError prepareCall",
        "branchIfError prepareCall prepareFailed",
        "returnOk noResult",
        "label prepareFailed",
        "returnError prepareError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: sqlite prepare without finalize fails",
          proc.returncode == 3
          and "SS3906" in proc.stderr
          and "prepareCall" in proc.stderr,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_strict_executable_accepts_sqlite_prepare_finalize_defer():
    src = "\n".join([
        "languageMode strictExecutable",
        "project StrictSqlitePrepareFinalize",
        "entry console main",
        "error MainError",
        "errorCase MainError PrepareFailed",
        "storage module immutable selectSql CNullTerminatedByteString \"select 1\"",
        "operation main",
        "output main Result Void MainError",
        "purpose main \"SQLite statement finalize defer is lowered\"",
        "memory main heap yes",
        "async main no",
        "label start",
        "const database SqliteDatabase 0",
        "call prepareCall sqlite.prepareStatement",
        "arg prepareCall database database",
        "arg prepareCall sql selectSql",
        "run prepareCall",
        "bindOk statement SqliteStatement prepareCall",
        "bindError prepareError MainError prepareCall",
        "branchIfError prepareCall prepareFailed",
        "defer finalizeStatementDefer sqlite.finalizeStatement statement",
        "returnOk noResult",
        "label prepareFailed",
        "returnError prepareError",
        "",
    ])
    proc = run_semsc_source(src, "--parse-only", "--quiet")
    check("strictExecutable owned resources: sqlite finalize defer passes",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


# ============================================================
# End-to-end compile + JIT for a canonical program
# ============================================================

def test_compile_hello_world_to_ir():
    src_path = ROOT / "sem" / "hello.sscript"
    source = src_path.read_text(encoding="utf-8")
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    check("compile: hello.sscript defines @main",
          "define i32 @\"main\"" in ir_text or "define i32 @main" in ir_text,
          "no main defined in IR")
    check("compile: hello.sscript references puts",
          "@\"puts\"" in ir_text or "@puts" in ir_text,
          "no puts in IR")


def test_compile_i32_comparison_to_i32_ir():
    source = "\n".join([
        "project I32Compare",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "enum StatusCode repr CSignedInt32",
        "enumCase StatusCode NegativeStatus -1",
        "enumCase StatusCode ZeroStatus 0",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "purpose main \"exercise width-specific i32 comparison lowering\"",
        "invariant main \"math.lessThanCSignedInt32 lowers to an i32 signed compare\"",
        "label startMain",
        "const successExit ExitCode 0",
        "const failureExit ExitCode 1",
        "call negativeCheckCall math.lessThanCSignedInt32",
        "arg negativeCheckCall left NegativeStatus",
        "arg negativeCheckCall right ZeroStatus",
        "run negativeCheckCall",
        "bind statusIsNegative Bool negativeCheckCall",
        "branchIf statusIsNegative returnSuccess",
        "returnValue failureExit",
        "label returnSuccess",
        "returnValue successExit",
        "",
    ])
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    check("compile: math.lessThanCSignedInt32 uses i32 compare",
          "icmp slt i32" in ir_text,
          f"IR was:\n{ir_text}")


def test_compile_rejects_implicit_i32_to_i64_math():
    source = "\n".join([
        "project StrictMath",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "purpose main \"reject implicit math widening\"",
        "const successExit ExitCode 0",
        "const leftStatus CSignedInt32 1",
        "const rightStatus CSignedInt32 1",
        "call statusCheckCall math.equalI64",
        "arg statusCheckCall left leftStatus",
        "arg statusCheckCall right rightStatus",
        "run statusCheckCall",
        "returnValue successExit",
        "",
    ])
    try:
        prog = semsc.parse(source)
        semsc.Codegen(prog).compile()
    except (ValueError, semsc.CompilerDiagnosticError) as exc:
        message = str(exc)
        check("compile: math.equalI64 rejects implicit i32 widening",
              "expects I64 exactly" in message
              and "explicit conversion operation" in message,
              message)
        return
    check("compile: math.equalI64 rejects implicit i32 widening",
          False,
          "compile unexpectedly succeeded")


def test_compile_explicit_i32_to_i64_conversion_lowers_to_sext():
    source = "\n".join([
        "project ExplicitMathConversion",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "purpose main \"explicit conversion is visible in IR\"",
        "const successExit ExitCode 0",
        "const sourceValue CSignedInt32 -1",
        "call widenCall math.signExtendCSignedInt32ToCSignedInt64",
        "arg widenCall inputValue sourceValue",
        "run widenCall",
        "bind widenedValue CSignedInt64 widenCall",
        "returnValue successExit",
        "",
    ])
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    check("compile: explicit i32->i64 conversion uses sext",
          "sext i32" in ir_text and " to i64" in ir_text,
          f"IR was:\n{ir_text}")


def test_compile_pointer_load_byte_sign_extends_to_i32():
    source = "\n".join([
        "project LoadByteShape",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "purpose main \"pointer.loadByte returns a signed CSignedInt32 byte value\"",
        "const successExit ExitCode 0",
        "const text CNullTerminatedByteString \"A\"",
        "const zeroOffset CByteCount 0",
        "call loadByteCall pointer.loadByte",
        "arg loadByteCall buffer text",
        "arg loadByteCall offset zeroOffset",
        "run loadByteCall",
        "bind loadedByte CSignedInt32 loadByteCall",
        "returnValue successExit",
        "",
    ])
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    check("compile: pointer.loadByte loads i8",
          "load i8" in ir_text,
          f"IR was:\n{ir_text}")
    check("compile: pointer.loadByte sign-extends to i32",
          "sext i8" in ir_text and " to i32" in ir_text,
          f"IR was:\n{ir_text}")


def test_html_template_parser_records_body_and_rejects_bad_edges():
    source = "\n".join([
        "project HtmlParser",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate CardTemplate",
        "htmlArg CardTemplate titleText HtmlText",
        "htmlBody CardTemplate",
        "  <article class=\"card\">",
        "    <h1>{htmlArg.titleText}</h1>",
        "  </article>",
        "operation main",
        "output main ExitCode",
        "purpose main \"parser-only HTML island smoke\"",
        "returnValue 0",
        "",
    ])
    prog = semsc.parse(source)
    template = prog.html_templates.get("CardTemplate")
    check("html parser: template recorded",
          template is not None,
          f"templates={list(prog.html_templates)}")
    check("html parser: arg recorded",
          template is not None
          and template.args == [("titleText", "HtmlText", 6)],
          f"args={getattr(template, 'args', None)!r}")
    check("html parser: indented body preserved until next column-0 verb",
          template is not None
          and template.body_lines == [
              ("<article class=\"card\">", 8),
              ("  <h1>{htmlArg.titleText}</h1>", 9),
              ("</article>", 10),
          ]
          and "main" in prog.operations,
          f"body={getattr(template, 'body_lines', None)!r} ops={list(prog.operations)}")

    bad_cases = [
        ("unknown htmlArg template",
         "project Bad\nhtmlArg MissingTemplate titleText HtmlText\n",
         "htmlArg references unknown htmlTemplate"),
        ("duplicate htmlTemplate",
         "project Bad\nhtmlTemplate Card\nhtmlTemplate Card\n",
         "already declared"),
        ("duplicate htmlArg",
         "\n".join([
             "project Bad",
             "htmlTemplate Card",
             "htmlArg Card titleText HtmlText",
             "htmlArg Card titleText HtmlText",
             "",
         ]),
         "already declares"),
        ("unknown htmlBody template",
         "project Bad\nhtmlBody MissingTemplate\n  <p>bad</p>\n",
         "htmlBody references unknown htmlTemplate"),
        ("duplicate htmlBody",
         "\n".join([
             "project Bad",
             "htmlTemplate Card",
             "htmlBody Card",
             "  <p>first</p>",
             "htmlBody Card",
             "  <p>second</p>",
             "",
         ]),
         "already declares a body"),
    ]
    for label, bad_source, expected in bad_cases:
        raised = False
        msg = ""
        try:
            semsc.parse(bad_source)
        except SyntaxError as exc:
            raised = True
            msg = str(exc)
        check(f"html parser: rejects {label}",
              raised and expected in msg,
              f"raised={raised} msg={msg!r}")


def test_html_template_simple_jit_output():
    source = "\n".join([
        "project HtmlSimple",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate GreetingTemplate",
        "htmlArg GreetingTemplate titleText HtmlText",
        "htmlBody GreetingTemplate",
        "  <h1>{htmlArg.titleText}</h1>",
        "storage module immutable successCode ExitCode 0",
        "storage module immutable greetingTitle HtmlText \"Hello HTML\"",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"hydrate a tiny HTML template and print it\"",
        "call hydrateGreetingCall html.hydrate.GreetingTemplate",
        "arg hydrateGreetingCall titleText greetingTitle",
        "run hydrateGreetingCall",
        "bind greetingHtml HtmlDocument hydrateGreetingCall",
        "call writeGreetingCall console.writeLine",
        "arg writeGreetingCall text greetingHtml",
        "run writeGreetingCall",
        "ignoreValue writeGreetingCall CSignedInt32",
        "returnValue successCode",
        "",
    ])
    proc = run_semsc_source(source, "--run", "--quiet", suffix=".sem")
    check("html simple: JIT run succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html simple: output is exact hydrated HTML plus console newline",
          proc.stdout == "<h1>Hello HTML</h1>\n\n",
          f"stdout={proc.stdout!r}")


def test_html_template_edge_output_repeated_adjacent_and_blank_lines():
    source = "\n".join([
        "project HtmlEdges",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate EdgeTemplate",
        "htmlArg EdgeTemplate title_text HtmlText",
        "htmlArg EdgeTemplate className HtmlClass",
        "htmlBody EdgeTemplate",
        "  <section class=\"{ htmlArg.className }\">{htmlArg.title_text}{htmlArg.title_text}</section>",
        "",
        "  <footer>{ htmlArg.title_text }</footer>",
        "storage module immutable successCode ExitCode 0",
        "storage module immutable edgeTitle HtmlText \"Echo\"",
        "storage module immutable edgeClass HtmlClass \"edge-card\"",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"hydrate edge-case HTML spacing\"",
        "call hydrateEdgeCall html.hydrate.EdgeTemplate",
        "arg hydrateEdgeCall title_text edgeTitle",
        "arg hydrateEdgeCall className edgeClass",
        "run hydrateEdgeCall",
        "bind edgeHtml HtmlDocument hydrateEdgeCall",
        "call writeEdgeCall console.writeLine",
        "arg writeEdgeCall text edgeHtml",
        "run writeEdgeCall",
        "ignoreValue writeEdgeCall CSignedInt32",
        "returnValue successCode",
        "",
    ])
    proc = run_semsc_source(source, "--run", "--quiet", suffix=".sem")
    expected = (
        "<section class=\"edge-card\">EchoEcho</section>\n"
        "\n"
        "<footer>Echo</footer>\n"
        "\n"
    )
    check("html edges: JIT run succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html edges: repeated adjacent args and blank lines render exactly",
          proc.stdout == expected,
          f"stdout={proc.stdout!r} expected={expected!r}")


def test_html_template_raw_style_and_script_do_not_hydrate_braces():
    source = "\n".join([
        "project HtmlRawText",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate RawTemplate",
        "htmlArg RawTemplate titleText HtmlText",
        "htmlBody RawTemplate",
        "  <style>",
        "    .card::before { content: \"{htmlArg.titleText}\"; }",
        "  </style>",
        "  <script>",
        "    const template = \"{htmlArg.titleText}\";",
        "    const object = { value: \"raw\" };",
        "  </script>",
        "  <h1>{htmlArg.titleText}</h1>",
        "storage module immutable successCode ExitCode 0",
        "storage module immutable rawTitle HtmlText \"Hydrated Title\"",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"hydrate HTML while preserving raw text element braces\"",
        "call hydrateRawCall html.hydrate.RawTemplate",
        "arg hydrateRawCall titleText rawTitle",
        "run hydrateRawCall",
        "bind rawHtml HtmlDocument hydrateRawCall",
        "call writeRawCall console.writeLine",
        "arg writeRawCall text rawHtml",
        "run writeRawCall",
        "ignoreValue writeRawCall CSignedInt32",
        "returnValue successCode",
        "",
    ])
    proc = run_semsc_source(source, "--run", "--quiet", suffix=".sem")
    expected = (
        "<style>\n"
        "  .card::before { content: \"{htmlArg.titleText}\"; }\n"
        "</style>\n"
        "<script>\n"
        "  const template = \"{htmlArg.titleText}\";\n"
        "  const object = { value: \"raw\" };\n"
        "</script>\n"
        "<h1>Hydrated Title</h1>\n"
        "\n"
    )
    check("html raw text: JIT run succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html raw text: style/script braces remain static",
          proc.stdout == expected,
          f"stdout={proc.stdout!r} expected={expected!r}")


def test_html_template_escapes_html_text_by_sink_context():
    source = "\n".join([
        "project HtmlEscaping",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate EscapeTemplate",
        "htmlArg EscapeTemplate labelText HtmlText",
        "htmlBody EscapeTemplate",
        "  <p data-label=\"{htmlArg.labelText}\">{htmlArg.labelText}</p>",
        "storage module immutable successCode ExitCode 0",
        "storage module immutable labelText HtmlText \"A < B & \\\"C\\\"\"",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"hydrate escaped HTML text\"",
        "call hydrateEscapeCall html.hydrate.EscapeTemplate",
        "arg hydrateEscapeCall labelText labelText",
        "run hydrateEscapeCall",
        "bind escapedHtml HtmlDocument hydrateEscapeCall",
        "call writeEscapedCall console.writeLine",
        "arg writeEscapedCall text escapedHtml",
        "run writeEscapedCall",
        "ignoreValue writeEscapedCall CSignedInt32",
        "returnValue successCode",
        "",
    ])
    proc = run_semsc_source(source, "--run", "--quiet", suffix=".sem")
    expected = (
        "<p data-label=\"A &lt; B &amp; &quot;C&quot;\">"
        "A &lt; B &amp; \"C\"</p>\n\n"
    )
    check("html escaping: JIT run succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html escaping: text and attribute sinks escape correctly",
          proc.stdout == expected,
          f"stdout={proc.stdout!r} expected={expected!r}")


def test_html_standard_module_import_exposes_hydrate_namespace_and_exports():
    source = "\n".join([
        "project HtmlStandardImport",
        "target console",
        "runtime native 1",
        "entry console main",
        "importModule html standard.html",
        "importConstant importedHtmlModuleVersionText html htmlModuleVersionText",
        "htmlTemplate StandardTemplate",
        "htmlArg StandardTemplate titleText HtmlText",
        "htmlBody StandardTemplate",
        "  <h1>{htmlArg.titleText}</h1>",
        "storage module immutable successCode ExitCode 0",
        "storage module immutable titleText HtmlText \"Imported HTML\"",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"hydrate HTML after importing the standard.html module\"",
        "call hydrateStandardCall html.hydrate.StandardTemplate",
        "arg hydrateStandardCall titleText titleText",
        "run hydrateStandardCall",
        "bind documentHtml HtmlDocument hydrateStandardCall",
        "call writeDocumentCall console.writeLine",
        "arg writeDocumentCall text documentHtml",
        "run writeDocumentCall",
        "ignoreValue writeDocumentCall CSignedInt32",
        "call writeVersionCall console.writeLine",
        "arg writeVersionCall text importedHtmlModuleVersionText",
        "run writeVersionCall",
        "ignoreValue writeVersionCall CSignedInt32",
        "returnValue successCode",
        "",
    ])
    with tempfile.TemporaryDirectory(dir=ROOT) as tmpdir:
        src_path = Path(tmpdir) / "standard_html_import.sem"
        src_path.write_text(source, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--run", "--quiet"],
            capture_output=True, text=True,
        )
    expected = "<h1>Imported HTML</h1>\n\nstandard.html 0.1\n"
    check("html standard import: JIT run succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html standard import: hydrate namespace and exported constant work",
          proc.stdout == expected,
          f"stdout={proc.stdout!r} expected={expected!r}")


def test_standard_library_module_relay_exposes_standard_modules():
    relay_path = ROOT / "std" / "module.sem"
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
         str(relay_path), "--parse-only"],
        capture_output=True, text=True,
    )
    check("stdlib relay module: parse succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    relay_text = relay_path.read_text(encoding="utf-8")
    canonical_modules = (
        "array", "assert", "bit", "bool", "char", "compare", "constants",
        "convert", "ctype", "errno", "errno_more", "gui", "html", "http",
        "inttypes", "iso646", "json", "limits", "math", "math_float",
        "memory", "numeric", "process", "random", "signal", "signal_more",
        "sqlite", "sort", "stddef", "stdio", "stdlib", "string", "time",
    )
    for module_name in canonical_modules:
        check(f"stdlib relay module: standard.{module_name} is explicitly imported",
              f"importModule standard.{module_name}" in relay_text,
              f"missing standard.{module_name} relay import")
        check(f"stdlib module tree: standard.{module_name} uses main.sem entry",
              (ROOT / "std" / module_name / "main.sem").is_file(),
              f"missing {module_name}/main.sem")
        check(f"stdlib module tree: standard.{module_name} test is main.test.sem",
              (ROOT / "std" / module_name / "main.test.sem").is_file(),
              f"missing {module_name}/main.test.sem")


def _external_standard_import_source():
    return "\n".join([
        "project ExternalStandardImport",
        "target console",
        "runtime native 1",
        "entry console main",
        "importModule html standard.html",
        "importConstant importedHtmlModuleVersionText html htmlModuleVersionText",
        "storage module immutable successCode ExitCode 0",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"print the imported standard.html version\"",
        "call writeVersionCall console.writeLine",
        "arg writeVersionCall text importedHtmlModuleVersionText",
        "run writeVersionCall",
        "ignoreValue writeVersionCall CSignedInt32",
        "returnValue successCode",
        "",
    ])


def _write_minimal_std_html(std_root: Path, version_text: str) -> None:
    (std_root / "html").mkdir(parents=True)
    (std_root / "module.sem").write_text("""module standard
modulePurpose standard "Custom test standard-library relay."
moduleOwns standard "Relay import coverage for tests."
moduleDoesNotOwn standard "Bundled std modules."
moduleInvariant standard "Child modules resolve from this temporary std root."
importModule standard.html
""", encoding="utf-8", newline="\n")
    (std_root / "html" / "main.sem").write_text(f"""module standard.html
modulePurpose standard.html "Custom test HTML standard module."
moduleOwns standard.html "The htmlModuleVersionText export."
moduleDoesNotOwn standard.html "Compiler-owned HTML hydration."
moduleInvariant standard.html "This fixture proves --std-path overrides the bundled std."
type HtmlText CNullTerminatedByteString
exportType standard.html HtmlText
exportConstant standard.html htmlModuleVersionText
storage module immutable htmlModuleVersionText HtmlText "{version_text}"
""", encoding="utf-8", newline="\n")


def test_standard_import_resolves_from_bundled_compiler_std_outside_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "external_standard_import.sem"
        src_path.write_text(_external_standard_import_source(),
                            encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--run", "--quiet"],
            capture_output=True, text=True,
        )
    check("stdlib discovery: external app resolves bundled compiler std",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("stdlib discovery: external app imports standard.html export",
          proc.stdout == "standard.html 0.1\n",
          f"stdout={proc.stdout!r}")


def test_standard_import_std_path_override_wins_outside_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        custom_std = root / "custom-std"
        _write_minimal_std_html(custom_std, "custom.html 9")
        src_path = root / "external_standard_import.sem"
        src_path.write_text(_external_standard_import_source(),
                            encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--run", "--quiet",
             "--std-path", str(custom_std)],
            capture_output=True, text=True,
        )
    check("stdlib discovery: --std-path resolves custom std root",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("stdlib discovery: --std-path takes precedence over bundled std",
          proc.stdout == "custom.html 9\n",
          f"stdout={proc.stdout!r}")


def test_html_template_long_dynamic_arg_is_bounded_and_terminated():
    long_text = "x" * 70000
    source = "\n".join([
        "project HtmlLongDynamic",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate LongTemplate",
        "htmlArg LongTemplate bodyText HtmlText",
        "htmlBody LongTemplate",
        "  <p>{htmlArg.bodyText}</p>",
        "storage module immutable successCode ExitCode 0",
        f"storage module immutable longBodyText HtmlText \"{long_text}\"",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"hydrate long dynamic HTML without overflowing the buffer\"",
        "call hydrateLongCall html.hydrate.LongTemplate",
        "arg hydrateLongCall bodyText longBodyText",
        "run hydrateLongCall",
        "bind longHtml HtmlDocument hydrateLongCall",
        "call writeLongCall console.writeLine",
        "arg writeLongCall text longHtml",
        "run writeLongCall",
        "ignoreValue writeLongCall CSignedInt32",
        "returnValue successCode",
        "",
    ])
    proc = run_semsc_source(source, "--run", "--quiet", suffix=".sem")
    check("html long dynamic: JIT run succeeds",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html long dynamic: output is bounded and null-terminated",
          proc.stdout.startswith("<p>xxx")
          and len(proc.stdout) == 65536
          and proc.stdout.endswith("\n"),
          f"stdout length={len(proc.stdout)} tail={proc.stdout[-20:]!r}")


def _write_complex_html_project(root: Path) -> Path:
    build_path = root / "build.sem"
    build_path.write_text("\n".join([
        "buildProject htmlAggressive",
        "project HtmlAggressive",
        "modulePath htmlAggressive github.com/example/html-aggressive",
        "languageVersion htmlAggressive \"1.0\"",
        "projectVersion htmlAggressive \"0.1.0\"",
        "projectLicense htmlAggressive MIT",
        "sourceRoot htmlAggressive \".\"",
        "registerModule htmlAggressive app.html_aggressive \".\"",
        "registerModule htmlAggressive app.html_aggressive.shared \"shared\"",
        "registerModule htmlAggressive app.html_aggressive.components \"components\"",
        "mainFile htmlAggressive \"main.sem\"",
        "mainOperation htmlAggressive main",
        "targetRuntime htmlAggressive nativeExe",
        "buildProfile htmlAggressive dev",
        "runtimeChecks htmlAggressive panic",
        "persistLlvmIr htmlAggressive auto",
        "optLevel htmlAggressive 2",
        "target console",
        "runtime native 1",
        "entry console main",
        "importModule app.html_aggressive",
        "",
    ]), encoding="utf-8", newline="\n")

    (root / "shared").mkdir()
    (root / "shared" / "main.sem").write_text("\n".join([
        "module app.html_aggressive.shared",
        "exportConstant app.html_aggressive.shared pageTitleText",
        "exportConstant app.html_aggressive.shared bodyText",
        "exportConstant app.html_aggressive.shared cardClassName",
        "exportConstant app.html_aggressive.shared stateClassName",
        "storage module immutable pageTitleText HtmlText \"Aggressive HTML\"",
        "storage module immutable bodyText HtmlText \"Nested modules preserve copy.\"",
        "storage module immutable cardClassName HtmlClass \"card card-active\"",
        "storage module immutable stateClassName HtmlClass \"ready\"",
        "",
    ]), encoding="utf-8", newline="\n")

    (root / "components").mkdir()
    (root / "components" / "main.sem").write_text("\n".join([
        "module app.html_aggressive.components",
        "importModule app.html_aggressive.shared",
        "exportOperation app.html_aggressive.components renderDocument",
        "htmlTemplate ComplexDocumentTemplate",
        "htmlArg ComplexDocumentTemplate pageTitleText HtmlText",
        "htmlArg ComplexDocumentTemplate bodyText HtmlText",
        "htmlArg ComplexDocumentTemplate cardClassName HtmlClass",
        "htmlArg ComplexDocumentTemplate stateClassName HtmlClass",
        "htmlBody ComplexDocumentTemplate",
        "  <!doctype html>",
        "  <html lang=\"en\">",
        "    <head>",
        "      <title>{htmlArg.pageTitleText}</title>",
        "      <style>",
        "        .meter { width: 100%; content: \"{literal-braces-stay-static}\"; }",
        "        .card[data-state=\"ready\"] { border: 1px solid #ccd4e0; }",
        "      </style>",
        "      <script>const boot = { ready: true, label: \"{literal-script-brace}\" };</script>",
        "    </head>",
        "    <body data-state=\"{htmlArg.stateClassName}\">",
        "      <>",
        "        <section class=\"{htmlArg.cardClassName}\">",
        "          <h1>{htmlArg.pageTitleText}</h1>",
        "          <p>{htmlArg.bodyText}</p>",
        "        </section>",
        "      </>",
        "    </body>",
        "  </html>",
        "operation renderDocument",
        "output renderDocument HtmlDocument",
        "memoryHeap renderDocument no",
        "async renderDocument no",
        "purpose renderDocument \"hydrate a complex full-document template\"",
        "call hydrateDocumentCall html.hydrate.ComplexDocumentTemplate",
        "arg hydrateDocumentCall pageTitleText pageTitleText",
        "arg hydrateDocumentCall bodyText bodyText",
        "arg hydrateDocumentCall cardClassName cardClassName",
        "arg hydrateDocumentCall stateClassName stateClassName",
        "run hydrateDocumentCall",
        "bind documentHtml HtmlDocument hydrateDocumentCall",
        "returnValue documentHtml",
        "",
    ]), encoding="utf-8", newline="\n")

    (root / "main.sem").write_text("\n".join([
        "module app.html_aggressive",
        "importModule app.html_aggressive.components",
        "exportOperation app.html_aggressive main",
        "storage module immutable successCode ExitCode 0",
        "operation main",
        "output main ExitCode",
        "effect main write console.stdout",
        "authority main console.stdout write",
        "memoryHeap main no",
        "async main no",
        "purpose main \"print the complex hydrated HTML document\"",
        "call renderDocumentCall renderDocument",
        "run renderDocumentCall",
        "bind documentHtml HtmlDocument renderDocumentCall",
        "call writeDocumentCall console.writeLine",
        "arg writeDocumentCall text documentHtml",
        "run writeDocumentCall",
        "ignoreValue writeDocumentCall CSignedInt32",
        "returnValue successCode",
        "",
    ]), encoding="utf-8", newline="\n")
    return build_path


def test_html_template_complex_modules_jit_and_aot_output():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = _write_complex_html_project(root)
        jit_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--run", "--quiet"],
            capture_output=True, text=True,
        )
        check("html complex: module build JIT run succeeds",
              jit_proc.returncode == 0,
              f"rc={jit_proc.returncode} stderr={jit_proc.stderr!r}")
        expected_needles = [
            "<!doctype html>",
            "<title>Aggressive HTML</title>",
            ".meter { width: 100%; content: \"{literal-braces-stay-static}\"; }",
            "const boot = { ready: true, label: \"{literal-script-brace}\" };",
            "<body data-state=\"ready\">",
            "<>",
            "<section class=\"card card-active\">",
            "<p>Nested modules preserve copy.</p>",
        ]
        for needle in expected_needles:
            check(f"html complex: JIT output contains {needle[:30]!r}",
                  needle in jit_proc.stdout,
                  f"stdout={jit_proc.stdout!r}")

        exe_path = root / "html-aggressive.exe"
        aot_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--emit-exe", str(exe_path), "--quiet"],
            capture_output=True, text=True,
        )
        check("html complex: AOT build succeeds",
              aot_proc.returncode == 0 and exe_path.exists(),
              f"rc={aot_proc.returncode} stderr={aot_proc.stderr!r}")
        if aot_proc.returncode == 0 and exe_path.exists():
            run_proc = subprocess.run(
                [str(exe_path)],
                capture_output=True, text=True,
            )
            check("html complex: AOT run succeeds",
                  run_proc.returncode == 0,
                  f"rc={run_proc.returncode} stderr={run_proc.stderr!r}")
            check("html complex: AOT output matches JIT output",
                  run_proc.stdout == jit_proc.stdout,
                  f"jit={jit_proc.stdout!r} aot={run_proc.stdout!r}")


def test_html_console_demo_runs_from_registered_modules():
    build_path = ROOT.parent / "app" / "html-console-demo" / "build.sem"
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
         str(build_path), "--run", "--quiet"],
        capture_output=True, text=True,
    )
    check("html demo: registered-module app runs",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("html demo: stdout contains hydrated todo page",
          "<title>Todo TUI HTML Console Demo</title>" in proc.stdout
          and "Split HTML rendering into modules" in proc.stdout
          and "<main class=\"todo-shell\">" in proc.stdout,
          f"stdout={proc.stdout!r}")


def test_html_template_codegen_rejects_bad_hydration_edges():
    cases = [
        ("unknown body arg",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{htmlArg.missingText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "unknown htmlArg `missingText`"),
        ("missing call arg",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Missing arg\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{htmlArg.titleText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "missing required arg `titleText`"),
        ("unsupported arg type",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable countValue I64 42",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate countValue I64",
             "htmlBody BadTemplate",
             "  <span>{htmlArg.countValue}</span>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall countValue countValue",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "requires a string-shaped HTML value type"),
        ("missing unused declared call arg",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlArg BadTemplate unusedText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{htmlArg.titleText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "missing required arg `unusedText`"),
        ("text value in class attribute",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <div class=\"{htmlArg.titleText}\"></div>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "requires HtmlClass"),
        ("text value in url attribute",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <a href=\"{htmlArg.titleText}\">link</a>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "requires SafeUrl"),
        ("fragment value in attribute",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable fragment HtmlFragment \"<b>bad</b>\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate fragment HtmlFragment",
             "htmlBody BadTemplate",
             "  <div data-fragment=\"{htmlArg.fragment}\"></div>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall fragment fragment",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "cannot hydrate attribute"),
        ("class value in text content",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable className HtmlClass \"todo-row\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate className HtmlClass",
             "htmlBody BadTemplate",
             "  <p>{htmlArg.className}</p>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall className className",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "cannot hydrate text content"),
        ("dynamic tag syntax",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable tagName HtmlText \"section\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate tagName HtmlText",
             "htmlBody BadTemplate",
             "  <{htmlArg.tagName}>bad</{htmlArg.tagName}>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall tagName tagName",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "cannot hydrate HTML tag syntax"),
        ("unknown hydrate target",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.MissingTemplate",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "unknown htmlTemplate `MissingTemplate`"),
        ("unqualified dynamic hole",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{titleText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "must reference declared htmlArg.NAME"),
        ("props dynamic hole",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{props.titleText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "must reference declared htmlArg.NAME"),
        ("arbitrary expression dynamic hole",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{titleText + otherText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "must reference declared htmlArg.NAME"),
        ("malformed htmlArg dynamic hole",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{htmlArg.}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "must reference declared htmlArg.NAME"),
        ("extra hydrate arg",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "storage module immutable titleText HtmlText \"Title\"",
             "storage module immutable extraText HtmlText \"Extra\"",
             "htmlTemplate BadTemplate",
             "htmlArg BadTemplate titleText HtmlText",
             "htmlBody BadTemplate",
             "  <h1>{htmlArg.titleText}</h1>",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "arg hydrateBadCall titleText titleText",
             "arg hydrateBadCall extraText extraText",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "is not declared by htmlTemplate"),
        ("empty html body",
         "\n".join([
             "project BadHtml",
             "target console",
             "runtime native 1",
             "entry console main",
             "htmlTemplate BadTemplate",
             "htmlBody BadTemplate",
             "operation main",
             "output main ExitCode",
             "purpose main \"bad html\"",
             "call hydrateBadCall html.hydrate.BadTemplate",
             "run hydrateBadCall",
             "returnValue 0",
             "",
         ]),
         "template has no body lines"),
    ]
    oversized_static_source = "\n".join([
        "project BadHtml",
        "target console",
        "runtime native 1",
        "entry console main",
        "htmlTemplate BadTemplate",
        "htmlBody BadTemplate",
        "  <pre>" + ("x" * 66000) + "</pre>",
        "operation main",
        "output main ExitCode",
        "purpose main \"bad html\"",
        "call hydrateBadCall html.hydrate.BadTemplate",
        "run hydrateBadCall",
        "returnValue 0",
        "",
    ])
    cases.append((
        "oversized static body",
        oversized_static_source,
        "exceeding hydrate buffer capacity",
    ))
    for label, source, expected in cases:
        try:
            prog = semsc.parse(source)
            semsc.Codegen(prog).compile()
        except (ValueError, semsc.CompilerDiagnosticError, SyntaxError) as exc:
            message = str(exc)
            check(f"html codegen: rejects {label}",
                  expected in message,
                  message)
        else:
            check(f"html codegen: rejects {label}",
                  False,
                  "compile unexpectedly succeeded")


def test_cli_accepts_sem_alias():
    src_path = ROOT / "tests" / "tiny.sem"
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
         str(src_path), "--parse-only", "--quiet"],
        capture_output=True, text=True,
    )
    check("compile: .sem alias parses",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_success_message_renderer():
    rendered = semsc._render_success_message(
        "SSOK001",
        "SemanticScript compile complete",
        "sample.sscript",
        outputs=[("llvm ir", "sample.ll"), ("executable", "sample.exe")],
        details=[("profile", "dev"), ("runtime checks", "panic")],
        next_steps=["Run sample.exe."],
    )
    check("success message: names code and title",
          rendered.startswith("success SSOK001: SemanticScript compile complete"),
          rendered)
    check("success message: lists outputs",
          "Outputs:\n  llvm ir: sample.ll\n  executable: sample.exe" in rendered,
          rendered)
    check("success message: lists next step",
          "Next:\n  Run sample.exe." in rendered,
          rendered)


def test_persisted_ir_path_resolution():
    build_dir = str(Path("sample-build"))
    check("persist llvm ir: auto without --emit-ir discards",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", build_dir=build_dir) is None)
    check("persist llvm ir: explicit --emit-ir wins",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", emit_ir="custom.ll",
              build_dir=build_dir) == str((Path("sample-build") / "custom.ll").resolve()))
    check("persist llvm ir: yes creates build sidecar",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", persist_llvm_ir="yes",
              build_dir=build_dir) == str((Path("sample-build") / "sample.ll").resolve()))
    check("persist llvm ir: yes prefers executable basename",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", emit_exe="out.exe",
              persist_llvm_ir="yes", build_dir=build_dir) == str(Path("out.ll").resolve()))
    check("persist llvm ir: no suppresses even explicit path",
          semsc._resolve_persisted_ir_path(
              "sample.sscript", emit_ir="custom.ll",
              persist_llvm_ir="no", build_dir=build_dir) is None)


def test_build_dir_path_resolution():
    source_path = str(Path("project") / "app" / "main.sem")
    check("build dir: default is source-local build folder",
          semsc._resolve_build_dir(source_path) == str(
              (Path("project") / "app" / "build").resolve()))
    check("build dir: exact relative override resolves beside source",
          semsc._resolve_build_dir(source_path, build_dir="artifacts") == str(
              (Path("project") / "app" / "artifacts").resolve()))
    check("build dir: root keeps managed build folder name",
          semsc._resolve_build_dir(source_path, build_root="..") == str(
              (Path("project") / "build").resolve()))
    check("build dir: root plus custom folder name",
          semsc._resolve_build_dir(
              source_path, build_root="..", build_folder_name="sem-build") == str(
              (Path("project") / "sem-build").resolve()))

    raised = False
    msg = ""
    try:
        semsc._resolve_build_dir(
            source_path,
            build_dir="exact",
            build_root="elsewhere")
    except ValueError as e:
        raised = True
        msg = str(e)
    check("build dir: exact override rejects build root",
          raised and "cannot be combined" in msg,
          f"raised={raised} msg={msg!r}")

    raised = False
    msg = ""
    try:
        semsc._resolve_build_dir(source_path, build_folder_name="nested/build")
    except ValueError as e:
        raised = True
        msg = str(e)
    check("build dir: folder name rejects paths",
          raised and "single directory name" in msg,
          f"raised={raised} msg={msg!r}")


def test_cli_persist_llvm_ir_flag():
    src = "\n".join([
        "project PersistIr",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "persist_ir.sscript"
        build_dir = Path(tmpdir) / "build"
        sidecar_path = build_dir / "persist_ir.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        auto_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--quiet"],
            capture_output=True, text=True,
        )
        check("persist llvm ir: auto leaves no sidecar",
              auto_proc.returncode == 0 and not sidecar_path.exists(),
              f"rc={auto_proc.returncode} stderr={auto_proc.stderr!r}")
        yes_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--persist-llvm-ir", "yes", "--quiet"],
            capture_output=True, text=True,
        )
        check("persist llvm ir: yes writes sidecar",
              yes_proc.returncode == 0 and sidecar_path.exists(),
              f"rc={yes_proc.returncode} stderr={yes_proc.stderr!r}")
        sidecar_path.unlink()
        no_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--persist-llvm-ir", "no", "--quiet"],
            capture_output=True, text=True,
        )
        check("persist llvm ir: no leaves no sidecar",
              no_proc.returncode == 0 and not sidecar_path.exists(),
              f"rc={no_proc.returncode} stderr={no_proc.stderr!r}")


def test_cli_emit_ir_without_path_uses_build_dir():
    src = "\n".join([
        "project EmitIrBuildDir",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "emit_ir_build_dir.sem"
        build_ir_path = Path(tmpdir) / "build" / "emit_ir_build_dir.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", "--quiet"],
            capture_output=True, text=True,
        )
        check("emit-ir without path writes build dir artifact",
              proc.returncode == 0 and build_ir_path.exists(),
              f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_cli_inspect_ir_outputs_agent_json():
    src = "\n".join([
        "project InspectIrJson",
        "target console",
        "entry console main",
        "error MainError",
        "errorCase MainError Placeholder CSignedInt32",
        "operation main",
        "input main console Console",
        "output main Result ExitCode MainError",
        "effect main write console.stdout",
        "memory main heap no",
        "async main no",
        "label start",
        "const greeting String \"hello\"",
        "const ok ExitCode 0",
        "call writeGreeting console.writeLine",
        "arg writeGreeting text greeting",
        "run writeGreeting",
        "returnOk ok",
        "",
    ])
    proc = run_semsc_source(src, "--inspect-ir")
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        payload = {}
        decode_error = str(exc)
    else:
        decode_error = ""

    check("inspect-ir: stdout is JSON",
          proc.returncode == 0 and payload.get("schemaVersion") == "sem.inspectIr.v0",
          f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r}")
    functions = {fn["name"]: fn for fn in payload.get("llvm", {}).get("functions", [])}
    check("inspect-ir: maps entry operation to LLVM main",
          functions.get("main", {}).get("operation") == "main"
          and any(block.get("name") == "entry" for block in functions.get("main", {}).get("blocks", [])),
          functions.get("main"))
    op = next((item for item in payload.get("operations", [])
               if item.get("name") == "main"), {})
    call = next((item for item in op.get("calls", [])
                 if item.get("name") == "writeGreeting"), {})
    trace_sites = payload.get("traceMap", {}).get("sites", [])
    check("inspect-ir: call site id appears in trace map",
          bool(call.get("siteId"))
          and any(site.get("siteId") == call.get("siteId")
                  and site.get("kind") == "call"
                  for site in trace_sites),
          f"call={call} sites={trace_sites}")
    runtime_symbols = {
        item.get("symbol")
        for item in payload.get("llvm", {}).get("runtimeSymbols", [])
    }
    check("inspect-ir: records runtime external provenance",
          "puts" in runtime_symbols,
          runtime_symbols)


def test_cli_emit_trace_map_sidecar():
    src = "\n".join([
        "project TraceMapSidecar",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "trace_map_sidecar.sem"
        trace_map_path = Path(tmpdir) / "build" / "trace_map_sidecar.trace-map.json"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-trace-map", "--quiet"],
            capture_output=True, text=True,
        )
        if trace_map_path.exists():
            payload = json.loads(trace_map_path.read_text(encoding="utf-8"))
        else:
            payload = {}
        check("trace-map: default sidecar path is written",
              proc.returncode == 0
              and not proc.stdout
              and payload.get("schemaVersion") == "sem.traceMap.v0"
              and any(site.get("kind") == "operation"
                      for site in payload.get("sites", [])),
              f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r}")


def test_sem_inspect_ir_command():
    src = "\n".join([
        "project SemInspectIrCommand",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "sem_inspect_ir.sem"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "inspect-ir", str(src_path)],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload = {}
            decode_error = str(exc)
        else:
            decode_error = ""
        check("sem inspect-ir: delegates to compiler JSON output",
              proc.returncode == 0
              and payload.get("schemaVersion") == "sem.inspectIr.v0"
              and payload.get("entry", {}).get("operation") == "main",
              f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r}")


def test_inspect_ir_reports_http_abi_and_runtime_link_inputs():
    src_path = ROOT / "tests" / "path_param_smoke.sscript"
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
         str(src_path), "--inspect-ir"],
        capture_output=True, text=True,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        payload = {}
        decode_error = str(exc)
    else:
        decode_error = ""

    route = next((item for item in payload.get("routes", [])
                  if item.get("handler") == "echoSlugHandler"), {})
    functions = payload.get("llvm", {}).get("functions", [])
    handler_fn = next((item for item in functions
                       if item.get("operation") == "echoSlugHandler"), {})
    components = {
        item.get("component")
        for item in payload.get("runtimeLink", {}).get("components", [])
    }
    site_kinds = {
        item.get("kind")
        for item in payload.get("traceMap", {}).get("sites", [])
    }
    check("inspect-ir: reports HTTP route native ABI",
          proc.returncode == 0
          and route.get("nativeAbi", {}).get("llvmSignature") == "i32 (i8*, i8*)"
          and handler_fn.get("nativeAbi", {}).get("kind") == "httpHandler",
          f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r}")
    check("inspect-ir: reports native HTTP runtime link inputs",
          "native_http" in components and "runtime.linkInput" in site_kinds,
          f"components={components} siteKinds={site_kinds}")


def test_inspect_ir_preserves_imported_source_origins():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        module_dir = root / "app"
        module_dir.mkdir()
        imported_path = module_dir / "lib.sem"
        imported_path.write_text("\n".join([
            "module app.lib",
            "exportOperation app.lib helper",
            "operation helper",
            "output helper ExitCode",
            "memory helper heap no",
            "async helper no",
            "label start",
            "returnValue 0",
            "",
        ]), encoding="utf-8", newline="\n")
        src_path = root / "main.sem"
        src_path.write_text("\n".join([
            "project ImportOrigin",
            "entry console main",
            "importModule app.lib",
            "operation main",
            "output main ExitCode",
            "memory main heap no",
            "async main no",
            "label start",
            "returnValue 0",
            "",
        ]), encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--inspect-ir"],
            capture_output=True, text=True,
        )
        payload = json.loads(proc.stdout) if proc.returncode == 0 else {}
        imported_sources = payload.get("source", {}).get("importedSources", [])
        helper = next((op for op in payload.get("operations", [])
                       if op.get("name") == "helper"), {})
        origin = helper.get("sourceSpan", {}).get("origin", {})
        check("inspect-ir: source model preserves imported file origins",
              proc.returncode == 0
              and payload.get("source", {}).get("sourceModel") == "flattenedResolvedStreamWithOrigins"
              and any(item.get("path") == str(imported_path.resolve())
                      for item in imported_sources)
              and origin.get("path") == str(imported_path.resolve())
              and origin.get("line") == 3
              and origin.get("imported") is True,
              f"rc={proc.returncode} stderr={proc.stderr!r} payload={payload}")


def test_sem_run_trace_emits_agent_jsonl_events():
    src = "\n".join([
        "project TraceRunJsonl",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "const leftValue CSignedInt32 -1",
        "const rightValue CSignedInt32 0",
        "const successExit ExitCode 0",
        "call negativeCheckCall math.lessThanCSignedInt32",
        "arg negativeCheckCall left leftValue",
        "arg negativeCheckCall right rightValue",
        "run negativeCheckCall",
        "bind statusIsNegative Bool negativeCheckCall",
        "branchIf statusIsNegative returnSuccess",
        "returnValue rightValue",
        "label returnSuccess",
        "returnValue successExit",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "trace_run.sem"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "run", "--trace", str(src_path)],
            capture_output=True, text=True,
        )
        try:
            events = [json.loads(line) for line in proc.stderr.splitlines()
                      if line.strip()]
        except json.JSONDecodeError as exc:
            events = []
            decode_error = str(exc)
        else:
            decode_error = ""
        event_names = [event.get("event") for event in events]
        seqs = [event.get("seq") for event in events]
        check("sem run --trace: emits clean agent JSONL",
              proc.returncode == 0
              and proc.stdout == ""
              and event_names[:3] == ["op.enter", "call.start", "call.end"]
              and "branch.decision" in event_names
              and "return.value" in event_names
              and "op.exit" in event_names
              and seqs == list(range(1, len(events) + 1))
              and all(event.get("schemaVersion") == "sem.traceEvent.v0"
                      and event.get("siteId")
                      and event.get("timestampNs") == event.get("seq")
                      for event in events)
              and any(event.get("valueStatus") == "redacted"
                      for event in events),
              f"rc={proc.returncode} stdout={proc.stdout!r} stderr={proc.stderr!r} decode={decode_error!r}")


def test_sem_profile_json_writes_agent_artifacts_and_deltas():
    src = "\n".join([
        "project ProfileJson",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "profile.sem"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "run", "--profile", "--json", str(src_path)],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload = {}
            decode_error = str(exc)
        else:
            decode_error = ""
        artifacts = payload.get("artifacts", {})
        artifact_paths_exist = all(
            Path(path).exists()
            for key, path in artifacts.items()
            if key.endswith("Path") and path
        )
        index_path = artifacts.get("artifactIndexPath", "")
        delta_proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "compare-profiles", index_path, index_path],
            capture_output=True, text=True,
        ) if index_path else subprocess.CompletedProcess([], 1, "", "missing index")
        try:
            delta_payload = json.loads(delta_proc.stdout)
        except json.JSONDecodeError:
            delta_payload = {}
        check("sem run --profile --json: writes profile artifacts and deltas",
              proc.returncode == 0
              and payload.get("schemaVersion") == "sem.profile.v0"
              and payload.get("run", {}).get("traceEventCount", 0) >= 3
              and payload.get("run", {}).get("wallTimeNs", 0) >= payload.get("run", {}).get("durationNs", 0)
              and "startupTimeNs" in payload.get("run", {})
              and payload.get("hot", {}).get("operations", {}).get("main") == 1
              and artifact_paths_exist
              and payload.get("optimizationLoop", {}).get("schemaVersion") == "sem.optimizationLoop.v0"
              and delta_proc.returncode == 0
              and delta_payload.get("schemaVersion") == "sem.profileDelta.v0"
              and delta_payload.get("run", {}).get("traceEventCount", {}).get("delta") == 0,
              f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r} payload={payload} delta={delta_proc.stderr!r}")


def test_sem_profile_compile_failure_uses_failure_schema():
    src = "\n".join([
        "project ProfileCompileFailure",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "profile_failure.sem"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "run", "--profile", "--json", str(src_path), "--",
             "--build-dir", "exact", "--build-root", "elsewhere"],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload = {}
            decode_error = str(exc)
        else:
            decode_error = ""
        artifacts = payload.get("artifacts", {})
        check("sem run --profile: compile failures use failure schema",
              proc.returncode != 0
              and payload.get("schemaVersion") == "sem.profileFailure.v0"
              and payload.get("phase") == "compile"
              and payload.get("suspectedCategory") == "compileFailure"
              and payload.get("compile", {}).get("returnCode") != 0
              and Path(artifacts.get("artifactIndexPath", "")).exists()
              and Path(artifacts.get("profilePath", "")).exists(),
              f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r} payload={payload}")


def test_sem_explain_crash_reports_runtime_panic_context():
    import shutil
    clang = (os.environ.get("SEMSC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("sem explain-crash: clang available", False,
              f"clang not found at {clang}")
        return
    src = "\n".join([
        "project RuntimePanicDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "const numeratorValue CSignedInt64 7",
        "const zeroDivisor CSignedInt64 0",
        "call divideByZeroCall math.divideI64",
        "arg divideByZeroCall left numeratorValue",
        "arg divideByZeroCall right zeroDivisor",
        "run divideByZeroCall",
        "bind quotientValue CSignedInt64 divideByZeroCall",
        "returnValue quotientValue",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "runtime_panic.sem"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "run", "--explain-crash", str(src_path)],
            capture_output=True, text=True,
            timeout=300,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload = {}
            decode_error = str(exc)
        else:
            decode_error = ""
        artifacts = payload.get("artifacts", {})
        event_names = [event.get("event")
                       for event in payload.get("lastTraceEvents", [])]
        check("sem run --explain-crash: reports panic and durable artifacts",
              proc.returncode == 0
              and payload.get("schemaVersion") == "sem.crash.v0"
              and payload.get("suspectedCategory") == "runtimePanic"
              and payload.get("panic", {}).get("code") == "SSRUN001"
              and payload.get("panic", {}).get("operation") == "main"
              and payload.get("semanticContext", {}).get("operation") == "main"
              and "divideByZeroCall -> math.divideI64" in payload.get("panic", {}).get("call", "")
              and event_names == ["op.enter", "call.start"]
              and Path(artifacts.get("artifactIndexPath", "")).exists()
              and Path(artifacts.get("traceEventsPath", "")).exists(),
              f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r} payload={payload}")


def test_sem_bench_json_reports_stable_deltas():
    import shutil
    clang = (os.environ.get("SEMSC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("sem bench json: clang available", False,
              f"clang not found at {clang}")
        return
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "sem.py"),
         "bench", "--json", "--runs", "1", "--warmup", "0",
         "--benchmark", "arith"],
        capture_output=True, text=True,
        timeout=300,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        payload = {}
        decode_error = str(exc)
    else:
        decode_error = ""
    bench = next((item for item in payload.get("benchmarks", [])
                  if item.get("name") == "arith"), {})
    check("sem bench --json: reports stable benchmark deltas",
          proc.returncode in (0, 1)
          and payload.get("schemaVersion") == "sem.benchmark.v0"
          and payload.get("summary", {}).get("benchmarkCount") == 1
          and "semanticToCRatio" in bench.get("delta", {})
          and "semanticMinusCClockTicks" in bench.get("delta", {})
          and Path(bench.get("artifacts", {}).get("semanticExecutablePath", "")).exists(),
          f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r} payload={payload}")


def test_cli_build_root_and_folder_name():
    src = "\n".join([
        "project EmitIrBuildRoot",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "returnValue 0",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "emit_ir_build_root.sem"
        build_ir_path = (
            Path(tmpdir) / "outside-artifacts" / "sem-out" / "emit_ir_build_root.ll")
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir",
             "--build-root", "outside-artifacts",
             "--build-folder-name", "sem-out",
             "--quiet"],
            capture_output=True, text=True,
        )
        check("build root: emit-ir writes under custom managed build folder",
              proc.returncode == 0 and build_ir_path.exists(),
              f"rc={proc.returncode} stderr={proc.stderr!r}")


def test_cli_build_dir_overrides_build_tape_folder_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        module_path = root / "main.sem"
        override_build_dir = root / "agent-artifacts"
        build_path.write_text("\n".join([
            "buildProject buildDirOverride",
            "project BuildDirOverride",
            "modulePath buildDirOverride github.com/example/build-dir-override",
            "languageVersion buildDirOverride \"1.0\"",
            "projectVersion buildDirOverride \"1.0.0\"",
            "projectLicense buildDirOverride MIT",
            "sourceRoot buildDirOverride \".\"",
            "registerModule buildDirOverride app.build_dir_override \".\"",
            "mainFile buildDirOverride \"main.sem\"",
            "mainOperation buildDirOverride main",
            "targetRuntime buildDirOverride nativeExe",
            "buildProfile buildDirOverride dev",
            "runtimeChecks buildDirOverride panic",
            "persistLlvmIr buildDirOverride auto",
            "optLevel buildDirOverride 0",
            "buildFolderName buildDirOverride build-from-tape",
            "target console",
            "runtime native 1",
            "entry console main",
            "importModule app.build_dir_override",
            "",
        ]), encoding="utf-8", newline="\n")
        module_path.write_text("\n".join([
            "module app.build_dir_override",
            "exportOperation app.build_dir_override main",
            "operation main",
            "output main ExitCode",
            "memory main heap no",
            "async main no",
            "returnValue 0",
            "",
        ]), encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "inspect-ir", str(root), "--", "--build-dir", str(override_build_dir)],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            payload = {}
            decode_error = str(exc)
        else:
            decode_error = ""
        check("build dir: CLI override ignores buildFolderName metadata",
              proc.returncode == 0
              and payload.get("schemaVersion") == "sem.inspectIr.v0"
              and "cannot be combined" not in proc.stderr,
              f"rc={proc.returncode} stderr={proc.stderr!r} decode={decode_error!r}")


def test_build_tape_path_normalization():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        relative_path = semsc._normalize_build_tape_path(
            str(build_path), "main.sem", ".")
        absolute_target = root / "src" / "main.sem"
        absolute_path = semsc._normalize_build_tape_path(
            str(build_path), str(absolute_target), "src")
        check("build tape: relative path normalizes beside sourceRoot",
              relative_path == str((root / "main.sem").resolve()),
              relative_path)
        check("build tape: absolute path remains absolute",
              absolute_path == str(absolute_target.resolve()),
              absolute_path)


def test_build_tape_validation_rejects_missing_required_rows():
    with tempfile.TemporaryDirectory() as tmpdir:
        build_path = Path(tmpdir) / "build.sem"
        raised = False
        msg = ""
        try:
            semsc._validate_build_tape_source(
                "buildProject incomplete\nproject Incomplete\n",
                str(build_path))
        except SyntaxError as e:
            raised = True
            msg = str(e)
        check("build tape: missing required rows rejected",
              raised and "missing required row" in msg,
              f"raised={raised} msg={msg!r}")


def test_build_tape_validation_accepts_dependency_fetch_rows():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        (root / "main.sem").write_text("module app.deps\n", encoding="utf-8")
        digest = "a" * 64
        source = "\n".join([
            "buildProject depFetch",
            "project DepFetch",
            "modulePath depFetch github.com/example/dep-fetch",
            "languageVersion depFetch \"1.0\"",
            "projectVersion depFetch \"1.0.0\"",
            "projectLicense depFetch MIT",
            "sourceRoot depFetch \".\"",
            "registerModule depFetch app.deps \".\"",
            "mainFile depFetch \"main.sem\"",
            "mainOperation depFetch main",
            "targetRuntime depFetch nativeExe",
            "buildProfile depFetch dev",
            "runtimeChecks depFetch panic",
            "persistLlvmIr depFetch auto",
            "optLevel depFetch 2",
            "dependency depFetch semstd github.com/example/semstd v1.0.0",
            "dependencyFetch depFetch semstd github example/semstd v1.0.0",
            "dependencyIntegrity depFetch semstd commit:abcdef1234567890",
            "dependency depFetch api github.com/example/api v2.0.0",
            "dependencyFetch depFetch api http \"https://example.com/api.tar.gz\"",
            f"dependencyIntegrity depFetch api sha256:{digest}",
            "dependencyCache depFetch \".semcache\"",
            "dependencyLock depFetch \"sem.lock\"",
            "",
        ])
        raised = False
        msg = ""
        try:
            semsc._validate_build_tape_source(source, str(build_path))
        except SyntaxError as e:
            raised = True
            msg = str(e)
        check("build tape: dependency fetch rows validate",
              not raised,
              msg)


def test_build_tape_validation_rejects_insecure_dependency_fetch():
    with tempfile.TemporaryDirectory() as tmpdir:
        build_path = Path(tmpdir) / "build.sem"
        source = "\n".join([
            "buildProject depFetch",
            "modulePath depFetch github.com/example/dep-fetch",
            "languageVersion depFetch \"1.0\"",
            "projectVersion depFetch \"1.0.0\"",
            "projectLicense depFetch MIT",
            "sourceRoot depFetch \".\"",
            "targetRuntime depFetch library",
            "buildProfile depFetch dev",
            "runtimeChecks depFetch panic",
            "persistLlvmIr depFetch auto",
            "optLevel depFetch 2",
            "dependency depFetch api github.com/example/api v2.0.0",
            "dependencyFetch depFetch api http \"http://example.com/api.tar.gz\"",
            "",
        ])
        raised = False
        msg = ""
        try:
            semsc._validate_build_tape_source(source, str(build_path))
        except SyntaxError as e:
            raised = True
            msg = str(e)
        check("build tape: insecure dependency fetch rejected",
              raised and "https URL" in msg,
              f"raised={raised} msg={msg!r}")


def test_hello_gui_sample_uses_refined_gui_surface():
    build_path = HELLO_GUI_DIR / "build.sem"
    main_path = HELLO_GUI_DIR / "main.sem"
    check("hello gui sample: build.sem exists",
          build_path.exists(),
          str(build_path))
    check("hello gui sample: main.sem exists",
          main_path.exists(),
          str(main_path))
    if not build_path.exists() or not main_path.exists():
        return

    build_text = build_path.read_text(encoding="utf-8")
    main_text = main_path.read_text(encoding="utf-8")
    check("hello gui sample: build tape selects windowsGui with standard entry syntax",
          "target windowsGui" in build_text
          and "targetRuntime helloGui windowsGui" in build_text
          and re.search(r"(?m)^entry\s+console\s+main\b", build_text)
          and re.search(r"(?m)^mainOperation\s+helloGui\s+main\b", build_text)
          and not re.search(r"(?m)^entry\s+windowsGui\b", build_text)
          and "GuiSurface\" \"standard.gui|gui.* functions" in build_text,
          build_text)

    required_rows = [
        "importModule gui standard.gui",
        "operation main",
        "call createApplicationCall gui.applicationCreate",
        "call createWindowCall gui.windowCreate",
        "call createTitleLabelCall gui.textLabelCreate",
        "call createTaskInputCall gui.textBoxCreate",
        "call createAddButtonCall gui.buttonCreate",
        "call createTaskListCall gui.listBoxCreate",
        "call addTaskListCall gui.windowAddControl",
        "call setMainWindowCall gui.applicationSetMainWindow",
        "call runApplicationCall gui.applicationRun",
    ]
    check("hello gui sample: uses standard.gui function calls",
          all(row in main_text for row in required_rows),
          main_text)
    heavy_gui_decl = re.search(
        r"(?m)^gui(Application|Window|Button|TextBox|ListBox|CheckBox|MenuItem|StatusBar|TextLabel|Control)\b",
        main_text)
    check("hello gui sample: avoids GUI-specific top-level keyword rows",
          heavy_gui_decl is None,
          heavy_gui_decl.group(0) if heavy_gui_decl else main_text)
    check("hello gui sample: keeps construction explicit in operation bodies",
          "gui." in main_text
          and "input addTaskFromInput session GuiSession" in main_text
          and "input addTaskFromInput event GuiEvent" in main_text,
          main_text)


def test_hello_gui_parser_contract_when_supported():
    main_path = HELLO_GUI_DIR / "main.sem"
    source = main_path.read_text(encoding="utf-8")
    try:
        prog = semsc.parse(source)
    except SyntaxError as e:
        msg = str(e)
        check("gui parser: pending until gui* parser support lands",
              _gui_support_pending_message(msg),
              msg)
        return

    check("gui parser: standard.gui import alias is recorded",
          prog.import_aliases.get("gui") == "standard.gui",
          repr(prog.import_aliases))
    check("gui parser: main operation is recorded through normal operation syntax",
          "main" in prog.operations,
          repr(prog.operations))
    operation = prog.operations.get("main")
    call_targets = {
        args[1]
        for verb, args, _line in (operation.lines if operation else [])
        if verb == "call" and len(args) >= 2
    }
    check("gui parser: GUI construction is ordinary dotted call targets",
          {
              "gui.applicationCreate",
              "gui.windowCreate",
              "gui.textLabelCreate",
              "gui.textBoxCreate",
              "gui.buttonCreate",
              "gui.listBoxCreate",
              "gui.windowAddControl",
              "gui.applicationSetMainWindow",
              "gui.applicationRun",
          }.issubset(call_targets),
          repr(sorted(call_targets)))


def test_hello_gui_build_tape_contract_when_supported():
    build_path = HELLO_GUI_DIR / "build.sem"
    source = build_path.read_text(encoding="utf-8")
    try:
        semsc._validate_build_tape_source(source, str(build_path))
    except SyntaxError as e:
        msg = str(e)
        check("gui build tape: pending until windowsGui targetRuntime is accepted",
              _gui_support_pending_message(msg),
              msg)
        return

    try:
        resolved = semsc._resolve_imports(source, str(build_path))
        prog = semsc.parse(resolved)
    except SyntaxError as e:
        msg = str(e)
        check("gui build tape: pending until minimal GUI parse bridge is complete",
              _gui_support_pending_message(msg),
              msg)
        return
    check("gui build tape: targetRuntime windowsGui is recorded",
          semsc._build_metadata_value(prog, "targetRuntime") == "windowsGui",
          repr(semsc._build_metadata_rows(prog, "targetRuntime")))
    check("gui build tape: target windowsGui is recorded",
          "windowsGui" in prog.targets,
          repr(prog.targets))
    check("gui build tape: windowsGui uses the standard entry/mainOperation rows",
          prog.entry == ("console", "main")
          and re.search(r"(?m)^entry\s+console\s+main\b", source)
          and semsc._build_metadata_value(prog, "mainOperation") == "main",
          f"entry={prog.entry!r} mainOperation={semsc._build_metadata_value(prog, 'mainOperation')!r}")


def test_hello_gui_codegen_contract_when_supported():
    build_path = HELLO_GUI_DIR / "build.sem"
    with tempfile.TemporaryDirectory() as tmpdir:
        ir_path = Path(tmpdir) / "hello_gui.ll"
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--emit-ir", str(ir_path), "--quiet"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            message = proc.stdout + proc.stderr
            check("gui codegen: pending until windowsGui lowering lands",
                  _gui_support_pending_message(message),
                  message)
            return
        ir_text = ir_path.read_text(encoding="utf-8") if ir_path.exists() else ""

    check("gui codegen: declares standard.gui builder runtime calls",
          "ss_gui_application_create" in ir_text
          and "ss_gui_window_create" in ir_text
          and "ss_gui_button_create" in ir_text
          and "ss_gui_application_run_builder" in ir_text,
          ir_text)
    check("gui codegen: emits standard.gui window text",
          "Hello GUI" in ir_text,
          ir_text)


def test_build_tape_llvm_flags_drive_outputs():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        module_path = root / "main.sem"
        build_ir_path = root / "artifacts" / "sem-build" / "custom.ll"
        build_path.write_text("\n".join([
            "buildProject llvmFlags",
            "project LlvmFlags",
            "modulePath llvmFlags github.com/example/llvm-flags",
            "languageVersion llvmFlags \"1.0\"",
            "projectVersion llvmFlags \"1.0.0\"",
            "projectLicense llvmFlags MIT",
            "sourceRoot llvmFlags \".\"",
            "registerModule llvmFlags app.llvm_flags \".\"",
            "mainFile llvmFlags \"main.sem\"",
            "mainOperation llvmFlags main",
            "targetRuntime llvmFlags nativeExe",
            "buildProfile llvmFlags dev",
            "runtimeChecks llvmFlags panic",
            "persistLlvmIr llvmFlags auto",
            "optLevel llvmFlags 0",
            "emitLlvmIr llvmFlags yes",
            "llvmIrOutput llvmFlags \"custom.ll\"",
            "buildRoot llvmFlags \"artifacts\"",
            "buildFolderName llvmFlags sem-build",
            "target console",
            "runtime native 1",
            "entry console main",
            "importModule app.llvm_flags",
            "",
        ]), encoding="utf-8", newline="\n")
        module_path.write_text("\n".join([
            "module app.llvm_flags",
            "exportOperation app.llvm_flags main",
            "operation main",
            "output main ExitCode",
            "memory main heap no",
            "async main no",
            "purpose main \"build tape llvm flag smoke\"",
            "returnValue 0",
            "",
        ]), encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(build_path), "--quiet"],
            capture_output=True, text=True,
        )
        ir_exists = build_ir_path.exists()
    check("build tape: llvm flags write IR into configured build folder",
          proc.returncode == 0 and ir_exists,
          f"rc={proc.returncode} stderr={proc.stderr!r} path={build_ir_path}")


def test_cpu_build_config_defaults_to_portable_generic():
    prog = semsc.parse("project CpuDefault\n")
    config = semsc._resolve_cpu_build_config(prog)
    check("cpu flags: default baseline is portable generic",
          config.baseline == "generic" and not config.llvm_features and not config.clang_args,
          config.summary())


def test_cpu_build_config_collects_feature_overrides():
    prog = semsc.parse("\n".join([
        "buildProject cpuSmoke",
        "project CpuSmoke",
        "modulePath cpuSmoke github.com/example/cpu-smoke",
        "languageVersion cpuSmoke \"1.0\"",
        "projectVersion cpuSmoke \"1.0.0\"",
        "projectLicense cpuSmoke MIT",
        "sourceRoot cpuSmoke \".\"",
        "targetRuntime cpuSmoke nativeExe",
        "buildProfile cpuSmoke dev",
        "runtimeChecks cpuSmoke panic",
        "persistLlvmIr cpuSmoke auto",
        "optLevel cpuSmoke 2",
        "cpuBaseline cpuSmoke generic",
        "cpuFeature cpuSmoke avx2 off",
        "cpuFeatureCheck cpuSmoke off",
        "",
    ]))
    config = semsc._resolve_cpu_build_config(prog)
    check("cpu flags: build tape feature disables lower to LLVM feature string",
          "-avx2" in config.llvm_features and "-mno-avx2" in config.clang_args,
          f"llvm={config.llvm_features!r} clang={config.clang_args!r}")


def test_cpu_feature_check_rejects_missing_required_feature():
    prog = semsc.parse("\n".join([
        "project CpuMissingFeature",
        "cpuFeatureCheck cpuMissing require",
        "cpuFeature cpuMissing madeup-feature-for-test on",
        "",
    ]))
    raised = False
    msg = ""
    try:
        semsc._resolve_cpu_build_config(prog)
    except ValueError as e:
        raised = True
        msg = str(e)
    check("cpu flags: required missing host feature fails before codegen",
          raised and "missing required feature" in msg,
          f"raised={raised} msg={msg!r}")


def test_sem_build_driver_discovers_build_tape():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        build_path = root / "build.sem"
        module_path = root / "main.sem"
        build_path.write_text("\n".join([
            "buildProject semDriver",
            "project SemDriver",
            "modulePath semDriver github.com/example/sem-driver",
            "languageVersion semDriver \"1.0\"",
            "projectVersion semDriver \"1.0.0\"",
            "projectLicense semDriver MIT",
            "sourceRoot semDriver \".\"",
            "registerModule semDriver app.sem_driver \".\"",
            "mainFile semDriver \"main.sem\"",
            "mainOperation semDriver main",
            "targetRuntime semDriver nativeExe",
            "buildProfile semDriver dev",
            "runtimeChecks semDriver panic",
            "persistLlvmIr semDriver auto",
            "optLevel semDriver 2",
            "target console",
            "runtime native 1",
            "entry console main",
            "importModule app.sem_driver",
            "",
        ]), encoding="utf-8", newline="\n")
        module_path.write_text("\n".join([
            "module app.sem_driver",
            "exportOperation app.sem_driver main",
            "operation main",
            "output main ExitCode",
            "memory main heap no",
            "async main no",
            "purpose main \"sem build discovery smoke\"",
            "returnValue 0",
            "",
        ]), encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "sem.py"),
             "build", str(root), "--parse-only", "--quiet"],
            capture_output=True, text=True,
        )
    check("sem build: discovers build.sem and passes compiler flags",
          proc.returncode == 0,
          f"rc={proc.returncode} stderr={proc.stderr!r} stdout={proc.stdout!r}")


def test_codegen_diagnostic_is_agent_readable():
    src = "\n".join([
        "project BadDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "call badCall math.addI64",
        "arg badCall left missingValue",
        "arg badCall right 1",
        "run badCall",
        "bind resultValue CSignedInt64 badCall",
        "returnValue resultValue",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "bad.sscript"
        ir_path = Path(tmpdir) / "bad.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", str(ir_path)],
            capture_output=True, text=True,
        )
        stderr = proc.stderr
        check("diagnostics: call-lowering failure exits 3",
              proc.returncode == 3,
              f"rc={proc.returncode} stderr={stderr!r}")
        check("diagnostics: agent log names code and phase",
              "error SSCG002" in stderr and "phase: codegen.call-lowering" in stderr,
              stderr)
        check("diagnostics: SemanticScript stack points to call",
              "call badCall math.addI64" in stderr
              and "source: call badCall math.addI64" in stderr,
              stderr)
        json_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", str(ir_path),
             "--diagnostics-format", "json"],
            capture_output=True, text=True,
        )
        try:
            payload = json.loads(json_proc.stderr)
        except json.JSONDecodeError:
            payload = {}
        check("diagnostics: json renderer is machine-readable",
              payload.get("code") == "SSCG002"
              and payload.get("semanticStack", [{}])[0].get("callName") == "badCall",
              json_proc.stderr)


def test_web_codegen_rejects_unsupported_http_target():
    src = "\n".join([
        "project UnsupportedHttpTarget",
        "target webServer",
        "runtime native 1",
        "module fixture",
        "webServer fixtureServer",
        "serverHost fixtureServer \"127.0.0.1\"",
        "serverPort fixtureServer 18081",
        "route fixtureServer GET \"/json\" jsonHandler",
        "capability httpResponseWriter http.response write",
        "operation jsonHandler",
        "input jsonHandler request HttpRequest",
        "input jsonHandler response HttpResponse",
        "output jsonHandler CSignedInt32",
        "effect jsonHandler write http.response",
        "memory jsonHandler arena request",
        "async jsonHandler no",
        "useCapability jsonHandler httpResponseWriter",
        "purpose jsonHandler \"Exercise unsupported HTTP target diagnostics\"",
        "label startJsonHandler",
        "const okStatus CSignedInt32 200",
        "const jsonBody CNullTerminatedByteString \"{}\"",
        "call jsonWriteCall http.responseJson",
        "arg jsonWriteCall response response",
        "arg jsonWriteCall status okStatus",
        "arg jsonWriteCall body jsonBody",
        "run jsonWriteCall",
        "bind responseStatus CSignedInt32 jsonWriteCall",
        "returnValue responseStatus",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "unsupported_http.sscript"
        ir_path = Path(tmpdir) / "unsupported_http.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", str(ir_path)],
            capture_output=True, text=True,
        )
    check("web codegen: unsupported http target exits 3",
          proc.returncode == 3,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("web codegen: unsupported http target names call",
          "unsupported native HTTP call target" in proc.stderr
          and "http.responseJson" in proc.stderr
          and "call jsonWriteCall http.responseJson" in proc.stderr,
          proc.stderr)


def test_sqlite_codegen_emits_runtime_externs_and_calls():
    """Deep-audit smoke for the standard.sqlite lowering. Parses the
    canonical syntax sample, runs codegen, and asserts the IR actually
    declares each ss_sqlite_* extern and calls into it. Without these
    asserts a regression that quietly dropped the dispatch block (or
    no-op'd it to ir.Constant(I32, 0)) would still produce IR that
    compiles — see the project memory `feedback_verify_impld_claims`
    for why we require failure under no-op lowering."""
    sample_path = ROOT / "sem" / "syntax_sample_sqlite.sscript"
    source = sample_path.read_text(encoding="utf-8")
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    expected_externs = (
        "ss_sqlite_database_open",
        "ss_sqlite_database_close",
        "ss_sqlite_database_last_insert_rowid",
        "ss_sqlite_exec",
        "ss_sqlite_statement_prepare",
        "ss_sqlite_statement_finalize",
        "ss_sqlite_statement_step",
        "ss_sqlite_statement_bind_text",
        "ss_sqlite_statement_bind_int64",
        "ss_sqlite_statement_column_int64",
        "ss_sqlite_statement_column_text",
    )
    for symbol in expected_externs:
        check(f"sqlite lowering: IR declares @{symbol}",
              f"@\"{symbol}\"" in ir_text or f"@{symbol}" in ir_text,
              f"no declare for {symbol}")
        check(f"sqlite lowering: IR calls @{symbol}",
              f"call i32 @\"{symbol}\"" in ir_text
              or f"call i32 @{symbol}" in ir_text
              or f"call i64 @\"{symbol}\"" in ir_text
              or f"call i64 @{symbol}" in ir_text
              or f"call i8* @\"{symbol}\"" in ir_text
              or f"call i8* @{symbol}" in ir_text
              or f"call ptr @\"{symbol}\"" in ir_text
              or f"call ptr @{symbol}" in ir_text,
              f"no call to {symbol}")
    # openDatabase + prepareStatement allocate an i8* slot for the
    # out-pointer; missing alloca would mean the handle isn't being
    # read back from the call.
    check("sqlite lowering: openDatabase allocates database slot",
          "openDatabaseCall_databaseSlot" in ir_text,
          "no databaseSlot alloca emitted for sqlite.openDatabase")
    check("sqlite lowering: prepareStatement allocates statement slot",
          "prepareInsertCall_statementSlot" in ir_text
          or "prepareSelectCall_statementSlot" in ir_text,
          "no statementSlot alloca emitted for sqlite.prepareStatement")


def test_sqlite_codegen_rejects_unsupported_target():
    """If a `sqlite.*` call name isn't in the dispatch block the
    compiler must fail loudly rather than fall through to the
    external-module zero-result fallback — the latter would silently
    produce a no-op exe. Mirrors test_web_codegen_rejects_unsupported_http_target."""
    src = "\n".join([
        "project UnsupportedSqliteTarget",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "purpose main \"exercise the sqlite unsupported-target diagnostic\"",
        "label start",
        "const dbPath CNullTerminatedByteString \":memory:\"",
        "call unsupportedSqliteCall sqlite.notARealEntryPoint",
        "arg unsupportedSqliteCall path dbPath",
        "run unsupportedSqliteCall",
        "bind unsupportedSqliteResult CSignedInt32 unsupportedSqliteCall",
        "returnValue unsupportedSqliteResult",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "unsupported_sqlite.sscript"
        ir_path = Path(tmpdir) / "unsupported_sqlite.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-ir", str(ir_path)],
            capture_output=True, text=True,
        )
    check("sqlite codegen: unsupported target exits 3",
          proc.returncode == 3,
          f"rc={proc.returncode} stderr={proc.stderr!r}")
    check("sqlite codegen: unsupported target names call",
          "unsupported native sqlite call target" in proc.stderr
          and "sqlite.notARealEntryPoint" in proc.stderr,
          proc.stderr)


def test_sqlite_syntax_sample_runs_end_to_end():
    """End-to-end deep-audit: compile the sqlite syntax sample to a
    native exe via --emit-exe (which triggers the native_sqlite link
    inputs and the vendored amalgamation), run the resulting binary,
    and assert it reports the round-trip body text on stdout. This is
    the test that would fail under a missing _native_sqlite_link_inputs
    wiring — semsc would emit IR but the link step would fail to
    resolve ss_sqlite_* symbols."""
    sample_path = ROOT / "sem" / "syntax_sample_sqlite.sscript"
    with tempfile.TemporaryDirectory() as tmpdir:
        exe_path = Path(tmpdir) / ("sqlite_sample.exe"
                                    if os.name == "nt"
                                    else "sqlite_sample")
        build_dir = Path(tmpdir) / "build"
        compile_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(sample_path), "--emit-exe", str(exe_path),
             "--build-dir", str(build_dir), "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        check("sqlite e2e: compile-and-link succeeds",
              compile_proc.returncode == 0,
              f"rc={compile_proc.returncode} stderr={compile_proc.stderr!r}")
        if compile_proc.returncode != 0 or not exe_path.exists():
            return
        run_proc = subprocess.run(
            [str(exe_path)],
            capture_output=True, text=True, timeout=30,
        )
        check("sqlite e2e: exe exits 0",
              run_proc.returncode == 0,
              f"rc={run_proc.returncode} stderr={run_proc.stderr!r}")
        check("sqlite e2e: stdout carries selected row body",
              "hello from sqlite syntax sample" in run_proc.stdout,
              f"stdout={run_proc.stdout!r}")


def test_json_runtime_health_demo_runs_clean():
    """Compile + run SemanticScript/runtime/native_json/health_demo.c
    directly via clang. The C-side smoke is the authoritative byte-
    for-byte assertion of escape correctness — it pins the encoder's
    output text and round-trips every primitive. Failing this check
    indicates a regression in the JSON runtime independent of any
    semsc lowering."""
    runtime_dir = ROOT / "runtime" / "native_json"
    runtime_src = runtime_dir / "sem_json_runtime.c"
    demo_src = runtime_dir / "health_demo.c"
    if not runtime_src.exists() or not demo_src.exists():
        check("json runtime: source files present",
              False, f"missing {runtime_src} or {demo_src}")
        return
    clang = os.environ.get("SEMSC_CLANG")
    if not clang:
        from shutil import which
        clang = which("clang") or r"C:\Program Files\LLVM\bin\clang.exe"
    if not Path(clang).exists():
        check("json runtime: clang available",
              False, f"clang not at {clang}")
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        exe_path = Path(tmpdir) / ("json_health.exe" if os.name == "nt"
                                    else "json_health")
        compile_proc = subprocess.run(
            [str(clang), "-O2", "-Wall", "-Wextra",
             str(runtime_src), str(demo_src),
             "-o", str(exe_path)],
            capture_output=True, text=True, timeout=60,
        )
        check("json runtime: health demo compiles clean",
              compile_proc.returncode == 0
              and "warning" not in compile_proc.stderr.lower(),
              f"rc={compile_proc.returncode} stderr={compile_proc.stderr!r}")
        if not exe_path.exists():
            return
        run_proc = subprocess.run(
            [str(exe_path)], capture_output=True, text=True, timeout=10)
        check("json runtime: health demo exits 0",
              run_proc.returncode == 0,
              f"rc={run_proc.returncode} stderr={run_proc.stderr!r}")
        check("json runtime: encoder produces expected escapes",
              "\\\"json\\\"" in run_proc.stdout
              and "\\\\world" in run_proc.stdout
              and "\\n" in run_proc.stdout
              and "\\t" in run_proc.stdout
              and "\\u0001" in run_proc.stdout,
              f"stdout={run_proc.stdout!r}")
        check("json runtime: finder recovers values",
              "id=42 done=0 completedAt_present=1 missing_present=0"
              in run_proc.stdout,
              f"stdout={run_proc.stdout!r}")
        check("json runtime: ok marker present",
              "sem_json_health_demo: ok" in run_proc.stdout,
              f"stdout={run_proc.stdout!r}")


def test_json_codegen_emits_runtime_externs_and_calls():
    """IR-level deep audit for the standard.json dispatch. Parses the
    json runtime smoke fixture, runs codegen, asserts every ss_json_*
    extern this fixture exercises is both declared AND called. Without
    these checks a regression that no-op'd the dispatch handlers
    would still produce IR that compiles (returning zero everywhere)
    and the AS smoke would silently start asserting against junk."""
    fixture = ROOT / "tests" / "json_runtime_smoke.sscript"
    source = fixture.read_text(encoding="utf-8")
    prog = semsc.parse(source)
    cg = semsc.Codegen(prog)
    mod = cg.compile()
    ir_text = str(mod)
    expected_externs = (
        "ss_json_builder_create",
        "ss_json_builder_destroy",
        "ss_json_builder_object_open",
        "ss_json_builder_object_close",
        "ss_json_builder_field_int64",
        "ss_json_builder_field_string",
        "ss_json_builder_field_bool",
        "ss_json_builder_field_null",
        "ss_json_builder_finish",
        "ss_json_find_int64",
        "ss_json_find_bool",
        "ss_json_find_string",
        "ss_json_has_field",
    )
    for symbol in expected_externs:
        check(f"json lowering: IR declares @{symbol}",
              f"@\"{symbol}\"" in ir_text or f"@{symbol}" in ir_text,
              f"no declare for {symbol}")
        check(f"json lowering: IR calls @{symbol}",
              f"@\"{symbol}\"" in ir_text or f"@{symbol}" in ir_text,
              f"no call to {symbol}")


def test_json_runtime_smoke_runs_end_to_end():
    """End-to-end smoke for the standard.json AS-side surface. Compiles
    the primary fixture (object + 4 primitive field types + finder
    round-trips) via --emit-exe, runs it, asserts exit 0 and the
    success marker on stdout. Failure here typically means the linker
    didn't pull in sem_json_runtime.c or one of the dispatchers got
    its arg ordering wrong."""
    sample_path = ROOT / "tests" / "json_runtime_smoke.sscript"
    with tempfile.TemporaryDirectory() as tmpdir:
        exe_path = Path(tmpdir) / ("json_smoke.exe" if os.name == "nt"
                                    else "json_smoke")
        compile_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(sample_path), "--emit-exe", str(exe_path),
             "--build-dir", str(Path(tmpdir) / "build"), "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        check("json e2e smoke: compile-and-link succeeds",
              compile_proc.returncode == 0,
              f"rc={compile_proc.returncode} stderr={compile_proc.stderr!r}")
        if compile_proc.returncode != 0 or not exe_path.exists():
            return
        run_proc = subprocess.run(
            [str(exe_path)], capture_output=True, text=True, timeout=10)
        check("json e2e smoke: exe exits 0",
              run_proc.returncode == 0,
              f"rc={run_proc.returncode} stderr={run_proc.stderr!r}")
        check("json e2e smoke: success marker on stdout",
              "jsonRuntimeSmokeOk" in run_proc.stdout,
              f"stdout={run_proc.stdout!r}")


def test_json_adversarial_smoke_runs_end_to_end():
    """Second AS-side fixture exercising negative numbers, near-INT64_MAX
    values, and empty strings — cases the primary smoke skips. A
    regression in integer-overflow handling, snprintf format width,
    or empty-string framing would surface here first."""
    sample_path = ROOT / "tests" / "json_runtime_adversarial.sscript"
    with tempfile.TemporaryDirectory() as tmpdir:
        exe_path = Path(tmpdir) / ("json_adv.exe" if os.name == "nt"
                                    else "json_adv")
        compile_proc = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(sample_path), "--emit-exe", str(exe_path),
             "--build-dir", str(Path(tmpdir) / "build"), "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        check("json adversarial: compile-and-link succeeds",
              compile_proc.returncode == 0,
              f"rc={compile_proc.returncode} stderr={compile_proc.stderr!r}")
        if compile_proc.returncode != 0 or not exe_path.exists():
            return
        run_proc = subprocess.run(
            [str(exe_path)], capture_output=True, text=True, timeout=10)
        check("json adversarial: exe exits 0",
              run_proc.returncode == 0,
              f"rc={run_proc.returncode} stderr={run_proc.stderr!r}")
        check("json adversarial: success marker on stdout",
              "jsonAdversarialOk" in run_proc.stdout,
              f"stdout={run_proc.stdout!r}")


def test_backend_diagnostic_maps_symbol_to_source_call():
    src = "\n".join([
        "project BackendDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "call loadJsonCall c.fscanf",
        "returnValue 0",
        "",
    ])
    prog = semsc.parse(src)
    prog.source_path = "backend_bad.sscript"
    cg = semsc.Codegen(prog)
    fake_call = {
        "name": "loadJsonCall",
        "operation": "main",
        "line": 8,
        "target": "c.fscanf",
    }
    cg.provenance.record_external("fscanf", fake_call)
    diag = cg.provenance.explain_backend_error(
        "lld-link: error: undefined symbol: fscanf\n"
        ">>> referenced by tmp.o:(main)\n"
    )
    rendered = diag.render("agent")
    check("diagnostics: backend undefined symbol maps to source",
          diag.code == "SSBE001"
          and diag.primary.line == 8
          and "call loadJsonCall c.fscanf" in rendered,
          rendered)


def test_runtime_check_resolution_profiles():
    check("runtime profile: dev defaults to panic",
          semsc._resolve_runtime_checks("dev") == "panic")
    check("runtime profile: prod defaults to traps",
          semsc._resolve_runtime_checks("prod") == "traps")
    check("runtime profile: explicit override wins",
          semsc._resolve_runtime_checks("prod", "panic") == "panic"
          and semsc._resolve_runtime_checks("dev", "off") == "off")


def test_runtime_profiles_control_panic_context():
    import shutil
    clang = (os.environ.get("SEMSC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("runtime checks: clang available", False,
              f"clang not found at {clang}")
        return
    src = "\n".join([
        "project RuntimePanicDiagnostic",
        "entry console main",
        "operation main",
        "output main ExitCode",
        "memory main heap no",
        "async main no",
        "label start",
        "const numeratorValue CSignedInt64 7",
        "const zeroDivisor CSignedInt64 0",
        "call divideByZeroCall math.divideI64",
        "arg divideByZeroCall left numeratorValue",
        "arg divideByZeroCall right zeroDivisor",
        "run divideByZeroCall",
        "bind quotientValue CSignedInt64 divideByZeroCall",
        "returnValue quotientValue",
        "",
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        src_path = Path(tmpdir) / "runtime_panic.sscript"
        dev_exe_path = Path(tmpdir) / "runtime_panic_dev.exe"
        dev_ir_path = Path(tmpdir) / "runtime_panic_dev.ll"
        prod_exe_path = Path(tmpdir) / "runtime_panic_prod.exe"
        prod_ir_path = Path(tmpdir) / "runtime_panic_prod.ll"
        src_path.write_text(src, encoding="utf-8", newline="\n")
        dev_build = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-exe", str(dev_exe_path),
             "--emit-ir", str(dev_ir_path), "--quiet"],
            capture_output=True, text=True,
        )
        if dev_build.returncode != 0:
            check("runtime profile: dev sample builds", False, dev_build.stderr)
            return
        dev_ir_text = dev_ir_path.read_text(encoding="utf-8")
        check("runtime profile: dev panic path avoids C stdio",
              "puts" not in dev_ir_text and "fflush" not in dev_ir_text,
              dev_ir_text)
        dev_run = subprocess.run(
            [str(dev_exe_path)], capture_output=True, text=True)
        dev_output = dev_run.stdout + dev_run.stderr
        check("runtime profile: dev sample exits nonzero",
              dev_run.returncode != 0,
              f"rc={dev_run.returncode} output={dev_output!r}")
        check("runtime profile: dev output names source row by default",
              "error SSRUN001: SemanticScript runtime panic" in dev_output
              and "call: divideByZeroCall -> math.divideI64" in dev_output
              and "10 | call divideByZeroCall math.divideI64" in dev_output
              and "reason: zero divisor before math.divideI64" in dev_output
              and "--build-profile prod" not in dev_output
              and "--runtime-checks off" not in dev_output,
              dev_output)

        prod_build = subprocess.run(
            [sys.executable, str(COMPILER_DIR / "semsc.py"),
             str(src_path), "--emit-exe", str(prod_exe_path),
             "--emit-ir", str(prod_ir_path), "--build-profile", "prod",
             "--quiet"],
            capture_output=True, text=True,
        )
        if prod_build.returncode != 0:
            check("runtime profile: prod sample builds", False, prod_build.stderr)
            return
        prod_ir_text = prod_ir_path.read_text(encoding="utf-8")
        prod_run = subprocess.run(
            [str(prod_exe_path)], capture_output=True, text=True)
        prod_output = prod_run.stdout + prod_run.stderr
        check("runtime profile: prod sample exits nonzero",
              prod_run.returncode != 0,
              f"rc={prod_run.returncode} output={prod_output!r}")
        check("runtime profile: prod hides source context",
              "llvm.trap" in prod_ir_text
              and "SSRUN001" not in prod_ir_text
              and "SemanticScript runtime panic" not in prod_output
              and "SSRUN001" not in prod_output,
              f"ir={prod_ir_text!r}\noutput={prod_output!r}")


# ============================================================
# Bootstrap chain validation
# ============================================================

def _ensure_built(stage_basename):
    src = BOOTSTRAP_DIR / f"{stage_basename}.sscript"
    exe = BOOTSTRAP_DIR / f"{stage_basename}.exe"
    if exe.exists() and exe.stat().st_mtime >= src.stat().st_mtime:
        return exe
    proc = subprocess.run(
        [sys.executable, str(COMPILER_DIR / "semsc.py"),
         str(src), "--emit-exe", str(exe), "--quiet"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to build {stage_basename}.exe\nSTDERR:\n{proc.stderr}")
    return exe


def _emit_ir(stage_exe):
    proc = subprocess.run([str(stage_exe)], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{stage_exe.name} exited {proc.returncode}\nSTDERR:\n{proc.stderr}")
    return proc.stdout


def test_bootstrap3_emits_constant_return_ir():
    exe = _ensure_built("bootstrap3")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input3.sscript").read_text(encoding="utf-8")
    expected = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap3: IR contains 'define i32 @main()'",
          "define i32 @main()" in ir_text,
          f"IR was:\n{ir_text}")
    check("bootstrap3: IR returns the parsed ExitCode literal",
          f"ret i32 {expected}" in ir_text,
          f"expected ret i32 {expected}, IR:\n{ir_text}")


def test_bootstrap4_emits_greeting_and_exit():
    exe = _ensure_built("bootstrap4")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input4.sscript").read_text(encoding="utf-8")
    marker = 'CNullTerminatedByteString "'
    idx = input_text.find(marker)
    g_start = idx + len(marker)
    g_end = input_text.index('"', g_start)
    expected_greeting = input_text[g_start:g_end]
    expected_exit = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap4: IR contains greeting bytes",
          expected_greeting in ir_text,
          f"greeting {expected_greeting!r} not in IR")
    check("bootstrap4: IR returns parsed ExitCode",
          f"ret i32 {expected_exit}" in ir_text,
          f"expected ret i32 {expected_exit}")
    check("bootstrap4: IR declares puts",
          "declare i32 @puts(i8*)" in ir_text,
          "no puts declaration in IR")


def test_bootstrap_general_real_dispatch():
    """bootstrap_general.sscript compiles a wide subset of sem/ via REAL
    per-line verb dispatch + escape-aware byte walker. We don't pattern-
    match the IR text (it uses `\\XX` hex escapes now); instead we link
    the IR with clang and diff the exe's stdout against the JS oracle."""
    import shutil
    exe = _ensure_built("bootstrap_general")
    clang = (os.environ.get("SEMSC_CLANG")
             or shutil.which("clang")
             or r"C:/Program Files/LLVM/bin/clang.exe")
    if not Path(clang).exists():
        check("bootstrap_general: clang available", False,
              f"clang not found at {clang}")
        return
    import tempfile
    work = Path(tempfile.gettempdir()) / "semsc_general_tests"
    work.mkdir(exist_ok=True)
    PROJECT_ROOT = BOOTSTRAP_DIR.parent.parent
    pairs = [
        ("hello.sscript", "hello.js"),
        ("hello_world.sscript", "hello-world.js"),
        ("hello_via_helper.sscript", "hello.js"),
        ("inventory_manager.sscript", "inventory-manager.js"),
        ("counterintuitive_closure_capture.sscript", "counterintuitive-closure-capture.js"),
        ("file_inventory.sscript", "file-inventory.js"),
        ("json_order_summary.sscript", "json-order-summary.js"),
    ]
    for sem_basename, js_basename in pairs:
        env = dict(os.environ)
        sem_path = BOOTSTRAP_DIR.parent / "sem" / sem_basename
        env["SEMANTIC_SCRIPT_INPUT"] = str(sem_path)
        proc = subprocess.run([str(exe)], env=env,
                              capture_output=True, text=True, timeout=15)
        ll = work / (sem_basename.replace(".sscript", ".ll"))
        ll.write_text(proc.stdout, encoding="utf-8", newline="\n")
        out_exe = work / (sem_basename.replace(".sscript", ".exe"))
        link = subprocess.run([clang, "-O2", "-o", str(out_exe), str(ll)],
                              capture_output=True, text=True)
        check(f"bootstrap_general: {sem_basename} produces linkable IR",
              link.returncode == 0,
              f"clang failure: {link.stderr.strip()[:200]}")
        if link.returncode != 0:
            continue
        run = subprocess.run([str(out_exe)],
                             capture_output=True, text=True, timeout=15)
        oracle = subprocess.run(
            ["node", str(PROJECT_ROOT / "samples" / "javascript" / js_basename)],
            capture_output=True, text=True, timeout=15)
        sem_out = run.stdout.replace("\r\n", "\n").rstrip("\n")
        js_out = oracle.stdout.replace("\r\n", "\n").rstrip("\n")
        check(f"bootstrap_general: {sem_basename} stdout matches JS oracle",
              sem_out == js_out,
              f"SEM={sem_out[:80]!r}  JS={js_out[:80]!r}")


def test_bootstrap6_scales_with_input():
    exe = _ensure_built("bootstrap6")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input6.sscript").read_text(encoding="utf-8")
    greetings = re.findall(r'CNullTerminatedByteString "([^"]*)"', input_text)
    n = len(greetings)
    check("bootstrap6: emits one @.s<i> constant per input greeting",
          all(f"@.s{i}" in ir_text for i in range(n)),
          f"missing @.s<i> for some i in 0..{n-1}")
    check("bootstrap6: emits one @print<i> helper per input greeting",
          all(f"@print{i}()" in ir_text for i in range(n)),
          f"missing @print<i> for some i in 0..{n-1}")
    check("bootstrap6: main calls every helper in order",
          all(f"call void @print{i}()" in ir_text for i in range(n)),
          "main is missing one or more @print<i> calls")
    expected_exit = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap6: ret i32 matches parsed ExitCode",
          f"ret i32 {expected_exit}" in ir_text,
          "ret i32 doesn't match parsed ExitCode")


def test_bootstrap5_emits_countdown_loop():
    exe = _ensure_built("bootstrap5")
    ir_text = _emit_ir(exe)
    input_text = (BOOTSTRAP_DIR / "input5.sscript").read_text(encoding="utf-8")
    expected_start = int(re.search(r"CountdownValue (\d+)", input_text).group(1))
    expected_exit = int(re.search(r"ExitCode (\d+)", input_text).group(1))
    check("bootstrap5: IR contains loopHead label",
          "loopHead:" in ir_text,
          "no loopHead label")
    check("bootstrap5: IR contains loopBody label",
          "loopBody:" in ir_text,
          "no loopBody label")
    check("bootstrap5: IR contains loopExit label",
          "loopExit:" in ir_text,
          "no loopExit label")
    check("bootstrap5: IR stores parsed start value",
          f"store i64 {expected_start}, i64* %counter" in ir_text,
          f"no store of {expected_start}")
    check("bootstrap5: IR returns parsed ExitCode",
          f"ret i32 {expected_exit}" in ir_text,
          f"no ret i32 {expected_exit}")


# ============================================================
# Driver
# ============================================================

def main():
    print(f"Running semsc {semsc.__version__} unit tests")
    print("=" * 60)
    test_tokenizer()
    test_parser_minimal()
    test_parser_syntax_error_has_line()
    test_parser_module_namespace_contract()
    test_parser_language_mode_strict_executable()
    test_build_registry_imports_registered_module()
    test_build_registry_qualified_import_call_lowers()
    test_build_registry_singular_import_call_lowers()
    test_build_registry_missing_source_is_error()
    test_strict_rejects_missing_output_contract()
    test_strict_rejects_unknown_output_contract_type()
    test_strict_requires_effect_capability_or_authority()
    test_strict_web_contracts_reject_invalid_route_method()
    test_strict_web_contracts_accept_lowercase_route_method()
    test_strict_executable_mode_rejects_http_contracts_without_lint_flag()
    test_strict_web_contracts_reject_middleware_i32_output()
    test_strict_web_contracts_reject_handler_input_name_mismatch()
    test_strict_web_contracts_reject_missing_response_forwarder()
    test_strict_web_contracts_reject_wrong_response_forwarder()
    test_strict_web_contracts_reject_nullable_header_response_body()
    test_strict_web_contracts_accept_valid_route_middleware_and_forwarder()
    test_strict_rejects_plain_run_for_fallible_heap_allocation()
    test_strict_accepts_complete_legacy_checked_fallible_call_pattern()
    test_strict_executable_run_checked_heap_allocation_lowers()
    test_strict_rejects_plain_run_for_fallible_sqlite_prepare()
    test_strict_rejects_missing_status_for_fallible_http_response_write()
    test_strict_executable_rejects_heap_allocation_without_oom_branch()
    test_strict_executable_rejects_heap_allocation_without_free()
    test_strict_executable_rejects_double_heap_free()
    test_strict_executable_accepts_explicit_heap_free()
    test_strict_executable_rejects_sqlite_open_setup_failure_without_close()
    test_strict_executable_accepts_sqlite_open_setup_failure_close()
    test_strict_executable_rejects_sqlite_prepare_without_finalize()
    test_strict_executable_accepts_sqlite_prepare_finalize_defer()
    test_compile_hello_world_to_ir()
    test_compile_i32_comparison_to_i32_ir()
    test_compile_rejects_implicit_i32_to_i64_math()
    test_compile_explicit_i32_to_i64_conversion_lowers_to_sext()
    test_compile_pointer_load_byte_sign_extends_to_i32()
    test_html_template_parser_records_body_and_rejects_bad_edges()
    test_html_template_simple_jit_output()
    test_html_template_edge_output_repeated_adjacent_and_blank_lines()
    test_html_template_raw_style_and_script_do_not_hydrate_braces()
    test_html_template_escapes_html_text_by_sink_context()
    test_html_standard_module_import_exposes_hydrate_namespace_and_exports()
    test_standard_library_module_relay_exposes_standard_modules()
    test_standard_import_resolves_from_bundled_compiler_std_outside_repo()
    test_standard_import_std_path_override_wins_outside_repo()
    test_html_template_long_dynamic_arg_is_bounded_and_terminated()
    test_html_template_complex_modules_jit_and_aot_output()
    test_html_console_demo_runs_from_registered_modules()
    test_html_template_codegen_rejects_bad_hydration_edges()
    test_cli_accepts_sem_alias()
    test_success_message_renderer()
    test_persisted_ir_path_resolution()
    test_build_dir_path_resolution()
    test_cli_persist_llvm_ir_flag()
    test_cli_emit_ir_without_path_uses_build_dir()
    test_cli_inspect_ir_outputs_agent_json()
    test_cli_emit_trace_map_sidecar()
    test_sem_inspect_ir_command()
    test_inspect_ir_reports_http_abi_and_runtime_link_inputs()
    test_inspect_ir_preserves_imported_source_origins()
    test_sem_run_trace_emits_agent_jsonl_events()
    test_sem_profile_json_writes_agent_artifacts_and_deltas()
    test_sem_profile_compile_failure_uses_failure_schema()
    test_sem_explain_crash_reports_runtime_panic_context()
    test_sem_bench_json_reports_stable_deltas()
    test_cli_build_root_and_folder_name()
    test_cli_build_dir_overrides_build_tape_folder_metadata()
    test_build_tape_path_normalization()
    test_build_tape_validation_rejects_missing_required_rows()
    test_build_tape_validation_accepts_dependency_fetch_rows()
    test_build_tape_validation_rejects_insecure_dependency_fetch()
    test_hello_gui_sample_uses_refined_gui_surface()
    test_hello_gui_parser_contract_when_supported()
    test_hello_gui_build_tape_contract_when_supported()
    test_hello_gui_codegen_contract_when_supported()
    test_build_tape_llvm_flags_drive_outputs()
    test_cpu_build_config_defaults_to_portable_generic()
    test_cpu_build_config_collects_feature_overrides()
    test_cpu_feature_check_rejects_missing_required_feature()
    test_sem_build_driver_discovers_build_tape()
    test_codegen_diagnostic_is_agent_readable()
    test_web_codegen_rejects_unsupported_http_target()
    test_sqlite_codegen_emits_runtime_externs_and_calls()
    test_sqlite_codegen_rejects_unsupported_target()
    test_sqlite_syntax_sample_runs_end_to_end()
    test_json_runtime_health_demo_runs_clean()
    test_json_codegen_emits_runtime_externs_and_calls()
    test_json_runtime_smoke_runs_end_to_end()
    test_json_adversarial_smoke_runs_end_to_end()
    test_backend_diagnostic_maps_symbol_to_source_call()
    test_runtime_check_resolution_profiles()
    test_runtime_profiles_control_panic_context()
    test_bootstrap3_emits_constant_return_ir()
    test_bootstrap4_emits_greeting_and_exit()
    test_bootstrap5_emits_countdown_loop()
    test_bootstrap6_scales_with_input()
    test_bootstrap_general_real_dispatch()

    print("=" * 60)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} test(s)")
        for label in FAILURES:
            print(f"  - {label}")
        sys.exit(1)
    print("All unit tests passed.")


if __name__ == "__main__":
    main()
