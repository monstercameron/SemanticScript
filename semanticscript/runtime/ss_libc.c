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

/* Variadic formatter backing `c.snprintf`. The buffer crosses as an
 * OpaquePointer (Int64); forward to the UCRT's C99-correct vsnprintf. Exists
 * because the bare `snprintf` symbol is not exported on Windows (header inline),
 * so the JIT cannot relocate a direct call to it. */
SS_EXPORT int ss_c_snprintf(long long buffer, long long size,
                            const char *format, ...) {
    va_list args;
    va_start(args, format);
    int result = vsnprintf((char *)(intptr_t)buffer, (size_t)size, format, args);
    va_end(args);
    return result;
}

/* Explicit reinterpret: an OpaquePointer byte buffer viewed as a String. The
 * `c.cString` intrinsic maps to the method name verbatim (ss_c_ + "cString"),
 * so the exported symbol must keep the camelCase tail. */
SS_EXPORT const char *ss_c_cString(long long pointer) {
    return (const char *)(intptr_t)pointer;
}
