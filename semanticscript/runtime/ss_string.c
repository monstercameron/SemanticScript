/*
 * ss_string.c — string-namespace runtime helpers (standard.string, README §26).
 *
 * These back the byte-oriented string operations the `string.concat` intrinsic
 * does not cover: bytewise comparison, (in)equality, and substring/character
 * search. Each is a pure function over NUL-terminated UTF-8 byte strings bound
 * through the generic `body runtimeBinding <symbol>` seam (so no compiler change
 * is needed), with the typed home in std/standard.string.sem. Strings cross the
 * EAV boundary as `String` (i8*); results are Int64/Int32. (X-200)
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ss_runtime_export.h"

/* Bytewise comparison (memcmp/strcmp semantics): negative if left < right,
 * 0 if equal, positive if left > right. NULL sorts before any non-NULL string. */
SS_EXPORT int32_t ss_string_compare(const char *left, const char *right) {
    if (left == right) return 0;
    if (left == NULL) return -1;
    if (right == NULL) return 1;
    int r = strcmp(left, right);
    return r < 0 ? -1 : (r > 0 ? 1 : 0);
}

/* 1 if the two byte strings are equal, 0 otherwise. */
SS_EXPORT int32_t ss_string_equal(const char *left, const char *right) {
    return ss_string_compare(left, right) == 0 ? 1 : 0;
}

/* 1 if the two byte strings differ, 0 if equal (the negation of equal). */
SS_EXPORT int32_t ss_string_not_equal(const char *left, const char *right) {
    return ss_string_compare(left, right) == 0 ? 0 : 1;
}

/* Byte offset of the first occurrence of `needle` in `haystack`, or -1 if not
 * found. An empty needle matches at offset 0 (strstr semantics). */
SS_EXPORT int64_t ss_string_find(const char *haystack, const char *needle) {
    if (haystack == NULL || needle == NULL) return -1;
    const char *hit = strstr(haystack, needle);
    return hit == NULL ? -1 : (int64_t)(hit - haystack);
}

/* Number of bytes in the string (NUL-terminated length), or 0 for NULL. */
SS_EXPORT int64_t ss_string_length(const char *text) {
    return text == NULL ? 0 : (int64_t)strlen(text);
}

/* Byte offset of the FIRST occurrence of byte `ch` in `text`, or -1 if absent.
 * `ch` is taken modulo 256 (the low byte). */
SS_EXPORT int64_t ss_string_find_char_first(const char *text, int32_t ch) {
    if (text == NULL) return -1;
    const char *hit = strchr(text, (int)(unsigned char)ch);
    return hit == NULL ? -1 : (int64_t)(hit - text);
}

/* Byte offset of the LAST occurrence of byte `ch` in `text`, or -1 if absent. */
SS_EXPORT int64_t ss_string_find_char_last(const char *text, int32_t ch) {
    if (text == NULL) return -1;
    const char *hit = strrchr(text, (int)(unsigned char)ch);
    return hit == NULL ? -1 : (int64_t)(hit - text);
}

/* Allocate a NUL-terminated decimal rendering of a signed Int64 value. The
 * caller receives a normal SemanticScript String pointer; there is no ownership
 * surface for freeing converted strings yet, matching string.concat's current
 * process-lifetime behavior. */
SS_EXPORT const char *ss_string_i64_to_string(int64_t value) {
    char tmp[32];
    int n = snprintf(tmp, sizeof tmp, "%lld", (long long)value);
    if (n < 0 || n >= (int)sizeof tmp) return NULL;
    char *out = (char *)malloc((size_t)n + 1);
    if (out == NULL) return NULL;
    memcpy(out, tmp, (size_t)n + 1);
    return out;
}
