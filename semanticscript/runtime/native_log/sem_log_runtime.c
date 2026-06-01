/*
 * Implementation of the standard.log SemanticScript stdlib package.
 *
 * See sem_log_runtime.h for the surface contract. Everything here is
 * stdio-only: append-mode fopen + fwrite + fflush. No third-party
 * dependency, no platform-specific code beyond the platform mkdir
 * needed to materialize logs/ on demand.
 */

#include "sem_log_runtime.h"

#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#  include <direct.h>     /* _mkdir */
#else
#  include <sys/stat.h>   /* mkdir */
#  include <sys/types.h>
#endif

/* Default path: writes to logs/log.log under whatever cwd the process
 * was launched from. For the taskforge-web app launched from build/ this
 * means build/logs/log.log. Apps can override via ss_log_set_path
 * BEFORE the first write lands. */
static char  g_log_path[1024] = "logs/log.log";
static int   g_log_path_locked = 0;
static FILE *g_log_file = NULL;

/* mkdir helper. Returns 1 on success or if the directory already
 * exists, 0 on hard failure. We deliberately swallow the
 * "already-exists" case rather than treating it as an error — the only
 * thing the caller cares about is "is the directory there now." */
static int log_mkdir_p_single(const char *path) {
    if (path == NULL || path[0] == '\0') return 1;
#ifdef _WIN32
    int rc = _mkdir(path);
#else
    int rc = mkdir(path, 0755);
#endif
    if (rc == 0) return 1;
    /* errno == EEXIST is fine; everything else is a real failure. */
    return 0;
}

/* Ensure the directory holding g_log_path exists. Walks up to the last
 * slash, copies that prefix, and tries to create it. We only attempt
 * one level — if `logs/log.log` resolves to `a/b/c/log.log` and `a/b`
 * doesn't exist either, the open will fail and the caller sees an
 * SS_LOG_ERR_ENGINE. That's deliberate; a refine can add full
 * mkdir -p semantics if any project actually wants nested log dirs. */
static void log_ensure_parent_directory(void) {
    char parent[1024];
    size_t i;
    size_t slash_at = 0;
    int has_slash = 0;
    for (i = 0; g_log_path[i] != '\0' && i < sizeof(parent) - 1; ++i) {
        parent[i] = g_log_path[i];
        if (g_log_path[i] == '/' || g_log_path[i] == '\\') {
            slash_at = i;
            has_slash = 1;
        }
    }
    parent[i] = '\0';
    if (!has_slash) return;
    parent[slash_at] = '\0';
    (void)log_mkdir_p_single(parent);
}

static FILE *log_open_if_needed(void) {
    if (g_log_file != NULL) return g_log_file;
    log_ensure_parent_directory();
    g_log_file = fopen(g_log_path, "ab");
    if (g_log_file == NULL) return NULL;
    g_log_path_locked = 1;
    return g_log_file;
}

int ss_log_set_path(const char *new_path) {
    if (new_path == NULL || new_path[0] == '\0') return SS_LOG_ERR_CONFIG;
    if (g_log_path_locked) return SS_LOG_ERR_CONFIG;
    size_t len = strlen(new_path);
    if (len >= sizeof(g_log_path)) return SS_LOG_ERR_CONFIG;
    memcpy(g_log_path, new_path, len + 1);
    return SS_LOG_OK;
}

int ss_log_write_line(const char *line) {
    if (line == NULL || line[0] == '\0') return SS_LOG_OK;
    FILE *fp = log_open_if_needed();
    if (fp == NULL) return SS_LOG_ERR_ENGINE;
    size_t len = strlen(line);
    /* R-150: a short write, a failed newline, or a flush error means the log line
     * did not fully reach the sink — report it instead of always claiming OK. */
    if (fwrite(line, 1, len, fp) != len) return SS_LOG_ERR_ENGINE;
    if (fputc('\n', fp) == EOF) return SS_LOG_ERR_ENGINE;
    if (fflush(fp) != 0) return SS_LOG_ERR_ENGINE;
    return SS_LOG_OK;
}

/* Escape `src` for embedding inside a JSON string literal. Writes at
 * most `dst_capacity - 1` bytes plus a trailing '\0'. Stops gracefully
 * (truncates the source) if the destination would overflow rather
 * than corrupting the buffer. R-150: returns 1 if the source had to be
 * truncated to fit (so the caller can surface SS_LOG_ERR_TRUNCATED), 0
 * if the whole source was escaped. */
static int log_escape_json(char *dst, size_t dst_capacity, const char *src) {
    size_t out = 0;
    if (dst_capacity == 0) return src != NULL && *src != '\0';
    if (src == NULL) src = "";
    for (; *src != '\0' && out + 2 < dst_capacity; ++src) {
        char c = *src;
        if (c == '"' || c == '\\') {
            if (out + 3 >= dst_capacity) break;
            dst[out++] = '\\';
            dst[out++] = c;
        } else if ((unsigned char)c < 0x20) {
            if (out + 7 >= dst_capacity) break;
            int written = snprintf(dst + out, dst_capacity - out,
                                   "\\u%04x", (unsigned char)c);
            if (written < 0) break;
            out += (size_t)written;
        } else {
            dst[out++] = c;
        }
    }
    dst[out] = '\0';
    return *src != '\0';  /* unconsumed input remains -> truncated */
}

int ss_log_event(const char *level_text,
                 const char *event_text,
                 const char *message_text) {
    char level_buf[32];
    char event_buf[128];
    char message_buf[2048];
    /* R-150: track whether any field had to be truncated to fit its buffer. */
    int truncated = 0;
    truncated |= log_escape_json(level_buf, sizeof(level_buf),
                                 level_text != NULL ? level_text : "");
    truncated |= log_escape_json(event_buf, sizeof(event_buf),
                                 event_text != NULL ? event_text : "");
    truncated |= log_escape_json(message_buf, sizeof(message_buf),
                                 message_text != NULL ? message_text : "");
    /* No wall-clock import here — we rely on the user-provided ts when
     * they call ss_log_write_line directly. For these convenience
     * wrappers we omit ts entirely; the access-log path injects ts via
     * ss_log_http_access. A future refine could re-import clock_gettime
     * here, but that pulls a platform dependency into the otherwise
     * stdio-only adapter. */
    char line[2304];
    int n = snprintf(line, sizeof(line),
        "{\"level\":\"%s\",\"event\":\"%s\",\"message\":\"%s\"}",
        level_buf, event_buf, message_buf);
    if (n <= 0) return SS_LOG_ERR_ENGINE;
    if ((size_t)n >= sizeof(line)) { n = (int)sizeof(line) - 1; truncated = 1; }
    line[n] = '\0';
    /* R-150: still write the (possibly truncated) line so the log entry is not
     * lost, but a write failure dominates and truncation is reported otherwise —
     * the caller learns the record was not faithful instead of seeing OK. */
    int write_status = ss_log_write_line(line);
    if (write_status != SS_LOG_OK) return write_status;
    return truncated ? SS_LOG_ERR_TRUNCATED : SS_LOG_OK;
}

int ss_log_info(const char *message_text)  { return ss_log_event("info",  "app", message_text); }
int ss_log_warn(const char *message_text)  { return ss_log_event("warn",  "app", message_text); }
int ss_log_error(const char *message_text) { return ss_log_event("error", "app", message_text); }

int ss_log_http_access(const char *method_text,
                       const char *path_text,
                       int http_status,
                       long long start_ms,
                       long long now_ms) {
    long long latency = now_ms - start_ms;
    if (latency < 0) latency = 0;
    char method_buf[16];
    char path_buf[1024];
    /* R-150: report method/path/line truncation + write failure instead of a
     * silent void, so the access-log path has a deterministic status. */
    int truncated = 0;
    truncated |= log_escape_json(method_buf, sizeof(method_buf),
                                 method_text != NULL ? method_text : "");
    truncated |= log_escape_json(path_buf, sizeof(path_buf),
                                 path_text != NULL ? path_text : "");
    char line[1280];
    int n = snprintf(line, sizeof(line),
        "{\"ts\":%lld,\"level\":\"info\",\"event\":\"http.access\","
        "\"method\":\"%s\",\"path\":\"%s\",\"status\":%d,"
        "\"latency_ms\":%lld}",
        now_ms, method_buf, path_buf, http_status, latency);
    if (n <= 0) return SS_LOG_ERR_ENGINE;
    if ((size_t)n >= sizeof(line)) { n = (int)sizeof(line) - 1; truncated = 1; }
    line[n] = '\0';
    int write_status = ss_log_write_line(line);
    if (write_status != SS_LOG_OK) return write_status;
    return truncated ? SS_LOG_ERR_TRUNCATED : SS_LOG_OK;
}
