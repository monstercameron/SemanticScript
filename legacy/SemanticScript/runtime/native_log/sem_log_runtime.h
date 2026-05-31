#ifndef SEM_LOG_RUNTIME_H
#define SEM_LOG_RUNTIME_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * SemanticScript-owned C ABI for the standard.log stdlib package.
 *
 * Surface design
 *
 *   - One append-mode FILE* held in module-static storage. Opened
 *     lazily on the first write so apps that never log don't pay for
 *     a file handle.
 *   - Path defaults to "logs/log.log" relative to the process cwd
 *     (so the on-disk file for an app launched from app/build/ lands
 *     at app/build/logs/log.log). The parent directory is created on
 *     demand if missing.
 *   - ss_log_set_path() lets a caller override the path BEFORE the
 *     first write lands. Once any write has succeeded the path is
 *     locked so a misbehaving caller can't fragment the audit trail
 *     mid-run.
 *   - ss_log_write_line() expects a single JSON object and appends a
 *     newline. fflush is called after every write so a crash loses at
 *     most the one in-flight line.
 *   - ss_log_access() is invoked by the http runtime once per
 *     dispatched request and writes a structured access entry of
 *     shape {"ts":N,"level":"info","event":"http.access",
 *     "method":"...","path":"...","status":N,"latency_ms":N}.
 *
 * Return codes mirror the SS_LOG_* enum below. The http runtime's
 * SS_HTTP_OK / SS_HTTP_ERR_CONFIG / SS_HTTP_ERR_ENGINE numeric values
 * are aligned so callers can pass log return codes through code paths
 * that expect http return codes (and vice versa).
 */
enum {
    SS_LOG_OK                  = 0,
    SS_LOG_ERR_CONFIG          = 1,
    SS_LOG_ERR_RUNTIME_GENERIC = 2,
    SS_LOG_ERR_ENGINE          = 3
};

int ss_log_set_path(const char *new_path);
int ss_log_write_line(const char *line);

/*
 * Convenience writers that build the JSON envelope automatically. They
 * are pure wrappers around ss_log_write_line so AS apps can pick the
 * level and let the runtime handle escaping + envelope formatting.
 *
 *   ss_log_event(level, event, message)
 *     -> {"ts":N,"level":"<level>","event":"<event>","message":"<message>"}
 *   ss_log_info(message)  -> shorthand for level=info, event=app
 *   ss_log_warn(message)  -> shorthand for level=warn, event=app
 *   ss_log_error(message) -> shorthand for level=error, event=app
 *
 * Level and event strings are written as plain JSON string values; any
 * embedded `"` or control characters get backslash-escaped before the
 * line is emitted. Message accepts the same escaping. NULL inputs are
 * treated as empty strings rather than being silently dropped — so a
 * misuse surfaces as a log line with empty fields rather than a hidden
 * skip that's hard to debug.
 */
int ss_log_event(const char *level_text,
                 const char *event_text,
                 const char *message_text);
int ss_log_info(const char *message_text);
int ss_log_warn(const char *message_text);
int ss_log_error(const char *message_text);

/* Helper for the http runtime to log one request after dispatch. Not
 * intended for direct call from AS — handlers should use ss_log_event
 * with their own event tag for business-level structured events. */
void ss_log_http_access(const char *method_text,
                        const char *path_text,
                        int http_status,
                        long long start_ms,
                        long long now_ms);

#ifdef __cplusplus
}
#endif

#endif
