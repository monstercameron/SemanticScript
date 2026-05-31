/*
 * ss_net.c — minimal blocking HTTP/1.1 GET client for the `net.fetchText`
 * intrinsic (APP-RUN-1). Parses an `http://host[:port]/path` URL, performs a
 * GET over a winsock TCP socket, strips the response headers, and returns a
 * heap-owned copy of the body (released by ss_net_free_text). HTTPS/TLS and
 * chunked transfer-encoding are out of scope; the server is expected to reply
 * with a Content-Length body and `Connection: close`.
 */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

static char *ss_net_strdup(const char *s, size_t n) {
    char *p = (char *)malloc(n + 1);
    if (!p) return NULL;
    memcpy(p, s, n);
    p[n] = 0;
    return p;
}

/* Split "http://host[:port]/path" into host, port, path. 0 on success. */
static int ss_net_parse_url(const char *url, char *host, size_t hostcap,
                            int *port, char *path, size_t pathcap) {
    const char *p = url;
    if (strncmp(p, "http://", 7) == 0) {
        p += 7;
    } else if (strncmp(p, "https://", 8) == 0) {
        return -1;  /* TLS not supported */
    }
    const char *slash = strchr(p, '/');
    const char *host_end = slash ? slash : p + strlen(p);
    const char *colon = memchr(p, ':', (size_t)(host_end - p));
    size_t hl;
    if (colon) {
        hl = (size_t)(colon - p);
        *port = atoi(colon + 1);
    } else {
        hl = (size_t)(host_end - p);
        *port = 80;
    }
    if (hl == 0 || hl >= hostcap) return -1;
    memcpy(host, p, hl);
    host[hl] = 0;
    if (slash) {
        if (strlen(slash) >= pathcap) return -1;
        strcpy(path, slash);
    } else {
        strcpy(path, "/");
    }
    return 0;
}

SS_EXPORT char *ss_net_fetch_text(const char *url) {
    if (!url) return NULL;
    char host[256], path[1024];
    int port = 80;
    if (ss_net_parse_url(url, host, sizeof host, &port, path, sizeof path) != 0)
        return NULL;

    static int wsa_started = 0;
    if (!wsa_started) {
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return NULL;
        wsa_started = 1;
    }

    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    char portstr[16];
    snprintf(portstr, sizeof portstr, "%d", port);
    if (getaddrinfo(host, portstr, &hints, &res) != 0) return NULL;

    SOCKET s = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    if (s == INVALID_SOCKET) { freeaddrinfo(res); return NULL; }
    if (connect(s, res->ai_addr, (int)res->ai_addrlen) != 0) {
        closesocket(s);
        freeaddrinfo(res);
        return NULL;
    }
    freeaddrinfo(res);

    char req[1600];
    int reqlen = snprintf(req, sizeof req,
        "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: ss-net/1.0\r\n"
        "Accept: */*\r\nConnection: close\r\n\r\n",
        path, host);
    if (reqlen <= 0 || send(s, req, reqlen, 0) != reqlen) {
        closesocket(s);
        return NULL;
    }

    size_t cap = 4096, len = 0;
    char *buf = (char *)malloc(cap);
    if (!buf) { closesocket(s); return NULL; }
    for (;;) {
        if (len + 2048 + 1 > cap) {
            cap *= 2;
            char *nb = (char *)realloc(buf, cap);
            if (!nb) { free(buf); closesocket(s); return NULL; }
            buf = nb;
        }
        int n = recv(s, buf + len, 2048, 0);
        if (n <= 0) break;
        len += (size_t)n;
    }
    closesocket(s);
    buf[len] = 0;

    /* body starts after the blank line separating headers from content */
    char *sep = strstr(buf, "\r\n\r\n");
    char *body = sep ? sep + 4 : buf;
    char *out = ss_net_strdup(body, strlen(body));
    free(buf);
    return out;  /* heap-owned; released by ss_net_free_text */
}

SS_EXPORT void ss_net_free_text(char *body) {
    if (body) free(body);
}
