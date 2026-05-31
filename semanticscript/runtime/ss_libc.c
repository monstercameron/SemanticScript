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

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

SS_EXPORT long long ss_c_malloc(long long size) {
    return (long long)(intptr_t)malloc((size_t)size);
}

SS_EXPORT void ss_c_free(long long pointer) {
    free((void *)(intptr_t)pointer);
}

SS_EXPORT void ss_c_memset(long long pointer, int value, long long count) {
    memset((void *)(intptr_t)pointer, value, (size_t)count);
}

SS_EXPORT int ss_c_strcmp(const char *left, const char *right) {
    return strcmp(left, right);
}

SS_EXPORT long long ss_c_strlen(const char *text) {
    return (long long)strlen(text);
}

SS_EXPORT long long ss_c_atoll(const char *text) {
    return atoll(text);
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
    va_list args;
    va_start(args, format);
    int result = vfprintf((FILE *)(intptr_t)stream, format, args);
    va_end(args);
    return result;
}

/* Fixed-signature libc seams. Streams/buffers cross as OpaquePointer (Int64); a
 * NULL/0 stream to fflush flushes all open streams (the C contract). */
SS_EXPORT int ss_c_putchar(int character) { return putchar(character); }
SS_EXPORT int ss_c_puts(const char *text) { return puts(text); }
SS_EXPORT int ss_c_fflush(long long stream) {
    return fflush((FILE *)(intptr_t)stream);
}
SS_EXPORT long long ss_c_fopen(const char *path, const char *mode) {
    return (long long)(intptr_t)fopen(path, mode);
}
SS_EXPORT int ss_c_fclose(long long stream) {
    return fclose((FILE *)(intptr_t)stream);
}
SS_EXPORT long long ss_c_fgets(long long buffer, int count, long long stream) {
    return (long long)(intptr_t)fgets((char *)(intptr_t)buffer, count,
                                      (FILE *)(intptr_t)stream);
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
