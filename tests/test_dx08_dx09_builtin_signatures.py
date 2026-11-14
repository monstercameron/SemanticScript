#!/usr/bin/env python3
"""DX-08/DX-09: expose built-in target signatures and validate math call args.

DX-08: agents can look up built-in intrinsic arg slots and output types with
`targets --signature <target>` instead of guessing names such as `lhs`/`rhs`.
The lookup uses shipped standard.<module>.semsig rows first, then generated
fallbacks for concrete targets the code generator models but the sidecar omits.

DX-09: `check` validates slot-sensitive math.* calls against those signatures
(SS1201). Positional families are documented by signatures but not slot-linted.
"""
import importlib
import json

import pytest

ss = importlib.import_module("semanticscript")

_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
    "main let a immutable Int64 10\nmain let b immutable Int64 2\nmain let okc immutable ExitCode 0\n"
    "main do divCall\nmain return okc\n"
    "divCall is call\ndivCall in main\ndivCall invokes math.divideInt64\n"
)


def _codes(arg_rows):
    src = _HEAD + arg_rows + "divCall out q Int64\n"
    return {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


def _modeled_concrete_targets():
    modeled = set(ss._CODEGEN_MODELED_EXACT)
    for d in (ss._INT_BINOPS, ss._INT_CMP, ss._INT_UNARY_INTRIN, ss._MATH_COMPUTED,
              ss._FLOAT_BINOPS, ss._FLOAT_CMP_ORDERED, ss._FLOAT_CMP_UNORDERED,
              ss._FLOAT_UNARY_INTRIN, ss._FLOAT_BINARY_INTRIN):
        modeled.update(d)
    for fam, methods in ss._FAMILY_RT.items():
        for meth in methods:
            modeled.add(f"{fam}.{meth}")
    return sorted(modeled)


# --- DX-08 ---

def test_signature_lookup_returns_slots_and_out():
    sig = ss._builtin_target_signature("math.divideInt64")
    assert [(a["slot"], a["type"]) for a in sig["args"]] == [("left", "Int64"), ("right", "Int64")]
    assert sig["out"] == "Int64"


def test_unknown_target_has_no_signature():
    assert ss._builtin_target_signature("math.nope") is None
    assert ss._builtin_target_signature("notamodule.x") is None


def test_all_concrete_modeled_targets_have_signatures():
    missing = [t for t in _modeled_concrete_targets()
               if ss._builtin_target_signature(t) is None]
    assert missing == []


def test_targets_signature_command(capsys):
    rc = ss.main(["targets", "--signature", "math.divideInt64", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["surface"] == "sem.targetSignature.v1"
    assert {a["slot"] for a in data["args"]} == {"left", "right"}


@pytest.mark.parametrize("target, expected_slots", [
    ("math.addInt32", {"left", "right"}),
    ("console.writeFloat", {"value"}),
    ("console.writeLine", {"text"}),
    ("assert.equalInt64", {"left", "right"}),
    ("json.setObjectFieldInt64", {"document", "cursor", "fieldName", "value"}),
    ("log.logInfo", {"messageText"}),
    ("http.responseText", {"response", "status", "body", "contentType"}),
    ("http.requestBodyText", {"request"}),
    ("sqlite.queryScalarInt64", {"database", "sql"}),
    ("convert.toString", {"value"}),
    ("convert.to.string", {"value"}),
    ("sqlite.prepareStatement", {"database", "sql"}),
    ("pointer.offset", {"base", "offset"}),
    ("html.render", {"template"}),
])
def test_targets_signature_command_for_generated_fallbacks(capsys, target, expected_slots):
    rc = ss.main(["targets", "--signature", target, "--json"])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0 and data["surface"] == "sem.targetSignature.v1"
    assert {a["slot"] for a in data["args"]} == expected_slots


@pytest.mark.parametrize("family", ["json.*", "log.*", "console.*", "assert.*", "http.*", "sqlite.*"])
def test_signature_family_lookup_matches_docs_surface(capsys, family):
    rc = ss.main(["targets", "--signature", family, "--json"])
    target_payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert target_payload["surface"] == "sem.targetSignatures.v1"
    assert target_payload["count"] > 0
    assert all(s["target"].startswith(family[:-1]) for s in target_payload["signatures"])

    rc = ss.main(["docs", "examples/hello_world.sem", "--get", family, "--json"])
    docs_payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    entity = docs_payload["entity"]
    assert entity["kind"] == "intrinsicFamily"
    assert entity["signatures"] == target_payload["signatures"]


# --- DX-09 ---

def test_wrong_slot_names_rejected_at_check():
    assert "SS1201" in _codes("divCall arg lhs Int64 a\ndivCall arg rhs Int64 b\n")


def test_correct_slot_names_accepted():
    assert "SS1201" not in _codes("divCall arg left Int64 a\ndivCall arg right Int64 b\n")


def test_missing_required_slot_rejected():
    assert "SS1201" in _codes("divCall arg left Int64 a\n")


def test_assert_equal_int64_expected_actual_shape_rejected_at_check():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "TestResult is alias\nTestResult for Bool\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let expected immutable Int64 1\nmain let actual immutable Int64 2\n"
        "main let okc immutable ExitCode 0\nmain do checkIt\nmain return okc\n"
        "checkIt is call\ncheckIt in main\ncheckIt invokes assert.equalInt64\n"
        "checkIt arg expected Int64 expected\ncheckIt arg actual Int64 actual\n"
        "checkIt out result TestResult\n"
    )
    codes = {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}
    assert "SS1201" in codes


def test_generated_math_signature_rejects_wrong_slots():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let a immutable Int32 10\nmain let b immutable Int32 2\nmain let okc immutable ExitCode 0\n"
        "main do addCall\nmain return okc\n"
        "addCall is call\naddCall in main\naddCall invokes math.addInt32\n"
        "addCall arg lhs Int32 a\naddCall arg rhs Int32 b\naddCall out q Int32\n"
    )
    codes = {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}
    assert "SS1201" in codes


def test_positional_family_not_flagged():
    # convert.toFloat64's semsig slot is `value`, but the family lowers
    # positionally, so a different slot name (`inputValue`) must not be flagged.
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let n immutable Int64 3\nmain let okc immutable ExitCode 0\n"
        "main do cv\nmain return okc\n"
        "cv is call\ncv in main\ncv invokes convert.toFloat64\n"
        "cv arg inputValue Int64 n\ncv out f Float64\n"
    )
    assert "SS1201" not in {d.code for d in ss.lint(ss.parse(src))}


def test_json_swapped_document_cursor_rejected_at_check():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "JsonDocument is alias\nJsonDocument for Int64\n"
        "JsonCursor is alias\nJsonCursor for Int64\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let doc immutable JsonDocument 1\nmain let cur immutable JsonCursor 2\n"
        "main let keyName immutable String \"id\"\nmain let fieldValue immutable Int64 42\n"
        "main let okc immutable ExitCode 0\nmain do setField\nmain return okc\n"
        "setField is call\nsetField in main\nsetField invokes json.setObjectFieldInt64\n"
        "setField arg document JsonCursor cur\n"
        "setField arg cursor JsonDocument doc\n"
        "setField arg fieldName String keyName\nsetField arg value Int64 fieldValue\n"
        "setField out status Int32\n"
    )
    assert "SS1201" in {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


def test_external_signature_out_type_rejected_at_check():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "JsonDocument is alias\nJsonDocument for Int64\n"
        "JsonCursor is alias\nJsonCursor for Int64\n"
        "JsonCapacityBytes is alias\nJsonCapacityBytes for Int64\n"
        "JsonAccessError is error\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let text immutable String \"{}\"\nmain let cap immutable JsonCapacityBytes 64\n"
        "main let okc immutable ExitCode 0\nmain do parseDoc\nmain return okc\n"
        "parseDoc is call\nparseDoc in main\nparseDoc invokes json.createDocument\n"
        "parseDoc arg jsonText String text\n"
        "parseDoc arg capacityBytes JsonCapacityBytes cap\n"
        "parseDoc out cursor JsonCursor\n"
        "parseDoc catch e JsonAccessError\n"
    )
    errors = [d for d in ss.lint(ss.parse(src)) if d.severity == "error"]
    assert "SS1201" in {d.code for d in errors}
    assert any("signature returns 'JsonDocument'" in d.message for d in errors)


def test_external_signature_catch_type_rejected_at_check():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "JsonDocument is alias\nJsonDocument for Int64\n"
        "JsonCapacityBytes is alias\nJsonCapacityBytes for Int64\n"
        "JsonAccessError is error\n"
        "OtherError is error\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let text immutable String \"{}\"\nmain let cap immutable JsonCapacityBytes 64\n"
        "main let okc immutable ExitCode 0\nmain do parseDoc\nmain return okc\n"
        "parseDoc is call\nparseDoc in main\nparseDoc invokes json.createDocument\n"
        "parseDoc arg jsonText String text\n"
        "parseDoc arg capacityBytes JsonCapacityBytes cap\n"
        "parseDoc out document JsonDocument\n"
        "parseDoc catch e OtherError\n"
    )
    errors = [d for d in ss.lint(ss.parse(src)) if d.severity == "error"]
    assert "SS1201" in {d.code for d in errors}
    assert any("signature raises 'JsonAccessError'" in d.message for d in errors)


def test_log_missing_message_rejected_at_check():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let okc immutable ExitCode 0\nmain do logCall\nmain return okc\n"
        "logCall is call\nlogCall in main\nlogCall invokes log.logInfo\nlogCall out status Int32\n"
    )
    assert "SS1201" in {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


def _http_response_text_source(body_type="String", body_binding="textValue", include_content_type=False):
    content_type_rows = (
        "main let contentType immutable String \"text/plain\"\n"
        "send arg contentType String contentType\n"
        if include_content_type else ""
    )
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "HttpResponse is alias\nHttpResponse for OpaquePointer\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let response immutable HttpResponse 0\nmain let status immutable Int32 200\n"
        f"main let {body_binding} immutable {body_type} "
        f"{'\"ok\"' if body_type == 'String' else '1'}\n"
        "main let okc immutable ExitCode 0\n"
        f"{content_type_rows}"
        "main do send\nmain return okc\n"
        "send is call\nsend in main\nsend invokes http.responseText\n"
        "send arg response HttpResponse response\nsend arg status Int32 status\n"
        f"send arg body {body_type} {body_binding}\n"
        "send out rc Int32\n"
    )


def test_http_response_text_accepts_omitted_optional_content_type():
    codes = {d.code for d in ss.lint(ss.parse(_http_response_text_source()))
             if d.severity == "error"}
    assert "SS1201" not in codes


def test_http_response_text_rejects_opaque_pointer_body_before_codegen():
    src = _http_response_text_source(body_type="OpaquePointer", body_binding="ptr")
    errors = [d for d in ss.lint(ss.parse(src)) if d.severity == "error"]
    assert "SS1201" in {d.code for d in errors}
    assert any("expects 'String'" in d.message for d in errors)


def test_http_sidecar_only_target_is_not_false_green():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let okc immutable ExitCode 0\nmain do routeCall\nmain return okc\n"
        "routeCall is call\nrouteCall in main\nrouteCall invokes http.route\n"
        'routeCall discards "sidecar-only server contract is not lowered directly"\n'
    )
    assert "SS1198" in {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


def _opaque_pointer_call_source(call_rows):
    return (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let ptr immutable OpaquePointer 1\nmain let okc immutable ExitCode 0\n"
        f"{call_rows}"
    )


@pytest.mark.parametrize("call_rows", [
    (
        "main do show\nmain return okc\n"
        "show is call\nshow in main\nshow invokes console.writeLine\n"
        "show arg text OpaquePointer ptr\n"
    ),
    (
        "main do show\nmain return okc\n"
        "show is call\nshow in main\nshow invokes console.writeIntegerLine\n"
        "show arg value OpaquePointer ptr\n"
    ),
    (
        "main do cv\nmain return okc\n"
        "cv is call\ncv in main\ncv invokes convert.to.string\n"
        "cv arg value OpaquePointer ptr\ncv out text String\n"
    ),
])
def test_opaque_pointer_to_string_or_integer_slots_rejected_before_codegen(call_rows):
    src = _opaque_pointer_call_source(call_rows)
    assert "SS1201" in {d.code for d in ss.lint(ss.parse(src)) if d.severity == "error"}


def test_convert_to_string_int64_runs_without_compiler_typeerror():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let n immutable Int64 42\nmain let okc immutable ExitCode 0\n"
        "main do cv\nmain do show\nmain return okc\n"
        "cv is call\ncv in main\ncv invokes convert.toString\n"
        "cv arg value Int64 n\ncv out text String\n"
        "show is call\nshow in main\nshow invokes console.writeLine\n"
        "show arg text String text\n"
    )
    out, err, code = ss._record_run_full(src)
    assert code == 0, err
    assert out.strip() == "42"


def test_json_invalid_document_handle_returns_error_not_segfault():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "JsonAccessError is error\n"
        "JsonDocument is alias\nJsonDocument for Int64\n"
        "JsonCursor is alias\nJsonCursor for Int64\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let badDoc immutable JsonDocument 1\nmain let root immutable JsonCursor 0\n"
        "main let fieldName immutable String \"id\"\nmain let fieldValue immutable Int64 42\n"
        "main let okc immutable ExitCode 0\nmain let failc immutable ExitCode 7\n"
        "main do setField\nmain branch ifError setField goto failed\nmain return okc\n"
        "main at failed return failc\n"
        "setField is call\nsetField in main\nsetField invokes json.setObjectFieldInt64\n"
        "setField arg document JsonDocument badDoc\n"
        "setField arg cursor JsonCursor root\n"
        "setField arg fieldName String fieldName\nsetField arg value Int64 fieldValue\n"
        "setField catch e JsonAccessError\n"
    )
    out, err, code = ss._record_run_full(src)
    assert code == 7, err
    assert out == ""


def test_json_invalid_document_with_bogus_scratch_does_not_access_violate():
    src = (
        "P is project\nP module m\nP target console\nP entry main\n"
        'm is module\nm path a.b\nm purpose "p"\nm invariant "i"\nm exports main\n'
        "ByteCount is alias\nByteCount for Int64\n"
        "JsonDocument is alias\nJsonDocument for OpaquePointer\n"
        "JsonCapacityBytes is alias\nJsonCapacityBytes for Int64\n"
        "JsonText is alias\nJsonText for String\n"
        "ExitCode is alias\nExitCode for Int32\n"
        "main is operation\nmain out ExitCode\nmain async no\nmain purpose \"p\"\nmain invariant \"i\"\n"
        "main let badDoc immutable JsonDocument 1\n"
        "main let cap immutable JsonCapacityBytes 16\n"
        "main let okc immutable ExitCode 0\n"
        "main do allocScratch\nmain defer releaseScratch\n"
        "main do serialize\nmain do show\nmain return okc\n"
        "allocScratch is call\nallocScratch in main\nallocScratch invokes c.malloc\n"
        "allocScratch arg size ByteCount cap\n"
        "allocScratch out scratch OpaquePointer\n"
        "allocScratch catch allocError OpaquePointer\n"
        "allocScratch owns scratch\n"
        "allocScratch cleanedBy releaseScratch\n"
        "releaseScratchWorker is call\nreleaseScratchWorker in main\n"
        "releaseScratchWorker invokes c.free\n"
        "releaseScratchWorker arg resource OpaquePointer scratch\n"
        "releaseScratchWorker discards \"cleanup status ignored\"\n"
        "releaseScratch is cleanup\nreleaseScratch in main\n"
        "releaseScratch call releaseScratchWorker\n"
        "releaseScratch cleans scratch\n"
        "serialize is call\nserialize in main\nserialize invokes json.serializeDocument\n"
        "serialize arg document JsonDocument badDoc\n"
        "serialize arg scratch OpaquePointer scratch\n"
        "serialize arg scratchCapacity JsonCapacityBytes cap\n"
        "serialize out text JsonText\n"
        "show is call\nshow in main\nshow invokes console.writeLine\n"
        "show arg text JsonText text\n"
    )
    out, err, code = ss._record_run_full(src)
    assert code == 0, err
    assert out == "\n"
