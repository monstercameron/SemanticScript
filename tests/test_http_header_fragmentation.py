#!/usr/bin/env python3
"""R-263: a request whose header block is split across TCP segments parses.

handle_client read the header block with a single recv, so headers split across
segments (or simply not delivered in one packet) made find_header_end fail and
the server replied a spurious 400. It now accumulates with a recv loop until the
\\r\\n\\r\\n terminator arrives. This drives handle_client over a real loopback
pair from a server thread while the client sends the request in two pieces with a
gap between them, forcing the first recv to see only a partial header block. A
zeroed config has no routes, so a correctly-parsed request yields 404 — proving
the headers were parsed despite the split (the bug produced 400).
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

#include "{runtime}"

#ifdef _WIN32
#  include <windows.h>
#  define SLEEP_MS(ms) Sleep(ms)
typedef HANDLE thread_t;
#else
#  include <pthread.h>
#  include <unistd.h>
#  define SLEEP_MS(ms) usleep((ms) * 1000)
typedef pthread_t thread_t;
#endif

static ss_socket_t g_server_fd;

#ifdef _WIN32
static DWORD WINAPI server_thread(LPVOID arg) {
#else
static void *server_thread(void *arg) {
#endif
    (void)arg;
    SSHttpServerConfig config;
    memset(&config, 0, sizeof(config));   /* no routes -> unknown path is 404 */
    handle_client(g_server_fd, &config);
    ss_close_socket(g_server_fd);
#ifdef _WIN32
    return 0;
#else
    return NULL;
#endif
}

static int loopback_pair(ss_socket_t *server, ss_socket_t *client) {
    ss_socket_t listener = socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr;
    socklen_t addr_len = sizeof(addr);
    if (listener == SS_INVALID_SOCKET) return 0;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    addr.sin_port = 0;
    if (bind(listener, (struct sockaddr *)&addr, sizeof(addr)) != 0) return 0;
    if (listen(listener, 1) != 0) return 0;
    if (getsockname(listener, (struct sockaddr *)&addr, &addr_len) != 0) return 0;
    *client = socket(AF_INET, SOCK_STREAM, 0);
    if (*client == SS_INVALID_SOCKET) return 0;
    if (connect(*client, (struct sockaddr *)&addr, sizeof(addr)) != 0) return 0;
    *server = accept(listener, NULL, NULL);
    ss_close_socket(listener);
    return *server != SS_INVALID_SOCKET;
}

int main(void) {
    ss_socket_t client;
    if (!ss_platform_net_startup()) { fprintf(stderr, "net startup\n"); return 2; }
    if (!loopback_pair(&g_server_fd, &client)) { fprintf(stderr, "pair\n"); return 2; }

    /* run handle_client on the server end in a thread */
    thread_t th;
#ifdef _WIN32
    th = CreateThread(NULL, 0, server_thread, NULL, 0, NULL);
    assert(th != NULL);
#else
    assert(pthread_create(&th, NULL, server_thread, NULL) == 0);
#endif

    /* send the request in TWO pieces, splitting the header block, with a gap so
     * the server's first recv sees only the first piece. */
    const char *part1 = "GET /nope HTTP/1.1\r\nHost: x\r\nX-Split: ";
    const char *part2 = "yes\r\nConnection: close\r\n\r\n";
    send(client, part1, (int)strlen(part1), 0);
    SLEEP_MS(120);
    send(client, part2, (int)strlen(part2), 0);

    char reply[1024];
    size_t total = 0;
    while (total < sizeof(reply) - 1) {
        int n = (int)recv(client, reply + total, (int)(sizeof(reply) - 1 - total), 0);
        if (n <= 0) break;
        total += (size_t)n;
    }
    reply[total] = '\0';
    ss_close_socket(client);
#ifdef _WIN32
    WaitForSingleObject(th, 2000);
#else
    pthread_join(th, NULL);
#endif

    /* headers were parsed despite the split -> route lookup -> 404 (not a 400
     * header-parse failure). */
    assert(strncmp(reply, "HTTP/1.1 404", 12) == 0);
    printf("header-fragmentation: OK\n");
    return 0;
}
'''


def test_split_header_block_parses_not_400(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native HTTP harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_http",
                           "sem_http_runtime.c").replace("\\", "/")
    platform_time = os.path.join(ROOT, "semanticscript", "runtime", "native_platform",
                                 "ss_platform_time.c").replace("\\", "/")
    harness = tmp_path / "harness_http_frag.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), platform_time, "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    else:
        cmd.append("-lpthread")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe)], capture_output=True, text=True, encoding="utf-8",
                         timeout=30)
    assert ran.returncode == 0, ran.stderr
    assert "header-fragmentation: OK" in ran.stdout
