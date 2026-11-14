#!/usr/bin/env python3
"""R-264: HTTP cache headers come from a containment-verified handle, not a stat.

build_file_cache_headers ran only the lexical path check, then snprintf'd
"<root>/<rel>" and stat'd it — and stat follows a symlink/junction placed under
the static root, leaking the TARGET's size/mtime through the ETag/Last-Modified
headers even when the byte-serving path (which uses the realpath/handle guard
response_file_within_root) later refuses to send the bytes. It now opens the
file, runs that same containment guard on the open handle, and fstats the
validated handle.

Asserted at the source level (matching the other sem_http_runtime.c tests); the
fix is also behaviorally verified out-of-band: a harness confirms a legitimate
file under the root still yields an ETag + Last-Modified, while a `..` escape and
a missing file are rejected with no headers.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = (ROOT / "semanticscript" / "runtime" / "native_http" / "sem_http_runtime.c").read_text(
    encoding="utf-8")


def _build_cache_headers_body():
    m = re.search(r"static int build_file_cache_headers\(.*?\n\}", _SRC, re.S)
    assert m, "build_file_cache_headers not found"
    return m.group(0)


def test_cache_headers_run_containment_guard_before_metadata():
    body = _build_cache_headers_body()
    # opens the file and validates containment on the open handle before metadata
    assert "fopen(absolute_path" in body
    assert "response_file_within_root(" in body
    assert "fclose(" in body


def test_metadata_reader_is_handle_based_fstat():
    # the metadata reader fstats a handle, not stat's a rebuilt (symlink-followed) path
    m = re.search(r"static int read_file_cache_metadata\(\s*FILE \*file_handle", _SRC)
    assert m, "read_file_cache_metadata should take a FILE* handle"
    reader = re.search(r"static int read_file_cache_metadata\(.*?\n\}", _SRC, re.S).group(0)
    assert "_fstat64(_fileno(" in reader or "fstat(fileno(" in reader
    assert "_stat64(absolute_path" not in reader and "stat(absolute_path" not in reader
