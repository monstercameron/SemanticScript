/*
 * ss_libc.c — explicit libc shims for the `c.*` intrinsics (APP-RUN-6). Each
 * entry points keep the old Int64 handle ABI for stable runtime tracking; the
 * compiler bridges source-visible OpaquePointer/FileHandle values explicitly at
 * those call sites. The one explicit pointer<->String
 * reinterpret an app needs (e.g. viewing a freshly written byte buffer as a
 * NUL-terminated string) is ss_c_cstring, surfaced as `c.cString`.
 */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stdio.h>
#include <stdarg.h>
#include <errno.h>  /* R-175: strict ss_c_atoll overflow detection */
#include "native_platform/ss_platform.h"
#include "ss_runtime_export.h"

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

/* R-267: scan a printf format for a `%n` conversion — the ONLY directive that
 * writes through a pointer argument, i.e. the arbitrary-write primitive of an
 * uncontrolled-format-string attack. `%%` is a literal percent and is skipped;
 * flags/width/precision/length modifiers between `%` and the conversion are
 * stepped over so `%-10.5n` is still caught. Returns 1 if the format must be
 * refused. (%s/%x/%p info-leak reads cannot be distinguished from legitimate
 * formatting, so the contract is: these shims are LITERAL-format-only — the EAV
 * `c.printf` binding enforces a constant format via SS3088, and dynamic strings
 * must go through ss_c_print_str, the %s-safe path below. This is the C-layer
 * last line of defense for a bypassed/forged caller.) */
static int ss_c_format_has_percent_n(const char *format) {
    if (format == NULL) {
        return 0;
    }
    for (size_t i = 0; format[i] != '\0'; ++i) {
        if (format[i] != '%') {
            continue;
        }
        ++i;
        if (format[i] == '\0') {
            break;            /* trailing '%' */
        }
        if (format[i] == '%') {
            continue;         /* '%%' -> literal percent, not a conversion */
        }
        while (format[i] != '\0'
               && strchr("-+ #0'.*123456789hlLjztq", format[i]) != NULL) {
            ++i;
        }
        if (format[i] == '\0') {
            break;
        }
        if (format[i] == 'n') {
            return 1;         /* the memory-WRITE directive */
        }
    }
    return 0;
}

/* R-267: print a dynamic string as DATA, never as a printf format. This is the
 * %s-safe path for app/user-derived text — directives like %s/%x/%n inside
 * `text` are emitted literally, not interpreted. Prefer this over c.printf for
 * any non-literal string. Returns a non-negative count on success, -1 on a NULL
 * input or write error. */
SS_EXPORT int ss_c_print_str(const char *text) {
    if (text == NULL) {
        return -1;
    }
    int result = fputs(text, stdout);
    return result < 0 ? -1 : result;
}

/* Variadic formatters backing `c.snprintf`/`c.printf`/`c.fprintf`. Buffers and
 * streams cross as OpaquePointer (Int64). These shims exist because the bare
 * snprintf/printf/fprintf symbols are header inlines on Windows UCRT with no
 * exported symbol, so the JIT cannot relocate a direct call; each forwards to
 * its v*-counterpart, which IS a real exported symbol. The `format` argument is
 * LITERAL-format-only (R-267): a `%n`-bearing format is refused outright, and
 * dynamic strings belong in ss_c_print_str, not the format position. */
SS_EXPORT int ss_c_snprintf(long long buffer, long long size,
                            const char *format, ...) {
    /* R-187: do not cast a negative signed size to huge size_t, and do not let
     * libc dereference a NULL output buffer/format string. A zero-size write is
     * treated as a safe no-op/error sentinel for this raw shim rather than
     * forwarding a boundary case whose portability depends on libc details. */
    if (buffer == 0 || size <= 0 || format == NULL
        || ss_c_format_has_percent_n(format)) {   /* R-267 */
        return -1;
    }
    va_list args;
    va_start(args, format);
    int result = vsnprintf((char *)(intptr_t)buffer, (size_t)size, format, args);
    va_end(args);
    return result;
}

SS_EXPORT int ss_c_printf(const char *format, ...) {
    if (format == NULL || ss_c_format_has_percent_n(format)) {   /* R-267 */
        return -1;
    }
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
    if (format == NULL || ss_c_format_has_percent_n(format)) {   /* R-267 */
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
    /* R-187: fgets dereferences the destination buffer and interprets count as a
     * bounded write size. Reject NULL buffers and non-positive counts before
     * libc sees them; return 0/NULL, matching the existing end-of-input signal. */
    if (buffer == 0 || count <= 0) {
        return 0;
    }
    /* R-199: a read after fclose would dereference the freed FILE object — refuse
     * a stale/foreign handle and return 0 (NULL = no line), which the read loop
     * already treats as end-of-input. Live handles + standard streams are fine. */
    if (!ss_c_stream_usable(file)) {
        return 0;
    }
    return (long long)(intptr_t)fgets((char *)(intptr_t)buffer, count, file);
}
SS_EXPORT long long ss_c_memmove(long long dest, long long src, long long count) {
    /* R-187: memmove dereferences both pointers when count is positive, and a
     * negative signed count would wrap to a huge size_t. Positive copies require
     * non-NULL pointers; zero is a deterministic no-op that returns dest without
     * entering libc. */
    if (count < 0 || dest == 0 || src == 0) {
        return 0;
    }
    if (count == 0) {
        return dest;
    }
    return (long long)(intptr_t)memmove((void *)(intptr_t)dest,
                                        (void *)(intptr_t)src, (size_t)count);
}

#define SS_C_KEY_LEFT 1000
#define SS_C_KEY_RIGHT 1001
#define SS_C_KEY_UP 1002
#define SS_C_KEY_DOWN 1003
#define SS_C_KEY_DELETE 1004

/* `c.terminalReadKey` headless contract (APP-RUN-2): read one key from stdin so
 * the TUI state machine is driveable by a scripted keystroke stream in tests and
 * pipes. Input exhaustion (EOF) reports Esc (27) so the read loop quits cleanly
 * rather than spinning on a sentinel.
 *
 * R-029: interactive terminals get real platform behavior. Windows uses _getch
 * extended-key decoding; POSIX uses termios raw mode, read(2), and ANSI escape
 * sequence decoding. Non-TTY stdin deliberately keeps the byte-at-a-time stdio
 * path so scripts and CI remain deterministic. */
#ifdef _WIN32
SS_EXPORT int ss_c_terminalReadKey(void) {
    if (!_isatty(_fileno(stdin))) {
        int piped = getchar();
        return piped == EOF ? 27 : piped;
    }
    int key = _getch();
    if (key == 0 || key == 224) {
        int ext = _getch();
        switch (ext) {
            case 75: return SS_C_KEY_LEFT;
            case 77: return SS_C_KEY_RIGHT;
            case 72: return SS_C_KEY_UP;
            case 80: return SS_C_KEY_DOWN;
            case 83: return SS_C_KEY_DELETE;
            default: return 0;
        }
    }
    return key == EOF ? 27 : key;
}

static int ss_c_terminal_dimension(int want_columns) {
    CONSOLE_SCREEN_BUFFER_INFO info;
    if (GetConsoleScreenBufferInfo(GetStdHandle(STD_OUTPUT_HANDLE), &info)) {
        int value = want_columns
            ? (int)(info.srWindow.Right - info.srWindow.Left + 1)
            : (int)(info.srWindow.Bottom - info.srWindow.Top + 1);
        if (value > 0) {
            return value;
        }
    }
    return want_columns ? 80 : 24;
}

SS_EXPORT int ss_c_terminalColumns(void) {
    return ss_c_terminal_dimension(1);
}

SS_EXPORT int ss_c_terminalRows(void) {
    return ss_c_terminal_dimension(0);
}
#else
static struct termios ss_c_terminal_saved;
static int ss_c_terminal_raw_enabled = 0;

static void ss_c_terminal_restore(void) {
    if (ss_c_terminal_raw_enabled) {
        tcsetattr(STDIN_FILENO, TCSAFLUSH, &ss_c_terminal_saved);
        ss_c_terminal_raw_enabled = 0;
    }
}

static int ss_c_terminal_enable_raw(void) {
    if (!isatty(STDIN_FILENO)) {
        return 0;
    }
    if (ss_c_terminal_raw_enabled) {
        return 1;
    }
    if (tcgetattr(STDIN_FILENO, &ss_c_terminal_saved) != 0) {
        return 0;
    }
    struct termios raw = ss_c_terminal_saved;
    raw.c_lflag &= (tcflag_t)~(ECHO | ICANON);
    raw.c_iflag &= (tcflag_t)~(IXON | ICRNL);
    raw.c_cc[VMIN] = 1;
    raw.c_cc[VTIME] = 0;
    if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) != 0) {
        return 0;
    }
    ss_c_terminal_raw_enabled = 1;
    atexit(ss_c_terminal_restore);
    return 1;
}

static int ss_c_terminal_read_byte_timeout(unsigned char *out, int timeout_ms) {
    fd_set set;
    FD_ZERO(&set);
    FD_SET(STDIN_FILENO, &set);
    struct timeval tv;
    tv.tv_sec = timeout_ms / 1000;
    tv.tv_usec = (timeout_ms % 1000) * 1000;
    int ready = select(STDIN_FILENO + 1, &set, NULL, NULL, &tv);
    if (ready <= 0) {
        return 0;
    }
    return read(STDIN_FILENO, out, 1) == 1;
}

static int ss_c_terminal_decode_escape(void) {
    unsigned char second = 0;
    unsigned char third = 0;
    if (!ss_c_terminal_read_byte_timeout(&second, 25)) {
        return 27;
    }
    if (second != '[' && second != 'O') {
        return 27;
    }
    if (!ss_c_terminal_read_byte_timeout(&third, 25)) {
        return 27;
    }
    switch (third) {
        case 'A': return SS_C_KEY_UP;
        case 'B': return SS_C_KEY_DOWN;
        case 'C': return SS_C_KEY_RIGHT;
        case 'D': return SS_C_KEY_LEFT;
        case '3': {
            unsigned char tilde = 0;
            if (ss_c_terminal_read_byte_timeout(&tilde, 25) && tilde == '~') {
                return SS_C_KEY_DELETE;
            }
            return 27;
        }
        default:
            return 27;
    }
}

SS_EXPORT int ss_c_terminalReadKey(void) {
    if (!isatty(STDIN_FILENO) || !ss_c_terminal_enable_raw()) {
        int key = getchar();
        return key == EOF ? 27 : key;
    }
    unsigned char key = 0;
    if (read(STDIN_FILENO, &key, 1) != 1) {
        return 27;
    }
    if (key == 27) {
        return ss_c_terminal_decode_escape();
    }
    return (int)key;
}

SS_EXPORT int ss_c_terminalColumns(void) {
    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
        return (int)ws.ws_col;
    }
    const char *cols = getenv("COLUMNS");
    int value = cols ? atoi(cols) : 0;
    return value > 0 ? value : 80;
}

SS_EXPORT int ss_c_terminalRows(void) {
    struct winsize ws;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &ws) == 0 && ws.ws_row > 0) {
        return (int)ws.ws_row;
    }
    const char *rows = getenv("LINES");
    int value = rows ? atoi(rows) : 0;
    return value > 0 ? value : 24;
}
#endif

/* Explicit reinterpret: an OpaquePointer byte buffer viewed as a String. The
 * `c.cString` intrinsic maps to the method name verbatim (ss_c_ + "cString"),
 * so the exported symbol must keep the camelCase tail. */
SS_EXPORT const char *ss_c_cString(long long pointer) {
    return (const char *)(intptr_t)pointer;
}
