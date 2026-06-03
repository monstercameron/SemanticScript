#!/usr/bin/env python3
"""R-267: the ss_libc printf shims are literal-format-only (uncontrolled-format-string defense).

ss_c_printf/ss_c_fprintf/ss_c_snprintf forwarded an app-controlled `format`
straight to v*printf, so if user data reached the format position the attacker
controlled the format string (%s/%x/%p info-leak, %n arbitrary write). The EAV
`c.printf` binding already requires a constant format (SS3088), but the C shim
is the last line of defense and had none.

The shims now refuse any `%n`-bearing format (the memory-WRITE primitive) before
calling v*printf, and ss_c_print_str is the %s-safe path that prints a dynamic
string as DATA — directives inside it are emitted literally, never interpreted.
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
#include <stdint.h>
#include <string.h>

/* ss_libc.c is compiled alongside with -DSS_RUNTIME_STATIC, so SS_EXPORT is
 * empty and these plain externs match the definitions exactly. */
int ss_c_printf(const char *format, ...);
int ss_c_snprintf(long long buffer, long long size, const char *format, ...);
int ss_c_print_str(const char *text);

int main(void) {
    /* a %n-bearing format is the arbitrary-write primitive: every shim refuses
     * it (returns -1) BEFORE reaching v*printf, so no memory write occurs. The
     * flags/width/length modifiers between % and n must not hide it. */
    assert(ss_c_printf("%n") == -1);
    assert(ss_c_printf("pre %n post") == -1);
    assert(ss_c_printf("%-10.5n") == -1);
    char nbuf[64];
    assert(ss_c_snprintf((long long)(intptr_t)nbuf, (long long)sizeof(nbuf), "x%nx") == -1);

    /* %% is a literal percent, not a conversion: still allowed. */
    assert(ss_c_printf("100%% complete\n") >= 0);

    /* the %s-safe path prints user/attacker text VERBATIM — the directives in it
     * are emitted literally, proving they are treated as data, not a format. */
    const char *attack = "%s%x%p%d-LITERAL-%%";
    FILE *cap = freopen("ssc_fmt_capture.txt", "w", stdout);
    assert(cap != NULL);
    int wrote = ss_c_print_str(attack);
    fflush(stdout);
    assert(wrote >= 0);

    FILE *rd = fopen("ssc_fmt_capture.txt", "rb");
    assert(rd != NULL);
    char got[128];
    size_t got_n = fread(got, 1, sizeof(got) - 1, rd);
    got[got_n] = '\0';
    fclose(rd);
    /* byte-for-byte the input: no %s/%x/%p/%d was interpreted. */
    assert(strcmp(got, attack) == 0);

    fprintf(stderr, "c-printf-format: OK\n");
    return 0;
}
'''


def test_c_printf_user_format_does_not_interpret_directives(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native ss_libc harness")
    rt = os.path.join(ROOT, "semanticscript", "runtime")
    harness = tmp_path / "harness_c_printf.c"
    harness.write_text(HARNESS, encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", "-DSS_RUNTIME_STATIC",
                      "-D_CRT_SECURE_NO_WARNINGS",
                      str(harness),
                      os.path.join(rt, "ss_libc.c"),
                      "-o", str(exe)]
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if built.returncode != 0:
        pytest.skip("ss_libc harness build unavailable: " + built.stderr[-300:])
    ran = subprocess.run([str(exe)], cwd=str(tmp_path),
                         capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "c-printf-format: OK" in ran.stderr
