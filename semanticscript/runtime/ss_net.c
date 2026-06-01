/*
 * ss_net.c — minimal blocking HTTP/1.1 GET client for the `net.fetchText`
 * intrinsic (APP-RUN-1). Parses an `http://host[:port]/path` URL, performs a
 * GET over a winsock TCP socket, strips the response headers, and returns a
 * heap-owned copy of the body (released by ss_net_free_text). HTTPS/TLS and
 * chunked transfer-encoding are out of scope; chunked responses fail closed
 * rather than exposing wire framing as body text.
 */
#include <winsock2.h>
#include <ws2tcpip.h>
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "ss_runtime_export.h"

static char *ss_net_strdup(const char *s, size_t n) {
    char *p = (char *)malloc(n + 1);
    if (!p) return NULL;
    memcpy(p, s, n);
    p[n] = 0;
    return p;
}

static int ss_net_ascii_case_equal_n(const char *left, const char *right, size_t length) {
    size_t index;
    for (index = 0; index < length; ++index) {
        unsigned char left_ch = (unsigned char)left[index];
        unsigned char right_ch = (unsigned char)right[index];
        if (tolower(left_ch) != tolower(right_ch)) {
            return 0;
        }
    }
    return 1;
}

static int ss_net_is_ows(char ch) {
    return ch == ' ' || ch == '\t';
}

static int ss_net_header_value_has_token(
    const char *value,
    size_t value_length,
    const char *token
) {
    const char *scan = value;
    const char *end = value + value_length;
    size_t token_length = strlen(token);
    while (scan < end) {
        while (scan < end && (*scan == ',' || ss_net_is_ows(*scan))) {
            ++scan;
        }
        const char *token_start = scan;
        while (scan < end && *scan != ',') {
            ++scan;
        }
        const char *token_end = scan;
        while (token_end > token_start && ss_net_is_ows(token_end[-1])) {
            --token_end;
        }
        if ((size_t)(token_end - token_start) == token_length &&
                ss_net_ascii_case_equal_n(token_start, token, token_length)) {
            return 1;
        }
        if (scan < end && *scan == ',') {
            ++scan;
        }
    }
    return 0;
}

static int ss_net_headers_have_chunked_transfer_encoding(
    const char *headers,
    size_t headers_length
) {
    const char *scan = headers;
    const char *end = headers + headers_length;
    const char *header_name = "Transfer-Encoding";
    size_t header_name_length = strlen(header_name);
    while (scan < end) {
        const char *line_end = scan;
        while (line_end < end && *line_end != '\r' && *line_end != '\n') {
            ++line_end;
        }
        const char *colon = memchr(scan, ':', (size_t)(line_end - scan));
        if (colon != NULL) {
            const char *name_start = scan;
            const char *name_end = colon;
            while (name_end > name_start && ss_net_is_ows(name_end[-1])) {
                --name_end;
            }
            if ((size_t)(name_end - name_start) == header_name_length &&
                    ss_net_ascii_case_equal_n(name_start, header_name, header_name_length)) {
                const char *value_start = colon + 1;
                while (value_start < line_end && ss_net_is_ows(*value_start)) {
                    ++value_start;
                }
                if (ss_net_header_value_has_token(
                        value_start, (size_t)(line_end - value_start), "chunked")) {
                    return 1;
                }
            }
        }
        scan = line_end;
        while (scan < end && (*scan == '\r' || *scan == '\n')) {
            ++scan;
        }
    }
    return 0;
}

static char *ss_net_response_body_from_wire(const char *response) {
    if (response == NULL) {
        return NULL;
    }
    char *separator = strstr(response, "\r\n\r\n");
    if (separator != NULL && ss_net_headers_have_chunked_transfer_encoding(
            response, (size_t)(separator - response))) {
        return NULL;
    }
    char *body = separator != NULL ? separator + 4 : (char *)response;
    return ss_net_strdup(body, strlen(body));
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
    /* R-172: the authority (host[:port]) ends at the first '/', '?' or '#' —
     * NOT just '/'. Previously a query-only URL ("host?q=1") folded the query
     * into the host and lost it. */
    const char *auth_end = p;
    while (*auth_end && *auth_end != '/' && *auth_end != '?' && *auth_end != '#') {
        ++auth_end;
    }
    /* R-166: strict port — digits only, in 1..65535, no trailing junk
     * (atoi accepted "8080junk", ":", "-5", out-of-range). */
    size_t hl;
    const char *host_start = p;
    const char *port_str = NULL;  /* points just past the ':' if a port is given */
    if (*p == '[') {
        /* R-186: bracketed IPv6 literal "[addr]" / "[addr]:port". The colon
         * inside the brackets is part of the address, not a port separator, so
         * a bare memchr(':') would split it wrong. The host stored for
         * getaddrinfo is the address WITHOUT the brackets. */
        const char *rb = memchr(p, ']', (size_t)(auth_end - p));
        if (rb == NULL || rb == p + 1) return -1;  /* no close bracket / empty */
        host_start = p + 1;
        hl = (size_t)(rb - host_start);
        const char *after = rb + 1;
        if (after < auth_end) {
            if (*after != ':') return -1;          /* junk after ']' */
            port_str = after + 1;
        }
    } else {
        const char *colon = memchr(p, ':', (size_t)(auth_end - p));
        if (colon) {
            hl = (size_t)(colon - p);
            port_str = colon + 1;
        } else {
            hl = (size_t)(auth_end - p);
        }
    }
    if (port_str != NULL) {
        char *endp = NULL;
        long pv = strtol(port_str, &endp, 10);
        if (port_str == auth_end || endp != auth_end || pv < 1 || pv > 65535) {
            return -1;
        }
        *port = (int)pv;
    } else {
        *port = 80;
    }
    if (hl == 0 || hl >= hostcap) return -1;
    memcpy(host, host_start, hl);
    host[hl] = 0;
    /* R-172: build the request target from auth_end with the fragment
     * ('#'...) stripped (fragments are client-only and must not be sent). A
     * query-only URL yields "/?q"; an empty/fragment-only tail yields "/". */
    const char *target = auth_end;
    const char *frag = strchr(target, '#');
    size_t tlen = frag ? (size_t)(frag - target) : strlen(target);
    if (tlen == 0) {
        if (pathcap < 2) return -1;
        strcpy(path, "/");
    } else if (*target == '?') {
        if (tlen + 2 > pathcap) return -1;  /* leading '/' + tail + NUL */
        path[0] = '/';
        memcpy(path + 1, target, tlen);
        path[tlen + 1] = 0;
    } else {  /* starts with '/' */
        if (tlen + 1 > pathcap) return -1;
        memcpy(path, target, tlen);
        path[tlen] = 0;
    }
    return 0;
}

/* R-092: the high-level signature's HttpRequestPolicy (timeoutMillis, maxBodyBytes,
 * redirectLimit) is now passed through and enforced. `redirect_limit` is accepted
 * but trivially honored: this client never follows redirects (a 3xx body is
 * returned as-is), so 0 redirects are followed <= any non-negative limit. A value
 * of 0 for timeout/max_body means "use the built-in default/hard cap". */
SS_EXPORT char *ss_net_fetch_text(const char *url, long long timeout_ms,
                                  long long max_body_bytes,
                                  long long redirect_limit) {
    (void)redirect_limit;
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

    /* R-092: enforce the policy timeout on the data phases. SO_RCVTIMEO/SO_SNDTIMEO
     * bound send() and recv() so a slow/stalled peer can't hang the call forever
     * (the connect() above still uses the OS default). On timeout recv() returns
     * an error, which the read loop treats as fail-closed (NULL). */
    if (timeout_ms > 0) {
        DWORD tv = (DWORD)(timeout_ms > 0x7fffffffLL ? 0x7fffffffLL : timeout_ms);
        setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char *)&tv, sizeof tv);
        setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char *)&tv, sizeof tv);
    }

    char req[1600];
    int reqlen = snprintf(req, sizeof req,
        "GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: ss-net/1.0\r\n"
        "Accept: */*\r\nConnection: close\r\n\r\n",
        path, host);
    /* R-140: snprintf returns the would-be length; a long host/path truncates
     * (reqlen >= sizeof req). Sending `reqlen` bytes then reads past the buffer,
     * so reject truncation outright. */
    if (reqlen <= 0 || reqlen >= (int)sizeof req
            || send(s, req, reqlen, 0) != reqlen) {
        closesocket(s);
        return NULL;
    }

    /* R-140/R-092: bound the response so a large/hostile peer can't grow the
     * buffer without limit (DoS). The policy's maxBodyBytes caps it when set;
     * otherwise a 64 MiB hard limit applies (the headers are included in this
     * budget — the body is sliced out afterward). A response that exceeds the cap,
     * or any recv timeout/error, fails closed (NULL) rather than returning a
     * truncated or partial body. */
    const size_t SS_NET_HARD_CAP = (size_t)64 * 1024 * 1024;
    size_t resp_cap = SS_NET_HARD_CAP;
    if (max_body_bytes > 0 && (size_t)max_body_bytes < resp_cap) {
        resp_cap = (size_t)max_body_bytes;
    }
    size_t cap = 4096, len = 0;
    char *buf = (char *)malloc(cap);
    if (!buf) { closesocket(s); return NULL; }
    for (;;) {
        if (len + 2048 + 1 > cap) {
            size_t ncap = cap * 2;
            /* never grow far past the response cap (+slack for the final NUL) */
            if (ncap > resp_cap + 2048 + 1) ncap = resp_cap + 2048 + 1;
            if (ncap <= cap) { free(buf); closesocket(s); return NULL; }
            char *nb = (char *)realloc(buf, ncap);
            if (!nb) { free(buf); closesocket(s); return NULL; }
            buf = nb;
            cap = ncap;
        }
        int n = recv(s, buf + len, 2048, 0);
        if (n == 0) break;                 /* peer closed -> body complete */
        if (n < 0) {                       /* R-092: timeout/error -> fail closed */
            free(buf); closesocket(s); return NULL;
        }
        len += (size_t)n;
        if (len > resp_cap) {              /* R-092: over the policy/hard limit */
            free(buf); closesocket(s); return NULL;
        }
    }
    closesocket(s);
    buf[len] = 0;

    char *out = ss_net_response_body_from_wire(buf);
    free(buf);
    return out;  /* heap-owned; released by ss_net_free_text */
}

SS_EXPORT void ss_net_free_text(char *body) {
    if (body) free(body);
}
