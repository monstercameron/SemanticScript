"""Shared call and route contract facts for compiler and linter checks.

Keep this module deliberately small: it is for source-of-truth facts that both
`semsc.py` and `semlint.py` need to agree on without importing either tool.
"""

from __future__ import annotations

from typing import Optional


SUPPORTED_HTTP_ROUTE_METHODS: frozenset[str] = frozenset({
    "GET",
    "HEAD",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
})


RESULT_FALLIBLE_CALL_TARGETS: frozenset[str] = frozenset({
    "console.writeLine",
    "console.writeIntegerLine",
    "console.writeInteger",
    "console.writeFloatLine",
    "math.checkedMultiplyI64",
    "sqlite.openDatabase",
    "sqlite.closeDatabase",
    "sqlite.exec",
    "sqlite.prepareStatement",
    "sqlite.finalizeStatement",
    "sqlite.resetStatement",
    "sqlite.stepStatement",
    "sqlite.bindInt64",
    "sqlite.bindDouble",
    "sqlite.bindText",
    "sqlite.bindBlob",
    "sqlite.bindNull",
    "json.createDocument",
    "json.createEmptyDocument",
    "json.serializeDocument",
    "json.objectFieldAt",
    "json.arrayElementAt",
    "json.cursorParent",
    "json.cursorAtPath",
    "json.cursorString",
    "json.cursorArrayLength",
    "json.cursorObjectFieldCount",
    "json.cursorObjectFieldNameAt",
    "json.cursorObjectFieldValueAt",
    "json.setObjectFieldString",
    "json.setObjectFieldInt64",
    "json.setObjectFieldDouble",
    "json.setObjectFieldBool",
    "json.setObjectFieldNull",
    "json.setObjectFieldObject",
    "json.setObjectFieldArray",
    "json.setObjectFieldJsonText",
    "json.appendArrayElementString",
    "json.appendArrayElementInt64",
    "json.appendArrayElementDouble",
    "json.appendArrayElementBool",
    "json.appendArrayElementNull",
    "json.appendArrayElementObject",
    "json.appendArrayElementArray",
    "json.appendArrayElementJsonText",
    "json.insertArrayElementString",
    "json.insertArrayElementInt64",
    "json.insertArrayElementDouble",
    "json.insertArrayElementBool",
    "json.insertArrayElementNull",
    "json.insertArrayElementObject",
    "json.insertArrayElementArray",
    "json.insertArrayElementJsonText",
    "json.replaceArrayElementString",
    "json.replaceArrayElementInt64",
    "json.replaceArrayElementDouble",
    "json.replaceArrayElementBool",
    "json.replaceArrayElementNull",
    "json.replaceArrayElementObject",
    "json.replaceArrayElementArray",
    "json.replaceArrayElementJsonText",
    "json.removeObjectField",
    "json.removeArrayElementAt",
    "json.clearObject",
    "json.clearArray",
})


EXPLICIT_DISPOSITION_FALLIBLE_CALL_TARGETS: frozenset[str] = frozenset({
    "c.fopen",
    "c.freopen",
    "c.fread",
    "c.fwrite",
    "c.fclose",
    "c.fputs",
    "c.fputc",
    "c.putchar",
    "c.fgets",
    "c.fseek",
    "c.ftell",
    "c.open",
    "c.read",
    "c.write",
    "c.close",
    "c.malloc",
    "c.calloc",
    "c.realloc",
    "c.alignedAlloc",
    "c.aligned_alloc",
    "http.responseText",
    "http.responseBytes",
    "http.responseSseEvent",
    "http.responseHeader",
    "http.responseFile",
    "http.ensureDirectory",
})


KNOWN_FALLIBLE_CALL_TARGETS: frozenset[str] = (
    RESULT_FALLIBLE_CALL_TARGETS
    | EXPLICIT_DISPOSITION_FALLIBLE_CALL_TARGETS
)


def normalize_route_method(method: str) -> str:
    return method.upper()


def is_supported_route_method(method: str) -> bool:
    return normalize_route_method(method) in SUPPORTED_HTTP_ROUTE_METHODS


def fallibility_kind(target: str) -> Optional[str]:
    if target in RESULT_FALLIBLE_CALL_TARGETS:
        return "result"
    if target in EXPLICIT_DISPOSITION_FALLIBLE_CALL_TARGETS:
        return "explicitDisposition"
    return None
