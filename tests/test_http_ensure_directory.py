#!/usr/bin/env python3
"""R-030: ss_http_filesystem_ensure_directory creates nested directories.

It previously created only a single level, so a nested output path (logs/2026/06)
failed unless every parent already existed, and it swallowed EEXIST without
checking the existing entry is actually a directory. It now walks the path
(mkdir -p), and EEXIST is accepted only when the entry is a directory — an
existing plain file blocking a path segment is an error, not a silent success.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>

#include "{runtime}"

static int is_dir(const char *p) {
#ifdef _WIN32
    DWORD a = GetFileAttributesA(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
#else
    struct stat st;
    return stat(p, &st) == 0 && S_ISDIR(st.st_mode);
#endif
}

int main(int argc, char **argv) {
    assert(argc >= 2);
    char nested[1024];
    snprintf(nested, sizeof(nested), "%s/a/b/c", argv[1]);
    /* nested creation: every parent is made, not just the leaf */
    assert(ss_http_filesystem_ensure_directory(nested) == SS_HTTP_OK);
    assert(is_dir(nested));
    /* idempotent: an existing directory tree is fine */
    assert(ss_http_filesystem_ensure_directory(nested) == SS_HTTP_OK);
    /* a plain file blocking a path segment is an error, not a silent success */
    char filepath[1024];
    snprintf(filepath, sizeof(filepath), "%s/afile", argv[1]);
    FILE *f = fopen(filepath, "wb");
    assert(f != NULL);
    fputc('x', f);
    fclose(f);
    char blocked[1024];
    snprintf(blocked, sizeof(blocked), "%s/afile/sub", argv[1]);
    assert(ss_http_filesystem_ensure_directory(blocked) != SS_HTTP_OK);
    printf("ensure_directory: OK\n");
    return 0;
}
'''


def test_ensure_directory_creates_nested_and_rejects_file_segment(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native HTTP harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_http",
                           "sem_http_runtime.c").replace("\\", "/")
    platform_time = os.path.join(ROOT, "semanticscript", "runtime", "native_platform",
                                 "ss_platform_time.c").replace("\\", "/")
    harness = tmp_path / "harness_ensure_dir.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), platform_time, "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe), str(tmp_path).replace("\\", "/")],
                         capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "ensure_directory: OK" in ran.stdout
