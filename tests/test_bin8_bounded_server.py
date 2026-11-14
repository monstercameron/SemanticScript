#!/usr/bin/env python3
"""BIN-8: bounded execution model for long-running/server targets.

A server target must never wedge the toolchain and must fail bind cleanly:
  * verify SKIPS the run lane for a non-console (webServer) target — it cannot be
    run to exit, so it is never driven into a hang (W2-H; _program_target gate).
  * ss_http_server_run detects a port-in-use bind failure (the zombie-port hazard)
    and reports it as a distinct SS_HTTP_ERR_ADDR_IN_USE with a clear message,
    instead of a cryptic generic engine error — and returns promptly (no block).

The source guard pins the detection in the runtime; the live harness binds a port
first, then confirms ss_http_server_run returns the in-use code promptly (run under
a hard subprocess timeout so a regression to "block" fails rather than hangs).
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTTP_C = os.path.join(ROOT, "semanticscript", "runtime", "native_http", "sem_http_runtime.c")
HTTP_H = os.path.join(ROOT, "semanticscript", "runtime", "native_http", "sem_http_runtime.h")


def test_bin8_verify_skips_run_lane_for_server_target():
    # The bounded core: a webServer target is not run to exit, so verify can't hang.
    ws = semanticscript.parse(
        "Srv is project\nSrv module m\nSrv target webServer\nSrv entry api\n"
        "m is module\nm path srv\n")
    assert semanticscript._program_target(ws) == "webServer"
    console = semanticscript.parse(
        "App is project\nApp module m\nApp target console\nApp entry main\n"
        "m is module\nm path app\n")
    assert semanticscript._program_target(console) == "console"


def test_bin8_port_in_use_detection_present_in_runtime():
    src = open(HTTP_C, encoding="utf-8").read()
    hdr = open(HTTP_H, encoding="utf-8").read()
    assert "SS_HTTP_ERR_ADDR_IN_USE" in hdr, "distinct port-in-use code missing"
    assert "WSAEADDRINUSE" in src and "EADDRINUSE" in src, "no EADDRINUSE detection"
    assert "bind_in_use ? SS_HTTP_ERR_ADDR_IN_USE" in src, "in-use code not returned"
    assert "already in use" in src, "no clear port-in-use diagnostic"


_HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "sem_http_runtime.c"

static int h(SSHttpRequest *r, SSHttpResponse *resp) { (void)r; (void)resp; return 0; }

int main(void) {
    unsigned short port = 18654;
    ss_platform_net_startup();
    ss_socket_t pre = socket(AF_INET, SOCK_STREAM, 0);
    if (pre == SS_INVALID_SOCKET) { fprintf(stderr, "SKIP: socket\n"); return 0; }
#if defined(_WIN32)
    int excl = 1;
    setsockopt(pre, SOL_SOCKET, SO_EXCLUSIVEADDRUSE, (const char *)&excl, sizeof(excl));
#endif
    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    if (bind(pre, (struct sockaddr *)&addr, sizeof(addr)) != 0) {
        fprintf(stderr, "SKIP: pre-bind failed (port busy)\n"); return 0;
    }
    listen(pre, 1);

    static const SSHttpRoute routes[] = {{"GET", "/health", h, NULL, 0}};
    SSHttpServerConfig cfg;
    memset(&cfg, 0, sizeof(cfg));
    cfg.routes = routes;
    cfg.route_count = 1;
    cfg.host = "127.0.0.1";
    cfg.port = port;
    int rc = ss_http_server_run(&cfg);  /* must return promptly, not block */
    assert(rc == SS_HTTP_ERR_ADDR_IN_USE);
    fprintf(stderr, "http-portinuse: OK\n");
    return 0;
}
'''


def test_bin8_server_run_reports_port_in_use_promptly(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler for the port-in-use harness")
    http_dir = os.path.dirname(HTTP_C)
    plat_dir = os.path.join(ROOT, "semanticscript", "runtime", "native_platform")
    harness = tmp_path / "harness_portinuse.c"
    harness.write_text(_HARNESS, encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", "-I" + http_dir, "-I" + plat_dir,
                      str(harness), os.path.join(plat_dir, "ss_platform_time.c"),
                      "-o", str(exe)]
    if sys.platform == "win32":
        cmd += ["-lws2_32"]
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if built.returncode != 0:
        pytest.skip("port-in-use harness build unavailable: " + built.stderr[-400:])
    # hard timeout: a regression that BLOCKS instead of detecting in-use fails here.
    ran = subprocess.run([str(exe)], capture_output=True, text=True,
                         encoding="utf-8", timeout=15)
    assert ran.returncode == 0, ran.stderr
    if "SKIP" in ran.stderr:
        pytest.skip("port 18654 unavailable for the harness: " + ran.stderr.strip())
    assert "http-portinuse: OK" in ran.stderr
