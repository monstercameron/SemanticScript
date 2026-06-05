#!/usr/bin/env python3
"""R-260: a JSON object with a duplicate key is rejected, not silently accepted.

The document parser appended every name:value pair with no duplicate check, so
`{"role":"user","role":"admin"}` resolved to `user` on first-wins lookup but
re-serialized BOTH keys — a privilege-confusion / request-smuggling primitive
when a downstream parser picks the other value. A repeated key is ambiguous, so
parsing now fails closed; well-formed objects with distinct keys are unaffected.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "{runtime}"

int main(void) {
    SSJsonDocument *doc = NULL;

    /* duplicate key -> rejected, no document handed back */
    assert(ss_json_document_create_from_text("{\"role\":\"user\",\"role\":\"admin\"}", 256, &doc) != SS_JSON_OK);
    assert(doc == NULL);

    /* duplicate also rejected when nested */
    assert(ss_json_document_create_from_text("{\"a\":{\"k\":1,\"k\":2}}", 256, &doc) != SS_JSON_OK);
    assert(doc == NULL);

    /* distinct keys parse normally */
    assert(ss_json_document_create_from_text("{\"a\":1,\"b\":2,\"c\":3}", 256, &doc) == SS_JSON_OK);
    assert(doc != NULL);
    int64_t root = ss_json_document_root(doc);
    int64_t b = -1;
    assert(ss_json_navigate_object_field(doc, root, "b", &b) == SS_JSON_OK);
    assert(ss_json_cursor_int64(doc, b, -1) == 2);
    ss_json_document_destroy(doc);

    /* a repeated key value (same name, same value) is still a duplicate name */
    assert(ss_json_document_create_from_text("{\"x\":1,\"x\":1}", 256, &doc) != SS_JSON_OK);

    printf("json-dup-keys: OK\n");
    return 0;
}
'''


def test_duplicate_object_keys_rejected(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native JSON harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_json",
                           "sem_json_runtime.c").replace("\\", "/")
    harness = tmp_path / "harness_json_dupkeys.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "json-dup-keys: OK" in ran.stdout
