/*
 * ss_libc.c — explicit libc shims for the `c.*` intrinsics (APP-RUN-6). Each
 * takes/returns Int64 for OpaquePointer handles and const char* for String, so
 * the EAV-declared arg/out types line up with the symbol exactly and the
 * compiler performs no implicit coercion. The one explicit pointer<->String
 * reinterpret an app needs (e.g. viewing a freshly written byte buffer as a
 * NUL-terminated string) is ss_c_cstring, surfaced as `c.cString`.
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <errno.h>  /* R-175: strict ss_c_atoll overflow detection */

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

/*
 * R-199: liveness registries for the raw c.* heap/file handles (the sqlite R-139 /
 * event R-196 / json R-198 / async R-195 tombstone pattern). c.malloc/c.fopen
 * hand back plain OpaquePointers and c.free/c.fclose are app-visible cleanup with
 * no ownership tracking, so a double free, a free of a forged/foreign pointer, a
 * double fclose, or a read after fclose corrupted the allocator / used freed
 * memory. Track every handle we hand out and validate by pointer VALUE before any
 * free/use — a stale or foreign handle fails closed (a no-op / safe sentinel)
 * instead of reaching libc. Single-threaded use; no lock.
 */
typedef struct { void **items; size_t count; size_t cap; } ss_c_registry;

static ss_c_registry ss_c_live_allocs;
static ss_c_registry ss_c_live_streams;

static int ss_c_track(ss_c_registry *r, void *handle) {
    if (r->count == r->cap) {
        size_t next = r->cap == 0 ? 16 : r->cap * 2;
        if (r->cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(void *)) {
            return 0;
        }
        void **grown = (void **)realloc(r->items, next * sizeof(void *));
        if (!grown) return 0;
        r->items = grown;
        r->cap = next;
    }
    r->items[r->count++] = handle;
    return 1;
}

static int ss_c_is_live(const ss_c_registry *r, const void *handle) {
    for (size_t i = 0; i < r->count; i++) {
        if (r->items[i] == handle) return 1;
    }
    return 0;
}

static int ss_c_untrack(ss_c_registry *r, void *handle) {
    for (size_t i = 0; i < r->count; i++) {
        if (r->items[i] == handle) {
            r->items[i] = r->items[r->count - 1];
            r->count--;
            return 1;
        }
    }
    return 0;
}

/* A stream is usable for read/write/flush if it is a live c.fopen handle OR one of
 * the process standard streams (which are not tracked because they are never
 * fopen'd here). This lets a use-after-fclose fail closed without rejecting
 * stdin/stdout/stderr. */
static int ss_c_stream_usable(FILE *stream) {
    return stream != NULL
        && (stream == stdin || stream == stdout || stream == stderr
            || ss_c_is_live(&ss_c_live_streams, stream));
}

SS_EXPORT long long ss_c_malloc(long long size) {
    /* R-133: a negative size would wrap to a huge size_t. Reject it (and a zero
     * request) as a failed allocation — `c.malloc` is fallible, so 0/NULL is the
     * app-observable "could not allocate" signal it already handles. */
    if (size <= 0) {
        return 0;
    }
    void *block = malloc((size_t)size);
    if (block == NULL) {
        return 0;
    }
    /* R-199: register so free validates the handle. If the registry cannot grow,
     * release the block and report allocation failure rather than hand out an
     * untracked pointer that free would then refuse. */
    if (!ss_c_track(&ss_c_live_allocs, block)) {
        free(block);
        return 0;
    }
    return (long long)(intptr_t)block;
}

SS_EXPORT void ss_c_free(long long pointer) {
    void *block = (void *)(intptr_t)pointer;
    /* R-199: only free a pointer we handed out and have not already freed. A
     * double free, or a free of a forged/foreign pointer, fails membership and is
     * a no-op instead of corrupting the allocator. */
    if (block == NULL || !ss_c_untrack(&ss_c_live_allocs, block)) {
        return;
    }
    free(block);
}

SS_EXPORT void ss_c_memset(long long pointer, int value, long long count) {
    /* R-133: ignore a negative count (would wrap to a huge size_t) and a NULL
     * destination rather than corrupt memory. */
    if (pointer == 0 || count <= 0) {
        return;
    }
    memset((void *)(intptr_t)pointer, value, (size_t)count);
}

SS_EXPORT int ss_c_strcmp(const char *left, const char *right) {
    return strcmp(left, right);
}

SS_EXPORT long long ss_c_strlen(const char *text) {
    return (long long)strlen(text);
}

SS_EXPORT long long ss_c_atoll(const char *text) {
    /* R-175: parse strictly. Plain atoll() silently accepts trailing junk
     * ("12abc" -> 12), so a malformed request id was used as a real id. Require
     * the whole token (after optional surrounding whitespace and a sign) to be
     * digits; any other content yields 0, which callers reject via their
     * positive-id validation. */
    if (text == NULL) {
        return 0;
    }
    errno = 0;
    char *endp = NULL;
    long long value = strtoll(text, &endp, 10);
    if (endp == text || errno == ERANGE) {
        return 0;  /* no digits, or overflow */
    }
    while (*endp == ' ' || *endp == '\t' || *endp == '\n' || *endp == '\r') {
        ++endp;
    }
    return *endp == '\0' ? value : 0;  /* trailing junk -> malformed */
}

/* Variadic formatters backing `c.snprintf`/`c.printf`/`c.fprintf`. Buffers and
 * streams cross as OpaquePointer (Int64). These shims exist because the bare
 * snprintf/printf/fprintf symbols are header inlines on Windows UCRT with no
 * exported symbol, so the JIT cannot relocate a direct call; each forwards to
 * its v*-counterpart, which IS a real exported symbol. */
SS_EXPORT int ss_c_snprintf(long long buffer, long long size,
                            const char *format, ...) {
    va_list args;
    va_start(args, format);
    int result = vsnprintf((char *)(intptr_t)buffer, (size_t)size, format, args);
    va_end(args);
    return result;
}

SS_EXPORT int ss_c_printf(const char *format, ...) {
    va_list args;
    va_start(args, format);
    int result = vprintf(format, args);
    va_end(args);
    return result;
}

SS_EXPORT int ss_c_fprintf(long long stream, const char *format, ...) {
    FILE *file = (FILE *)(intptr_t)stream;
    /* R-199: refuse to write through a stale (closed) or foreign stream handle —
     * a use-after-fclose would otherwise touch the freed FILE object. Live
     * c.fopen handles and the standard streams are allowed. */
    if (!ss_c_stream_usable(file)) {
        return -1;
    }
    va_list args;
    va_start(args, format);
    int result = vfprintf(file, format, args);
    va_end(args);
    return result;
}

/* Fixed-signature libc seams. Streams/buffers cross as OpaquePointer (Int64); a
 * NULL/0 stream to fflush flushes all open streams (the C contract). */
SS_EXPORT int ss_c_putchar(int character) { return putchar(character); }
SS_EXPORT int ss_c_puts(const char *text) { return puts(text); }
SS_EXPORT int ss_c_fflush(long long stream) {
    FILE *file = (FILE *)(intptr_t)stream;
    /* A NULL/0 stream flushes all open streams (the C contract) — keep that. A
     * non-null handle must be a live c.fopen handle or a standard stream (R-199);
     * a stale/closed handle fails closed rather than flushing freed memory. */
    if (file == NULL) {
        return fflush(NULL);
    }
    if (!ss_c_stream_usable(file)) {
        return EOF;
    }
    return fflush(file);
}
SS_EXPORT long long ss_c_fopen(const char *path, const char *mode) {
    FILE *stream = fopen(path, mode);
    if (stream == NULL) {
        return 0;
    }
    /* R-199: register so fclose/fgets/fprintf can validate the handle. */
    if (!ss_c_track(&ss_c_live_streams, stream)) {
        fclose(stream);
        return 0;
    }
    return (long long)(intptr_t)stream;
}
SS_EXPORT int ss_c_fclose(long long stream) {
    FILE *file = (FILE *)(intptr_t)stream;
    /* R-199: only close a live c.fopen handle. A double fclose, or a close of a
     * foreign/standard stream, fails membership and is a no-op (return 0) instead
     * of a double free of the FILE object. */
    if (file == NULL || !ss_c_untrack(&ss_c_live_streams, file)) {
        return 0;
    }
    return fclose(file);
}
SS_EXPORT long long ss_c_fgets(long long buffer, int count, long long stream) {
    FILE *file = (FILE *)(intptr_t)stream;
    /* R-199: a read after fclose would dereference the freed FILE object — refuse
     * a stale/foreign handle and return 0 (NULL = no line), which the read loop
     * already treats as end-of-input. Live handles + standard streams are fine. */
    if (!ss_c_stream_usable(file)) {
        return 0;
    }
    return (long long)(intptr_t)fgets((char *)(intptr_t)buffer, count, file);
}
SS_EXPORT long long ss_c_memmove(long long dest, long long src, long long count) {
    return (long long)(intptr_t)memmove((void *)(intptr_t)dest,
                                        (void *)(intptr_t)src, (size_t)count);
}

/* `c.terminalReadKey` headless contract (APP-RUN-2): read one key from stdin so
 * the TUI state machine is driveable by a scripted keystroke stream in tests and
 * pipes. Input exhaustion (EOF) reports Esc (27) so the read loop quits cleanly
 * rather than spinning on a sentinel. */
SS_EXPORT int ss_c_terminalReadKey(void) {
    int key = getchar();
    return key == EOF ? 27 : key;
}

/* Explicit reinterpret: an OpaquePointer byte buffer viewed as a String. The
 * `c.cString` intrinsic maps to the method name verbatim (ss_c_ + "cString"),
 * so the exported symbol must keep the camelCase tail. */
SS_EXPORT const char *ss_c_cString(long long pointer) {
    return (const char *)(intptr_t)pointer;
}
