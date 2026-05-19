#include "sem_json_runtime.h"

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * Container kind tracking. The builder maintains a small stack so we
 * know whether the most recent open was an object (where field names
 * are required) or an array (where they're forbidden), and whether
 * we're at the first sibling (so we can decide between writing a
 * leading comma or not).
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
    int written = snprintf(number_text, sizeof(number_text), "%.17g", value);
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
    int written = snprintf(number_text, sizeof(number_text), "%.17g", value);
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

/* Decode the four-hex-digit \uXXXX BMP escape into UTF-8 bytes. Writes
 * 1-3 bytes into `out`. Returns bytes written, or -1 on malformed
 * hex. Surrogate-pair handling is deferred — a single \uD8xx without
 * a low surrogate writes the replacement character (U+FFFD). */
static int decode_unicode_escape(const char *hex_chars, char *out) {
    int code_point = 0;
    for (int hex_index = 0; hex_index < 4; ++hex_index) {
        char c = hex_chars[hex_index];
        int digit;
        if (c >= '0' && c <= '9') digit = c - '0';
        else if (c >= 'a' && c <= 'f') digit = 10 + (c - 'a');
        else if (c >= 'A' && c <= 'F') digit = 10 + (c - 'A');
        else return -1;
        code_point = (code_point << 4) | digit;
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
        char emit_buf[3];
        int emit_count;
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
                emit_count = decode_unicode_escape(scan + 2, emit_buf);
                if (emit_count < 0) return NULL;
                scan += 4;  /* additional skip past the 4 hex digits */
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

long long ss_json_find_int64(
    const char *json_text, const char *field_name, long long missing_default
) {
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL) return missing_default;
    /* Accept leading minus + digits. atoll handles the rest including
     * any trailing fractional part by truncating. */
    if (*value_start != '-' && (*value_start < '0' || *value_start > '9')) {
        return missing_default;
    }
    return atoll(value_start);
}

double ss_json_find_double(
    const char *json_text, const char *field_name, double missing_default
) {
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL) return missing_default;
    if (*value_start != '-' && (*value_start < '0' || *value_start > '9')
        && *value_start != '.') {
        return missing_default;
    }
    return atof(value_start);
}

int ss_json_find_bool(
    const char *json_text, const char *field_name, int missing_default
) {
    const char *value_start = find_field_value(json_text, field_name);
    if (value_start == NULL) return missing_default;
    if (strncmp(value_start, "true", 4) == 0) return 1;
    if (strncmp(value_start, "false", 5) == 0) return 0;
    return missing_default;
}
