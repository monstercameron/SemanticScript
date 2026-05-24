#ifndef SEM_JSON_RUNTIME_H
#define SEM_JSON_RUNTIME_H

/*
 * SemanticScript-owned C ABI for JSON encode / decode at the field level.
 *
 * This header is self-contained - it does not include any upstream JSON
 * library. The intent is that SemanticScript code composes a JSON document
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
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSJsonBuilder SSJsonBuilder;
typedef struct SSJsonDocument SSJsonDocument;

enum {
    SS_JSON_OK                 = 0,
    SS_JSON_ERR_CONFIG         = 1,  /* NULL arguments or invalid capacity. */
    SS_JSON_ERR_OVERFLOW       = 2,  /* Append would exceed the builder's capacity. */
    SS_JSON_ERR_STRUCTURE      = 3,  /* Mismatched open/close, or a field outside any object. */
    SS_JSON_ERR_ALLOCATION     = 4   /* malloc failed in builder creation. */
};

/*
 * Document-access error codes. These are numerically aligned with the
 * planned standard.json JsonAccessError case ordinals. The older
 * builder/finder SS_JSON_ERR_CONFIG / OVERFLOW / STRUCTURE /
 * ALLOCATION names above stay available for source and ABI
 * compatibility with the pre-document runtime.
 */
enum {
    SS_JSON_ERR_PATH_NOT_FOUND    = 1,
    SS_JSON_ERR_WRONG_TYPE        = 2,
    SS_JSON_ERR_INDEX_OUT_OF_RANGE = 3,
    SS_JSON_ERR_FIELD_NAME_TOO_LONG = 4,
    SS_JSON_ERR_DOCUMENT_NOT_MUTABLE = 5,
    SS_JSON_ERR_CAPACITY_EXCEEDED = 6,
    SS_JSON_ERR_MALFORMED_PATH    = 7,
    SS_JSON_ERR_SCRATCH_TOO_SMALL = 8
};

typedef enum SSJsonNodeKind {
    SS_JSON_NODE_OBJECT  = 0,
    SS_JSON_NODE_ARRAY   = 1,
    SS_JSON_NODE_STRING  = 2,
    SS_JSON_NODE_INTEGER = 3,
    SS_JSON_NODE_DOUBLE  = 4,
    SS_JSON_NODE_BOOLEAN = 5,
    SS_JSON_NODE_NULL    = 6
} SSJsonNodeKind;

#define SS_JSON_MAX_FIELD_NAME_BYTES 1024

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

/* ----- primitive codec helpers -----
 *
 * High-level json.stringify.<primitive> / json.parse.<primitive> aliases lower
 * through these helpers so formatting, escaping, strict token parsing,
 * trailing-junk rejection, and caller scratch capacity checks live in the
 * native JSON runtime rather than in compiler-side formatting stubs. */
int ss_json_stringify_string(
    const char *value,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);
int ss_json_stringify_int64(
    long long value,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);
int ss_json_stringify_double(
    double value,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);
int ss_json_stringify_bool(
    int value_truthiness,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);

int ss_json_parse_int64(const char *json_text, long long *out);
int ss_json_parse_double(const char *json_text, double *out);
int ss_json_parse_bool(const char *json_text, int *out);

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

/* ----- document tree (CRUD side) -----
 *
 * SSJsonDocument owns a mutable parsed JSON tree. Cursors are stable
 * int64_t node-table indices; cursor 0 is always the root for a valid
 * document. Scalar updates mutate the existing node so previously held
 * cursors to that node remain valid. The structural operations below
 * invalidate removed/replaced descendant cursors by marking their
 * backing nodes inactive:
 *   - ss_json_remove_object_field
 *   - ss_json_remove_array_element_at
 *   - ss_json_clear_object
 *   - ss_json_clear_array
 *   - ss_json_set_object_field_object
 *   - ss_json_set_object_field_array
 *   - ss_json_set_object_field_json_text when the grafted value is a
 *     container or replaces an existing container
 *   - ss_json_insert_array_element_* for position-based path lookups
 *   - ss_json_replace_array_element_object
 *   - ss_json_replace_array_element_array
 *   - ss_json_replace_array_element_json_text when the grafted value
 *     is a container or replaces an existing container
 *
 * The document keeps copied string values and field names in a
 * capacity-bounded arena. CapacityExceeded means appending the new
 * bytes would exceed capacity_bytes; failed copies do not advance the
 * arena. Removed strings are not reclaimed until document destroy.
 */

int ss_json_document_create_from_text(
    const char *json_text,
    int64_t capacity_bytes,
    SSJsonDocument **out
);

int ss_json_document_create_empty(
    int64_t capacity_bytes,
    int32_t root_kind,
    SSJsonDocument **out
);

void ss_json_document_destroy(SSJsonDocument *document);

int ss_json_document_serialize(
    SSJsonDocument *document,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);

int64_t ss_json_document_length(SSJsonDocument *document);
int64_t ss_json_document_root(SSJsonDocument *document);

int ss_json_navigate_object_field(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int64_t *out
);

int ss_json_navigate_array_element(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
);

int ss_json_cursor_parent(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
);

int ss_json_cursor_at_path(
    SSJsonDocument *document,
    const char *path,
    int64_t *out
);

int32_t ss_json_cursor_kind(SSJsonDocument *document, int64_t cursor);
int ss_json_cursor_is_null(SSJsonDocument *document, int64_t cursor);
long long ss_json_cursor_int64(
    SSJsonDocument *document,
    int64_t cursor,
    long long missing_default
);
double ss_json_cursor_double(
    SSJsonDocument *document,
    int64_t cursor,
    double missing_default
);
int ss_json_cursor_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int missing_default
);

int ss_json_cursor_string(
    SSJsonDocument *document,
    int64_t cursor,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);

int ss_json_cursor_array_length(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
);

int ss_json_cursor_object_field_count(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
);

int ss_json_cursor_object_field_name_at(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    char *scratch,
    int64_t scratch_capacity,
    const char **out
);

int ss_json_cursor_object_field_value_at(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
);

int ss_json_set_object_field_string(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    const char *value
);
int ss_json_set_object_field_int64(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    long long value
);
int ss_json_set_object_field_double(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    double value
);
int ss_json_set_object_field_bool(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int value_truthiness
);
int ss_json_set_object_field_null(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name
);

/* Container setters replace any existing field child and invalidate
 * that old child subtree. The new container cursor is returned in out. */
int ss_json_set_object_field_object(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int64_t *out
);
int ss_json_set_object_field_array(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    int64_t *out
);
int ss_json_set_object_field_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name,
    const char *json_text,
    int64_t *out
);

int ss_json_append_array_element_string(
    SSJsonDocument *document,
    int64_t cursor,
    const char *value
);
int ss_json_append_array_element_int64(
    SSJsonDocument *document,
    int64_t cursor,
    long long value
);
int ss_json_append_array_element_double(
    SSJsonDocument *document,
    int64_t cursor,
    double value
);
int ss_json_append_array_element_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int value_truthiness
);
int ss_json_append_array_element_null(
    SSJsonDocument *document,
    int64_t cursor
);
int ss_json_append_array_element_object(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
);
int ss_json_append_array_element_array(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t *out
);
int ss_json_append_array_element_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    const char *json_text,
    int64_t *out
);

/* Insert shifts later array positions; existing node cursors remain
 * valid, but path/index lookups after the insertion observe the new
 * positions. Container inserts return the inserted cursor in out. */
int ss_json_insert_array_element_string(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *value
);
int ss_json_insert_array_element_int64(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    long long value
);
int ss_json_insert_array_element_double(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    double value
);
int ss_json_insert_array_element_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int value_truthiness
);
int ss_json_insert_array_element_null(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index
);
int ss_json_insert_array_element_object(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
);
int ss_json_insert_array_element_array(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
);
int ss_json_insert_array_element_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *json_text,
    int64_t *out
);

int ss_json_replace_array_element_string(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *value
);
int ss_json_replace_array_element_int64(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    long long value
);
int ss_json_replace_array_element_double(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    double value
);
int ss_json_replace_array_element_bool(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int value_truthiness
);
int ss_json_replace_array_element_null(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index
);

/* Replacing with a container invalidates the old element subtree and
 * returns the new container cursor in out. */
int ss_json_replace_array_element_object(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
);
int ss_json_replace_array_element_array(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    int64_t *out
);
int ss_json_replace_array_element_json_text(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index,
    const char *json_text,
    int64_t *out
);

/* Returns 0 when a field was removed and 1 when it was absent; returns
 * SS_JSON_ERR_WRONG_TYPE for non-object cursors. Removed child cursors
 * and descendants are invalidated. */
int ss_json_remove_object_field(
    SSJsonDocument *document,
    int64_t cursor,
    const char *field_name
);

/* Removal shifts later array positions and invalidates the removed
 * element subtree. */
int ss_json_remove_array_element_at(
    SSJsonDocument *document,
    int64_t cursor,
    int64_t index
);

/* Clear preserves the cursor's kind and invalidates all removed child
 * subtrees. */
int ss_json_clear_object(SSJsonDocument *document, int64_t cursor);
int ss_json_clear_array(SSJsonDocument *document, int64_t cursor);

#ifdef __cplusplus
}
#endif

#endif
