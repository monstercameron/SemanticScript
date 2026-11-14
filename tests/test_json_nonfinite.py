#!/usr/bin/env python3
"""R-261: the JSON serializer never emits the invalid tokens `inf`/`nan`.

JSON has no representation for non-finite doubles, but the serializer formatted
every double with `%.17g` unconditionally, so an infinity/NaN produced literal
`inf`/`-inf`/`nan` — malformed JSON that breaks any conforming parser downstream.
Non-finite doubles now serialize to `null` (matches JS JSON.stringify), valid
JSON, on every path (stringify, builder field/element, document node serialize).
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
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "{runtime}"

int main(void) {
    char scratch[64];
    const char *out = NULL;

    /* standalone double stringify (R-261 site) */
    assert(ss_json_stringify_double(INFINITY, scratch, (int64_t)sizeof(scratch), &out) == SS_JSON_OK);
    assert(out != NULL && strcmp(out, "null") == 0);
    assert(ss_json_stringify_double(-INFINITY, scratch, (int64_t)sizeof(scratch), &out) == SS_JSON_OK);
    assert(strcmp(out, "null") == 0);
    assert(ss_json_stringify_double(NAN, scratch, (int64_t)sizeof(scratch), &out) == SS_JSON_OK);
    assert(strcmp(out, "null") == 0);
    /* a finite double still round-trips normally */
    assert(ss_json_stringify_double(2.5, scratch, (int64_t)sizeof(scratch), &out) == SS_JSON_OK);
    assert(strcmp(out, "2.5") == 0);

    /* document node serialize path: a non-finite field becomes null, and the
     * whole document stays valid JSON (no `inf`/`nan` substring). */
    SSJsonDocument *doc = NULL;
    assert(ss_json_document_create_empty(4096, SS_JSON_NODE_OBJECT, &doc) == SS_JSON_OK);
    int64_t root = ss_json_document_root(doc);
    assert(ss_json_set_object_field_double(doc, root, "x", INFINITY) == SS_JSON_OK);
    assert(ss_json_set_object_field_double(doc, root, "y", 1.5) == SS_JSON_OK);
    char big[256];
    const char *ser = NULL;
    assert(ss_json_document_serialize(doc, big, (int64_t)sizeof(big), &ser) == SS_JSON_OK);
    assert(ser != NULL);
    assert(strstr(ser, "inf") == NULL && strstr(ser, "nan") == NULL);
    assert(strstr(ser, "null") != NULL);   /* x serialized as null */
    assert(strstr(ser, "1.5") != NULL);    /* y intact */
    ss_json_document_destroy(doc);

    printf("json-nonfinite: OK\n");
    return 0;
}
'''


def test_serializer_emits_null_for_non_finite_doubles(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native JSON harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_json",
                           "sem_json_runtime.c").replace("\\", "/")
    harness = tmp_path / "harness_json_nonfinite.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "json-nonfinite: OK" in ran.stdout
