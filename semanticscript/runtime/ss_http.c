/*
 * ss_http.c — return-value shim over the SemanticScript HTTP runtime.
 *
 * legacy/SemanticScript/runtime/native_http/sem_http_runtime.c is a self-contained
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

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

/* ---- URL / HTML codecs: buffer-managing String adapters over the
 * caller-scratch-buffer legacy entry points (distinct `_str` names so they do
 * not collide with the same-named `ss_http_*` they wrap). ---- */

SS_EXPORT const char *ss_http_url_encode_str(const char *input) {
    size_t n = input ? strlen(input) : 0;
    size_t capacity = n * 3 + 1;  /* worst case every byte -> %XX */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_url_encode(input, buffer, capacity);
    return buffer;
}

SS_EXPORT const char *ss_http_url_decode_str(const char *input) {
    size_t n = input ? strlen(input) : 0;
    size_t capacity = n + 1;  /* decode never grows */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_url_decode(input, buffer, capacity);
    return buffer;
}

SS_EXPORT const char *ss_http_html_escape_str(const char *input) {
    size_t n = input ? strlen(input) : 0;
    int capacity = (int)(n * 6 + 1);  /* worst case ' -> &#39; */
    char *buffer = (char *)malloc((size_t)capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_html_escape(input, buffer, capacity);
    return buffer;
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
SS_EXPORT int ss_http_serve_routes(const char *host, int port, int count,
                                   const char **methods, const char **paths,
                                   void **handlers) {
    if (count <= 0) return -1;
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
