#ifndef SEM_HTTP_RUNTIME_H
#define SEM_HTTP_RUNTIME_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSHttpRequest SSHttpRequest;
typedef struct SSHttpResponse SSHttpResponse;

typedef int (*SSHttpHandler)(SSHttpRequest *request, SSHttpResponse *response);
typedef int (*SSHttpMiddleware)(SSHttpRequest *request, SSHttpResponse *response, void *next);

typedef struct SSHttpRoute {
    const char *method;
    const char *path;
    SSHttpHandler handler;
    SSHttpMiddleware middleware;
    int timeout_millis;
} SSHttpRoute;

typedef struct SSHttpStaticRoute {
    const char *prefix;
    const char *root_directory;
} SSHttpStaticRoute;

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
    /* Optional fallback handler invoked when the request path matches
     * at least one compiled route pattern but the HTTP method does not.
     * NULL keeps the historic behavior where that request falls through
     * to the not-found path. */
    SSHttpHandler method_not_allowed_handler;
    /* Optional declarative static file prefixes. Each entry serves GET
     * requests whose path is exactly `prefix` (as index.html) or starts with
     * `prefix/`, rooted under root_directory. */
    const SSHttpStaticRoute *static_routes;
    size_t static_route_count;
} SSHttpServerConfig;

/* ss_http_server_run() result codes. */
enum {
    SS_HTTP_OK = 0,
    SS_HTTP_ERR_CONFIG = 1,
    SS_HTTP_ERR_RUNTIME_UNAVAILABLE = 2,
    SS_HTTP_ERR_ENGINE = 3,
    /* BIN-8: the listen port is already bound (a still-running / not-yet-released
     * server, the zombie-port hazard). Distinct from a generic engine error so a
     * caller/agent can diagnose it cleanly instead of a cryptic failure. */
    SS_HTTP_ERR_ADDR_IN_USE = 4
};

/* Middleware return values, surfaced in SemanticScript source through the
 * v0.3 Bool ABI:
 *   true/non-zero continues to the route handler
 *   false/zero skips the handler and sends the middleware-written response
 * Any other non-zero value is treated as a middleware failure and the
 * dispatcher emits a 500 with body "middleware failed\n". The
 * short-circuit return path additionally validates that middleware
 * actually wrote a response body before sending — a bare short-circuit
 * with response.body == NULL is itself a 500 with a descriptive body
 * so the regression is visible at the client. */
enum {
    SS_HTTP_MIDDLEWARE_CONTINUE = 1,
    SS_HTTP_MIDDLEWARE_SHORT_CIRCUIT = 0
};

/*
 * Runs the blocking native HTTP/1.1 fallback server until the process receives
 * SIGINT/SIGTERM (or the equivalent Windows console close/break event). Signal
 * shutdown stops accepting new clients, lets the currently accepted request
 * return from its handler and flush its one-shot response, closes the listen
 * socket, frees compiled route state, and returns SS_HTTP_OK.
 *
 * This is process-level graceful shutdown only. standard.http exposes the
 * drain flag for SemanticScript handlers/middleware, but request cancellation
 * tokens and in-flight handler interruption are still outside this adapter.
 * standard.http owns the SSE stream API surface; this adapter only provides
 * the low-level blocking socket hooks that open/write/close a stream for a
 * handler that explicitly uses them before returning.
 */
int ss_http_server_run(const SSHttpServerConfig *config);

/*
 * Returns 1 once process-level graceful shutdown has been requested by a
 * signal/console handler, otherwise 0. This is the low-level ABI used by
 * standard.http.serverIsShuttingDown; application-specific rejection policy
 * belongs in SemanticScript.
 */
int ss_http_server_is_shutting_down(void);

/*
 * Discovers the executable/resource directory without mutating process cwd.
 * ss_http_set_cwd_to_executable_dir keeps its legacy name for ABI compatibility:
 * it now stores the directory for ss_http_executable_dir() and returns success,
 * but never calls chdir()/SetCurrentDirectory().
 */
int ss_http_set_cwd_to_executable_dir(void);
const char *ss_http_executable_dir(void);

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

int ss_http_sse_open(SSHttpResponse *response, int status);
int ss_http_sse_write_event(
    SSHttpResponse *response,
    const char *event_name,
    const char *event_data
);
int ss_http_sse_write_event_with_id(
    SSHttpResponse *response,
    long long event_id,
    const char *event_name,
    const char *event_data
);
int ss_http_sse_heartbeat(SSHttpResponse *response, const char *comment);
int ss_http_sse_close(SSHttpResponse *response);
int ss_http_client_disconnected(SSHttpResponse *response);

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
 * Convenience predicates for nullable request-derived string values returned by
 * requestHeader/query/pathParam/cookie/body readers. NULL is treated as empty so
 * handlers can test "missing or empty" without touching request memory directly.
 */
long long ss_http_request_value_length(const char *value);
int ss_http_request_value_is_empty(const char *value);

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
long long ss_http_session_expires_at(long long now_millis, long long ttl_millis);
bool ss_http_session_is_expired(long long now_millis, long long expires_at_millis);

/*
 * Outbound blocking HTTP/1.1 client. Connects to host:port, sends
 * `method path` with a Host header, an optional caller header line
 * (e.g. "Authorization: Bearer ..."), and an optional JSON body, then reads
 * the full response. Returns a malloc'd null-terminated copy of the response
 * BODY on a 2xx status, or NULL on transport error / non-2xx. Caller frees.
 */
const char *ss_http_client_fetch(
    const char *method,
    const char *host,
    int port,
    const char *path,
    const char *header_line,
    const char *body
);

/*
 * Escape the HTML special characters & < > " ' into entities, writing into the
 * caller's bounded out buffer (always null-terminated; truncates rather than
 * overflows). Returns out, or NULL on bad args.
 */
const char *ss_http_html_escape(const char *input, char *out, int out_capacity);

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

/*
 * URL-decode / URL-encode one component into caller-owned scratch memory.
 * Decode uses form-compatible semantics (`+` -> space) and rejects malformed
 * percent escapes. Encode passes RFC 3986 unreserved bytes through and writes
 * spaces as %20. Both return NULL on bad arguments or insufficient scratch.
 */
const char *ss_http_url_decode(
    const char *input,
    char *scratch_buffer,
    size_t scratch_capacity
);

const char *ss_http_url_encode(
    const char *input,
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
