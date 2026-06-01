#include "sem_json_runtime.h"

#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <math.h>      /* R-261: isfinite — JSON has no inf/nan */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * Container kind tracking. The builder maintains a small stack so we
 * know whether the most recent open was an object (where field names
 * are required) or an array (where they're forbidden), and whether
 * we're at the first sibling (so we can decide between writing a
 * leading comma or not). The document parser uses the same ceiling as
 * its runtime recursion guard for untrusted nested JSON.
 */
#define SS_JSON_MAX_NESTING_DEPTH 16

typedef enum SSJsonContainerKind {
    SS_JSON_CONTAINER_NONE   = 0,
    SS_JSON_CONTAINER_OBJECT = 1,
    SS_JSON_CONTAINER_ARRAY  = 2
} SSJsonContainerKind;

typedef struct SSJsonContainerFrame {
    SSJsonContainerKind kind;
    int has_emitted_first_element;
} SSJsonContainerFrame;

struct SSJsonBuilder {
    char *buffer;             /* heap-allocated, null-terminated at all times */
    size_t capacity;          /* total bytes available (including the trailing null) */
    size_t length;            /* bytes used, excluding the trailing null */
    int error_state;          /* SS_JSON_OK or the first SS_JSON_ERR_* that fired */
    SSJsonContainerFrame stack[SS_JSON_MAX_NESTING_DEPTH];
    int stack_depth;
};

/* ----- internal helpers ----- */

static int builder_ok(const SSJsonBuilder *builder) {
    return builder != NULL && builder->error_state == SS_JSON_OK;
}

static int builder_append_byte(SSJsonBuilder *builder, char byte) {
    if (builder->length + 1 >= builder->capacity) {
        builder->error_state = SS_JSON_ERR_OVERFLOW;
        return SS_JSON_ERR_OVERFLOW;
    }
    builder->buffer[builder->length++] = byte;
    builder->buffer[builder->length] = '\0';
    return SS_JSON_OK;
}

static int builder_append_bytes(
    SSJsonBuilder *builder, const char *bytes, size_t byte_count
) {
    if (builder->length + byte_count >= builder->capacity) {
        builder->error_state = SS_JSON_ERR_OVERFLOW;
        return SS_JSON_ERR_OVERFLOW;
    }
    memcpy(builder->buffer + builder->length, bytes, byte_count);
    builder->length += byte_count;
    builder->buffer[builder->length] = '\0';
    return SS_JSON_OK;
}

static int builder_append_cstring(SSJsonBuilder *builder, const char *text) {
    return builder_append_bytes(builder, text, strlen(text));
}

/* Append a JSON-quoted, escape-correct string literal (including the
 * surrounding double quotes). Per RFC 8259 we must escape ", \, and
 * every control byte U+0000..U+001F. We also escape DEL (0x7F) and
 * forward slash is left untouched (allowed but not required). */
static int builder_append_quoted_string(SSJsonBuilder *builder, const char *text) {
    if (text == NULL) {
        return builder_append_cstring(builder, "null");
    }
    int rc = builder_append_byte(builder, '"');
    if (rc != SS_JSON_OK) return rc;
    const unsigned char *scan = (const unsigned char *)text;
    while (*scan != '\0') {
        unsigned char byte = *scan++;
        switch (byte) {
            case '"':  rc = builder_append_bytes(builder, "\\\"", 2); break;
            case '\\': rc = builder_append_bytes(builder, "\\\\", 2); break;
            case '\b': rc = builder_append_bytes(builder, "\\b", 2); break;
            case '\f': rc = builder_append_bytes(builder, "\\f", 2); break;
            case '\n': rc = builder_append_bytes(builder, "\\n", 2); break;
            case '\r': rc = builder_append_bytes(builder, "\\r", 2); break;
            case '\t': rc = builder_append_bytes(builder, "\\t", 2); break;
            default:
                if (byte < 0x20) {
                    char escaped[7];
                    int written = snprintf(escaped, sizeof(escaped),
                                           "\\u%04x", byte);
                    if (written < 0 || written >= (int)sizeof(escaped)) {
                        rc = SS_JSON_ERR_OVERFLOW;
                        break;
                    }
                    rc = builder_append_bytes(builder, escaped, (size_t)written);
                } else {
                    rc = builder_append_byte(builder, (char)byte);
                }
        }
        if (rc != SS_JSON_OK) return rc;
    }
    return builder_append_byte(builder, '"');
}

static int builder_write_sibling_separator(SSJsonBuilder *builder) {
    if (builder->stack_depth == 0) {
        return SS_JSON_OK;
    }
    SSJsonContainerFrame *top = &builder->stack[builder->stack_depth - 1];
    if (top->has_emitted_first_element) {
        return builder_append_byte(builder, ',');
    }
    top->has_emitted_first_element = 1;
    return SS_JSON_OK;
}

static int builder_require_container(
    SSJsonBuilder *builder, SSJsonContainerKind required
) {
    if (builder->stack_depth == 0
        || builder->stack[builder->stack_depth - 1].kind != required) {
        builder->error_state = SS_JSON_ERR_STRUCTURE;
        return SS_JSON_ERR_STRUCTURE;
    }
    return SS_JSON_OK;
}

static int builder_push(
    SSJsonBuilder *builder, SSJsonContainerKind kind
) {
    if (builder->stack_depth >= SS_JSON_MAX_NESTING_DEPTH) {
        builder->error_state = SS_JSON_ERR_STRUCTURE;
        return SS_JSON_ERR_STRUCTURE;
    }
    builder->stack[builder->stack_depth].kind = kind;
    builder->stack[builder->stack_depth].has_emitted_first_element = 0;
    builder->stack_depth++;
    return SS_JSON_OK;
}

static int builder_pop(SSJsonBuilder *builder, SSJsonContainerKind expected) {
    int rc = builder_require_container(builder, expected);
    if (rc != SS_JSON_OK) return rc;
    builder->stack_depth--;
    return SS_JSON_OK;
}

/* Marks the parent (one level below the current frame) as having
 * emitted a sibling, so any FOLLOWING field at the parent level will
 * be prefixed with a comma. Called immediately after a nested
 * container closes. */
static void builder_record_emitted_at_parent(SSJsonBuilder *builder) {
    if (builder->stack_depth >= 1) {
        builder->stack[builder->stack_depth - 1].has_emitted_first_element = 1;
    }
}

/* ----- builder public API ----- */

SSJsonBuilder *ss_json_builder_create(size_t capacity) {
    if (capacity < 2) {
        /* Need room for at least `{}` plus the terminator. */
        return NULL;
    }
    SSJsonBuilder *builder = (SSJsonBuilder *)calloc(1, sizeof(*builder));
    if (builder == NULL) {
        return NULL;
    }
    builder->buffer = (char *)malloc(capacity);
    if (builder->buffer == NULL) {
        free(builder);
        return NULL;
    }
    builder->buffer[0] = '\0';
    builder->capacity = capacity;
    builder->length = 0;
    builder->error_state = SS_JSON_OK;
    builder->stack_depth = 0;
    return builder;
}

void ss_json_builder_destroy(SSJsonBuilder *builder) {
    if (builder == NULL) {
        return;
    }
    free(builder->buffer);
    free(builder);
}

int ss_json_builder_object_open(SSJsonBuilder *builder) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_write_sibling_separator(builder);
    if (rc != SS_JSON_OK) return rc;
    rc = builder_append_byte(builder, '{');
    if (rc != SS_JSON_OK) return rc;
    return builder_push(builder, SS_JSON_CONTAINER_OBJECT);
}

int ss_json_builder_object_close(SSJsonBuilder *builder) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_pop(builder, SS_JSON_CONTAINER_OBJECT);
    if (rc != SS_JSON_OK) return rc;
    rc = builder_append_byte(builder, '}');
    if (rc != SS_JSON_OK) return rc;
    builder_record_emitted_at_parent(builder);
    return SS_JSON_OK;
}

int ss_json_builder_array_open(SSJsonBuilder *builder) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_write_sibling_separator(builder);
    if (rc != SS_JSON_OK) return rc;
    rc = builder_append_byte(builder, '[');
    if (rc != SS_JSON_OK) return rc;
    return builder_push(builder, SS_JSON_CONTAINER_ARRAY);
}

int ss_json_builder_array_close(SSJsonBuilder *builder) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_pop(builder, SS_JSON_CONTAINER_ARRAY);
    if (rc != SS_JSON_OK) return rc;
    rc = builder_append_byte(builder, ']');
    if (rc != SS_JSON_OK) return rc;
    builder_record_emitted_at_parent(builder);
    return SS_JSON_OK;
}

/* Common prefix for a named field: maybe-leading-comma, "name":. */
static int builder_emit_field_prefix(
    SSJsonBuilder *builder, const char *field_name
) {
    int rc = builder_require_container(builder, SS_JSON_CONTAINER_OBJECT);
    if (rc != SS_JSON_OK) return rc;
    rc = builder_write_sibling_separator(builder);
    if (rc != SS_JSON_OK) return rc;
    rc = builder_append_quoted_string(builder, field_name);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_byte(builder, ':');
}

/* Common prefix for an array element: maybe-leading-comma. */
static int builder_emit_element_prefix(SSJsonBuilder *builder) {
    int rc = builder_require_container(builder, SS_JSON_CONTAINER_ARRAY);
    if (rc != SS_JSON_OK) return rc;
    return builder_write_sibling_separator(builder);
}

int ss_json_builder_field_int64(
    SSJsonBuilder *builder, const char *field_name, long long value
) {
    if (!builder_ok(builder) || field_name == NULL) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_field_prefix(builder, field_name);
    if (rc != SS_JSON_OK) return rc;
    char number_text[32];
    int written = snprintf(number_text, sizeof(number_text), "%lld", value);
    if (written < 0 || written >= (int)sizeof(number_text)) {
        builder->error_state = SS_JSON_ERR_OVERFLOW;
        return SS_JSON_ERR_OVERFLOW;
    }
    return builder_append_bytes(builder, number_text, (size_t)written);
}

int ss_json_builder_field_double(
    SSJsonBuilder *builder, const char *field_name, double value
) {
    if (!builder_ok(builder) || field_name == NULL) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_field_prefix(builder, field_name);
    if (rc != SS_JSON_OK) return rc;
    char number_text[32];
    /* %.17g is the shortest round-trippable representation for IEEE
     * 754 double. JSON itself doesn't constrain the format beyond the
     * grammar; this matches Python's json.dumps default. */
    int written;
    if (!isfinite(value)) {  /* R-261: inf/nan are not valid JSON -> emit null */
        memcpy(number_text, "null", 5);
        written = 4;
    } else {
        written = snprintf(number_text, sizeof(number_text), "%.17g", value);
    }
    if (written < 0 || written >= (int)sizeof(number_text)) {
        builder->error_state = SS_JSON_ERR_OVERFLOW;
        return SS_JSON_ERR_OVERFLOW;
    }
    return builder_append_bytes(builder, number_text, (size_t)written);
}

int ss_json_builder_field_bool(
    SSJsonBuilder *builder, const char *field_name, int value_truthiness
) {
    if (!builder_ok(builder) || field_name == NULL) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_field_prefix(builder, field_name);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_cstring(builder, value_truthiness ? "true" : "false");
}

int ss_json_builder_field_string(
    SSJsonBuilder *builder, const char *field_name, const char *value
) {
    if (!builder_ok(builder) || field_name == NULL) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_field_prefix(builder, field_name);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_quoted_string(builder, value);
}

int ss_json_builder_field_null(
    SSJsonBuilder *builder, const char *field_name
) {
    if (!builder_ok(builder) || field_name == NULL) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_field_prefix(builder, field_name);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_cstring(builder, "null");
}

int ss_json_builder_element_int64(SSJsonBuilder *builder, long long value) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_element_prefix(builder);
    if (rc != SS_JSON_OK) return rc;
    char number_text[32];
    int written = snprintf(number_text, sizeof(number_text), "%lld", value);
    if (written < 0 || written >= (int)sizeof(number_text)) {
        builder->error_state = SS_JSON_ERR_OVERFLOW;
        return SS_JSON_ERR_OVERFLOW;
    }
    return builder_append_bytes(builder, number_text, (size_t)written);
}

int ss_json_builder_element_double(SSJsonBuilder *builder, double value) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_element_prefix(builder);
    if (rc != SS_JSON_OK) return rc;
    char number_text[32];
    int written;
    if (!isfinite(value)) {  /* R-261: inf/nan are not valid JSON -> emit null */
        memcpy(number_text, "null", 5);
        written = 4;
    } else {
        written = snprintf(number_text, sizeof(number_text), "%.17g", value);
    }
    if (written < 0 || written >= (int)sizeof(number_text)) {
        builder->error_state = SS_JSON_ERR_OVERFLOW;
        return SS_JSON_ERR_OVERFLOW;
    }
    return builder_append_bytes(builder, number_text, (size_t)written);
}

int ss_json_builder_element_bool(SSJsonBuilder *builder, int value_truthiness) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_element_prefix(builder);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_cstring(builder, value_truthiness ? "true" : "false");
}

int ss_json_builder_element_string(SSJsonBuilder *builder, const char *value) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_element_prefix(builder);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_quoted_string(builder, value);
}

int ss_json_builder_element_null(SSJsonBuilder *builder) {
    if (!builder_ok(builder)) return SS_JSON_ERR_CONFIG;
    int rc = builder_emit_element_prefix(builder);
    if (rc != SS_JSON_OK) return rc;
    return builder_append_cstring(builder, "null");
}

const char *ss_json_builder_finish(SSJsonBuilder *builder) {
    if (builder == NULL || builder->error_state != SS_JSON_OK) {
        return NULL;
    }
    return builder->buffer;
}

size_t ss_json_builder_length(const SSJsonBuilder *builder) {
    if (builder == NULL) return 0;
    return builder->length;
}

int ss_json_stringify_string(
    const char *value,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (scratch == NULL || out == NULL || scratch_capacity < 2) {
        return SS_JSON_ERR_CONFIG;
    }
    *out = NULL;
    SSJsonBuilder builder;
    memset(&builder, 0, sizeof(builder));
    builder.buffer = scratch;
    builder.capacity = (size_t)scratch_capacity;
    builder.length = 0;
    builder.error_state = SS_JSON_OK;
    builder.buffer[0] = '\0';
    int rc = builder_append_quoted_string(&builder, value);
    if (rc != SS_JSON_OK) {
        scratch[0] = '\0';
        return rc;
    }
    *out = scratch;
    return SS_JSON_OK;
}

int ss_json_stringify_int64(
    long long value,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (scratch == NULL || out == NULL || scratch_capacity < 2) {
        return SS_JSON_ERR_CONFIG;
    }
    *out = NULL;
    SSJsonBuilder builder;
    memset(&builder, 0, sizeof(builder));
    builder.buffer = scratch;
    builder.capacity = (size_t)scratch_capacity;
    builder.length = 0;
    builder.error_state = SS_JSON_OK;
    builder.buffer[0] = '\0';
    char number_text[32];
    int written = snprintf(number_text, sizeof(number_text), "%lld", value);
    if (written < 0 || written >= (int)sizeof(number_text)) {
        scratch[0] = '\0';
        return SS_JSON_ERR_OVERFLOW;
    }
    int rc = builder_append_bytes(&builder, number_text, (size_t)written);
    if (rc != SS_JSON_OK) {
        scratch[0] = '\0';
        return rc;
    }
    *out = scratch;
    return SS_JSON_OK;
}

int ss_json_stringify_double(
    double value,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (scratch == NULL || out == NULL || scratch_capacity < 2) {
        return SS_JSON_ERR_CONFIG;
    }
    *out = NULL;
    SSJsonBuilder builder;
    memset(&builder, 0, sizeof(builder));
    builder.buffer = scratch;
    builder.capacity = (size_t)scratch_capacity;
    builder.length = 0;
    builder.error_state = SS_JSON_OK;
    builder.buffer[0] = '\0';
    char number_text[32];
    int written;
    if (!isfinite(value)) {  /* R-261: inf/nan are not valid JSON -> emit null */
        memcpy(number_text, "null", 5);
        written = 4;
    } else {
        written = snprintf(number_text, sizeof(number_text), "%.17g", value);
    }
    if (written < 0 || written >= (int)sizeof(number_text)) {
        scratch[0] = '\0';
        return SS_JSON_ERR_OVERFLOW;
    }
    int rc = builder_append_bytes(&builder, number_text, (size_t)written);
    if (rc != SS_JSON_OK) {
        scratch[0] = '\0';
        return rc;
    }
    *out = scratch;
    return SS_JSON_OK;
}

int ss_json_stringify_bool(
    int value_truthiness,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (scratch == NULL || out == NULL || scratch_capacity < 2) {
        return SS_JSON_ERR_CONFIG;
    }
    *out = NULL;
    SSJsonBuilder builder;
    memset(&builder, 0, sizeof(builder));
    builder.buffer = scratch;
    builder.capacity = (size_t)scratch_capacity;
    builder.length = 0;
    builder.error_state = SS_JSON_OK;
    builder.buffer[0] = '\0';
    int rc = builder_append_cstring(
        &builder, value_truthiness ? "true" : "false");
    if (rc != SS_JSON_OK) {
        scratch[0] = '\0';
        return rc;
    }
    *out = scratch;
    return SS_JSON_OK;
}

/* ----- finder (decode) helpers ----- */

static const char *skip_whitespace(const char *scan) {
    while (*scan == ' ' || *scan == '\t' || *scan == '\n' || *scan == '\r') {
        ++scan;
    }
    return scan;
}

/* Skip over one JSON value at *scan, returning a pointer just past the
 * end of that value. Returns NULL on malformed input. Handles strings
 * (including escapes), numbers, true/false/null, nested objects, and
 * nested arrays. Used to walk past values at the wrong key when
 * searching for a target field name. */
static const char *skip_value(const char *scan) {
    scan = skip_whitespace(scan);
    if (*scan == '"') {
        ++scan;
        while (*scan != '\0') {
            if (*scan == '\\' && scan[1] != '\0') {
                scan += 2;
                continue;
            }
            if (*scan == '"') {
                return scan + 1;
            }
            ++scan;
        }
        return NULL;
    }
    if (*scan == '{' || *scan == '[') {
        char open = *scan;
        char close = (open == '{') ? '}' : ']';
        int depth = 1;
        ++scan;
        while (*scan != '\0' && depth > 0) {
            if (*scan == '"') {
                /* Strings inside containers can hold quoted braces;
                 * burn through them so depth tracking isn't fooled. */
                ++scan;
                while (*scan != '\0' && *scan != '"') {
                    if (*scan == '\\' && scan[1] != '\0') {
                        scan += 2;
                    } else {
                        ++scan;
                    }
                }
                if (*scan == '"') ++scan;
                continue;
            }
            if (*scan == open) ++depth;
            else if (*scan == close) --depth;
            ++scan;
        }
        return depth == 0 ? scan : NULL;
    }
    /* Literal (true/false/null) or number — scan until a structural
     * char or whitespace. */
    while (*scan != '\0'
           && *scan != ','
           && *scan != '}'
           && *scan != ']'
           && *scan != ' '
           && *scan != '\t'
           && *scan != '\n'
           && *scan != '\r') {
        ++scan;
    }
    return scan;
}

/* Find the value position for `field_name` at the top level of
 * `json_text`. Returns a pointer to the first byte of the value (after
 * the ':' and leading whitespace), or NULL if absent. */
static const char *find_field_value(
    const char *json_text, const char *field_name
) {
    if (json_text == NULL || field_name == NULL) return NULL;
    size_t name_length = strlen(field_name);
    const char *scan = skip_whitespace(json_text);
    if (*scan != '{') return NULL;
    ++scan;
    while (1) {
        scan = skip_whitespace(scan);
        if (*scan == '}') return NULL;
        if (*scan != '"') return NULL;
        ++scan;
        const char *key_start = scan;
        while (*scan != '\0') {
            if (*scan == '\\' && scan[1] != '\0') {
                scan += 2;
                continue;
            }
            if (*scan == '"') break;
            ++scan;
        }
        if (*scan != '"') return NULL;
        size_t key_length = (size_t)(scan - key_start);
        ++scan;  /* past closing quote */
        scan = skip_whitespace(scan);
        if (*scan != ':') return NULL;
        ++scan;
        scan = skip_whitespace(scan);
        if (key_length == name_length
            && memcmp(key_start, field_name, key_length) == 0) {
            return scan;
        }
        const char *value_end = skip_value(scan);
        if (value_end == NULL) return NULL;
        scan = skip_whitespace(value_end);
        if (*scan == ',') {
            ++scan;
            continue;
        }
        if (*scan == '}') {
            return NULL;
        }
        return NULL;
    }
}

int ss_json_has_field(const char *json_text, const char *field_name) {
    return find_field_value(json_text, field_name) != NULL ? 1 : 0;
}

/* Parse exactly four hex digits at `p` into a 0..0xFFFF value, or -1 if any of
 * the four is not a hex digit (a NUL stops it too, since NUL is not hex). */
static int parse_hex4(const char *p) {
    int value = 0;
    for (int i = 0; i < 4; ++i) {
        char c = p[i];
        int digit;
        if (c >= '0' && c <= '9') digit = c - '0';
        else if (c >= 'a' && c <= 'f') digit = 10 + (c - 'a');
        else if (c >= 'A' && c <= 'F') digit = 10 + (c - 'A');
        else return -1;
        value = (value << 4) | digit;
    }
    return value;
}

/* Decode the four-hex-digit \uXXXX escape at `hex_chars` into UTF-8 bytes,
 * writing up to 4 bytes into `out` (out must hold >= 4). Returns bytes written,
 * or -1 on malformed hex / a forbidden NUL. R-259: a high surrogate (U+D800..
 * U+DBFF) immediately followed by a `\uXXXX` low surrogate (U+DC00..U+DFFF) is
 * combined into the real astral code point (4-byte UTF-8); `*extra_consumed` is
 * set to 6 (the trailing `\uXXXX`) so the caller advances past it. A lone or
 * unpaired surrogate still writes U+FFFD. */
static int decode_unicode_escape(const char *hex_chars, char *out,
                                 int *extra_consumed) {
    *extra_consumed = 0;
    int code_point = parse_hex4(hex_chars);
    if (code_point < 0) return -1;
    if (code_point >= 0xD800 && code_point <= 0xDBFF) {
        /* R-259: try to pair with a trailing \uXXXX low surrogate. */
        if (hex_chars[4] == '\\' && hex_chars[5] == 'u') {
            int low = parse_hex4(hex_chars + 6);
            if (low >= 0xDC00 && low <= 0xDFFF) {
                int cp = 0x10000
                    + (((code_point - 0xD800) << 10) | (low - 0xDC00));
                *extra_consumed = 6;  /* the paired \uXXXX */
                out[0] = (char)(0xF0 | (cp >> 18));
                out[1] = (char)(0x80 | ((cp >> 12) & 0x3F));
                out[2] = (char)(0x80 | ((cp >> 6) & 0x3F));
                out[3] = (char)(0x80 | (cp & 0x3F));
                return 4;
            }
        }
        /* lone high surrogate -> U+FFFD */
        out[0] = (char)0xEF; out[1] = (char)0xBF; out[2] = (char)0xBD;
        return 3;
    }
    if (code_point == 0) {
        /* R-192: U+0000 decodes to a literal NUL, but SemanticScript Strings
         * (and this runtime's field names) are NUL-terminated `char *`. An
         * embedded NUL truncates the value, so `"admin\u0000guest"` would read as
         * `admin` and a field `"user\u0000id"` could compare equal to `"user"` —
         * letting untrusted JSON smuggle a hidden suffix past length-based
         * validators, auth/role checks, field lookups, and SQL binds. Reject as
         * malformed rather than decode it. (Other control codes are left intact:
         * they are valid JSON and do not break a NUL-terminated string.) */
        return -1;
    }
    if (code_point >= 0xD800 && code_point <= 0xDFFF) {
        /* Lone surrogate — emit U+FFFD. */
        out[0] = (char)0xEF;
        out[1] = (char)0xBF;
        out[2] = (char)0xBD;
        return 3;
    }
    if (code_point < 0x80) {
        out[0] = (char)code_point;
        return 1;
    }
    if (code_point < 0x800) {
        out[0] = (char)(0xC0 | (code_point >> 6));
        out[1] = (char)(0x80 | (code_point & 0x3F));
        return 2;
    }
    out[0] = (char)(0xE0 | (code_point >> 12));
    out[1] = (char)(0x80 | ((code_point >> 6) & 0x3F));
    out[2] = (char)(0x80 | (code_point & 0x3F));
    return 3;
}

const char *ss_json_find_string(
    const char *json_text,
    const char *field_name,
    char *scratch_buffer,
    size_t scratch_capacity
) {
    if (scratch_buffer == NULL || scratch_capacity == 0) return NULL;
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL || *value_start != '"') return NULL;
    const char *scan = value_start + 1;
    size_t written = 0;
    while (*scan != '\0' && *scan != '"') {
        if (*scan != '\\') {
            if (written + 1 >= scratch_capacity) return NULL;
            scratch_buffer[written++] = *scan++;
            continue;
        }
        char escape = scan[1];
        if (escape == '\0') return NULL;
        char emit_buf[4];   /* R-259: an astral code point is 4 UTF-8 bytes */
        int emit_count;
        int extra_consumed = 0;
        switch (escape) {
            case '"':  emit_buf[0] = '"';  emit_count = 1; break;
            case '\\': emit_buf[0] = '\\'; emit_count = 1; break;
            case '/':  emit_buf[0] = '/';  emit_count = 1; break;
            case 'b':  emit_buf[0] = '\b'; emit_count = 1; break;
            case 'f':  emit_buf[0] = '\f'; emit_count = 1; break;
            case 'n':  emit_buf[0] = '\n'; emit_count = 1; break;
            case 'r':  emit_buf[0] = '\r'; emit_count = 1; break;
            case 't':  emit_buf[0] = '\t'; emit_count = 1; break;
            case 'u':
                if (scan[2] == '\0' || scan[3] == '\0'
                    || scan[4] == '\0' || scan[5] == '\0') {
                    return NULL;
                }
                emit_count = decode_unicode_escape(scan + 2, emit_buf, &extra_consumed);
                if (emit_count < 0) return NULL;
                scan += 4 + extra_consumed;  /* 4 hex digits + any paired \uXXXX */
                break;
            default:
                return NULL;
        }
        scan += 2;
        if (written + (size_t)emit_count >= scratch_capacity) return NULL;
        memcpy(scratch_buffer + written, emit_buf, (size_t)emit_count);
        written += (size_t)emit_count;
    }
    if (*scan != '"') return NULL;
    scratch_buffer[written] = '\0';
    return scratch_buffer;
}

/* R-156: a scalar value must be followed by a JSON value terminator (end of
 * string, whitespace, or a structural char) — so a malformed suffix like
 * "12abc" / ".5junk" / "truex" is rejected rather than silently accepted by
 * atoll/atof/strncmp-prefix. */
static int json_value_terminator(char c) {
    return c == '\0' || c == ',' || c == '}' || c == ']'
        || c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

long long ss_json_find_int64(
    const char *json_text, const char *field_name, long long missing_default
) {
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL) return missing_default;
    /* R-156: parse the full JSON number with strtod (handles int/frac/exp) and
     * require a terminator after it; "12abc" is rejected, "12.5" is accepted and
     * truncated toward zero (preserving the prior integer-truncation behavior). */
    char *endptr;
    double d = strtod(value_start, &endptr);
    if (endptr == value_start || !json_value_terminator(*endptr)) return missing_default;
    /* R-155-style range guard: an out-of-range/NaN/Inf double->long long is UB. */
    if (!(d >= -9223372036854775808.0 && d < 9223372036854775808.0)) return missing_default;
    return (long long)d;
}

double ss_json_find_double(
    const char *json_text, const char *field_name, double missing_default
) {
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL) return missing_default;
    char *endptr;
    double d = strtod(value_start, &endptr);  /* R-156: strict — reject junk suffixes */
    if (endptr == value_start || !json_value_terminator(*endptr)) return missing_default;
    return d;
}

int ss_json_find_bool(
    const char *json_text, const char *field_name, int missing_default
) {
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL) return missing_default;
    /* R-156: an exact true/false token, not just a prefix ("truex" is rejected). */
    if (strncmp(value_start, "true", 4) == 0 && json_value_terminator(value_start[4]))
        return 1;
    if (strncmp(value_start, "false", 5) == 0 && json_value_terminator(value_start[5]))
        return 0;
    return missing_default;
}

/* ----- document tree (CRUD) implementation ----- */

typedef struct SSJsonObjectField {
    char *name;
    int64_t child;
} SSJsonObjectField;

typedef struct SSJsonObjectValue {
    SSJsonObjectField *fields;
    int64_t length;
    int64_t capacity;
} SSJsonObjectValue;

typedef struct SSJsonArrayValue {
    int64_t *items;
    int64_t length;
    int64_t capacity;
} SSJsonArrayValue;

typedef struct SSJsonNode {
    SSJsonNodeKind kind;
    int active;
    int64_t parent;
    union {
        char *string_value;
        long long int_value;
        double double_value;
        int bool_value;
        SSJsonObjectValue object_value;
        SSJsonArrayValue array_value;
    } as;
} SSJsonNode;

struct SSJsonDocument {
    SSJsonNode *nodes;
    int64_t node_count;
    int64_t node_capacity;
    char *arena;
    int64_t arena_capacity;
    int64_t arena_used;
    int64_t capacity_bytes;
    int64_t bytes_used;
};

static int document_is_container_kind(int32_t kind) {
    return kind == SS_JSON_NODE_OBJECT || kind == SS_JSON_NODE_ARRAY;
}

static void document_sync_bytes_used(SSJsonDocument *document) {
    if (document != NULL) {
        document->bytes_used = document->arena_used;
    }
}

static int document_arena_reserve(SSJsonDocument *document, int64_t byte_count) {
    if (document == NULL || byte_count < 0) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    if (byte_count > document->arena_capacity - document->arena_used) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    return SS_JSON_OK;
}

static int document_arena_append_byte(SSJsonDocument *document, char value) {
    int rc = document_arena_reserve(document, 1);
    if (rc != SS_JSON_OK) return rc;
    document->arena[document->arena_used++] = value;
    document_sync_bytes_used(document);
    return SS_JSON_OK;
}

static int document_arena_copy_text(
    SSJsonDocument *document,
    const char *text,
    char **out
) {
    if (document == NULL || out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    if (text == NULL) {
        text = "";
    }
    size_t text_length = strlen(text);
    if (text_length > (size_t)INT64_MAX - 1) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    int64_t byte_count = (int64_t)text_length + 1;
    int rc = document_arena_reserve(document, byte_count);
    if (rc != SS_JSON_OK) return rc;
    char *dest = document->arena + document->arena_used;
    memcpy(dest, text, text_length + 1);
    document->arena_used += byte_count;
    document_sync_bytes_used(document);
    *out = dest;
    return SS_JSON_OK;
}

static int document_copy_field_name(
    SSJsonDocument *document,
    const char *field_name,
    char **out
) {
    if (field_name == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    size_t field_length = strlen(field_name);
    if (field_length > SS_JSON_MAX_FIELD_NAME_BYTES) {
        return SS_JSON_ERR_FIELD_NAME_TOO_LONG;
    }
    return document_arena_copy_text(document, field_name, out);
}

static int document_ensure_node_capacity(SSJsonDocument *document) {
    if (document == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    if (document->node_count < document->node_capacity) {
        return SS_JSON_OK;
    }
    int64_t next_capacity = document->node_capacity == 0 ? 16 : document->node_capacity * 2;
    if (next_capacity <= document->node_capacity
        || next_capacity > (int64_t)(SIZE_MAX / sizeof(SSJsonNode))) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    SSJsonNode *next_nodes = (SSJsonNode *)realloc(
        document->nodes, (size_t)next_capacity * sizeof(SSJsonNode));
    if (next_nodes == NULL) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    document->nodes = next_nodes;
    document->node_capacity = next_capacity;
    return SS_JSON_OK;
}

static int document_add_node(
    SSJsonDocument *document,
    SSJsonNodeKind kind,
    int64_t parent,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    int rc = document_ensure_node_capacity(document);
    if (rc != SS_JSON_OK) return rc;
    int64_t cursor = document->node_count++;
    SSJsonNode *node = &document->nodes[cursor];
    memset(node, 0, sizeof(*node));
    node->kind = kind;
    node->active = 1;
    node->parent = parent;
    *out = cursor;
    return SS_JSON_OK;
}

/*
 * R-198: a registry of live documents (the sqlite R-139 / event R-196 tombstone
 * pattern). destroyDocument is void and the handle is a plain OpaquePointer, so a
 * double destroy or a cursor/serialize/read on an already-destroyed handle could
 * dereference the freed document/arena/nodes. Membership is checked by pointer
 * VALUE before any field is read, so a stale handle is rejected without touching
 * freed memory. The central accessor document_node_at gates on it, so every
 * cursor read (and root/serialize/field/set, which all funnel through it) fails
 * safe to NULL/sentinel. Single-threaded runtime — no lock needed.
 */
static SSJsonDocument **g_live_documents = NULL;
static size_t g_live_document_count = 0;
static size_t g_live_document_capacity = 0;

static int ss_json_track_document(SSJsonDocument *document) {
    if (g_live_document_count == g_live_document_capacity) {
        size_t next = g_live_document_capacity == 0 ? 8 : g_live_document_capacity * 2;
        if (g_live_document_capacity > SIZE_MAX / 2
                || next > SIZE_MAX / sizeof(SSJsonDocument *)) {
            return 0;
        }
        SSJsonDocument **grown = (SSJsonDocument **)realloc(
            g_live_documents, next * sizeof(SSJsonDocument *));
        if (grown == NULL) {
            return 0;
        }
        g_live_documents = grown;
        g_live_document_capacity = next;
    }
    g_live_documents[g_live_document_count++] = document;
    return 1;
}

static int ss_json_is_live_document(const SSJsonDocument *document) {
    for (size_t i = 0; i < g_live_document_count; i++) {
        if (g_live_documents[i] == document) {
            return 1;
        }
    }
    return 0;
}

static int ss_json_untrack_document(SSJsonDocument *document) {
    for (size_t i = 0; i < g_live_document_count; i++) {
        if (g_live_documents[i] == document) {
            g_live_documents[i] = g_live_documents[g_live_document_count - 1];
            g_live_document_count--;
            return 1;
        }
    }
    return 0;
}

static SSJsonNode *document_node_at(SSJsonDocument *document, int64_t cursor) {
    /* R-198: reject a non-live (destroyed/stale) document by membership BEFORE
     * reading node_count — the deref would otherwise be a use-after-free. */
    if (document == NULL || !ss_json_is_live_document(document)
            || cursor < 0 || cursor >= document->node_count) {
        return NULL;
    }
    SSJsonNode *node = &document->nodes[cursor];
    return node->active ? node : NULL;
}

static int document_ensure_object_capacity(SSJsonNode *node, int64_t needed) {
    if (node == NULL || node->kind != SS_JSON_NODE_OBJECT || needed < 0) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    if (needed <= node->as.object_value.capacity) {
        return SS_JSON_OK;
    }
    int64_t next_capacity = node->as.object_value.capacity == 0 ? 4 : node->as.object_value.capacity * 2;
    while (next_capacity < needed) {
        int64_t doubled = next_capacity * 2;
        if (doubled <= next_capacity) {
            return SS_JSON_ERR_CAPACITY_EXCEEDED;
        }
        next_capacity = doubled;
    }
    if (next_capacity > (int64_t)(SIZE_MAX / sizeof(SSJsonObjectField))) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    SSJsonObjectField *next_fields = (SSJsonObjectField *)realloc(
        node->as.object_value.fields,
        (size_t)next_capacity * sizeof(SSJsonObjectField));
    if (next_fields == NULL) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    node->as.object_value.fields = next_fields;
    node->as.object_value.capacity = next_capacity;
    return SS_JSON_OK;
}

static int document_ensure_array_capacity(SSJsonNode *node, int64_t needed) {
    if (node == NULL || node->kind != SS_JSON_NODE_ARRAY || needed < 0) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    if (needed <= node->as.array_value.capacity) {
        return SS_JSON_OK;
    }
    int64_t next_capacity = node->as.array_value.capacity == 0 ? 4 : node->as.array_value.capacity * 2;
    while (next_capacity < needed) {
        int64_t doubled = next_capacity * 2;
        if (doubled <= next_capacity) {
            return SS_JSON_ERR_CAPACITY_EXCEEDED;
        }
        next_capacity = doubled;
    }
    if (next_capacity > (int64_t)(SIZE_MAX / sizeof(int64_t))) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    int64_t *next_items = (int64_t *)realloc(
        node->as.array_value.items, (size_t)next_capacity * sizeof(int64_t));
    if (next_items == NULL) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    node->as.array_value.items = next_items;
    node->as.array_value.capacity = next_capacity;
    return SS_JSON_OK;
}

static void document_invalidate_subtree(SSJsonDocument *document, int64_t cursor);

static void document_clear_node_value(SSJsonDocument *document, SSJsonNode *node) {
    if (document == NULL || node == NULL || !node->active) {
        return;
    }
    if (node->kind == SS_JSON_NODE_OBJECT) {
        for (int64_t index = 0; index < node->as.object_value.length; ++index) {
            document_invalidate_subtree(document, node->as.object_value.fields[index].child);
        }
        free(node->as.object_value.fields);
        node->as.object_value.fields = NULL;
        node->as.object_value.length = 0;
        node->as.object_value.capacity = 0;
    } else if (node->kind == SS_JSON_NODE_ARRAY) {
        for (int64_t index = 0; index < node->as.array_value.length; ++index) {
            document_invalidate_subtree(document, node->as.array_value.items[index]);
        }
        free(node->as.array_value.items);
        node->as.array_value.items = NULL;
        node->as.array_value.length = 0;
        node->as.array_value.capacity = 0;
    }
}

static void document_invalidate_subtree(SSJsonDocument *document, int64_t cursor) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return;
    }
    document_clear_node_value(document, node);
    node->active = 0;
    node->parent = -1;
    node->kind = SS_JSON_NODE_NULL;
    node->as.string_value = NULL;
}

static void document_free_all_nodes(SSJsonDocument *document) {
    if (document == NULL || document->nodes == NULL) {
        return;
    }
    for (int64_t index = 0; index < document->node_count; ++index) {
        if (document->nodes[index].active) {
            document_clear_node_value(document, &document->nodes[index]);
        } else {
            if (document->nodes[index].kind == SS_JSON_NODE_OBJECT) {
                free(document->nodes[index].as.object_value.fields);
            } else if (document->nodes[index].kind == SS_JSON_NODE_ARRAY) {
                free(document->nodes[index].as.array_value.items);
            }
        }
    }
}

static SSJsonDocument *document_create_shell(int64_t capacity_bytes) {
    if (capacity_bytes < 0) {
        return NULL;
    }
    SSJsonDocument *document = (SSJsonDocument *)calloc(1, sizeof(*document));
    if (document == NULL) {
        return NULL;
    }
    size_t arena_alloc = capacity_bytes > 0 ? (size_t)capacity_bytes : 1;
    if (capacity_bytes > 0 && (int64_t)arena_alloc != capacity_bytes) {
        free(document);
        return NULL;
    }
    document->arena = (char *)malloc(arena_alloc);
    if (document->arena == NULL) {
        free(document);
        return NULL;
    }
    document->arena_capacity = capacity_bytes;
    document->capacity_bytes = capacity_bytes;
    document->arena_used = 0;
    document->bytes_used = 0;
    /* R-198: register before handing the handle out so every read/destroy can
     * validate it by membership. On registry-growth failure, release the shell
     * and fail (never expose an untracked document). */
    if (!ss_json_track_document(document)) {
        free(document->arena);
        free(document);
        return NULL;
    }
    return document;
}

static int is_json_value_delimiter(char c) {
    return c == '\0' || c == ',' || c == '}' || c == ']'
        || c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

static int parse_json_string_to_arena(
    SSJsonDocument *document,
    const char **scan_io,
    char **out
) {
    if (document == NULL || scan_io == NULL || *scan_io == NULL || out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    const char *scan = *scan_io;
    if (*scan != '"') {
        return SS_JSON_ERR_MALFORMED_PATH;
    }
    int64_t arena_mark = document->arena_used;
    ++scan;
    char *dest = document->arena + document->arena_used;
    while (*scan != '\0') {
        unsigned char byte = (unsigned char)*scan;
        if (byte == '"') {
            int rc = document_arena_append_byte(document, '\0');
            if (rc != SS_JSON_OK) {
                document->arena_used = arena_mark;
                document_sync_bytes_used(document);
                return rc;
            }
            *out = dest;
            *scan_io = scan + 1;
            return SS_JSON_OK;
        }
        if (byte < 0x20) {
            document->arena_used = arena_mark;
            document_sync_bytes_used(document);
            return SS_JSON_ERR_MALFORMED_PATH;
        }
        if (byte != '\\') {
            int rc = document_arena_append_byte(document, (char)byte);
            if (rc != SS_JSON_OK) {
                document->arena_used = arena_mark;
                document_sync_bytes_used(document);
                return rc;
            }
            ++scan;
            continue;
        }

        char escape = scan[1];
        if (escape == '\0') {
            document->arena_used = arena_mark;
            document_sync_bytes_used(document);
            return SS_JSON_ERR_MALFORMED_PATH;
        }
        char emit_buf[4];   /* R-259: an astral code point is 4 UTF-8 bytes */
        int emit_count = 0;
        int extra_consumed = 0;
        switch (escape) {
            case '"':  emit_buf[0] = '"';  emit_count = 1; break;
            case '\\': emit_buf[0] = '\\'; emit_count = 1; break;
            case '/':  emit_buf[0] = '/';  emit_count = 1; break;
            case 'b':  emit_buf[0] = '\b'; emit_count = 1; break;
            case 'f':  emit_buf[0] = '\f'; emit_count = 1; break;
            case 'n':  emit_buf[0] = '\n'; emit_count = 1; break;
            case 'r':  emit_buf[0] = '\r'; emit_count = 1; break;
            case 't':  emit_buf[0] = '\t'; emit_count = 1; break;
            case 'u':
                if (scan[2] == '\0' || scan[3] == '\0'
                    || scan[4] == '\0' || scan[5] == '\0') {
                    document->arena_used = arena_mark;
                    document_sync_bytes_used(document);
                    return SS_JSON_ERR_MALFORMED_PATH;
                }
                emit_count = decode_unicode_escape(scan + 2, emit_buf, &extra_consumed);
                if (emit_count < 0) {
                    document->arena_used = arena_mark;
                    document_sync_bytes_used(document);
                    return SS_JSON_ERR_MALFORMED_PATH;
                }
                scan += 4 + extra_consumed;  /* 4 hex digits + any paired \uXXXX */
                break;
            default:
                document->arena_used = arena_mark;
                document_sync_bytes_used(document);
                return SS_JSON_ERR_MALFORMED_PATH;
        }
        scan += 2;
        int rc = document_arena_reserve(document, emit_count);
        if (rc != SS_JSON_OK) {
            document->arena_used = arena_mark;
            document_sync_bytes_used(document);
            return rc;
        }
        memcpy(document->arena + document->arena_used, emit_buf, (size_t)emit_count);
        document->arena_used += emit_count;
        document_sync_bytes_used(document);
    }

    document->arena_used = arena_mark;
    document_sync_bytes_used(document);
    return SS_JSON_ERR_MALFORMED_PATH;
}

static int parse_json_number(
    const char **scan_io,
    long long *out_int,
    double *out_double,
    int *out_is_double
) {
    const char *start = *scan_io;
    const char *scan = start;
    int is_double = 0;

    if (*scan == '-') {
        ++scan;
    }
    if (*scan == '0') {
        ++scan;
        if (*scan >= '0' && *scan <= '9') {
            return SS_JSON_ERR_MALFORMED_PATH;
        }
    } else if (*scan >= '1' && *scan <= '9') {
        while (*scan >= '0' && *scan <= '9') {
            ++scan;
        }
    } else {
        return SS_JSON_ERR_MALFORMED_PATH;
    }

    if (*scan == '.') {
        is_double = 1;
        ++scan;
        if (*scan < '0' || *scan > '9') {
            return SS_JSON_ERR_MALFORMED_PATH;
        }
        while (*scan >= '0' && *scan <= '9') {
            ++scan;
        }
    }

    if (*scan == 'e' || *scan == 'E') {
        is_double = 1;
        ++scan;
        if (*scan == '+' || *scan == '-') {
            ++scan;
        }
        if (*scan < '0' || *scan > '9') {
            return SS_JSON_ERR_MALFORMED_PATH;
        }
        while (*scan >= '0' && *scan <= '9') {
            ++scan;
        }
    }

    if (!is_json_value_delimiter(*scan)) {
        return SS_JSON_ERR_MALFORMED_PATH;
    }

    if (is_double) {
        errno = 0;
        *out_double = strtod(start, NULL);
        if (errno == ERANGE) {
            return SS_JSON_ERR_MALFORMED_PATH;
        }
    } else {
        errno = 0;
        char *end_ptr = NULL;
        long long parsed = strtoll(start, &end_ptr, 10);
        if (errno == ERANGE || end_ptr != scan) {
            errno = 0;
            *out_double = strtod(start, NULL);
            if (errno == ERANGE) {
                return SS_JSON_ERR_MALFORMED_PATH;
            }
            is_double = 1;
        } else {
            *out_int = parsed;
        }
    }

    *out_is_double = is_double;
    *scan_io = scan;
    return SS_JSON_OK;
}

static int parse_json_value(
    SSJsonDocument *document,
    const char **scan_io,
    int64_t parent,
    int depth,
    int64_t *out
);

static int parse_json_object(
    SSJsonDocument *document,
    const char **scan_io,
    int64_t parent,
    int depth,
    int64_t *out
) {
    const char *scan = *scan_io;
    int64_t object_cursor;
    int rc = document_add_node(document, SS_JSON_NODE_OBJECT, parent, &object_cursor);
    if (rc != SS_JSON_OK) return rc;
    SSJsonNode *object_node = document_node_at(document, object_cursor);

    ++scan;
    scan = skip_whitespace(scan);
    if (*scan == '}') {
        *scan_io = scan + 1;
        *out = object_cursor;
        return SS_JSON_OK;
    }

    while (1) {
        scan = skip_whitespace(scan);
        char *field_name = NULL;
        rc = parse_json_string_to_arena(document, &scan, &field_name);
        if (rc != SS_JSON_OK) return rc;
        if (strlen(field_name) > SS_JSON_MAX_FIELD_NAME_BYTES) {
            return SS_JSON_ERR_FIELD_NAME_TOO_LONG;
        }
        /* R-260: reject a DUPLICATE key. `{"role":"user","role":"admin"}` would
         * otherwise resolve to "user" on first-wins lookup yet re-serialize both
         * keys — a privilege-confusion / request-smuggling primitive when a
         * downstream parser picks the other. An object with a repeated key is
         * ambiguous; fail closed. (object_node is valid here — the field-name
         * copy touched only the arena, not the node array, and the capacity grow
         * that can realloc happens below.) */
        for (int64_t dup_i = 0; dup_i < object_node->as.object_value.length; ++dup_i) {
            if (strcmp(object_node->as.object_value.fields[dup_i].name,
                       field_name) == 0) {
                return SS_JSON_ERR_MALFORMED_PATH;
            }
        }
        scan = skip_whitespace(scan);
        if (*scan != ':') {
            return SS_JSON_ERR_MALFORMED_PATH;
        }
        ++scan;
        rc = document_ensure_object_capacity(
            object_node, object_node->as.object_value.length + 1);
        if (rc != SS_JSON_OK) return rc;
        int64_t child_cursor;
        rc = parse_json_value(document, &scan, object_cursor, depth, &child_cursor);
        if (rc != SS_JSON_OK) return rc;
        object_node = document_node_at(document, object_cursor);
        int64_t field_index = object_node->as.object_value.length++;
        object_node->as.object_value.fields[field_index].name = field_name;
        object_node->as.object_value.fields[field_index].child = child_cursor;

        scan = skip_whitespace(scan);
        if (*scan == ',') {
            ++scan;
            continue;
        }
        if (*scan == '}') {
            *scan_io = scan + 1;
            *out = object_cursor;
            return SS_JSON_OK;
        }
        return SS_JSON_ERR_MALFORMED_PATH;
    }
}

static int parse_json_array(
    SSJsonDocument *document,
    const char **scan_io,
    int64_t parent,
    int depth,
    int64_t *out
) {
    const char *scan = *scan_io;
    int64_t array_cursor;
    int rc = document_add_node(document, SS_JSON_NODE_ARRAY, parent, &array_cursor);
    if (rc != SS_JSON_OK) return rc;
    SSJsonNode *array_node = document_node_at(document, array_cursor);

    ++scan;
    scan = skip_whitespace(scan);
    if (*scan == ']') {
        *scan_io = scan + 1;
        *out = array_cursor;
        return SS_JSON_OK;
    }

    while (1) {
        rc = document_ensure_array_capacity(
            array_node, array_node->as.array_value.length + 1);
        if (rc != SS_JSON_OK) return rc;
        int64_t child_cursor;
        rc = parse_json_value(document, &scan, array_cursor, depth, &child_cursor);
        if (rc != SS_JSON_OK) return rc;
        array_node = document_node_at(document, array_cursor);
        array_node->as.array_value.items[array_node->as.array_value.length++] = child_cursor;

        scan = skip_whitespace(scan);
        if (*scan == ',') {
            ++scan;
            scan = skip_whitespace(scan);
            continue;
        }
        if (*scan == ']') {
            *scan_io = scan + 1;
            *out = array_cursor;
            return SS_JSON_OK;
        }
        return SS_JSON_ERR_MALFORMED_PATH;
    }
}

static int parse_json_value(
    SSJsonDocument *document,
    const char **scan_io,
    int64_t parent,
    int depth,
    int64_t *out
) {
    const char *scan = skip_whitespace(*scan_io);
    if (*scan == '{') {
        if (depth >= SS_JSON_MAX_NESTING_DEPTH) {
            return SS_JSON_ERR_CAPACITY_EXCEEDED;
        }
        *scan_io = scan;
        return parse_json_object(document, scan_io, parent, depth + 1, out);
    }
    if (*scan == '[') {
        if (depth >= SS_JSON_MAX_NESTING_DEPTH) {
            return SS_JSON_ERR_CAPACITY_EXCEEDED;
        }
        *scan_io = scan;
        return parse_json_array(document, scan_io, parent, depth + 1, out);
    }
    if (*scan == '"') {
        char *value = NULL;
        int rc = parse_json_string_to_arena(document, &scan, &value);
        if (rc != SS_JSON_OK) return rc;
        int64_t cursor;
        rc = document_add_node(document, SS_JSON_NODE_STRING, parent, &cursor);
        if (rc != SS_JSON_OK) return rc;
        document->nodes[cursor].as.string_value = value;
        *scan_io = scan;
        *out = cursor;
        return SS_JSON_OK;
    }
    if (*scan == '-' || (*scan >= '0' && *scan <= '9')) {
        long long int_value = 0;
        double double_value = 0.0;
        int is_double = 0;
        int rc = parse_json_number(&scan, &int_value, &double_value, &is_double);
        if (rc != SS_JSON_OK) return rc;
        int64_t cursor;
        rc = document_add_node(
            document,
            is_double ? SS_JSON_NODE_DOUBLE : SS_JSON_NODE_INTEGER,
            parent,
            &cursor);
        if (rc != SS_JSON_OK) return rc;
        if (is_double) {
            document->nodes[cursor].as.double_value = double_value;
        } else {
            document->nodes[cursor].as.int_value = int_value;
        }
        *scan_io = scan;
        *out = cursor;
        return SS_JSON_OK;
    }
    if (strncmp(scan, "true", 4) == 0 && is_json_value_delimiter(scan[4])) {
        int64_t cursor;
        int rc = document_add_node(document, SS_JSON_NODE_BOOLEAN, parent, &cursor);
        if (rc != SS_JSON_OK) return rc;
        document->nodes[cursor].as.bool_value = 1;
        *scan_io = scan + 4;
        *out = cursor;
        return SS_JSON_OK;
    }
    if (strncmp(scan, "false", 5) == 0 && is_json_value_delimiter(scan[5])) {
        int64_t cursor;
        int rc = document_add_node(document, SS_JSON_NODE_BOOLEAN, parent, &cursor);
        if (rc != SS_JSON_OK) return rc;
        document->nodes[cursor].as.bool_value = 0;
        *scan_io = scan + 5;
        *out = cursor;
        return SS_JSON_OK;
    }
    if (strncmp(scan, "null", 4) == 0 && is_json_value_delimiter(scan[4])) {
        int64_t cursor;
        int rc = document_add_node(document, SS_JSON_NODE_NULL, parent, &cursor);
        if (rc != SS_JSON_OK) return rc;
        *scan_io = scan + 4;
        *out = cursor;
        return SS_JSON_OK;
    }
    return SS_JSON_ERR_MALFORMED_PATH;
}

int ss_json_document_create_empty(
    int64_t capacity_bytes,
    int32_t root_kind,
    SSJsonDocument **out
) {
    if (out == NULL || !document_is_container_kind(root_kind)) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = NULL;
    SSJsonDocument *document = document_create_shell(capacity_bytes);
    if (document == NULL) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    int64_t root_cursor;
    int rc = document_add_node(document, (SSJsonNodeKind)root_kind, -1, &root_cursor);
    if (rc != SS_JSON_OK) {
        ss_json_document_destroy(document);
        return rc;
    }
    *out = document;
    return SS_JSON_OK;
}

int ss_json_document_create_from_text(
    const char *json_text,
    int64_t capacity_bytes,
    SSJsonDocument **out
) {
    if (json_text == NULL || out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = NULL;
    SSJsonDocument *document = document_create_shell(capacity_bytes);
    if (document == NULL) {
        return SS_JSON_ERR_CAPACITY_EXCEEDED;
    }
    const char *scan = json_text;
    int64_t root_cursor;
    int rc = parse_json_value(document, &scan, -1, 0, &root_cursor);
    if (rc == SS_JSON_OK) {
        scan = skip_whitespace(scan);
        if (*scan != '\0' || root_cursor != 0) {
            rc = SS_JSON_ERR_MALFORMED_PATH;
        }
    }
    if (rc != SS_JSON_OK) {
        ss_json_document_destroy(document);
        return rc;
    }
    *out = document;
    return SS_JSON_OK;
}

static int primitive_parse_has_only_trailing_ws(const char *scan) {
    scan = skip_whitespace(scan);
    return *scan == '\0';
}

int ss_json_parse_int64(const char *json_text, long long *out) {
    if (json_text == NULL || out == NULL) {
        return SS_JSON_ERR_CONFIG;
    }
    const char *scan = skip_whitespace(json_text);
    long long int_value = 0;
    double double_value = 0.0;
    int is_double = 0;
    int rc = parse_json_number(&scan, &int_value, &double_value, &is_double);
    if (rc != SS_JSON_OK || is_double || !primitive_parse_has_only_trailing_ws(scan)) {
        return SS_JSON_ERR_MALFORMED_PATH;
    }
    *out = int_value;
    return SS_JSON_OK;
}

int ss_json_parse_double(const char *json_text, double *out) {
    if (json_text == NULL || out == NULL) {
        return SS_JSON_ERR_CONFIG;
    }
    const char *scan = skip_whitespace(json_text);
    long long int_value = 0;
    double double_value = 0.0;
    int is_double = 0;
    int rc = parse_json_number(&scan, &int_value, &double_value, &is_double);
    if (rc != SS_JSON_OK || !primitive_parse_has_only_trailing_ws(scan)) {
        return SS_JSON_ERR_MALFORMED_PATH;
    }
    *out = is_double ? double_value : (double)int_value;
    return SS_JSON_OK;
}

int ss_json_parse_bool(const char *json_text, int *out) {
    if (json_text == NULL || out == NULL) {
        return SS_JSON_ERR_CONFIG;
    }
    const char *scan = skip_whitespace(json_text);
    if (strncmp(scan, "true", 4) == 0 && primitive_parse_has_only_trailing_ws(scan + 4)) {
        *out = 1;
        return SS_JSON_OK;
    }
    if (strncmp(scan, "false", 5) == 0 && primitive_parse_has_only_trailing_ws(scan + 5)) {
        *out = 0;
        return SS_JSON_OK;
    }
    return SS_JSON_ERR_MALFORMED_PATH;
}

void ss_json_document_destroy(SSJsonDocument *document) {
    /* R-198: untrack first (membership by pointer value, no deref). A double
     * destroy or a bogus handle fails membership and becomes a no-op instead of
     * a double-free; only a confirmed-live document is dereferenced/freed. */
    if (document == NULL || !ss_json_untrack_document(document)) {
        return;
    }
    document_free_all_nodes(document);
    free(document->nodes);
    free(document->arena);
    free(document);
}

static int serialize_node_to_builder(
    SSJsonDocument *document,
    int64_t cursor,
    SSJsonBuilder *builder
) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return builder_append_cstring(builder, "null");
    }
    switch (node->kind) {
        case SS_JSON_NODE_OBJECT: {
            int rc = builder_append_byte(builder, '{');
            if (rc != SS_JSON_OK) return rc;
            for (int64_t index = 0; index < node->as.object_value.length; ++index) {
                if (index > 0) {
                    rc = builder_append_byte(builder, ',');
                    if (rc != SS_JSON_OK) return rc;
                }
                rc = builder_append_quoted_string(
                    builder, node->as.object_value.fields[index].name);
                if (rc != SS_JSON_OK) return rc;
                rc = builder_append_byte(builder, ':');
                if (rc != SS_JSON_OK) return rc;
                rc = serialize_node_to_builder(
                    document, node->as.object_value.fields[index].child, builder);
                if (rc != SS_JSON_OK) return rc;
            }
            return builder_append_byte(builder, '}');
        }
        case SS_JSON_NODE_ARRAY: {
            int rc = builder_append_byte(builder, '[');
            if (rc != SS_JSON_OK) return rc;
            for (int64_t index = 0; index < node->as.array_value.length; ++index) {
                if (index > 0) {
                    rc = builder_append_byte(builder, ',');
                    if (rc != SS_JSON_OK) return rc;
                }
                rc = serialize_node_to_builder(
                    document, node->as.array_value.items[index], builder);
                if (rc != SS_JSON_OK) return rc;
            }
            return builder_append_byte(builder, ']');
        }
        case SS_JSON_NODE_STRING:
            return builder_append_quoted_string(builder, node->as.string_value);
        case SS_JSON_NODE_INTEGER: {
            char number_text[32];
            int written = snprintf(number_text, sizeof(number_text), "%lld", node->as.int_value);
            if (written < 0 || written >= (int)sizeof(number_text)) {
                return SS_JSON_ERR_OVERFLOW;
            }
            return builder_append_bytes(builder, number_text, (size_t)written);
        }
        case SS_JSON_NODE_DOUBLE: {
            char number_text[32];
            int written;
            if (!isfinite(node->as.double_value)) {  /* R-261: inf/nan -> null */
                memcpy(number_text, "null", 5);
                written = 4;
            } else {
                written = snprintf(number_text, sizeof(number_text), "%.17g",
                                   node->as.double_value);
            }
            if (written < 0 || written >= (int)sizeof(number_text)) {
                return SS_JSON_ERR_OVERFLOW;
            }
            return builder_append_bytes(builder, number_text, (size_t)written);
        }
        case SS_JSON_NODE_BOOLEAN:
            return builder_append_cstring(builder, node->as.bool_value ? "true" : "false");
        case SS_JSON_NODE_NULL:
        default:
            return builder_append_cstring(builder, "null");
    }
}

int ss_json_document_serialize(
    SSJsonDocument *document,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (document == NULL || scratch == NULL || out == NULL || scratch_capacity <= 0) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = NULL;
    SSJsonBuilder stack_builder;
    memset(&stack_builder, 0, sizeof(stack_builder));
    stack_builder.buffer = scratch;
    stack_builder.capacity = (size_t)scratch_capacity;
    stack_builder.length = 0;
    stack_builder.error_state = SS_JSON_OK;
    stack_builder.stack_depth = 0;
    scratch[0] = '\0';

    int rc = serialize_node_to_builder(document, 0, &stack_builder);
    if (rc != SS_JSON_OK || stack_builder.error_state != SS_JSON_OK) {
        return SS_JSON_ERR_SCRATCH_TOO_SMALL;
    }
    *out = scratch;
    return SS_JSON_OK;
}

static int64_t json_quoted_length(const char *text) {
    if (text == NULL) {
        return 4;
    }
    int64_t length = 2;
    const unsigned char *scan = (const unsigned char *)text;
    while (*scan != '\0') {
        unsigned char byte = *scan++;
        switch (byte) {
            case '"':
            case '\\':
            case '\b':
            case '\f':
            case '\n':
            case '\r':
            case '\t':
                length += 2;
                break;
            default:
                length += byte < 0x20 ? 6 : 1;
                break;
        }
    }
    return length;
}

static int64_t document_node_serialized_length(SSJsonDocument *document, int64_t cursor) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return 4;
    }
    switch (node->kind) {
        case SS_JSON_NODE_OBJECT: {
            int64_t length = 2;
            for (int64_t index = 0; index < node->as.object_value.length; ++index) {
                if (index > 0) length += 1;
                length += json_quoted_length(node->as.object_value.fields[index].name);
                length += 1;
                length += document_node_serialized_length(
                    document, node->as.object_value.fields[index].child);
            }
            return length;
        }
        case SS_JSON_NODE_ARRAY: {
            int64_t length = 2;
            for (int64_t index = 0; index < node->as.array_value.length; ++index) {
                if (index > 0) length += 1;
                length += document_node_serialized_length(
                    document, node->as.array_value.items[index]);
            }
            return length;
        }
        case SS_JSON_NODE_STRING:
            return json_quoted_length(node->as.string_value);
        case SS_JSON_NODE_INTEGER: {
            char number_text[32];
            int written = snprintf(number_text, sizeof(number_text), "%lld", node->as.int_value);
            return written > 0 ? written : 0;
        }
        case SS_JSON_NODE_DOUBLE: {
            char number_text[32];
            int written;
            if (!isfinite(node->as.double_value)) {  /* R-261: inf/nan -> null */
                memcpy(number_text, "null", 5);
                written = 4;
            } else {
                written = snprintf(number_text, sizeof(number_text), "%.17g",
                                   node->as.double_value);
            }
            return written > 0 ? written : 0;
        }
        case SS_JSON_NODE_BOOLEAN:
            return node->as.bool_value ? 4 : 5;
        case SS_JSON_NODE_NULL:
        default:
            return 4;
    }
}

int64_t ss_json_document_length(SSJsonDocument *document) {
    if (document == NULL || document_node_at(document, 0) == NULL) {
        return 0;
    }
    return document_node_serialized_length(document, 0);
}

int64_t ss_json_document_root(SSJsonDocument *document) {
    return document != NULL && document_node_at(document, 0) != NULL ? 0 : -1;
}

static int object_find_field_index(
    SSJsonNode *node,
    const char *field_name,
    int64_t *out_index
) {
    if (node == NULL || node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    for (int64_t index = 0; index < node->as.object_value.length; ++index) {
        if (strcmp(node->as.object_value.fields[index].name, field_name) == 0) {
            *out_index = index;
            return SS_JSON_OK;
        }
    }
    return SS_JSON_ERR_PATH_NOT_FOUND;
}

int ss_json_navigate_object_field(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int64_t *out
) {
    if (out == NULL || field_name == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    int64_t field_index;
    int rc = object_find_field_index(node, field_name, &field_index);
    if (rc != SS_JSON_OK) return rc;
    *out = node->as.object_value.fields[field_index].child;
    return SS_JSON_OK;
}

int ss_json_navigate_array_element(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_ARRAY) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    if (index < 0 || index >= node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    *out = node->as.array_value.items[index];
    return SS_JSON_OK;
}

int ss_json_cursor_parent(SSJsonDocument *document, int64_t cursor, int64_t *out) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL || node->parent < 0) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    *out = node->parent;
    return SS_JSON_OK;
}

int ss_json_cursor_at_path(
    SSJsonDocument *document,
    const char *path,
    int64_t *out
) {
    if (document == NULL || path == NULL || out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    int64_t cursor = ss_json_document_root(document);
    if (cursor < 0) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    const char *scan = path;
    while (*scan != '\0') {
        if (*scan == '.') {
            ++scan;
            if (*scan == '\0' || *scan == '.' || *scan == '[' || *scan == ']') {
                return SS_JSON_ERR_MALFORMED_PATH;
            }
            char field_name[SS_JSON_MAX_FIELD_NAME_BYTES + 1];
            size_t length = 0;
            while (*scan != '\0' && *scan != '.' && *scan != '[' && *scan != ']') {
                if (length >= SS_JSON_MAX_FIELD_NAME_BYTES) {
                    return SS_JSON_ERR_FIELD_NAME_TOO_LONG;
                }
                field_name[length++] = *scan++;
            }
            field_name[length] = '\0';
            int rc = ss_json_navigate_object_field(document, cursor, field_name, &cursor);
            if (rc != SS_JSON_OK) return rc;
            continue;
        }
        if (*scan == '[') {
            ++scan;
            if (*scan < '0' || *scan > '9') {
                return SS_JSON_ERR_MALFORMED_PATH;
            }
            int64_t index = 0;
            while (*scan >= '0' && *scan <= '9') {
                int digit = *scan - '0';
                if (index > (INT64_MAX - digit) / 10) {
                    return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
                }
                index = index * 10 + digit;
                ++scan;
            }
            if (*scan != ']') {
                return SS_JSON_ERR_MALFORMED_PATH;
            }
            ++scan;
            int rc = ss_json_navigate_array_element(document, cursor, index, &cursor);
            if (rc != SS_JSON_OK) return rc;
            continue;
        }
        return SS_JSON_ERR_MALFORMED_PATH;
    }
    *out = cursor;
    return SS_JSON_OK;
}

int32_t ss_json_cursor_kind(SSJsonDocument *document, int64_t cursor) {
    SSJsonNode *node = document_node_at(document, cursor);
    return node != NULL ? (int32_t)node->kind : -1;
}

int ss_json_cursor_is_null(SSJsonDocument *document, int64_t cursor) {
    SSJsonNode *node = document_node_at(document, cursor);
    return node != NULL && node->kind == SS_JSON_NODE_NULL ? 1 : 0;
}

long long ss_json_cursor_int64(
    SSJsonDocument *document,
    int64_t cursor,
    long long missing_default
) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) return missing_default;
    if (node->kind == SS_JSON_NODE_INTEGER) return node->as.int_value;
    if (node->kind == SS_JSON_NODE_DOUBLE) {
        /* R-155: casting a double outside the long long range (or a NaN/Inf) to
         * long long is undefined behavior. Only convert a finite, in-range value
         * (truncating toward zero); anything else falls back to missing_default.
         * The bounds [-2^63, 2^63) bracket the doubles whose cast is in range;
         * NaN/Inf fail both comparisons (so they fall through to the default). */
        double d = node->as.double_value;
        if (d >= -9223372036854775808.0 && d < 9223372036854775808.0)
            return (long long)d;
        return missing_default;
    }
    return missing_default;
}

double ss_json_cursor_double(
    SSJsonDocument *document,
    int64_t cursor,
    double missing_default
) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) return missing_default;
    if (node->kind == SS_JSON_NODE_DOUBLE) return node->as.double_value;
    if (node->kind == SS_JSON_NODE_INTEGER) return (double)node->as.int_value;
    return missing_default;
}

int ss_json_cursor_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int missing_default
) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL || node->kind != SS_JSON_NODE_BOOLEAN) return missing_default;
    return node->as.bool_value ? 1 : 0;
}

int ss_json_cursor_string(
    SSJsonDocument *document,
    int64_t cursor,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (scratch == NULL || out == NULL || scratch_capacity <= 0) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = NULL;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_STRING) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    size_t value_length = strlen(node->as.string_value);
    if (value_length + 1 > (size_t)scratch_capacity) {
        return SS_JSON_ERR_SCRATCH_TOO_SMALL;
    }
    memcpy(scratch, node->as.string_value, value_length + 1);
    *out = scratch;
    return SS_JSON_OK;
}

int ss_json_cursor_array_length(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = 0;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_ARRAY) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    *out = node->as.array_value.length;
    return SS_JSON_OK;
}

int ss_json_cursor_object_field_count(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = 0;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    *out = node->as.object_value.length;
    return SS_JSON_OK;
}

int ss_json_cursor_object_field_name_at(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
) {
    if (scratch == NULL || out == NULL || scratch_capacity <= 0) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = NULL;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    if (index < 0 || index >= node->as.object_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    const char *name = node->as.object_value.fields[index].name;
    size_t name_length = strlen(name);
    if (name_length + 1 > (size_t)scratch_capacity) {
        return SS_JSON_ERR_SCRATCH_TOO_SMALL;
    }
    memcpy(scratch, name, name_length + 1);
    *out = scratch;
    return SS_JSON_OK;
}

int ss_json_cursor_object_field_value_at(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    if (index < 0 || index >= node->as.object_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    *out = node->as.object_value.fields[index].child;
    return SS_JSON_OK;
}

static int document_set_node_string(
    SSJsonDocument *document,
    SSJsonNode *node,
    const char *value
) {
    char *owned_value = NULL;
    int rc = document_arena_copy_text(document, value, &owned_value);
    if (rc != SS_JSON_OK) return rc;
    document_clear_node_value(document, node);
    node->kind = SS_JSON_NODE_STRING;
    node->active = 1;
    node->as.string_value = owned_value;
    return SS_JSON_OK;
}

static void document_set_node_int64(SSJsonDocument *document, SSJsonNode *node, long long value) {
    document_clear_node_value(document, node);
    node->kind = SS_JSON_NODE_INTEGER;
    node->active = 1;
    node->as.int_value = value;
}

static void document_set_node_double(SSJsonDocument *document, SSJsonNode *node, double value) {
    document_clear_node_value(document, node);
    node->kind = SS_JSON_NODE_DOUBLE;
    node->active = 1;
    node->as.double_value = value;
}

static void document_set_node_bool(SSJsonDocument *document, SSJsonNode *node, int value_truthiness) {
    document_clear_node_value(document, node);
    node->kind = SS_JSON_NODE_BOOLEAN;
    node->active = 1;
    node->as.bool_value = value_truthiness ? 1 : 0;
}

static void document_set_node_null(SSJsonDocument *document, SSJsonNode *node) {
    document_clear_node_value(document, node);
    node->kind = SS_JSON_NODE_NULL;
    node->active = 1;
}

static int object_prepare_field(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    SSJsonNode **out_object,
    int64_t *out_field_index,
    int *out_exists
) {
    if (field_name == NULL || out_object == NULL || out_field_index == NULL || out_exists == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    size_t field_length = strlen(field_name);
    if (field_length > SS_JSON_MAX_FIELD_NAME_BYTES) {
        return SS_JSON_ERR_FIELD_NAME_TOO_LONG;
    }
    SSJsonNode *object_node = document_node_at(document, cursor);
    if (object_node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (object_node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    int64_t field_index = -1;
    int rc = object_find_field_index(object_node, field_name, &field_index);
    if (rc == SS_JSON_OK) {
        *out_object = object_node;
        *out_field_index = field_index;
        *out_exists = 1;
        return SS_JSON_OK;
    }
    if (rc != SS_JSON_ERR_PATH_NOT_FOUND) {
        return rc;
    }
    *out_object = object_node;
    *out_field_index = -1;
    *out_exists = 0;
    return SS_JSON_OK;
}

static int object_append_field_with_child(
    SSJsonDocument *document,
    int64_t object_cursor,
    SSJsonNode *object_node,
    char *owned_field_name,
    int64_t child_cursor
) {
    (void)object_node;
    object_node = document_node_at(document, object_cursor);
    if (object_node == NULL || object_node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    int rc = document_ensure_object_capacity(
        object_node, object_node->as.object_value.length + 1);
    if (rc != SS_JSON_OK) return rc;
    object_node = document_node_at(document, object_cursor);
    int64_t field_index = object_node->as.object_value.length++;
    object_node->as.object_value.fields[field_index].name = owned_field_name;
    object_node->as.object_value.fields[field_index].child = child_cursor;
    SSJsonNode *child = document_node_at(document, child_cursor);
    if (child != NULL) {
        child->parent = object_cursor;
    }
    return SS_JSON_OK;
}

static int set_object_field_existing_or_new_scalar(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    SSJsonNodeKind kind,
    const void *value
) {
    SSJsonNode *object_node;
    int64_t field_index;
    int exists;
    int rc = object_prepare_field(
        document, cursor, field_name, &object_node, &field_index, &exists);
    if (rc != SS_JSON_OK) return rc;

    if (exists) {
        int64_t child_cursor = object_node->as.object_value.fields[field_index].child;
        SSJsonNode *child = document_node_at(document, child_cursor);
        if (child == NULL) {
            return SS_JSON_ERR_PATH_NOT_FOUND;
        }
        switch (kind) {
            case SS_JSON_NODE_STRING:
                return document_set_node_string(document, child, (const char *)value);
            case SS_JSON_NODE_INTEGER:
                document_set_node_int64(document, child, *(const long long *)value);
                return SS_JSON_OK;
            case SS_JSON_NODE_DOUBLE:
                document_set_node_double(document, child, *(const double *)value);
                return SS_JSON_OK;
            case SS_JSON_NODE_BOOLEAN:
                document_set_node_bool(document, child, *(const int *)value);
                return SS_JSON_OK;
            case SS_JSON_NODE_NULL:
            default:
                document_set_node_null(document, child);
                return SS_JSON_OK;
        }
    }

    int64_t arena_mark = document->arena_used;
    int64_t node_mark = document->node_count;
    char *owned_name = NULL;
    rc = document_copy_field_name(document, field_name, &owned_name);
    if (rc != SS_JSON_OK) return rc;
    int64_t child_cursor;
    rc = document_add_node(document, kind, cursor, &child_cursor);
    if (rc != SS_JSON_OK) {
        document->arena_used = arena_mark;
        document_sync_bytes_used(document);
        document->node_count = node_mark;
        return rc;
    }
    SSJsonNode *child = document_node_at(document, child_cursor);
    switch (kind) {
        case SS_JSON_NODE_STRING:
            rc = document_set_node_string(document, child, (const char *)value);
            break;
        case SS_JSON_NODE_INTEGER:
            document_set_node_int64(document, child, *(const long long *)value);
            rc = SS_JSON_OK;
            break;
        case SS_JSON_NODE_DOUBLE:
            document_set_node_double(document, child, *(const double *)value);
            rc = SS_JSON_OK;
            break;
        case SS_JSON_NODE_BOOLEAN:
            document_set_node_bool(document, child, *(const int *)value);
            rc = SS_JSON_OK;
            break;
        case SS_JSON_NODE_NULL:
        default:
            document_set_node_null(document, child);
            rc = SS_JSON_OK;
            break;
    }
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
        document->arena_used = arena_mark;
        document_sync_bytes_used(document);
        document->node_count = node_mark;
        return rc;
    }
    rc = object_append_field_with_child(document, cursor, object_node, owned_name, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
        document->arena_used = arena_mark;
        document_sync_bytes_used(document);
        document->node_count = node_mark;
        return rc;
    }
    return SS_JSON_OK;
}

int ss_json_set_object_field_string(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    const char *value
) {
    return set_object_field_existing_or_new_scalar(
        document, cursor, field_name, SS_JSON_NODE_STRING, value);
}

int ss_json_set_object_field_int64(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    long long value
) {
    return set_object_field_existing_or_new_scalar(
        document, cursor, field_name, SS_JSON_NODE_INTEGER, &value);
}

int ss_json_set_object_field_double(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    double value
) {
    return set_object_field_existing_or_new_scalar(
        document, cursor, field_name, SS_JSON_NODE_DOUBLE, &value);
}

int ss_json_set_object_field_bool(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int value_truthiness
) {
    return set_object_field_existing_or_new_scalar(
        document, cursor, field_name, SS_JSON_NODE_BOOLEAN, &value_truthiness);
}

int ss_json_set_object_field_null(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name
) {
    return set_object_field_existing_or_new_scalar(
        document, cursor, field_name, SS_JSON_NODE_NULL, NULL);
}

static int set_object_field_container(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    SSJsonNodeKind kind,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *object_node;
    int64_t field_index;
    int exists;
    int rc = object_prepare_field(
        document, cursor, field_name, &object_node, &field_index, &exists);
    if (rc != SS_JSON_OK) return rc;

    int64_t arena_mark = document->arena_used;
    int64_t node_mark = document->node_count;
    char *owned_name = NULL;
    if (!exists) {
        rc = document_copy_field_name(document, field_name, &owned_name);
        if (rc != SS_JSON_OK) return rc;
    }
    int64_t child_cursor;
    rc = document_add_node(document, kind, cursor, &child_cursor);
    if (rc != SS_JSON_OK) {
        document->arena_used = arena_mark;
        document_sync_bytes_used(document);
        document->node_count = node_mark;
        return rc;
    }
    if (exists) {
        /* R-237: document_add_node above may have realloc'd document->nodes,
         * freeing the buffer object_node (taken before the add) points into.
         * Re-fetch the node BEFORE reading the old child, or old_child is read
         * through a dangling pointer. */
        object_node = document_node_at(document, cursor);
        int64_t old_child = object_node->as.object_value.fields[field_index].child;
        document_invalidate_subtree(document, old_child);
        object_node->as.object_value.fields[field_index].child = child_cursor;
    } else {
        rc = object_append_field_with_child(document, cursor, object_node, owned_name, child_cursor);
        if (rc != SS_JSON_OK) {
            document_invalidate_subtree(document, child_cursor);
            document->arena_used = arena_mark;
            document_sync_bytes_used(document);
            document->node_count = node_mark;
            return rc;
        }
    }
    *out = child_cursor;
    return SS_JSON_OK;
}

int ss_json_set_object_field_object(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int64_t *out
) {
    return set_object_field_container(document, cursor, field_name, SS_JSON_NODE_OBJECT, out);
}

int ss_json_set_object_field_array(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int64_t *out
) {
    return set_object_field_container(document, cursor, field_name, SS_JSON_NODE_ARRAY, out);
}

static int clone_subtree(
    SSJsonDocument *target,
    SSJsonDocument *source,
    int64_t source_cursor,
    int64_t parent,
    int64_t *out
) {
    SSJsonNode *source_node = document_node_at(source, source_cursor);
    if (source_node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    int64_t target_cursor;
    int rc = document_add_node(target, source_node->kind, parent, &target_cursor);
    if (rc != SS_JSON_OK) return rc;
    SSJsonNode *target_node = document_node_at(target, target_cursor);
    switch (source_node->kind) {
        case SS_JSON_NODE_STRING:
            rc = document_arena_copy_text(
                target, source_node->as.string_value, &target_node->as.string_value);
            if (rc != SS_JSON_OK) return rc;
            break;
        case SS_JSON_NODE_INTEGER:
            target_node->as.int_value = source_node->as.int_value;
            break;
        case SS_JSON_NODE_DOUBLE:
            target_node->as.double_value = source_node->as.double_value;
            break;
        case SS_JSON_NODE_BOOLEAN:
            target_node->as.bool_value = source_node->as.bool_value;
            break;
        case SS_JSON_NODE_OBJECT:
            rc = document_ensure_object_capacity(
                target_node, source_node->as.object_value.length);
            if (rc != SS_JSON_OK) return rc;
            for (int64_t index = 0; index < source_node->as.object_value.length; ++index) {
                char *field_name = NULL;
                rc = document_arena_copy_text(
                    target,
                    source_node->as.object_value.fields[index].name,
                    &field_name);
                if (rc != SS_JSON_OK) return rc;
                int64_t child_cursor;
                rc = clone_subtree(
                    target,
                    source,
                    source_node->as.object_value.fields[index].child,
                    target_cursor,
                    &child_cursor);
                if (rc != SS_JSON_OK) return rc;
                target_node = document_node_at(target, target_cursor);
                int64_t field_index = target_node->as.object_value.length++;
                target_node->as.object_value.fields[field_index].name = field_name;
                target_node->as.object_value.fields[field_index].child = child_cursor;
            }
            break;
        case SS_JSON_NODE_ARRAY:
            rc = document_ensure_array_capacity(
                target_node, source_node->as.array_value.length);
            if (rc != SS_JSON_OK) return rc;
            for (int64_t index = 0; index < source_node->as.array_value.length; ++index) {
                int64_t child_cursor;
                rc = clone_subtree(
                    target,
                    source,
                    source_node->as.array_value.items[index],
                    target_cursor,
                    &child_cursor);
                if (rc != SS_JSON_OK) return rc;
                target_node = document_node_at(target, target_cursor);
                target_node->as.array_value.items[target_node->as.array_value.length++] = child_cursor;
            }
            break;
        case SS_JSON_NODE_NULL:
        default:
            break;
    }
    *out = target_cursor;
    return SS_JSON_OK;
}

static int clone_subtree_with_rollback(
    SSJsonDocument *target,
    SSJsonDocument *source,
    int64_t source_cursor,
    int64_t parent,
    int64_t *out
) {
    int64_t arena_mark = target->arena_used;
    int64_t node_mark = target->node_count;
    int rc = clone_subtree(target, source, source_cursor, parent, out);
    if (rc != SS_JSON_OK) {
        for (int64_t cursor = node_mark; cursor < target->node_count; ++cursor) {
            document_invalidate_subtree(target, cursor);
        }
        target->node_count = node_mark;
        target->arena_used = arena_mark;
        document_sync_bytes_used(target);
        if (out != NULL) *out = -1;
    }
    return rc;
}

static int document_set_node_from_source_scalar(
    SSJsonDocument *target,
    SSJsonNode *target_node,
    SSJsonNode *source_node
) {
    switch (source_node->kind) {
        case SS_JSON_NODE_STRING:
            return document_set_node_string(target, target_node, source_node->as.string_value);
        case SS_JSON_NODE_INTEGER:
            document_set_node_int64(target, target_node, source_node->as.int_value);
            return SS_JSON_OK;
        case SS_JSON_NODE_DOUBLE:
            document_set_node_double(target, target_node, source_node->as.double_value);
            return SS_JSON_OK;
        case SS_JSON_NODE_BOOLEAN:
            document_set_node_bool(target, target_node, source_node->as.bool_value);
            return SS_JSON_OK;
        case SS_JSON_NODE_NULL:
        default:
            document_set_node_null(target, target_node);
            return SS_JSON_OK;
    }
}

int ss_json_set_object_field_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    const char *json_text,
    int64_t *out
) {
    if (json_text == NULL || out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonDocument *source = NULL;
    int rc = ss_json_document_create_from_text(
        json_text, (int64_t)strlen(json_text) + 1, &source);
    if (rc != SS_JSON_OK) return rc;
    SSJsonNode *object_node;
    int64_t field_index;
    int exists;
    rc = object_prepare_field(document, cursor, field_name, &object_node, &field_index, &exists);
    if (rc != SS_JSON_OK) {
        ss_json_document_destroy(source);
        return rc;
    }
    SSJsonNode *source_root = document_node_at(source, 0);
    if (exists && source_root != NULL && !document_is_container_kind(source_root->kind)) {
        int64_t child_cursor = object_node->as.object_value.fields[field_index].child;
        SSJsonNode *child = document_node_at(document, child_cursor);
        rc = child != NULL
            ? document_set_node_from_source_scalar(document, child, source_root)
            : SS_JSON_ERR_PATH_NOT_FOUND;
        if (rc == SS_JSON_OK) {
            *out = child_cursor;
        }
        ss_json_document_destroy(source);
        return rc;
    }

    int64_t cloned_cursor;
    rc = clone_subtree_with_rollback(document, source, 0, cursor, &cloned_cursor);
    if (rc != SS_JSON_OK) {
        ss_json_document_destroy(source);
        return rc;
    }
    if (exists) {
        int64_t old_child = object_node->as.object_value.fields[field_index].child;
        document_invalidate_subtree(document, old_child);
        object_node = document_node_at(document, cursor);
        object_node->as.object_value.fields[field_index].child = cloned_cursor;
    } else {
        char *owned_name = NULL;
        int64_t arena_mark = document->arena_used;
        rc = document_copy_field_name(document, field_name, &owned_name);
        if (rc == SS_JSON_OK) {
            rc = object_append_field_with_child(
                document, cursor, object_node, owned_name, cloned_cursor);
        }
        if (rc != SS_JSON_OK) {
            document_invalidate_subtree(document, cloned_cursor);
            document->arena_used = arena_mark;
            document_sync_bytes_used(document);
            ss_json_document_destroy(source);
            return rc;
        }
    }
    *out = cloned_cursor;
    ss_json_document_destroy(source);
    return SS_JSON_OK;
}

static int array_prepare(
    SSJsonDocument *document,
    int64_t cursor,
    SSJsonNode **out_array
) {
    if (out_array == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    SSJsonNode *array_node = document_node_at(document, cursor);
    if (array_node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (array_node->kind != SS_JSON_NODE_ARRAY) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    *out_array = array_node;
    return SS_JSON_OK;
}

static int array_append_child(
    SSJsonDocument *document,
    int64_t array_cursor,
    SSJsonNode *array_node,
    int64_t child_cursor
) {
    (void)array_node;
    array_node = document_node_at(document, array_cursor);
    if (array_node == NULL || array_node->kind != SS_JSON_NODE_ARRAY) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    int rc = document_ensure_array_capacity(
        array_node, array_node->as.array_value.length + 1);
    if (rc != SS_JSON_OK) return rc;
    array_node = document_node_at(document, array_cursor);
    array_node->as.array_value.items[array_node->as.array_value.length++] = child_cursor;
    SSJsonNode *child = document_node_at(document, child_cursor);
    if (child != NULL) {
        child->parent = array_cursor;
    }
    return SS_JSON_OK;
}

static int array_insert_child(
    SSJsonDocument *document,
    int64_t array_cursor,
    SSJsonNode *array_node,
    int64_t index,
    int64_t child_cursor
) {
    (void)array_node;
    array_node = document_node_at(document, array_cursor);
    if (array_node == NULL || array_node->kind != SS_JSON_NODE_ARRAY) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    if (index < 0 || index > array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    int rc = document_ensure_array_capacity(
        array_node, array_node->as.array_value.length + 1);
    if (rc != SS_JSON_OK) return rc;
    array_node = document_node_at(document, array_cursor);
    int64_t move_count = array_node->as.array_value.length - index;
    if (move_count > 0) {
        memmove(
            &array_node->as.array_value.items[index + 1],
            &array_node->as.array_value.items[index],
            (size_t)move_count * sizeof(int64_t));
    }
    array_node->as.array_value.items[index] = child_cursor;
    array_node->as.array_value.length++;
    SSJsonNode *child = document_node_at(document, child_cursor);
    if (child != NULL) {
        child->parent = array_cursor;
    }
    return SS_JSON_OK;
}

static int create_scalar_node(
    SSJsonDocument *document,
    int64_t parent,
    SSJsonNodeKind kind,
    const void *value,
    int64_t *out
) {
    int64_t arena_mark = document->arena_used;
    int64_t node_mark = document->node_count;
    int rc = document_add_node(document, kind, parent, out);
    if (rc != SS_JSON_OK) return rc;
    SSJsonNode *node = document_node_at(document, *out);
    switch (kind) {
        case SS_JSON_NODE_STRING:
            rc = document_set_node_string(document, node, (const char *)value);
            break;
        case SS_JSON_NODE_INTEGER:
            document_set_node_int64(document, node, *(const long long *)value);
            rc = SS_JSON_OK;
            break;
        case SS_JSON_NODE_DOUBLE:
            document_set_node_double(document, node, *(const double *)value);
            rc = SS_JSON_OK;
            break;
        case SS_JSON_NODE_BOOLEAN:
            document_set_node_bool(document, node, *(const int *)value);
            rc = SS_JSON_OK;
            break;
        case SS_JSON_NODE_NULL:
        default:
            document_set_node_null(document, node);
            rc = SS_JSON_OK;
            break;
    }
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, *out);
        document->arena_used = arena_mark;
        document_sync_bytes_used(document);
        document->node_count = node_mark;
        *out = -1;
    }
    return rc;
}

static int append_array_scalar(
    SSJsonDocument *document,
    int64_t cursor,
    SSJsonNodeKind kind,
    const void *value
) {
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    int64_t child_cursor;
    rc = create_scalar_node(document, cursor, kind, value, &child_cursor);
    if (rc != SS_JSON_OK) return rc;
    rc = array_append_child(document, cursor, array_node, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
    }
    return rc;
}

int ss_json_append_array_element_string(
    SSJsonDocument *document,
    int64_t cursor,
    const char *value
) {
    return append_array_scalar(document, cursor, SS_JSON_NODE_STRING, value);
}

int ss_json_append_array_element_int64(
    SSJsonDocument *document,
    int64_t cursor,
    long long value
) {
    return append_array_scalar(document, cursor, SS_JSON_NODE_INTEGER, &value);
}

int ss_json_append_array_element_double(
    SSJsonDocument *document,
    int64_t cursor,
    double value
) {
    return append_array_scalar(document, cursor, SS_JSON_NODE_DOUBLE, &value);
}

int ss_json_append_array_element_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int value_truthiness
) {
    return append_array_scalar(document, cursor, SS_JSON_NODE_BOOLEAN, &value_truthiness);
}

int ss_json_append_array_element_null(SSJsonDocument *document, int64_t cursor) {
    return append_array_scalar(document, cursor, SS_JSON_NODE_NULL, NULL);
}

static int append_array_container(
    SSJsonDocument *document,
    int64_t cursor,
    SSJsonNodeKind kind,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    int64_t child_cursor;
    rc = document_add_node(document, kind, cursor, &child_cursor);
    if (rc != SS_JSON_OK) return rc;
    rc = array_append_child(document, cursor, array_node, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
        return rc;
    }
    *out = child_cursor;
    return SS_JSON_OK;
}

int ss_json_append_array_element_object(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
) {
    return append_array_container(document, cursor, SS_JSON_NODE_OBJECT, out);
}

int ss_json_append_array_element_array(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
) {
    return append_array_container(document, cursor, SS_JSON_NODE_ARRAY, out);
}

static int parse_and_clone_json_text(
    SSJsonDocument *document,
    const char *json_text,
    int64_t parent,
    int64_t *out
) {
    if (json_text == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    SSJsonDocument *source = NULL;
    int rc = ss_json_document_create_from_text(
        json_text, (int64_t)strlen(json_text) + 1, &source);
    if (rc != SS_JSON_OK) return rc;
    rc = clone_subtree_with_rollback(document, source, 0, parent, out);
    ss_json_document_destroy(source);
    return rc;
}

int ss_json_append_array_element_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    const char *json_text,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    int64_t child_cursor;
    rc = parse_and_clone_json_text(document, json_text, cursor, &child_cursor);
    if (rc != SS_JSON_OK) return rc;
    rc = array_append_child(document, cursor, array_node, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
        return rc;
    }
    *out = child_cursor;
    return SS_JSON_OK;
}

static int insert_array_scalar(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    SSJsonNodeKind kind,
    const void *value
) {
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index > array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    int64_t child_cursor;
    rc = create_scalar_node(document, cursor, kind, value, &child_cursor);
    if (rc != SS_JSON_OK) return rc;
    rc = array_insert_child(document, cursor, array_node, index, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
    }
    return rc;
}

int ss_json_insert_array_element_string(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *value
) {
    return insert_array_scalar(document, cursor, index, SS_JSON_NODE_STRING, value);
}

int ss_json_insert_array_element_int64(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    long long value
) {
    return insert_array_scalar(document, cursor, index, SS_JSON_NODE_INTEGER, &value);
}

int ss_json_insert_array_element_double(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    double value
) {
    return insert_array_scalar(document, cursor, index, SS_JSON_NODE_DOUBLE, &value);
}

int ss_json_insert_array_element_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int value_truthiness
) {
    return insert_array_scalar(document, cursor, index, SS_JSON_NODE_BOOLEAN, &value_truthiness);
}

int ss_json_insert_array_element_null(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index
) {
    return insert_array_scalar(document, cursor, index, SS_JSON_NODE_NULL, NULL);
}

static int insert_array_container(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    SSJsonNodeKind kind,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index > array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    int64_t child_cursor;
    rc = document_add_node(document, kind, cursor, &child_cursor);
    if (rc != SS_JSON_OK) return rc;
    rc = array_insert_child(document, cursor, array_node, index, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
        return rc;
    }
    *out = child_cursor;
    return SS_JSON_OK;
}

int ss_json_insert_array_element_object(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
) {
    return insert_array_container(document, cursor, index, SS_JSON_NODE_OBJECT, out);
}

int ss_json_insert_array_element_array(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
) {
    return insert_array_container(document, cursor, index, SS_JSON_NODE_ARRAY, out);
}

int ss_json_insert_array_element_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *json_text,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index > array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    int64_t child_cursor;
    rc = parse_and_clone_json_text(document, json_text, cursor, &child_cursor);
    if (rc != SS_JSON_OK) return rc;
    rc = array_insert_child(document, cursor, array_node, index, child_cursor);
    if (rc != SS_JSON_OK) {
        document_invalidate_subtree(document, child_cursor);
        return rc;
    }
    *out = child_cursor;
    return SS_JSON_OK;
}

static int replace_array_scalar(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    SSJsonNodeKind kind,
    const void *value
) {
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index >= array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    SSJsonNode *child = document_node_at(document, array_node->as.array_value.items[index]);
    if (child == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    switch (kind) {
        case SS_JSON_NODE_STRING:
            return document_set_node_string(document, child, (const char *)value);
        case SS_JSON_NODE_INTEGER:
            document_set_node_int64(document, child, *(const long long *)value);
            return SS_JSON_OK;
        case SS_JSON_NODE_DOUBLE:
            document_set_node_double(document, child, *(const double *)value);
            return SS_JSON_OK;
        case SS_JSON_NODE_BOOLEAN:
            document_set_node_bool(document, child, *(const int *)value);
            return SS_JSON_OK;
        case SS_JSON_NODE_NULL:
        default:
            document_set_node_null(document, child);
            return SS_JSON_OK;
    }
}

int ss_json_replace_array_element_string(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *value
) {
    return replace_array_scalar(document, cursor, index, SS_JSON_NODE_STRING, value);
}

int ss_json_replace_array_element_int64(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    long long value
) {
    return replace_array_scalar(document, cursor, index, SS_JSON_NODE_INTEGER, &value);
}

int ss_json_replace_array_element_double(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    double value
) {
    return replace_array_scalar(document, cursor, index, SS_JSON_NODE_DOUBLE, &value);
}

int ss_json_replace_array_element_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int value_truthiness
) {
    return replace_array_scalar(document, cursor, index, SS_JSON_NODE_BOOLEAN, &value_truthiness);
}

int ss_json_replace_array_element_null(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index
) {
    return replace_array_scalar(document, cursor, index, SS_JSON_NODE_NULL, NULL);
}

static int replace_array_container(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    SSJsonNodeKind kind,
    int64_t *out
) {
    if (out == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index >= array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    int64_t new_cursor;
    rc = document_add_node(document, kind, cursor, &new_cursor);
    if (rc != SS_JSON_OK) return rc;
    /* R-238: document_add_node may have realloc'd document->nodes, freeing the
     * buffer array_node points into. Re-fetch BEFORE reading the old child, or
     * old_child is read through a dangling pointer. */
    array_node = document_node_at(document, cursor);
    int64_t old_child = array_node->as.array_value.items[index];
    document_invalidate_subtree(document, old_child);
    array_node->as.array_value.items[index] = new_cursor;
    *out = new_cursor;
    return SS_JSON_OK;
}

int ss_json_replace_array_element_object(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
) {
    return replace_array_container(document, cursor, index, SS_JSON_NODE_OBJECT, out);
}

int ss_json_replace_array_element_array(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
) {
    return replace_array_container(document, cursor, index, SS_JSON_NODE_ARRAY, out);
}

int ss_json_replace_array_element_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *json_text,
    int64_t *out
) {
    if (out == NULL || json_text == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    *out = -1;
    SSJsonNode *array_node;
    int rc = array_prepare(document, cursor, &array_node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index >= array_node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    SSJsonDocument *source = NULL;
    rc = ss_json_document_create_from_text(
        json_text, (int64_t)strlen(json_text) + 1, &source);
    if (rc != SS_JSON_OK) return rc;
    SSJsonNode *source_root = document_node_at(source, 0);
    int64_t old_child_cursor = array_node->as.array_value.items[index];
    SSJsonNode *old_child = document_node_at(document, old_child_cursor);
    if (source_root != NULL && old_child != NULL && !document_is_container_kind(source_root->kind)) {
        rc = document_set_node_from_source_scalar(document, old_child, source_root);
        if (rc == SS_JSON_OK) {
            *out = old_child_cursor;
        }
        ss_json_document_destroy(source);
        return rc;
    }
    int64_t cloned_cursor;
    rc = clone_subtree_with_rollback(document, source, 0, cursor, &cloned_cursor);
    if (rc == SS_JSON_OK) {
        document_invalidate_subtree(document, old_child_cursor);
        array_node = document_node_at(document, cursor);
        array_node->as.array_value.items[index] = cloned_cursor;
        *out = cloned_cursor;
    }
    ss_json_document_destroy(source);
    return rc;
}

int ss_json_remove_object_field(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name
) {
    if (field_name == NULL) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    int64_t field_index;
    int rc = object_find_field_index(node, field_name, &field_index);
    if (rc == SS_JSON_ERR_PATH_NOT_FOUND) {
        return 1;
    }
    if (rc != SS_JSON_OK) return rc;
    document_invalidate_subtree(document, node->as.object_value.fields[field_index].child);
    int64_t move_count = node->as.object_value.length - field_index - 1;
    if (move_count > 0) {
        memmove(
            &node->as.object_value.fields[field_index],
            &node->as.object_value.fields[field_index + 1],
            (size_t)move_count * sizeof(SSJsonObjectField));
    }
    node->as.object_value.length--;
    return 0;
}

int ss_json_remove_array_element_at(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index
) {
    SSJsonNode *node;
    int rc = array_prepare(document, cursor, &node);
    if (rc != SS_JSON_OK) return rc;
    if (index < 0 || index >= node->as.array_value.length) {
        return SS_JSON_ERR_INDEX_OUT_OF_RANGE;
    }
    document_invalidate_subtree(document, node->as.array_value.items[index]);
    int64_t move_count = node->as.array_value.length - index - 1;
    if (move_count > 0) {
        memmove(
            &node->as.array_value.items[index],
            &node->as.array_value.items[index + 1],
            (size_t)move_count * sizeof(int64_t));
    }
    node->as.array_value.length--;
    return SS_JSON_OK;
}

int ss_json_clear_object(SSJsonDocument *document, int64_t cursor) {
    SSJsonNode *node = document_node_at(document, cursor);
    if (node == NULL) {
        return SS_JSON_ERR_PATH_NOT_FOUND;
    }
    if (node->kind != SS_JSON_NODE_OBJECT) {
        return SS_JSON_ERR_WRONG_TYPE;
    }
    for (int64_t index = 0; index < node->as.object_value.length; ++index) {
        document_invalidate_subtree(document, node->as.object_value.fields[index].child);
    }
    node->as.object_value.length = 0;
    return SS_JSON_OK;
}

int ss_json_clear_array(SSJsonDocument *document, int64_t cursor) {
    SSJsonNode *node;
    int rc = array_prepare(document, cursor, &node);
    if (rc != SS_JSON_OK) return rc;
    for (int64_t index = 0; index < node->as.array_value.length; ++index) {
        document_invalidate_subtree(document, node->as.array_value.items[index]);
    }
    node->as.array_value.length = 0;
    return SS_JSON_OK;
}
