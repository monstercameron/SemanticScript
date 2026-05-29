/*
 * eav_http.c — return-value shim over the SemanticScript HTTP runtime for eavc.
 *
 * SemanticScript/runtime/native_http/sem_http_runtime.c is a self-contained HTTP
 * runtime (its h2o binding is optional and OFF here) providing both a socket
 * server and a family of pure request/response/url/session helpers. semsc.py
 * reaches it through compiler-owned `http.*` intrinsics; eav keeps it out of the
 * compiler (README ss26/ss34) and binds it through the generic
 * `body runtimeBinding <symbol>` seam, with `std/standard.http.sem` owning the
 * typed contract.
 *
 * This shim exposes the pure, side-effect-light helpers (URL/HTML codec, session
 * expiry math, value probes) as plain `args -> single return` functions. The
 * `ss_http_url_*`/`html_escape` entry points take a caller scratch buffer; the
 * shim allocates a right-sized buffer so the EAV side just receives a String.
 * (The buffer is owned by the returned String; demo programs are short-lived.)
 */

#include "sem_http_runtime.h"
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#define EAV_EXPORT __declspec(dllexport)
#else
#define EAV_EXPORT __attribute__((visibility("default")))
#endif

EAV_EXPORT const char *eav_http_url_encode(const char *input) {
    size_t n = input ? strlen(input) : 0;
    size_t capacity = n * 3 + 1;  /* worst case every byte -> %XX */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_url_encode(input, buffer, capacity);
    return buffer;
}

EAV_EXPORT const char *eav_http_url_decode(const char *input) {
    size_t n = input ? strlen(input) : 0;
    size_t capacity = n + 1;  /* decode never grows */
    char *buffer = (char *)malloc(capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_url_decode(input, buffer, capacity);
    return buffer;
}

EAV_EXPORT const char *eav_http_html_escape(const char *input) {
    size_t n = input ? strlen(input) : 0;
    int capacity = (int)(n * 6 + 1);  /* worst case ' -> &#39; */
    char *buffer = (char *)malloc((size_t)capacity);
    if (!buffer) return 0;
    buffer[0] = 0;
    ss_http_html_escape(input, buffer, capacity);
    return buffer;
}

EAV_EXPORT long long eav_http_now_millis(void) {
    return ss_http_now_millis();
}

EAV_EXPORT long long eav_http_session_expires_at(long long now_millis, long long ttl_millis) {
    return ss_http_session_expires_at(now_millis, ttl_millis);
}

EAV_EXPORT int eav_http_session_is_expired(long long now_millis, long long expires_at_millis) {
    return ss_http_session_is_expired(now_millis, expires_at_millis) ? 1 : 0;
}

EAV_EXPORT long long eav_http_value_length(const char *value) {
    return ss_http_request_value_length(value);
}

EAV_EXPORT int eav_http_value_is_empty(const char *value) {
    return ss_http_request_value_is_empty(value);
}

EAV_EXPORT int eav_http_ensure_directory(const char *directory_path) {
    return ss_http_filesystem_ensure_directory(directory_path);
}

/* ---- server loop + request/response (WS3-017) ---- */

/* A handler is an EAV operation lowered as int(request, response) — its JIT/
 * native function pointer is passed straight through as an SSHttpHandler. */
EAV_EXPORT int eav_http_serve(const char *host, int port, const char *method,
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

EAV_EXPORT int eav_http_respond(void *response, int status, const char *body) {
    return ss_http_response_text((SSHttpResponse *)response, status, body, "text/plain");
}

EAV_EXPORT int eav_http_server_shutting_down(void) {
    return ss_http_server_is_shutting_down();
}

EAV_EXPORT const char *eav_http_request_path(void *request) {
    return ss_http_request_method((const SSHttpRequest *)request)
        ? ss_http_request_path((const SSHttpRequest *)request) : "";
}
