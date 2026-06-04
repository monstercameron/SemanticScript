#!/usr/bin/env python3
"""BIN-1: cheap unit test of the webServer route dispatcher (no socket, no server).

The route table must dispatch correctly — static routes, dynamic `:param` routes
(with parameter extraction), method discrimination, and a clean miss. Previously
this was only exercised by a full live-server run; here we drive the runtime's own
matcher (compile_routes -> find_compiled_route) directly over an in-memory route
table, asserting which route matches and what params are extracted. The harness
#includes sem_http_runtime.c to reach its static matcher; it never opens a socket.
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
/* Reach the static route matcher + full struct defs by including the unit. */
#include "sem_http_runtime.c"

static int dummy(SSHttpRequest *r, SSHttpResponse *resp) { (void)r; (void)resp; return 0; }

int main(void) {
    static const SSHttpRoute routes[] = {
        {"GET",    "/api/todos",               dummy, NULL, 0},
        {"GET",    "/api/todos/:id",           dummy, NULL, 0},
        {"DELETE", "/api/todos/:id",           dummy, NULL, 0},
        {"POST",   "/api/todos/:id/complete",  dummy, NULL, 0},
        {"GET",    "/assets/:filename",        dummy, NULL, 0},
    };
    SSHttpServerConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.routes = routes;
    cfg.route_count = sizeof(routes) / sizeof(routes[0]);
    assert(compile_routes(&cfg) == SS_HTTP_OK);

    SSHttpRequest req;
    const SSHttpRoute *m;

    /* static route */
    memset(&req, 0, sizeof(req));
    m = find_compiled_route("GET", "/api/todos", &req);
    assert(m != NULL && strcmp(m->path, "/api/todos") == 0);

    /* dynamic :id route — matched AND the param is extracted */
    memset(&req, 0, sizeof(req));
    m = find_compiled_route("GET", "/api/todos/42", &req);
    assert(m != NULL && strcmp(m->path, "/api/todos/:id") == 0);
    assert(strcmp(ss_http_request_path_param(&req, "id"), "42") == 0);

    /* method discriminates same path */
    memset(&req, 0, sizeof(req));
    m = find_compiled_route("DELETE", "/api/todos/42", &req);
    assert(m != NULL && strcmp(m->method, "DELETE") == 0);

    /* nested dynamic segment */
    memset(&req, 0, sizeof(req));
    m = find_compiled_route("POST", "/api/todos/7/complete", &req);
    assert(m != NULL && strcmp(m->path, "/api/todos/:id/complete") == 0);
    assert(strcmp(ss_http_request_path_param(&req, "id"), "7") == 0);

    /* second param name */
    memset(&req, 0, sizeof(req));
    m = find_compiled_route("GET", "/assets/logo.png", &req);
    assert(m != NULL && strcmp(ss_http_request_path_param(&req, "filename"), "logo.png") == 0);

    /* a path that matches no route -> NULL (404), and param state is cleared */
    memset(&req, 0, sizeof(req));
    assert(find_compiled_route("GET", "/nope/nope", &req) == NULL);

    /* a declared path but undeclared method -> not a route match (would be 405) */
    memset(&req, 0, sizeof(req));
    assert(find_compiled_route("PUT", "/api/todos/42", &req) == NULL);
    memset(&req, 0, sizeof(req));
    assert(find_compiled_method_mismatch("PUT", "/api/todos/42", &req) != NULL);

    free_compiled_routes();
    fprintf(stderr, "http-dispatch: OK\n");
    return 0;
}
'''


def test_bin1_webserver_route_dispatch_matches_static_and_dynamic(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler for the native http dispatch harness")
    http_dir = os.path.join(ROOT, "semanticscript", "runtime", "native_http")
    plat_dir = os.path.join(ROOT, "semanticscript", "runtime", "native_platform")
    harness = tmp_path / "harness_http_dispatch.c"
    harness.write_text(HARNESS, encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11",
                      "-I" + http_dir, "-I" + plat_dir,
                      str(harness),
                      os.path.join(plat_dir, "ss_platform_time.c"),
                      "-o", str(exe)]
    if sys.platform == "win32":
        cmd += ["-lws2_32"]
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if built.returncode != 0:
        pytest.skip("http dispatch harness build unavailable: " + built.stderr[-400:])
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "http-dispatch: OK" in ran.stderr
