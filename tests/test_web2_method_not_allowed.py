#!/usr/bin/env python3
"""WEB-2: a method mismatch returns 405, never 404 — even with no handler.

When a path exists but not for the request method, the dispatcher must return 405
Method Not Allowed (via the typed method-not-allowed handler if registered, else a
plain 405) — not fall through to the 404 not-found path. Previously the 405 branch
was gated on `method_not_allowed_handler != NULL`, so a server without that handler
mislabeled a method mismatch as an unknown route.

The matcher itself (find_compiled_method_mismatch finding the route for a wrong
method) is covered by test_http_route_dispatch (BIN-1); here we pin that the
dispatch loop turns that into a 405 unconditionally.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_C = os.path.join(ROOT, "semanticscript", "runtime", "native_http", "sem_http_runtime.c")


def test_web2_method_mismatch_is_405_without_a_handler():
    src = open(HTTP_C, encoding="utf-8").read()
    # the 405 branch fires on the mismatch alone, not gated by the handler.
    assert "if (find_compiled_method_mismatch(method, path, &request) != NULL) {" in src, \
        "405 branch must trigger on a method mismatch, not require a handler"
    # the handler call is now conditional inside the branch.
    assert "if (config->method_not_allowed_handler != NULL) {" in src
    # and there is a no-handler 405 fallback (not a fall-through to 404).
    assert "if (!handled) {" in src
    # the old handler-gated condition is gone.
    assert ("if (config->method_not_allowed_handler != NULL &&\n"
            "                find_compiled_method_mismatch") not in src
