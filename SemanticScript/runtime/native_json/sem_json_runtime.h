#ifndef SEM_JSON_RUNTIME_H
#define SEM_JSON_RUNTIME_H

/*
 * SemanticScript-owned C ABI for JSON encode / decode at the field level.
 *
 * This header is self-contained — it does not include any upstream JSON
 * library. The intent is that AgentScript code composes a JSON document
 * field-by-field via an opaque SSJsonBuilder handle (the encode path)
 * and reads a parsed document field-by-field via the ss_json_find_*
 * accessors (the decode path). There is no "record codec" abstraction
 * here because the reference compiler currently treats AS records as
 * pure metadata; encoding/decoding is therefore the caller's loop, with
 * this runtime providing the per-field primitives and the JSON-correct
 * escape/quote/format handling.
 *
 * Memory model
 *   - SSJsonBuilder is heap-allocated by ss_json_builder_create() and
 *     must be released by ss_json_builder_destroy(). The recommended
 *     idiom in AS source is `defer json.destroyBuilder builderName`
 *     immediately after the create call.
 *   - ss_json_builder_finish() returns a pointer into the builder's
 *     internal buffer. The pointer is valid until the next builder
 *     operation OR the builder is destroyed; callers must NOT free it
 *     directly.
 *   - ss_json_find_string() copies the decoded value into a caller-
 *     supplied scratch buffer (so the JSON-escape decoding has somewhere
 *     to write its results). The returned pointer aliases the scratch
 *     buffer; lifetime is owned by the caller.
 *
 * Error model
 *   - Every builder mutator returns SS_JSON_OK on success or
 *     SS_JSON_ERR_* on failure (buffer overflow, structural error like
 *     closing an object that wasn't open). Callers should bindError +
 *     branchIfError on every mutator OR explicitly ignoreOk if the
 *     budget for the response body is bounded by upstream sizing.
 *   - The decoder helpers return sentinel values on absent fields:
 *     find_string() returns NULL, find_int64()/find_bool()/find_double()
 *     each take a `missing_default` argument and return it when the
 *     named field is missing OR not the right type. has_field() is the
 *     unambiguous "is this field present" check.
 */

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSJsonBuilder SSJsonBuilder;

enum {
    SS_JSON_OK                 = 0,
    SS_JSON_ERR_CONFIG         = 1,  /* NULL arguments or invalid capacity. */
    SS_JSON_ERR_OVERFLOW       = 2,  /* Append would exceed the builder's capacity. */
    SS_JSON_ERR_STRUCTURE      = 3,  /* Mismatched open/close, or a field outside any object. */
    SS_JSON_ERR_ALLOCATION     = 4   /* malloc failed in builder creation. */
};

/* Suggested default capacity for response bodies. Callers may pass any
 * positive size_t into ss_json_builder_create(); this constant exists
 * so the AS storage row for "default" sizes has a documented value. */
#define SS_JSON_DEFAULT_BUILDER_CAPACITY 4096

/* ----- builder (encode side) ----- */

SSJsonBuilder *ss_json_builder_create(size_t capacity);
void           ss_json_builder_destroy(SSJsonBuilder *builder);

int ss_json_builder_object_open(SSJsonBuilder *builder);
int ss_json_builder_object_close(SSJsonBuilder *builder);
int ss_json_builder_array_open(SSJsonBuilder *builder);
int ss_json_builder_array_close(SSJsonBuilder *builder);

/* Field writers — write `,"name":value` if a sibling has already been
 * written in the current container, otherwise `"name":value`. The
 * `value` argument is rendered JSON-correctly: integers as decimal,
 * floats via snprintf %.17g, booleans as `true`/`false`, strings with
 * proper escaping for ", \, /, \b, \f, \n, \r, \t and control bytes
 * via \uXXXX. Null fields use the `null` literal. */
int ss_json_builder_field_int64(SSJsonBuilder *builder, const char *field_name, long long value);
int ss_json_builder_field_double(SSJsonBuilder *builder, const char *field_name, double value);
int ss_json_builder_field_bool(SSJsonBuilder *builder, const char *field_name, int value_truthiness);
int ss_json_builder_field_string(SSJsonBuilder *builder, const char *field_name, const char *value);
int ss_json_builder_field_null(SSJsonBuilder *builder, const char *field_name);

/* Array-element writers — same shape minus the field name. Use these
 * inside an `array_open` / `array_close` pair. */
int ss_json_builder_element_int64(SSJsonBuilder *builder, long long value);
int ss_json_builder_element_double(SSJsonBuilder *builder, double value);
int ss_json_builder_element_bool(SSJsonBuilder *builder, int value_truthiness);
int ss_json_builder_element_string(SSJsonBuilder *builder, const char *value);
int ss_json_builder_element_null(SSJsonBuilder *builder);

/* Returns the null-terminated body assembled so far. Pointer is valid
 * until the next builder mutator or destroy. Returns NULL if the
 * builder is in an error state. */
const char *ss_json_builder_finish(SSJsonBuilder *builder);
size_t      ss_json_builder_length(const SSJsonBuilder *builder);

/* ----- finder (decode side) -----
 *
 * All finders operate on a flat object — they scan for `"name":` at the
 * object's top level. They do NOT recurse into nested objects or
 * arrays. For deep documents, decode one level at a time using
 * ss_json_find_substring to extract the nested object as a string, then
 * call the finders again on that substring. */

/* Returns 1 if the named field is present, 0 otherwise. Inexpensive
 * compared to the typed finders — use this when you only need
 * presence, not the value. */
int ss_json_has_field(const char *json_text, const char *field_name);

/* Returns the decoded string value via `scratch_buffer` (which must
 * have at least `scratch_capacity` bytes). The decoder un-escapes
 * standard JSON escapes (\", \\, \/, \b, \f, \n, \r, \t) and \uXXXX
 * sequences in the BMP range. Returns NULL if the field is missing,
 * not a string, or wouldn't fit in the scratch buffer; otherwise
 * returns scratch_buffer. */
const char *ss_json_find_string(
    const char *json_text,
    const char *field_name,
    char *scratch_buffer,
    size_t scratch_capacity
);

/* Returns the int64 value of the named field, or `missing_default` if
 * the field is absent or not a number. Floats with a fractional part
 * are truncated. */
long long ss_json_find_int64(
    const char *json_text,
    const char *field_name,
    long long missing_default
);

double ss_json_find_double(
    const char *json_text,
    const char *field_name,
    double missing_default
);

/* Returns 1 for `true`, 0 for `false`, `missing_default` for anything
 * else (missing, null, wrong type). */
int ss_json_find_bool(
    const char *json_text,
    const char *field_name,
    int missing_default
);

#ifdef __cplusplus
}
#endif

#endif
