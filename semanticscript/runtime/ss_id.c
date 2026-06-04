/*
 * ss_id.c - standard.id runtime helpers (WS3-129).
 *
 * String-returning helpers use the out-param ABI and are owned by this runtime.
 * The registry mirrors the other native runtimes: release validates pointer
 * membership by value before freeing, so stale/foreign pointers fail closed.
 */
#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "native_platform/ss_platform_entropy.h"
#include "native_platform/ss_platform_time.h"
#include "ss_runtime_export.h"

#define SS_ID_OK 0
#define SS_ID_ERR 1
#define SS_ID_MAX_TEXT 512

typedef struct { char **items; size_t count; size_t cap; } ss_id_registry;

static ss_id_registry g_id_strings;
static int64_t g_monotonic_counter = 0;

static int ss_id_track(char *buffer) {
    if (buffer == NULL) return 0;
    if (g_id_strings.count == g_id_strings.cap) {
        size_t next = g_id_strings.cap == 0 ? 16 : g_id_strings.cap * 2;
        char **grown;
        if (g_id_strings.cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(char *)) {
            return 0;
        }
        grown = (char **)realloc(g_id_strings.items, next * sizeof(char *));
        if (grown == NULL) return 0;
        g_id_strings.items = grown;
        g_id_strings.cap = next;
    }
    g_id_strings.items[g_id_strings.count++] = buffer;
    return 1;
}

static int ss_id_untrack(const char *buffer) {
    size_t i;
    for (i = 0; i < g_id_strings.count; i++) {
        if (g_id_strings.items[i] == buffer) {
            g_id_strings.items[i] = g_id_strings.items[g_id_strings.count - 1];
            g_id_strings.count--;
            return 1;
        }
    }
    return 0;
}

static int set_owned_out(char *buffer, const char **out) {
    if (out == NULL || buffer == NULL) {
        free(buffer);
        return SS_ID_ERR;
    }
    *out = NULL;
    if (!ss_id_track(buffer)) {
        free(buffer);
        return SS_ID_ERR;
    }
    *out = buffer;
    return SS_ID_OK;
}

static char *alloc_text(size_t len) {
    char *out;
    if (len > SS_ID_MAX_TEXT) return NULL;
    out = (char *)malloc(len + 1);
    if (out != NULL) out[len] = '\0';
    return out;
}

SS_EXPORT int32_t ss_id_uuid_v4(const char **out) {
    static const char hex[] = "0123456789abcdef";
    unsigned char bytes[16];
    char *text;
    int i;
    int p = 0;
    if (out == NULL) return SS_ID_ERR;
    *out = NULL;
    if (ss_platform_random_bytes(bytes, sizeof(bytes)) != 0) return SS_ID_ERR;
    bytes[6] = (unsigned char)((bytes[6] & 0x0fu) | 0x40u);
    bytes[8] = (unsigned char)((bytes[8] & 0x3fu) | 0x80u);
    text = alloc_text(36);
    if (text == NULL) return SS_ID_ERR;
    for (i = 0; i < 16; i++) {
        if (i == 4 || i == 6 || i == 8 || i == 10) text[p++] = '-';
        text[p++] = hex[(bytes[i] >> 4) & 0x0f];
        text[p++] = hex[bytes[i] & 0x0f];
    }
    text[p] = '\0';
    return set_owned_out(text, out);
}

static int64_t current_time_millis(void) {
    return (int64_t)ss_platform_wall_time_ms();
}

static void fill_seeded_random(unsigned char bytes[10], uint64_t seed) {
    int i;
    uint64_t state = seed == 0 ? 0x9e3779b97f4a7c15ULL : seed;
    for (i = 0; i < 10; i++) {
        state = state * 6364136223846793005ULL + 1442695040888963407ULL;
        bytes[i] = (unsigned char)(state >> 56);
    }
}

static unsigned read_random_base32(const unsigned char bytes[10], int bit) {
    unsigned value = 0;
    int k;
    for (k = 0; k < 5; k++) {
        int at = bit + k;
        int byte_index = at / 8;
        int bit_index = 7 - (at % 8);
        value = (value << 1) | ((bytes[byte_index] >> bit_index) & 1u);
    }
    return value;
}

static int make_ulid(uint64_t millis, const unsigned char random_part[10], const char **out) {
    static const char enc[] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ";
    char *text = alloc_text(26);
    int i;
    if (text == NULL) return SS_ID_ERR;
    for (i = 9; i >= 0; i--) {
        text[i] = enc[millis & 31u];
        millis >>= 5;
    }
    for (i = 10; i < 26; i++) {
        text[i] = enc[read_random_base32(random_part, (i - 10) * 5)];
    }
    text[26] = '\0';
    return set_owned_out(text, out);
}

SS_EXPORT int32_t ss_id_ulid_now(const char **out) {
    unsigned char random_part[10];
    int64_t now = current_time_millis();
    if (out == NULL || now < 0) return SS_ID_ERR;
    *out = NULL;
    if (ss_platform_random_bytes(random_part, sizeof(random_part)) != 0) return SS_ID_ERR;
    return make_ulid((uint64_t)now, random_part, out);
}

SS_EXPORT int32_t ss_id_ulid_from_seed(int64_t time_millis, int64_t seed, const char **out) {
    unsigned char random_part[10];
    if (out == NULL || time_millis < 0) return SS_ID_ERR;
    *out = NULL;
    fill_seeded_random(random_part, (uint64_t)seed);
    return make_ulid((uint64_t)time_millis, random_part, out);
}

SS_EXPORT int64_t ss_id_monotonic_next(void) {
    if (g_monotonic_counter == INT64_MAX) {
        return INT64_MAX;
    }
    return ++g_monotonic_counter;
}

SS_EXPORT int32_t ss_id_slugify(const char *text, const char **out) {
    size_t n;
    size_t i;
    size_t j = 0;
    int last_dash = 1;
    char *slug;
    if (out == NULL || text == NULL) return SS_ID_ERR;
    *out = NULL;
    n = strlen(text);
    if (n == 0 || n > SS_ID_MAX_TEXT) return SS_ID_ERR;
    slug = alloc_text(n);
    if (slug == NULL) return SS_ID_ERR;
    for (i = 0; i < n; i++) {
        unsigned char ch = (unsigned char)text[i];
        if (ch < 0x20 || ch == 0x7f) {
            free(slug);
            return SS_ID_ERR;
        }
        if (ch >= 'A' && ch <= 'Z') {
            slug[j++] = (char)(ch - 'A' + 'a');
            last_dash = 0;
        } else if ((ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9')) {
            slug[j++] = (char)ch;
            last_dash = 0;
        } else if (ch == ' ' || ch == '-' || ch == '_' || ch == '.' || ch == '/') {
            if (!last_dash) {
                slug[j++] = '-';
                last_dash = 1;
            }
        } else if (ch < 0x80) {
            if (!last_dash) {
                slug[j++] = '-';
                last_dash = 1;
            }
        } else {
            free(slug);
            return SS_ID_ERR;
        }
    }
    if (j > 0 && slug[j - 1] == '-') j--;
    if (j == 0) {
        free(slug);
        return SS_ID_ERR;
    }
    slug[j] = '\0';
    return set_owned_out(slug, out);
}

typedef struct {
    const char *major;
    size_t major_len;
    const char *minor;
    size_t minor_len;
    const char *patch;
    size_t patch_len;
    const char *pre;
    size_t pre_len;
    int has_pre;
} ss_semver;

static int is_ident_char(char c) {
    return isalnum((unsigned char)c) || c == '-';
}

static int parse_num(const char **p, const char **start, size_t *len) {
    const char *s = *p;
    if (!isdigit((unsigned char)*s)) return 0;
    *start = s;
    while (isdigit((unsigned char)**p)) (*p)++;
    *len = (size_t)(*p - s);
    if (*len > 1 && s[0] == '0') return 0;
    return 1;
}

static int validate_ident_list(const char *p, size_t len, int pre) {
    size_t i = 0;
    while (i < len) {
        size_t start = i;
        int numeric = 1;
        while (i < len && p[i] != '.') {
            if (!is_ident_char(p[i])) return 0;
            if (!isdigit((unsigned char)p[i])) numeric = 0;
            i++;
        }
        if (i == start) return 0;
        if (pre && numeric && i - start > 1 && p[start] == '0') return 0;
        if (i < len && p[i] == '.') i++;
    }
    return 1;
}

static int parse_semver(const char *input, ss_semver *out) {
    const char *p = input;
    const char *build;
    if (input == NULL || out == NULL) return 0;
    memset(out, 0, sizeof(*out));
    if (*p == 'v' || *p == 'V') p++;
    if (!parse_num(&p, &out->major, &out->major_len) || *p++ != '.') return 0;
    if (!parse_num(&p, &out->minor, &out->minor_len) || *p++ != '.') return 0;
    if (!parse_num(&p, &out->patch, &out->patch_len)) return 0;
    if (*p == '-') {
        const char *pre_start = ++p;
        while (*p != '\0' && *p != '+') p++;
        out->pre = pre_start;
        out->pre_len = (size_t)(p - pre_start);
        out->has_pre = 1;
        if (out->pre_len == 0 || !validate_ident_list(out->pre, out->pre_len, 1)) {
            return 0;
        }
    }
    if (*p == '+') {
        build = ++p;
        while (*p != '\0') p++;
        if (p == build || !validate_ident_list(build, (size_t)(p - build), 0)) return 0;
    }
    return *p == '\0';
}

static int cmp_num(const char *a, size_t alen, const char *b, size_t blen) {
    int r;
    if (alen != blen) return alen < blen ? -1 : 1;
    r = memcmp(a, b, alen);
    return r < 0 ? -1 : (r > 0 ? 1 : 0);
}

static int ident_numeric(const char *s, size_t n) {
    size_t i;
    for (i = 0; i < n; i++) {
        if (!isdigit((unsigned char)s[i])) return 0;
    }
    return 1;
}

static int cmp_ident(const char *a, size_t alen, const char *b, size_t blen) {
    int anum = ident_numeric(a, alen);
    int bnum = ident_numeric(b, blen);
    int r;
    if (anum && bnum) return cmp_num(a, alen, b, blen);
    if (anum != bnum) return anum ? -1 : 1;
    r = memcmp(a, b, alen < blen ? alen : blen);
    if (r != 0) return r < 0 ? -1 : 1;
    if (alen == blen) return 0;
    return alen < blen ? -1 : 1;
}

static int cmp_pre(const ss_semver *a, const ss_semver *b) {
    size_t ai = 0;
    size_t bi = 0;
    if (!a->has_pre && !b->has_pre) return 0;
    if (!a->has_pre) return 1;
    if (!b->has_pre) return -1;
    while (ai < a->pre_len && bi < b->pre_len) {
        size_t as = ai;
        size_t bs = bi;
        int r;
        while (ai < a->pre_len && a->pre[ai] != '.') ai++;
        while (bi < b->pre_len && b->pre[bi] != '.') bi++;
        r = cmp_ident(a->pre + as, ai - as, b->pre + bs, bi - bs);
        if (r != 0) return r;
        if (ai < a->pre_len && a->pre[ai] == '.') ai++;
        if (bi < b->pre_len && b->pre[bi] == '.') bi++;
    }
    if (ai == a->pre_len && bi == b->pre_len) return 0;
    return ai == a->pre_len ? -1 : 1;
}

SS_EXPORT int32_t ss_id_semver_compare(const char *left, const char *right, int32_t *out) {
    ss_semver l;
    ss_semver r;
    int c;
    if (out == NULL) return SS_ID_ERR;
    *out = 0;
    if (!parse_semver(left, &l) || !parse_semver(right, &r)) return SS_ID_ERR;
    c = cmp_num(l.major, l.major_len, r.major, r.major_len);
    if (c == 0) c = cmp_num(l.minor, l.minor_len, r.minor, r.minor_len);
    if (c == 0) c = cmp_num(l.patch, l.patch_len, r.patch, r.patch_len);
    if (c == 0) c = cmp_pre(&l, &r);
    *out = c < 0 ? -1 : (c > 0 ? 1 : 0);
    return SS_ID_OK;
}

SS_EXPORT int32_t ss_id_release(const char *text) {
    if (text == NULL || !ss_id_untrack(text)) {
        return 0;
    }
    free((void *)text);
    return 1;
}
