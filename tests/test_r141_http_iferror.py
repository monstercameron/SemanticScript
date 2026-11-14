#!/usr/bin/env python3
"""R-141(b): a `catch` on an http.* response writer wires the native status into
`branch ifError`, instead of the old constant-false `err` that silently treated
every SS_HTTP_ERR_* return as success.

The ss_http_* response writers return SS_HTTP_OK (0) on success and a nonzero
SS_HTTP_ERR_* on failure, so the lowering must feed `icmp ne i32 <status>, 0`
into the branch — never `br i1 false`. (The i8* getters, i64 *Length, and the
`valueIsEmpty` predicate are NOT OK==0 channels and intentionally stay unwired;
the json string/cursor-mutation cases remain R-142.)
"""
import importlib

semanticscript = importlib.import_module("semanticscript")


def _ir_for_source(src: str) -> str:
    return str(semanticscript.lower_to_llvm(semanticscript.parse(src)))


SRC = (
    "Demo is project\nDemo module m\nDemo target console\nDemo entry main\n"
    "m is module\nm path demo.x\nm exports main\n"
    'm purpose "exercise a fallible http response writer"\nm invariant "i"\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "httpCap is capability\nhttpCap grants write http.response\n"
    'httpCap purpose "allow response writes"\n'
    "HttpResponseError is error\n"
    "main is operation\nmain out ExitCode\nmain effect write http.response\n"
    "main uses httpCap\nmain async no\n"
    'main purpose "branch on a native http failure"\nmain invariant "i"\n'
    "main let resp immutable HttpResponse 0\n"
    "main let st immutable Int32 200\n"
    'main let payloadText immutable String "x"\n'
    "main let okCode immutable ExitCode 0\nmain let failCode immutable ExitCode 7\n"
    "main do callIt\nmain branch ifError callIt goto failed\nmain return okCode\n"
    "main at failed return failCode\n"
    "callIt is call\ncallIt in main\ncallIt invokes http.responseText\n"
    "callIt arg response HttpResponse resp\n"
    "callIt arg status Int32 st\n"
    "callIt arg body String payloadText\n"
    "callIt out writeStatus Int32\n"
    "callIt catch httpErr HttpResponseError\n"
)


def test_http_response_writer_catch_wires_iferror():
    ir = _ir_for_source(SRC)
    assert "ss_http_response_text" in ir
    assert "icmp ne i32" in ir          # status != 0 feeds the branch
    assert "br i1 false" not in ir      # not the old constant-false err
