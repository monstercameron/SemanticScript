#!/usr/bin/env python3
"""R-254: bcrypt verify accepts all standard setting variants, not just $2b$.

ss_bcrypt_verify hard-rejected any stored hash not starting with $2b$, locking
out imported/interop hashes written as $2a$/$2x$/$2y$ (all valid bcrypt
settings). It now accepts $2a$/$2b$/$2x$/$2y$. For a pure-ASCII password every
variant produces identical hash bytes, so a $2b$ hash with its prefix rewritten
to another variant must still verify — proving the variant is both accepted and
recomputed correctly. An unknown variant ($2z$) is still rejected.
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
#include "../../semanticscript/runtime/native_bcrypt/sem_bcrypt_runtime.h"

int main(void) {
    const char *pw = "hunter2-ascii-pw";
    char hash[SS_BCRYPT_HASH_OUTPUT_SIZE];
    /* cost 6 keeps the test fast; the variant byte is hash[2] */
    assert(ss_bcrypt_hash(pw, 6, hash, sizeof(hash)) == SS_BCRYPT_OK);
    assert(hash[0] == '$' && hash[1] == '2' && hash[2] == 'b' && hash[3] == '$');
    assert(ss_bcrypt_verify(pw, hash) == SS_BCRYPT_MATCH);

    /* rewrite the prefix to each other valid variant — for an ASCII password the
     * hash bytes are identical, so verify must still MATCH (variant accepted). */
    char buf[SS_BCRYPT_HASH_OUTPUT_SIZE];
    const char variants[] = {'a', 'x', 'y'};
    for (int i = 0; i < 3; ++i) {
        memcpy(buf, hash, sizeof(hash));
        buf[2] = variants[i];
        int r = ss_bcrypt_verify(pw, buf);
        assert(r == SS_BCRYPT_MATCH);                 /* accepted + matches */
        /* a wrong password under the same variant is a MISMATCH, not MALFORMED */
        assert(ss_bcrypt_verify("WRONG", buf) == SS_BCRYPT_MISMATCH);
    }

    /* an unknown variant byte is still rejected as malformed */
    memcpy(buf, hash, sizeof(hash));
    buf[2] = 'z';
    assert(ss_bcrypt_verify(pw, buf) == SS_BCRYPT_ERR_MALFORMED);

    printf("bcrypt-variants: OK\n");
    return 0;
}
'''


def test_verify_accepts_all_bcrypt_variants(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native bcrypt harness")
    bc = os.path.join(ROOT, "semanticscript", "runtime", "native_bcrypt")
    plat = os.path.join(ROOT, "semanticscript", "runtime", "native_platform")
    tp = os.path.join(ROOT, "third_party", "bcrypt")
    harness = tmp_path / "harness_bcrypt_variants.c"
    harness.write_text(HARNESS, encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", "-I" + tp,
                      str(harness),
                      os.path.join(bc, "sem_bcrypt_runtime.c"),
                      os.path.join(plat, "ss_platform_entropy.c"),
                      os.path.join(tp, "crypt_blowfish.c"),
                      os.path.join(tp, "crypt_gensalt.c"),
                      "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lbcrypt")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if built.returncode != 0:
        pytest.skip("bcrypt harness link unavailable: " + built.stderr[-200:])
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "bcrypt-variants: OK" in ran.stdout
