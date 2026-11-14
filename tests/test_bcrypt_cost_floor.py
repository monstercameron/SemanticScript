#!/usr/bin/env python3
"""R-256: bcrypt has an enforced production cost floor + a no-cost-arg default.

`ss_bcrypt_hash` accepts the full bcrypt FORMAT range (cost 4..31) so verify-side
re-derivation and fast tests keep working — but cost 4 is weak-by-omission for
credential storage. The production surface must refuse a below-floor cost and
offer a default that has no cost argument to mis-set:

  * ss_bcrypt_hash_checked rejects cost < SS_BCRYPT_SAFE_MIN_COST with
    SS_BCRYPT_ERR_WEAK_COST (before any hashing), and succeeds at/above it.
  * ss_bcrypt_hash_default hashes at SS_BCRYPT_DEFAULT_COST (12) with no cost arg.
  * the low-level ss_bcrypt_hash still accepts the format floor (4) unchanged.
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

    /* below the enforced production floor: refused BEFORE hashing, with a code
     * distinct from a generic config error so the caller can tell why. */
    assert(SS_BCRYPT_SAFE_MIN_COST > SS_BCRYPT_MIN_COST);
    assert(ss_bcrypt_hash_checked(pw, SS_BCRYPT_MIN_COST, hash, sizeof(hash))
           == SS_BCRYPT_ERR_WEAK_COST);
    assert(ss_bcrypt_hash_checked(pw, SS_BCRYPT_SAFE_MIN_COST - 1, hash, sizeof(hash))
           == SS_BCRYPT_ERR_WEAK_COST);

    /* the no-cost-arg default hashes at the recommended production cost (12). */
    char dflt[SS_BCRYPT_HASH_OUTPUT_SIZE];
    assert(ss_bcrypt_hash_default(pw, dflt, sizeof(dflt)) == SS_BCRYPT_OK);
    assert(strncmp(dflt, "$2b$12$", 7) == 0);
    /* the default must verify against itself (it is a real, usable hash). */
    assert(ss_bcrypt_verify(pw, dflt) == SS_BCRYPT_MATCH);

    /* the low-level primitive is unchanged: the format floor (4) still hashes. */
    assert(ss_bcrypt_hash(pw, SS_BCRYPT_MIN_COST, hash, sizeof(hash)) == SS_BCRYPT_OK);
    assert(strncmp(hash, "$2b$04$", 7) == 0);

    printf("bcrypt-cost-floor: OK\n");
    return 0;
}
'''


def test_bcrypt_hash_rejects_cost_below_safe_floor(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native bcrypt harness")
    bc = os.path.join(ROOT, "semanticscript", "runtime", "native_bcrypt")
    plat = os.path.join(ROOT, "semanticscript", "runtime", "native_platform")
    tp = os.path.join(ROOT, "third_party", "bcrypt")
    harness = tmp_path / "harness_bcrypt_cost_floor.c"
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
    assert "bcrypt-cost-floor: OK" in ran.stdout
