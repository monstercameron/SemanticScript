#ifndef SEM_HTTP_RUNTIME_H
#define SEM_HTTP_RUNTIME_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSHttpRequest SSHttpRequest;
typedef struct SSHttpResponse SSHttpResponse;

typedef int (*SSHttpHandler)(SSHttpRequest *request, SSHttpResponse *response);

typedef struct SSHttpRoute {
    const char *method;
    const char *path;
    SSHttpHandler handler;
    SSHttpHandler middleware;
} SSHttpRoute;

typedef struct SSHttpServerConfig {
    const char *host;
    unsigned short port;
    const SSHttpRoute *routes;
    size_t route_count;
    /* Optional fallback handler invoked when no route matches the
     * incoming request. NULL keeps the historic behavior (plaintext
     * `404 not found\n`). When set, the handler receives the request
     * + a fresh response and is responsible for writing the body /
     * content-type; the dispatcher only sends what the handler
     * produced. */
    SSHttpHandler not_found_handler;
} SSHttpServerConfig;

/* ss_http_server_run() result codes. */
enum {
    SS_HTTP_OK = 0,
    SS_HTTP_ERR_CONFIG = 1,
    SS_HTTP_ERR_RUNTIME_UNAVAILABLE = 2,
    SS_HTTP_ERR_ENGINE = 3
};

/* Middleware return values, surfaced in SemanticScript source as the
 * built-in enum `MiddlewareControl` (repr CSignedInt32):
 *   continueMiddlewareControl       == 0  (call the route handler)
 *   shortCircuitMiddlewareControl   == 1  (skip handler; send the
 *                                          middleware-written response)
 * Any other non-zero value is treated as a middleware failure and the
 * dispatcher emits a 500 with body "middleware failed\n". The new
 * short-circuit return path additionally validates that middleware
 * actually wrote a response body before sending — a bare short-circuit
 * with response.body == NULL is itself a 500 with a descriptive body
 * so the regression is visible at the client. */
enum {
    SS_HTTP_MIDDLEWARE_CONTINUE = 0,
    SS_HTTP_MIDDLEWARE_SHORT_CIRCUIT = 1
};

int ss_http_server_run(const SSHttpServerConfig *config);

int ss_http_response_text(
    SSHttpResponse *response,
    int status,
    const char *body,
    const char *content_type
);

int ss_http_response_bytes(
    SSHttpResponse *response,
    int status,
    const void *body,
    size_t body_length,
    const char *content_type
);

int ss_http_response_sse_event(
    SSHttpResponse *response,
    int status,
    const char *event_name,
    const char *event_data
);

const char *ss_http_request_method(const SSHttpRequest *request);
const char *ss_http_request_path(const SSHttpRequest *request);
const char *ss_http_request_header(const SSHttpRequest *request, const char *name);
const char *ss_http_request_query_param(const SSHttpRequest *request, const char *name);
const char *ss_http_request_body_text(const SSHttpRequest *request);
const void *ss_http_request_body_bytes(const SSHttpRequest *request);
size_t ss_http_request_body_length(const SSHttpRequest *request);

/*
 * Returns the captured value for a path-pattern parameter (the route
 * declared `:name` segment), or NULL when the route has no such param.
 * The returned pointer is valid for the duration of the handler call and
 * points into a per-request scratch buffer — the full request path
 * remains intact and is still readable via ss_http_request_path().
 *
 * Routes are matched in registration order. When a literal route and a
 * parametric route could both apply to a request (e.g. `/api/todos` and
 * `/api/todos/:id` both reachable from `/api/todos/42`), the FIRST
 * declared route wins. Declare more-specific routes before parametric
 * ones to avoid surprises.
 */
const char *ss_http_request_path_param(const SSHttpRequest *request, const char *name);

/*
 * Returns the value of the named cookie from the request's `Cookie:`
 * header, or NULL when the header is absent or the cookie isn't
 * present. The returned pointer is valid for the duration of the
 * handler call and points into a per-request scratch buffer (the
 * decoded value is unescaped from any percent-encoding the client
 * applied). Maximum value length is 256 bytes; longer values return
 * NULL rather than truncate, so a session-token cookie that exceeds
 * its expected length surfaces as "no session attached".
 */
const char *ss_http_request_cookie(const SSHttpRequest *request, const char *cookie_name);

/*
 * Reads `requested_relative_path` from inside `root_directory`,
 * sniffs its content-type by extension, and writes the bytes into
 * `response` with the given status. Refuses any relative path that
 * contains `..` segments, starts with `/` or `\`, or contains a
 * drive-letter prefix on Windows. Refuses files larger than 16 MiB.
 * Returns SS_HTTP_OK on success or one of:
 *   SS_HTTP_ERR_CONFIG  — NULL inputs, traversal attempt, or oversize.
 *   SS_HTTP_ERR_ENGINE  — fopen / fread failure.
 *
 * On any error, the response is left untouched (the dispatcher's
 * 404/500 fallback applies). On success, the response body owns its
 * own malloc'd copy of the file bytes — the response writer frees it
 * after sending.
 */
int ss_http_response_file(
    SSHttpResponse *response,
    int status,
    const char *root_directory,
    const char *requested_relative_path
);

/*
 * Returns the wall-clock time in milliseconds since the Unix epoch.
 * Implementation uses GetSystemTimeAsFileTime on Windows and
 * clock_gettime(CLOCK_REALTIME) on POSIX. Used by request-log
 * middleware for the `[ts=…]` timestamp and the `[ms=…]` request
 * latency, by the session expiry math, and by SQL `created_at_ms`
 * inserts when the AS source would otherwise need to call out to
 * libc time().
 */
long long ss_http_now_millis(void);

/*
 * Ensures the named directory exists, creating it if missing. Refuses
 * to create parents — the directory's parent must already exist. The
 * taskforge-web app uses this once at startup to make sure
 * build/images/ is ready for uploads. Returns SS_HTTP_OK on success,
 * SS_HTTP_ERR_CONFIG on a NULL or empty path, or SS_HTTP_ERR_ENGINE
 * if the platform mkdir call failed for a reason other than
 * "directory already exists".
 */
int ss_http_filesystem_ensure_directory(const char *directory_path);

/*
 * Parses an application/x-www-form-urlencoded body for a named field,
 * URL-decodes the value, and writes it into the caller's scratch
 * buffer. Returns the scratch pointer on success or NULL when the
 * field is absent, the body is NULL, the decoded value would
 * overflow the scratch, or the body contains an invalid percent
 * escape. Same shape as ss_json_find_string so apps can call either
 * (or both) depending on the request's Content-Type header.
 *
 * URL-decoding handles `+` -> space and `%XX` -> hex byte. Field
 * names are matched as plain bytes (no decoding) since browsers and
 * the standard library both submit field names in their literal
 * form for ASCII identifiers.
 */
const char *ss_http_form_find_field(
    const char *body_text,
    const char *field_name,
    char *scratch_buffer,
    size_t scratch_capacity
);

const char *ss_http_multipart_part_text(SSHttpRequest *request, const char *name);
const void *ss_http_multipart_part_bytes(SSHttpRequest *request, const char *name);
size_t ss_http_multipart_part_length(SSHttpRequest *request, const char *name);
const char *ss_http_multipart_part_filename(SSHttpRequest *request, const char *name);
const char *ss_http_multipart_part_content_type(SSHttpRequest *request, const char *name);

int ss_http_response_header(
    SSHttpResponse *response,
    const char *name,
    const char *value
);

#ifdef __cplusplus
}
#endif

#endif
