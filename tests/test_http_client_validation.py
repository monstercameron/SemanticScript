#!/usr/bin/env python3
"""R-184: the outbound HTTP client validates request fields and status lines.

ss_http_client_fetch formats caller-supplied method/path/host/header_line into
the request, so a CR/LF in any of them would inject headers or split the request
(request smuggling). It now rejects CR/LF in every such field (reusing the R-183
ss_http_header_value_ok guard) and parses the response status line strictly
(HTTP/1.0|1.1 SP 3-digit 100..599) instead of "first space then atoi".

Source-level guard (the outbound client needs a live socket peer, exercised
end-to-end by the taskforge-api-client app via test_apps; the injection/parse
logic is checked here against the C source).
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "semanticscript", "runtime", "native_http",
                   "sem_http_runtime.c")


def _fetch_body():
    src = open(SRC, encoding="utf-8").read()
    m = re.search(r"const char \*ss_http_client_fetch\(.*?\n\}", src, re.S)
    assert m, "ss_http_client_fetch not found"
    return m.group(0)


def test_outbound_request_fields_reject_crlf_injection():
    body = _fetch_body()
    # every caller-supplied field that lands in the request must be CR/LF-checked
    for field in ("method", "path", "host", "header_line"):
        assert f"ss_http_header_value_ok({field})" in body, field


def test_outbound_status_line_strictly_validated():
    body = _fetch_body()
    # strict prefix + 3-digit code, not a loose atoi after the first space
    assert '"HTTP/1.1 ", 9' in body and '"HTTP/1.0 ", 9' in body
    assert "response[9] >= '1' && response[9] <= '5'" in body
    assert "atoi(status_space" not in body  # the loose parse is gone
