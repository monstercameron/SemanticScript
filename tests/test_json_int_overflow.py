#!/usr/bin/env python3
"""R-262: a JSON integer that overflows int64 is rejected, not silently lossy.

parse_json_number fell back to strtod on strtoll ERANGE, so an integer literal
above int64 max became a lossy double node and a later cursor_int64 returned a
corrupted value with no signal. An integer literal that can't be represented as
int64 is now rejected (fail-closed, matching the double-overflow case and the
runtime's other unrepresentable-input rejections). In-range integers and genuine
doubles are unaffected.
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

static int reads_int(const char *json, long long *out) {
    SSJsonDocument *doc = NULL;
    if (ss_json_document_create_from_text(json, 256, &doc) != SS_JSON_OK) {
        return 0;  /* rejected */
    }
    int64_t root = ss_json_document_root(doc);
    int64_t n = -1;
    int ok = (ss_json_navigate_object_field(doc, root, "n", &n) == SS_JSON_OK);
    if (ok) *out = ss_json_cursor_int64(doc, n, -999);
    ss_json_document_destroy(doc);
    return ok ? 1 : -1;
}

int main(void) {
    long long v = 0;

    /* int64 max parses exactly */
    assert(reads_int("{\"n\":9223372036854775807}", &v) == 1);
    assert(v == 9223372036854775807LL);

    /* int64 min parses exactly */
    assert(reads_int("{\"n\":-9223372036854775808}", &v) == 1);
    assert(v == (-9223372036854775807LL - 1));

    /* a small in-range integer is fine */
    assert(reads_int("{\"n\":42}", &v) == 1 && v == 42);

    /* overflow (> int64 max) is REJECTED, not a lossy double */
    assert(reads_int("{\"n\":99999999999999999999}", &v) == 0);
    /* underflow (< int64 min) likewise */
    assert(reads_int("{\"n\":-99999999999999999999}", &v) == 0);

    /* a genuine double is still accepted (not an integer-form literal) */
    SSJsonDocument *doc = NULL;
    assert(ss_json_document_create_from_text("{\"n\":1.5}", 256, &doc) == SS_JSON_OK);
    ss_json_document_destroy(doc);
    assert(ss_json_document_create_from_text("{\"n\":1e10}", 256, &doc) == SS_JSON_OK);
    ss_json_document_destroy(doc);

    printf("json-int-overflow: OK\n");
    return 0;
}
'''


def test_int64_overflow_rejected(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native JSON harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_json",
                           "sem_json_runtime.c").replace("\\", "/")
    harness = tmp_path / "harness_json_int_overflow.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "json-int-overflow: OK" in ran.stdout
