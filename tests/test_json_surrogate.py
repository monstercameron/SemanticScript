#!/usr/bin/env python3
"""R-259: a \\uD83D\\uDE00 surrogate pair decodes to the real astral code point.

decode_unicode_escape emitted U+FFFD for any code point in D800..DFFF with no
look-ahead, so an astral escape (emoji, CJK ext, math alphanumerics) became two
replacement characters — silent data loss. A high surrogate immediately followed
by a \\uXXXX low surrogate is now combined into the code point and emitted as
4-byte UTF-8; a lone/unpaired surrogate still becomes U+FFFD. Covers both the
find-string path and the document parse+cursor path.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# U+1F600 GRINNING FACE -> F0 9F 98 80
HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "{runtime}"

int main(void) {
    char scratch[64];

    /* find-string path: a surrogate pair becomes the 4-byte astral UTF-8 */
    const char *s = ss_json_find_string("{\"k\":\"\\uD83D\\uDE00\"}", "k",
                                        scratch, sizeof(scratch));
    assert(s != NULL);
    assert(strcmp(s, "\xF0\x9F\x98\x80") == 0);          /* U+1F600, not 2x FFFD */
    assert(strlen(s) == 4);

    /* a BMP escape still decodes normally (regression) */
    s = ss_json_find_string("{\"k\":\"\\u0041\"}", "k", scratch, sizeof(scratch));
    assert(s != NULL && strcmp(s, "A") == 0);

    /* a lone high surrogate (no low) falls back to U+FFFD */
    s = ss_json_find_string("{\"k\":\"\\uD83Dx\"}", "k", scratch, sizeof(scratch));
    assert(s != NULL && strcmp(s, "\xEF\xBF\xBD" "x") == 0);

    /* document parse + cursor path emits the same 4-byte astral UTF-8 */
    SSJsonDocument *doc = NULL;
    assert(ss_json_document_create_from_text("{\"k\":\"\\uD83D\\uDE00\"}", 256, &doc) == SS_JSON_OK);
    int64_t root = ss_json_document_root(doc);
    int64_t k = -1;
    assert(ss_json_navigate_object_field(doc, root, "k", &k) == SS_JSON_OK);
    char vbuf[32];
    const char *vout = NULL;
    assert(ss_json_cursor_string(doc, k, vbuf, sizeof(vbuf), &vout) == SS_JSON_OK);
    assert(vout != NULL && strcmp(vout, "\xF0\x9F\x98\x80") == 0);
    ss_json_document_destroy(doc);

    printf("json-surrogate: OK\n");
    return 0;
}
'''


def test_surrogate_pairs_decode_to_astral_codepoint(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native JSON harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_json",
                           "sem_json_runtime.c").replace("\\", "/")
    harness = tmp_path / "harness_json_surrogate.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "json-surrogate: OK" in ran.stdout
