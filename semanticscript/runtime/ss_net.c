/*
 * ss_net.c — minimal blocking HTTP/1.1 GET client for the `net.fetchText`
 * intrinsic (APP-RUN-1). Parses an `http://host[:port]/path` URL, performs a
 * GET over a TCP socket, strips the response headers, and returns a
 * heap-owned copy of the body (released by ss_net_free_text). HTTPS/TLS and
 * chunked transfer-encoding are out of scope; chunked responses fail closed
 * rather than exposing wire framing as body text.
 */
#include <ctype.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>
#include <limits.h>
#include "native_platform/ss_platform.h"
#include "ss_runtime_export.h"

#ifdef _WIN32
typedef SOCKET ss_net_socket_t;
typedef int ss_net_socklen_t;
#define SS_NET_INVALID_SOCKET INVALID_SOCKET
static int ss_net_socket_startup(void) {
    static int wsa_started = 0;
    if (!wsa_started) {
        WSADATA wsa;
        if (WSAStartup(MAKEWORD(2, 2), &wsa) != 0) return -1;
        wsa_started = 1;
    }
    return 0;
}
static int ss_net_close_socket(ss_net_socket_t socket) { return closesocket(socket); }
static int ss_net_set_nonblocking(ss_net_socket_t socket, int enabled) {
    u_long mode = enabled ? 1 : 0;
    return ioctlsocket(socket, FIONBIO, &mode);
}
static int ss_net_connect_in_progress(void) {
    int err = WSAGetLastError();
    return err == WSAEWOULDBLOCK || err == WSAEINPROGRESS ||
           err == WSAEALREADY || err == WSAEINVAL;
}
static int ss_net_select_nfds(ss_net_socket_t socket) {
    (void)socket;
    return 0;
}
static int ss_net_set_socket_timeouts(ss_net_socket_t socket, long long timeout_ms) {
    DWORD tv = (DWORD)timeout_ms;
    int ok = 1;
    ok = ok && setsockopt(socket, SOL_SOCKET, SO_RCVTIMEO,
                          (const char *)&tv, sizeof tv) == 0;
    ok = ok && setsockopt(socket, SOL_SOCKET, SO_SNDTIMEO,
                          (const char *)&tv, sizeof tv) == 0;
    return ok ? 0 : -1;
}
#else
typedef int ss_net_socket_t;
typedef socklen_t ss_net_socklen_t;
#define SS_NET_INVALID_SOCKET (-1)
static int ss_net_socket_startup(void) { return 0; }
static int ss_net_close_socket(ss_net_socket_t socket) { return close(socket); }
static int ss_net_set_nonblocking(ss_net_socket_t socket, int enabled) {
    int flags = fcntl(socket, F_GETFL, 0);
    if (flags < 0) return -1;
    flags = enabled ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK);
    return fcntl(socket, F_SETFL, flags);
}
static int ss_net_connect_in_progress(void) {
    return errno == EINPROGRESS || errno == EWOULDBLOCK || errno == EALREADY;
}
static int ss_net_select_nfds(ss_net_socket_t socket) { return socket + 1; }
static int ss_net_set_socket_timeouts(ss_net_socket_t socket, long long timeout_ms) {
    struct timeval tv;
    tv.tv_sec = (long)(timeout_ms / 1000);
    tv.tv_usec = (long)((timeout_ms % 1000) * 1000);
    int ok = 1;
    ok = ok && setsockopt(socket, SOL_SOCKET, SO_RCVTIMEO,
                          &tv, sizeof tv) == 0;
    ok = ok && setsockopt(socket, SOL_SOCKET, SO_SNDTIMEO,
                          &tv, sizeof tv) == 0;
    return ok ? 0 : -1;
}
#endif

typedef struct {
    ss_net_socket_t socket;
    int live;
} ss_net_socket_handle;

/*
 * R-204: net.fetchText returns a heap-owned body as a String-shaped char*. The
 * source type is still String-like, so the runtime must reject freeTextBody on a
 * literal/global string, stale duplicate, or arbitrary pointer before it reaches
 * the CRT allocator. Track only allocations produced by this module's body
 * extraction path; freeing anything else is a safe no-op.
 */
typedef struct { char **items; size_t count; size_t cap; } ss_net_body_registry;

static ss_net_body_registry ss_net_live_bodies;

static int ss_net_track_body(char *body) {
    if (body == NULL) {
        return 0;
    }
    if (ss_net_live_bodies.count == ss_net_live_bodies.cap) {
        size_t next = ss_net_live_bodies.cap == 0 ? 16 : ss_net_live_bodies.cap * 2;
        if (next <= ss_net_live_bodies.cap || next > SIZE_MAX / sizeof(char *)) {
            return 0;
        }
        char **grown = (char **)realloc(ss_net_live_bodies.items,
                                        next * sizeof(char *));
        if (grown == NULL) {
            return 0;
        }
        ss_net_live_bodies.items = grown;
        ss_net_live_bodies.cap = next;
    }
    ss_net_live_bodies.items[ss_net_live_bodies.count++] = body;
    return 1;
}

static int ss_net_body_is_live(const char *body) {
    size_t index;
    for (index = 0; index < ss_net_live_bodies.count; ++index) {
        if (ss_net_live_bodies.items[index] == body) {
            return 1;
        }
    }
    return 0;
}

static int ss_net_untrack_body(char *body) {
    size_t index;
    for (index = 0; index < ss_net_live_bodies.count; ++index) {
        if (ss_net_live_bodies.items[index] == body) {
            ss_net_live_bodies.items[index] =
                ss_net_live_bodies.items[ss_net_live_bodies.count - 1];
            ss_net_live_bodies.count--;
            return 1;
        }
    }
    return 0;
}

static char *ss_net_strdup(const char *s, size_t n) {
    char *p = (char *)malloc(n + 1);
    if (!p) return NULL;
    memcpy(p, s, n);
    p[n] = 0;
    if (!ss_net_track_body(p)) {
        free(p);
        return NULL;
    }
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

#define SS_NET_DEFAULT_TIMEOUT_MS 5000LL
#define SS_NET_MAX_TIMEOUT_MS 0x7fffffffLL
#define SS_NET_DEFAULT_RECEIVE_CAP ((size_t)1024 * 1024)

static long long ss_net_effective_timeout_ms(long long timeout_ms) {
    if (timeout_ms <= 0) {
        return SS_NET_DEFAULT_TIMEOUT_MS;
    }
    if (timeout_ms > SS_NET_MAX_TIMEOUT_MS) {
        return SS_NET_MAX_TIMEOUT_MS;
    }
    return timeout_ms;
}

static int ss_net_connect_with_timeout(ss_net_socket_t sock, const struct sockaddr *addr,
                                       int addrlen, long long timeout_ms) {
    if (ss_net_set_nonblocking(sock, 1) != 0) {
        return -1;
    }

    if (connect(sock, addr, addrlen) == 0) {
        return ss_net_set_nonblocking(sock, 0) == 0 ? 0 : -1;
    }

    if (!ss_net_connect_in_progress()) {
        ss_net_set_nonblocking(sock, 0);
        return -1;
    }

    fd_set write_set;
    fd_set except_set;
    FD_ZERO(&write_set);
    FD_ZERO(&except_set);
    FD_SET(sock, &write_set);
    FD_SET(sock, &except_set);

    struct timeval timeout;
    timeout.tv_sec = (long)(timeout_ms / 1000);
    timeout.tv_usec = (long)((timeout_ms % 1000) * 1000);
    int ready = select(ss_net_select_nfds(sock), NULL, &write_set, &except_set, &timeout);
    if (ready <= 0) {
        ss_net_set_nonblocking(sock, 0);
        return -1;
    }

    int so_error = 0;
    ss_net_socklen_t so_error_len = (ss_net_socklen_t)sizeof so_error;
    if (getsockopt(sock, SOL_SOCKET, SO_ERROR, (char *)&so_error,
                   &so_error_len) != 0 || so_error != 0) {
        ss_net_set_nonblocking(sock, 0);
        return -1;
    }

    return ss_net_set_nonblocking(sock, 0) == 0 ? 0 : -1;
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

static int ss_net_sockaddr_is_private(const struct sockaddr *addr) {
    if (addr == NULL) {
        return 1;
    }
    if (addr->sa_family == AF_INET) {
        const struct sockaddr_in *in = (const struct sockaddr_in *)addr;
        uint32_t ip = ntohl(in->sin_addr.s_addr);
        uint32_t first = (ip >> 24) & 0xffu;
        uint32_t second = (ip >> 16) & 0xffu;
        if (first == 0 || first == 10 || first == 127 || first >= 224) {
            return 1;
        }
        if (first == 100 && second >= 64 && second <= 127) {
            return 1;
        }
        if (first == 169 && second == 254) {
            return 1;
        }
        if (first == 172 && second >= 16 && second <= 31) {
            return 1;
        }
        if (first == 192 && second == 168) {
            return 1;
        }
        return 0;
    }
    if (addr->sa_family == AF_INET6) {
        const struct sockaddr_in6 *in6 = (const struct sockaddr_in6 *)addr;
        const unsigned char *b = (const unsigned char *)&in6->sin6_addr;
        int all_zero = 1;
        size_t i;
        for (i = 0; i < 16; ++i) {
            if (b[i] != 0) {
                all_zero = 0;
                break;
            }
        }
        if (all_zero) {
            return 1;
        }
        if (b[0] == 0 && b[1] == 0 && b[2] == 0 && b[3] == 0 &&
                b[4] == 0 && b[5] == 0 && b[6] == 0 && b[7] == 0 &&
                b[8] == 0 && b[9] == 0 && b[10] == 0 && b[11] == 0 &&
                b[12] == 0 && b[13] == 0 && b[14] == 0 && b[15] == 1) {
            return 1;
        }
        if ((b[0] & 0xfeu) == 0xfcu) {
            return 1;  /* unique-local fc00::/7 */
        }
        if (b[0] == 0xfeu && (b[1] & 0xc0u) == 0x80u) {
            return 1;  /* link-local fe80::/10 */
        }
        if (b[0] == 0xffu) {
            return 1;  /* multicast */
        }
    }
    return 0;
}

static int ss_net_parse_endpoint(const char *endpoint, char *host, size_t hostcap,
                                 char *port, size_t portcap) {
    if (endpoint == NULL || hostcap == 0 || portcap == 0) {
        return -1;
    }
    const char *p = endpoint;
    if (strncmp(p, "tcp://", 6) == 0) {
        p += 6;
    }
    const char *host_start = p;
    const char *host_end = NULL;
    const char *port_start = NULL;
    if (*p == '[') {
        const char *rb = strchr(p, ']');
        if (rb == NULL || rb == p + 1 || rb[1] != ':') {
            return -1;
        }
        host_start = p + 1;
        host_end = rb;
        port_start = rb + 2;
    } else {
        const char *colon = strrchr(p, ':');
        if (colon == NULL || colon == p) {
            return -1;
        }
        host_end = colon;
        port_start = colon + 1;
    }
    if (port_start == NULL || *port_start == 0) {
        return -1;
    }
    char *endp = NULL;
    long pv = strtol(port_start, &endp, 10);
    if (*endp != 0 || pv < 1 || pv > 65535) {
        return -1;
    }
    size_t hlen = (size_t)(host_end - host_start);
    size_t plen = strlen(port_start);
    if (hlen == 0 || hlen >= hostcap || plen == 0 || plen >= portcap) {
        return -1;
    }
    memcpy(host, host_start, hlen);
    host[hlen] = 0;
    memcpy(port, port_start, plen + 1);
    return 0;
}

SS_EXPORT void *ss_net_connect(const char *endpoint) {
    if (ss_net_socket_startup() != 0) return NULL;
    char host[256];
    char port[16];
    if (ss_net_parse_endpoint(endpoint, host, sizeof host, port, sizeof port) != 0) {
        return NULL;
    }
    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(host, port, &hints, &res) != 0) return NULL;

    ss_net_socket_t s = SS_NET_INVALID_SOCKET;
    struct addrinfo *ai;
    for (ai = res; ai != NULL; ai = ai->ai_next) {
        s = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (s == SS_NET_INVALID_SOCKET) {
            continue;
        }
        if (ss_net_connect_with_timeout(s, ai->ai_addr, (int)ai->ai_addrlen,
                                        SS_NET_DEFAULT_TIMEOUT_MS) == 0) {
            break;
        }
        ss_net_close_socket(s);
        s = SS_NET_INVALID_SOCKET;
    }
    freeaddrinfo(res);
    if (s == SS_NET_INVALID_SOCKET) return NULL;
    ss_net_set_socket_timeouts(s, SS_NET_DEFAULT_TIMEOUT_MS);

    ss_net_socket_handle *handle =
        (ss_net_socket_handle *)calloc(1, sizeof(ss_net_socket_handle));
    if (handle == NULL) {
        ss_net_close_socket(s);
        return NULL;
    }
    handle->socket = s;
    handle->live = 1;
    return handle;
}

SS_EXPORT long long ss_net_send(void *socket_handle, const char *payload) {
    ss_net_socket_handle *handle = (ss_net_socket_handle *)socket_handle;
    if (handle == NULL || !handle->live || payload == NULL) {
        return -1;
    }
    size_t len = strlen(payload);
    size_t sent = 0;
    while (sent < len) {
        int n = send(handle->socket, payload + sent, (int)(len - sent), 0);
        if (n <= 0) {
            return -1;
        }
        sent += (size_t)n;
    }
    return (long long)sent;
}

SS_EXPORT char *ss_net_receive(void *socket_handle) {
    ss_net_socket_handle *handle = (ss_net_socket_handle *)socket_handle;
    if (handle == NULL || !handle->live) {
        return NULL;
    }
    size_t cap = 256;
    size_t len = 0;
    char *buf = (char *)malloc(cap);
    if (buf == NULL) {
        return NULL;
    }
    for (;;) {
        if (len + 256 + 1 > cap) {
            size_t ncap = cap * 2;
            if (ncap > SS_NET_DEFAULT_RECEIVE_CAP + 1) {
                ncap = SS_NET_DEFAULT_RECEIVE_CAP + 1;
            }
            if (ncap <= cap) {
                free(buf);
                return NULL;
            }
            char *grown = (char *)realloc(buf, ncap);
            if (grown == NULL) {
                free(buf);
                return NULL;
            }
            buf = grown;
            cap = ncap;
        }
        int n = recv(handle->socket, buf + len, 256, 0);
        if (n == 0) {
            break;
        }
        if (n < 0) {
            free(buf);
            return NULL;
        }
        len += (size_t)n;
        if (len > SS_NET_DEFAULT_RECEIVE_CAP) {
            free(buf);
            return NULL;
        }
    }
    buf[len] = 0;
    char *out = ss_net_strdup(buf, len);
    free(buf);
    return out;
}

SS_EXPORT int ss_net_close(void *socket_handle) {
    ss_net_socket_handle *handle = (ss_net_socket_handle *)socket_handle;
    if (handle == NULL) {
        return 0;
    }
    int closed = 0;
    if (handle->live) {
        closed = ss_net_close_socket(handle->socket) == 0 ? 1 : 0;
        handle->live = 0;
    }
    free(handle);
    return closed;
}

/* R-092: the high-level signature's HttpRequestPolicy (timeoutMillis, maxBodyBytes,
 * redirectLimit) is now passed through and enforced. `redirect_limit` is accepted
 * but trivially honored: this client never follows redirects (a 3xx body is
 * returned as-is), so 0 redirects are followed <= any non-negative limit. A value
 * of 0 for timeout/max_body means "use the built-in default/hard cap".
 * allow_private is compiler-proven from an exact loopback/private capability with
 * a rationale; otherwise DNS answers resolving to private/link-local/loopback
 * ranges are skipped to close the DNS-rebinding half of R-078. */
SS_EXPORT char *ss_net_fetch_text(const char *url, long long timeout_ms,
                                  long long max_body_bytes,
                                  long long redirect_limit,
                                  long long allow_private) {
    (void)redirect_limit;
    if (!url) return NULL;
    char host[256], path[1024];
    int port = 80;
    if (ss_net_parse_url(url, host, sizeof host, &port, path, sizeof path) != 0)
        return NULL;

    if (ss_net_socket_startup() != 0) return NULL;

    struct addrinfo hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    char portstr[16];
    snprintf(portstr, sizeof portstr, "%d", port);
    if (getaddrinfo(host, portstr, &hints, &res) != 0) return NULL;

    long long effective_timeout_ms = ss_net_effective_timeout_ms(timeout_ms);
    ss_net_socket_t s = SS_NET_INVALID_SOCKET;
    struct addrinfo *ai;
    for (ai = res; ai != NULL; ai = ai->ai_next) {
        if (!allow_private && ss_net_sockaddr_is_private(ai->ai_addr)) {
            continue;
        }
        s = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
        if (s == SS_NET_INVALID_SOCKET) {
            continue;
        }
        if (ss_net_connect_with_timeout(s, ai->ai_addr, (int)ai->ai_addrlen,
                                        effective_timeout_ms) == 0) {
            break;
        }
        ss_net_close_socket(s);
        s = SS_NET_INVALID_SOCKET;
    }
    freeaddrinfo(res);
    if (s == SS_NET_INVALID_SOCKET) return NULL;

    /* R-092: enforce the policy/default timeout on every transport phase.
     * connect() uses nonblocking select(), and SO_RCVTIMEO/SO_SNDTIMEO bound
     * send() and recv() so a slow/stalled peer can't hang the call forever. */
    ss_net_set_socket_timeouts(s, effective_timeout_ms);

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
        ss_net_close_socket(s);
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
    if (!buf) { ss_net_close_socket(s); return NULL; }
    for (;;) {
        if (len + 2048 + 1 > cap) {
            size_t ncap = cap * 2;
            /* never grow far past the response cap (+slack for the final NUL) */
            if (ncap > resp_cap + 2048 + 1) ncap = resp_cap + 2048 + 1;
            if (ncap <= cap) { free(buf); ss_net_close_socket(s); return NULL; }
            char *nb = (char *)realloc(buf, ncap);
            if (!nb) { free(buf); ss_net_close_socket(s); return NULL; }
            buf = nb;
            cap = ncap;
        }
        int n = recv(s, buf + len, 2048, 0);
        if (n == 0) break;                 /* peer closed -> body complete */
        if (n < 0) {                       /* R-092: timeout/error -> fail closed */
            free(buf); ss_net_close_socket(s); return NULL;
        }
        len += (size_t)n;
        if (len > resp_cap) {              /* R-092: over the policy/hard limit */
            free(buf); ss_net_close_socket(s); return NULL;
        }
    }
    ss_net_close_socket(s);
    buf[len] = 0;

    char *out = ss_net_response_body_from_wire(buf);
    free(buf);
    return out;  /* heap-owned; released by ss_net_free_text */
}

SS_EXPORT void ss_net_free_text(char *body) {
    if (body == NULL || !ss_net_body_is_live(body) || !ss_net_untrack_body(body)) {
        return;
    }
    free(body);
}
