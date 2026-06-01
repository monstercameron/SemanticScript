/*
 * ss_http.c — return-value shim over the SemanticScript HTTP runtime.
 *
 * native_http/sem_http_runtime.c (ported into this runtime tree) is a self-contained
 * HTTP runtime (its h2o binding is optional and OFF here) providing both a socket
 * server and a family of pure request/response/url/session helpers. The legacy
 * semsc.py reached it through compiler-owned `http.*` intrinsics; semanticscript
 * keeps it out of the compiler (README ss26/ss34) and binds it through the generic
 * `body runtimeBinding <symbol>` seam, with `std/standard.http.sem` owning the
 * typed contract.
 *
 * Only the helpers that need ADAPTING live here. The pure same-signature
 * helpers (now_millis, session expiry math) and the request-path accessor are
 * bound straight to their legacy `ss_http_*` entry points by the stdlib, so they
 * are not re-shimmed. The URL/HTML codecs DO need a shim: the legacy entry points
 * take a caller scratch buffer, so the `*_str` adapters here allocate a
 * right-sized buffer and hand the EAV side a plain String. (The buffer is owned
 * by the returned String; demo programs are short-lived.)
 */

#include "sem_http_runtime.h"
#include <stdlib.h>
#include <string.h>
#include <stdint.h>  /* SIZE_MAX for the codec overflow guards (R-144) */

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

/* ---- URL / HTML codecs: buffer-managing String adapters over the
 * caller-scratch-buffer legacy entry points (distinct `_str` names so they do
 * not collide with the same-named `ss_http_*` they wrap). ---- */

/* R-144: the worst-case expansion multipliers below (3x url-encode, 6x
 * html-escape) can overflow size_t for a pathological input. Refuse to allocate
 * (return NULL, the fallible "could not build" signal) rather than wrap to a
 * too-small buffer and let the codec write past it. */
SS_EXPORT const char *ss_http_url_encode_str(const char *input) {
    size_t n = input ? strlen(input) : 0;
    if (n > (SIZE_MAX - 1) / 3) return 0;
    size_t capacity = n * 3 + 1;  /* worst case every byte -> %XX */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_url_encode(input, buffer, capacity);
    return buffer;
}

SS_EXPORT const char *ss_http_url_decode_str(const char *input) {
    size_t n = input ? strlen(input) : 0;
    if (n == SIZE_MAX) return 0;
    size_t capacity = n + 1;  /* decode never grows */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_url_decode(input, buffer, capacity);
    return buffer;
}

SS_EXPORT const char *ss_http_html_escape_str(const char *input) {
    size_t n = input ? strlen(input) : 0;
    /* worst case ' -> &#39' (6x). Guard the multiply AND the int the legacy
     * entry point takes, so a large capacity can't truncate to a small/negative
     * int and under-size the buffer. */
    if (n > (SIZE_MAX - 1) / 6) return 0;
    size_t capacity = n * 6 + 1;
    if (capacity > 0x7fffffffu) return 0;  /* must fit the int param below */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_html_escape(input, buffer, (int)capacity);
    return buffer;
}

/* R-136: free a buffer returned by ss_http_url_encode_str / ss_http_url_decode_str
 * / ss_http_html_escape_str. These are malloc'd INSIDE this runtime library, so
 * they must be released by this library's free() — the JIT/host may link a
 * different CRT heap, and freeing across heaps corrupts memory on Windows. The
 * html.render lowering calls this to release each escaped-hole buffer after it has
 * been concatenated in. */
SS_EXPORT void ss_http_free_str(const char *buffer) {
    if (buffer) free((void *)buffer);
}

/* ---- request-value probes (renamed off the legacy `request_value_*`) ---- */

SS_EXPORT long long ss_http_value_length(const char *value) {
    return ss_http_request_value_length(value);
}

SS_EXPORT int ss_http_value_is_empty(const char *value) {
    return ss_http_request_value_is_empty(value);
}

SS_EXPORT int ss_http_ensure_directory(const char *directory_path) {
    return ss_http_filesystem_ensure_directory(directory_path);
}

/* ---- server loop + request/response (WS3-017) ---- */

/* A handler is an EAV operation lowered as int(request, response) — its JIT/
 * native function pointer is passed straight through as an SSHttpHandler. */
SS_EXPORT int ss_http_serve(const char *host, int port, const char *method,
                            const char *path, SSHttpHandler handler) {
    SSHttpRoute route;
    route.method = method;
    route.path = path;
    route.handler = handler;
    route.middleware = 0;
    SSHttpServerConfig config;
    memset(&config, 0, sizeof(config));
    config.host = host;
    config.port = (unsigned short)port;
    config.routes = &route;
    config.route_count = 1;
    return ss_http_server_run(&config);  /* blocks until SIGINT/SIGTERM */
}

SS_EXPORT int ss_http_respond(void *response, int status, const char *body) {
    return ss_http_response_text((SSHttpResponse *)response, status, body, "text/plain");
}

/* A fixed handler + serve entry so an EAV program can stand up a real HTTP
 * server without passing an EAV operation as a C function pointer: GET <path>
 * replies 200 text/plain with a recognizable body. Proves the socket server,
 * routing, and request/response path end-to-end (WS3-017). Blocks until signal. */
static int ss_http_ok_handler(SSHttpRequest *request, SSHttpResponse *response) {
    (void)request;
    return ss_http_response_text(response, 200, "EAV HTTP OK 42", "text/plain");
}

SS_EXPORT int ss_http_serve_static(const char *host, int port, const char *path) {
    SSHttpRoute route;
    route.method = "GET";
    route.path = path;
    route.handler = ss_http_ok_handler;
    route.middleware = 0;
    SSHttpServerConfig config;
    memset(&config, 0, sizeof(config));
    config.host = host;
    config.port = (unsigned short)port;
    config.routes = &route;
    config.route_count = 1;
    return ss_http_server_run(&config);  /* blocks until SIGINT/SIGTERM */
}

SS_EXPORT int ss_http_server_shutting_down(void) {
    return ss_http_server_is_shutting_down();
}

/* APP-RUN-5: multi-route server entry for the `webServer` codegen target. The
 * lowered webServer entity passes parallel method/path/handler arrays (handlers
 * are the JIT-lowered `int(request,response)` functions reinterpreted as
 * SSHttpHandler); this assembles the route table + SSHttpServerConfig and blocks
 * in ss_http_server_run until SIGINT/SIGTERM. */
/* R-147: must match the compiler's _WEBSERVER_MAX_ROUTES. The source lane caps
 * the route count, but the shim re-checks defensively so a hand-rolled or fuzzed
 * caller cannot drive an unbounded allocation through the ABI. */
#define SS_HTTP_MAX_ROUTES 1024

SS_EXPORT int ss_http_serve_routes(const char *host, int port, int count,
                                   const char **methods, const char **paths,
                                   void **handlers) {
    /* Reject a non-positive or over-cap count up front: the cap keeps the
     * (size_t)count * sizeof(SSHttpRoute) product far below SIZE_MAX (no overflow
     * even on a 32-bit size_t) and bounds the allocation. */
    if (count <= 0 || count > SS_HTTP_MAX_ROUTES) return -1;
    SSHttpRoute *routes = (SSHttpRoute *)malloc((size_t)count * sizeof(SSHttpRoute));
    if (!routes) return -1;
    for (int i = 0; i < count; i++) {
        routes[i].method = methods[i];
        routes[i].path = paths[i];
        routes[i].handler = (SSHttpHandler)handlers[i];
        routes[i].middleware = 0;
    }
    SSHttpServerConfig config;
    memset(&config, 0, sizeof(config));
    config.host = host;
    config.port = (unsigned short)port;
    config.routes = routes;
    config.route_count = (size_t)count;
    int r = ss_http_server_run(&config);  /* blocks until SIGINT/SIGTERM */
    free(routes);
    return r;
}
