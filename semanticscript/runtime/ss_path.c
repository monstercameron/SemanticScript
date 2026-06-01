/*
 * ss_path.c - standard.path runtime helpers (WS3-111).
 *
 * The C ABI is intentionally small: fallible builders use the existing
 * out-param convention (`int fn(args..., const char **out)`) and return 0 on
 * success, nonzero on PathError. Successful string results are heap-allocated
 * inside this runtime and must be released with ss_path_release, which validates
 * ownership by pointer value before freeing.
 */
#include <ctype.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "ss_runtime_export.h"

#define SS_PATH_OK 0
#define SS_PATH_ERR 1
#define SS_PATH_MAX_INPUT 4096
#define SS_PATH_MAX_DECODE_PASSES 8

typedef struct { char **items; size_t count; size_t cap; } ss_path_registry;

static ss_path_registry g_path_strings;

static int ss_path_track(char *buffer) {
    if (buffer == NULL) return 0;
    if (g_path_strings.count == g_path_strings.cap) {
        size_t next = g_path_strings.cap == 0 ? 16 : g_path_strings.cap * 2;
        char **grown;
        if (g_path_strings.cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(char *)) {
            return 0;
        }
        grown = (char **)realloc(g_path_strings.items, next * sizeof(char *));
        if (grown == NULL) return 0;
        g_path_strings.items = grown;
        g_path_strings.cap = next;
    }
    g_path_strings.items[g_path_strings.count++] = buffer;
    return 1;
}

static int ss_path_untrack(const char *buffer) {
    size_t i;
    for (i = 0; i < g_path_strings.count; i++) {
        if (g_path_strings.items[i] == buffer) {
            g_path_strings.items[i] = g_path_strings.items[g_path_strings.count - 1];
            g_path_strings.count--;
            return 1;
        }
    }
    return 0;
}

static char *ss_path_strdup_owned(const char *text) {
    size_t n;
    char *out;
    if (text == NULL) return NULL;
    n = strlen(text);
    if (n > SS_PATH_MAX_INPUT) return NULL;
    out = (char *)malloc(n + 1);
    if (out == NULL) return NULL;
    memcpy(out, text, n + 1);
    if (!ss_path_track(out)) {
        free(out);
        return NULL;
    }
    return out;
}

static int hex_value(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
    if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
    return -1;
}

static int percent_decode_once(const char *input, char *out, int *changed) {
    size_t i = 0;
    size_t j = 0;
    *changed = 0;
    while (input[i] != '\0') {
        if (j >= SS_PATH_MAX_INPUT) return 0;
        if (input[i] == '%') {
            int hi;
            int lo;
            if (input[i + 1] == '\0' || input[i + 2] == '\0') return 0;
            hi = hex_value(input[i + 1]);
            lo = hex_value(input[i + 2]);
            if (hi < 0 || lo < 0) return 0;
            out[j++] = (char)((hi << 4) | lo);
            i += 3;
            *changed = 1;
        } else {
            out[j++] = input[i++];
        }
    }
    out[j] = '\0';
    return 1;
}

static int iterative_percent_decode(const char *input, char *out) {
    char cur[SS_PATH_MAX_INPUT + 1];
    char next[SS_PATH_MAX_INPUT + 1];
    size_t n;
    int pass;
    if (input == NULL) return 0;
    n = strlen(input);
    if (n == 0 || n > SS_PATH_MAX_INPUT) return 0;
    memcpy(cur, input, n + 1);
    for (pass = 0; pass < SS_PATH_MAX_DECODE_PASSES; pass++) {
        int changed = 0;
        if (!percent_decode_once(cur, next, &changed)) return 0;
        memcpy(cur, next, strlen(next) + 1);
        if (!changed) {
            memcpy(out, cur, strlen(cur) + 1);
            return 1;
        }
    }
    return 0;
}

static int is_drive_prefix(const char *s) {
    return isalpha((unsigned char)s[0]) && s[1] == ':';
}

static int append_segment(char *out, size_t *out_len, const char *start, size_t len) {
    if (*out_len != 0) {
        if (*out_len + 1 > SS_PATH_MAX_INPUT) return 0;
        out[(*out_len)++] = '/';
    }
    if (*out_len + len > SS_PATH_MAX_INPUT) return 0;
    memcpy(out + *out_len, start, len);
    *out_len += len;
    out[*out_len] = '\0';
    return 1;
}

static int normalize_lexical(const char *input, char *out) {
    char decoded[SS_PATH_MAX_INPUT + 1];
    char unified[SS_PATH_MAX_INPUT + 1];
    size_t i;
    size_t out_len = 0;
    if (!iterative_percent_decode(input, decoded)) return 0;
    if (decoded[0] == '/' || decoded[0] == '\\') return 0;
    if (is_drive_prefix(decoded)) return 0;
    for (i = 0; decoded[i] != '\0'; i++) {
        unsigned char ch = (unsigned char)decoded[i];
        if (ch == '\0' || ch < 0x20) return 0;
        if (decoded[i] == ':') return 0;
        unified[i] = (decoded[i] == '\\') ? '/' : decoded[i];
    }
    unified[i] = '\0';
    if (unified[0] == '\0') return 0;
    i = 0;
    out[0] = '\0';
    while (unified[i] != '\0') {
        size_t start;
        size_t len;
        while (unified[i] == '/') i++;
        start = i;
        while (unified[i] != '\0' && unified[i] != '/') i++;
        len = i - start;
        if (len == 0) break;
        if (len == 1 && unified[start] == '.') {
            continue;
        }
        if (len == 2 && unified[start] == '.' && unified[start + 1] == '.') {
            return 0;
        }
        if (!append_segment(out, &out_len, unified + start, len)) return 0;
    }
    if (out_len == 0) {
        out[0] = '.';
        out[1] = '\0';
    }
    return 1;
}

static int set_owned_out(const char *text, const char **out) {
    char *owned;
    if (out == NULL) return SS_PATH_ERR;
    *out = NULL;
    owned = ss_path_strdup_owned(text);
    if (owned == NULL) return SS_PATH_ERR;
    *out = owned;
    return SS_PATH_OK;
}

SS_EXPORT int32_t ss_path_from_literal(const char *literal, const char **out) {
    char normalized[SS_PATH_MAX_INPUT + 1];
    if (!normalize_lexical(literal, normalized)) return SS_PATH_ERR;
    return set_owned_out(normalized, out);
}

SS_EXPORT int32_t ss_path_normalize(const char *input, const char **out) {
    return ss_path_from_literal(input, out);
}

SS_EXPORT int32_t ss_path_join_under_root(const char *root, const char *child, const char **out) {
    char root_norm[SS_PATH_MAX_INPUT + 1];
    char child_norm[SS_PATH_MAX_INPUT + 1];
    char joined[SS_PATH_MAX_INPUT + 1];
    size_t root_len;
    size_t child_len;
    if (!normalize_lexical(root, root_norm) || !normalize_lexical(child, child_norm)) {
        return SS_PATH_ERR;
    }
    if (strcmp(root_norm, ".") == 0) {
        return set_owned_out(child_norm, out);
    }
    root_len = strlen(root_norm);
    child_len = strlen(child_norm);
    if (root_len + 1 + child_len > SS_PATH_MAX_INPUT) return SS_PATH_ERR;
    memcpy(joined, root_norm, root_len);
    joined[root_len] = '/';
    memcpy(joined + root_len + 1, child_norm, child_len + 1);
    return set_owned_out(joined, out);
}

SS_EXPORT int32_t ss_path_basename(const char *input, const char **out) {
    char normalized[SS_PATH_MAX_INPUT + 1];
    const char *slash;
    if (!normalize_lexical(input, normalized)) return SS_PATH_ERR;
    slash = strrchr(normalized, '/');
    return set_owned_out(slash == NULL ? normalized : slash + 1, out);
}

SS_EXPORT int32_t ss_path_extension(const char *input, const char **out) {
    char normalized[SS_PATH_MAX_INPUT + 1];
    const char *base;
    const char *dot;
    if (!normalize_lexical(input, normalized)) return SS_PATH_ERR;
    base = strrchr(normalized, '/');
    base = base == NULL ? normalized : base + 1;
    dot = strrchr(base, '.');
    if (dot == NULL || dot == base || dot[1] == '\0') {
        return set_owned_out("", out);
    }
    return set_owned_out(dot, out);
}

SS_EXPORT int32_t ss_path_parent(const char *input, const char **out) {
    char normalized[SS_PATH_MAX_INPUT + 1];
    char *slash;
    if (!normalize_lexical(input, normalized)) return SS_PATH_ERR;
    slash = strrchr(normalized, '/');
    if (slash == NULL) {
        return set_owned_out(".", out);
    }
    *slash = '\0';
    return set_owned_out(normalized, out);
}

SS_EXPORT int32_t ss_path_is_child_of(const char *root, const char *child, int32_t *out) {
    char root_norm[SS_PATH_MAX_INPUT + 1];
    char child_norm[SS_PATH_MAX_INPUT + 1];
    size_t root_len;
    if (out == NULL) return SS_PATH_ERR;
    *out = 0;
    if (!normalize_lexical(root, root_norm) || !normalize_lexical(child, child_norm)) {
        return SS_PATH_ERR;
    }
    if (strcmp(root_norm, ".") == 0) {
        *out = strcmp(child_norm, ".") == 0 ? 0 : 1;
        return SS_PATH_OK;
    }
    root_len = strlen(root_norm);
    if (strncmp(child_norm, root_norm, root_len) == 0 && child_norm[root_len] == '/') {
        *out = 1;
    }
    return SS_PATH_OK;
}

SS_EXPORT const char *ss_path_separator(void) {
#if defined(_WIN32)
    return "\\";
#else
    return "/";
#endif
}

SS_EXPORT int32_t ss_path_release(const char *path) {
    if (path == NULL || !ss_path_untrack(path)) {
        return 0;
    }
    free((void *)path);
    return 1;
}
