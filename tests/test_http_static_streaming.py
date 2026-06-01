#!/usr/bin/env python3
"""R-211: static files stream to the socket in fixed-size chunks.

ss_http_response_file (the public http.responseFile helper) reads the whole file
into response->owned_body before sending, so serving many large static assets
spikes heap. The static-route dispatch now calls serve_static_file_streamed,
which emits an identical header block (Content-Length = the real file size,
ETag/Last-Modified/Cache-Control preserved) and then copies the body straight
from the file to the socket SS_HTTP_STATIC_STREAM_CHUNK bytes at a time.

This drives the real C function over a 127.0.0.1 loopback socket pair against a
file larger than the chunk size, so a multi-chunk body is exercised end to end:
the status line, Content-Length, and every body byte must match, a HEAD reply
must carry the headers but no body, and a missing file must self-reply 404.
"""
import os
import subprocess
import sys

import pytest

import importlib
semanticscript = importlib.import_module("semanticscript")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

HARNESS = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "{runtime}"

/* Bind a 127.0.0.1 listener on an ephemeral port, connect a client, accept the
 * server end. Returns 0 on success, filling *server and *client. */
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

/* Read everything the peer sends until it closes (EOF). */
static size_t recv_all(ss_socket_t s, char *out, size_t cap) {
    size_t total = 0;
    while (total < cap) {
        int n = (int)recv(s, out + total, (int)(cap - total), 0);
        if (n <= 0) break;
        total += (size_t)n;
    }
    return total;
}

static const char *header_end(const char *buf, size_t len) {
    for (size_t i = 0; i + 3 < len; ++i) {
        if (memcmp(buf + i, "\r\n\r\n", 4) == 0) return buf + i + 4;
    }
    return NULL;
}

#define ASSET_BYTES 150000  /* > SS_HTTP_STATIC_STREAM_CHUNK so the body spans chunks */

static void write_asset(const char *dir) {
    char path[1024];
    snprintf(path, sizeof(path), "%s/asset.bin", dir);
    FILE *f = fopen(path, "wb");
    assert(f != NULL);
    for (int i = 0; i < ASSET_BYTES; ++i) {
        unsigned char b = (unsigned char)((i * 31 + 7) & 0xFF);
        fputc(b, f);
    }
    fclose(f);
}

/* Drive the PUBLIC ss_http_response_file over a fresh socket pair, exactly as
 * the server dispatch does: bind a backend whose socket is the server end, then
 * read the raw reply from the client end. *started_out reports whether the
 * response was committed to the socket (backend.stream_started). */
static int serve(const char *root, const char *relative, int head_only,
                 char *out, size_t cap, size_t *out_len, int *started_out) {
    ss_socket_t server, client;
    SSHttpResponse response;
    SSHttpResponseBackend backend;
    int rc;
    if (!loopback_pair(&server, &client)) return -100;
    memset(&response, 0, sizeof(response));
    memset(&backend, 0, sizeof(backend));
    backend.socket_handle = server;
    response.backend_response = &backend;
    response.head_only = head_only;
    rc = ss_http_response_file(&response, 200, root, relative);
    ss_close_socket(server);  /* signal EOF so recv_all on the client returns */
    *out_len = recv_all(client, out, cap);
    *started_out = backend.stream_started;
    ss_close_socket(client);
    clear_owned_response(&response);
    return rc;
}

int main(int argc, char **argv) {
    assert(argc >= 2);
    const char *dir = argv[1];
    char reply[ASSET_BYTES + 4096];
    size_t reply_len;
    int rc, started;

    if (!ss_http_client_winsock_ready()) { fprintf(stderr, "winsock\n"); return 2; }
    write_asset(dir);

    /* GET over a socket: a multi-chunk body, fully and exactly delivered, never
     * buffered into response.owned_body. */
    rc = serve(dir, "asset.bin", 0, reply, sizeof(reply), &reply_len, &started);
    assert(rc == SS_HTTP_OK);
    assert(started == 1);
    assert(strncmp(reply, "HTTP/1.1 200 ", 13) == 0);
    assert(strstr(reply, "\r\nContent-Length: 150000\r\n") != NULL);
    const char *body = header_end(reply, reply_len);
    assert(body != NULL);
    size_t body_len = reply_len - (size_t)(body - reply);
    assert(body_len == ASSET_BYTES);
    for (int i = 0; i < ASSET_BYTES; ++i) {
        unsigned char want = (unsigned char)((i * 31 + 7) & 0xFF);
        assert((unsigned char)body[i] == want);
    }

    /* HEAD: same Content-Length, no body bytes. */
    rc = serve(dir, "asset.bin", 1, reply, sizeof(reply), &reply_len, &started);
    assert(rc == SS_HTTP_OK);
    assert(started == 1);
    assert(strstr(reply, "\r\nContent-Length: 150000\r\n") != NULL);
    body = header_end(reply, reply_len);
    assert(body != NULL);
    assert(reply_len - (size_t)(body - reply) == 0);

    /* Missing file: NOTHING is sent and the response is left uncommitted, so a
     * handler can still write its own error body (taskforge-web's JSON 404). */
    rc = serve(dir, "missing.bin", 0, reply, sizeof(reply), &reply_len, &started);
    assert(rc != SS_HTTP_OK);
    assert(started == 0);
    assert(reply_len == 0);

    /* Buffered fallback: with no socket backend the public API still works,
     * filling response.body (the path callers without a server rely on). */
    {
        SSHttpResponse response;
        memset(&response, 0, sizeof(response));
        rc = ss_http_response_file(&response, 200, dir, "asset.bin");
        assert(rc == SS_HTTP_OK);
        assert(response.body != NULL);
        assert(response.body_length == ASSET_BYTES);
        for (int i = 0; i < ASSET_BYTES; ++i) {
            unsigned char want = (unsigned char)((i * 31 + 7) & 0xFF);
            assert((unsigned char)response.body[i] == want);
        }
        clear_owned_response(&response);
    }

    printf("static-streaming: OK\n");
    return 0;
}
'''


def test_static_file_streams_multichunk_body(tmp_path):
    cc = semanticscript._find_c_compiler()
    if cc is None:
        pytest.skip("no C compiler available for native HTTP streaming harness")
    runtime = os.path.join(ROOT, "semanticscript", "runtime", "native_http",
                           "sem_http_runtime.c").replace("\\", "/")
    harness = tmp_path / "harness_http_static_streaming.c"
    harness.write_text(HARNESS.replace("{runtime}", runtime), encoding="utf-8")
    exe = tmp_path / ("harness.exe" if sys.platform == "win32" else "harness")
    cmd = list(cc) + ["-std=c11", str(harness), "-o", str(exe)]
    if sys.platform == "win32":
        cmd.append("-lws2_32")
    built = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert built.returncode == 0, built.stderr
    ran = subprocess.run([str(exe), str(tmp_path)], capture_output=True,
                         text=True, encoding="utf-8")
    assert ran.returncode == 0, ran.stderr
    assert "static-streaming: OK" in ran.stdout
