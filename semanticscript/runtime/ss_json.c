/*
 * ss_json.c — direct-return shim over the SemanticScript JSON runtime
 * (native_json/sem_json_runtime.c) for the `json.*` intrinsics
 * (APP-RUN-6). The native document API returns a status int and writes the
 * produced handle/cursor through a `*out` pointer; the EAV side wants a plain
 * `args -> single return`, so each entry here performs the out-param dance and
 * returns the handle/cursor/string directly. Documents + cursors cross the EAV
 * boundary as Int64 (OpaquePointer / JsonCursor).
 */
#include "sem_json_runtime.h"
#include "ss_runtime_export.h"
#include <stdint.h>

#define DOC(h) ((SSJsonDocument *)(intptr_t)(h))

static int ss_json_valid_document(long long document) {
    return document != 0 && ss_json_is_live_document(DOC(document));
}

static const char *ss_json_empty_string(char *scratch, long long scratch_capacity) {
    if (scratch != NULL && scratch_capacity > 0) {
        scratch[0] = '\0';
        return scratch;
    }
    return "";
}

static int ss_json_native_root_kind(int root_kind) {
    int native_root_kind = root_kind;
    if (root_kind == 5) native_root_kind = SS_JSON_NODE_OBJECT;
    if (root_kind == 4) native_root_kind = SS_JSON_NODE_ARRAY;
    return native_root_kind;
}

SS_EXPORT int ss_json_append_object_status(
    long long document,
    long long cursor,
    long long *out
);

SS_EXPORT int ss_json_create_empty_status(
    long long capacity_bytes,
    int root_kind,
    long long *out
) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = 0;
    SSJsonDocument *d = 0;
    int rc = ss_json_document_create_empty(
        capacity_bytes, ss_json_native_root_kind(root_kind), &d);
    if (rc != SS_JSON_OK) return rc;
    *out = (long long)(intptr_t)d;
    return SS_JSON_OK;
}

SS_EXPORT long long ss_json_create_empty(long long capacity_bytes, int root_kind) {
    /* The public standard.json JsonValueKind enum is ordered
     * null/bool/number/string/array/object (array=4, object=5), while the native
     * document runtime stores node kinds as object=0, array=1. Translate the
     * public contract at the shim boundary so a documented `objectJson` root does
     * not silently create a null handle and serialize as an empty string. */
    long long out = 0;
    return ss_json_create_empty_status(capacity_bytes, root_kind, &out) == SS_JSON_OK
        ? out
        : 0;
}

SS_EXPORT int ss_json_from_text_status(
    const char *json_text,
    long long capacity_bytes,
    long long maximum_bytes,
    long long max_depth,
    long long max_elements,
    long long *out
) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = 0;
    SSJsonDocument *d = 0;
    int rc = ss_json_document_create_from_text_limited(
        json_text, capacity_bytes, maximum_bytes, max_depth, max_elements, &d);
    if (rc != SS_JSON_OK) return rc;
    *out = (long long)(intptr_t)d;
    return SS_JSON_OK;
}

SS_EXPORT long long ss_json_from_text(
    const char *json_text,
    long long capacity_bytes,
    long long maximum_bytes,
    long long max_depth,
    long long max_elements
) {
    long long out = 0;
    return ss_json_from_text_status(
        json_text, capacity_bytes, maximum_bytes, max_depth, max_elements, &out) == SS_JSON_OK
        ? out
        : 0;
}

SS_EXPORT int ss_json_root_status(long long document, long long *out) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = -1;
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    long long root = ss_json_document_root(DOC(document));
    if (root < 0) return SS_JSON_ERR_PATH_NOT_FOUND;
    *out = root;
    return SS_JSON_OK;
}

SS_EXPORT long long ss_json_root(long long document) {
    long long out = -1;
    return ss_json_root_status(document, &out) == SS_JSON_OK ? out : -1;
}

SS_EXPORT void ss_json_destroy(long long document) {
    if (!ss_json_valid_document(document)) return;
    ss_json_document_destroy(DOC(document));
}

SS_EXPORT int ss_json_serialize_status(
    long long document,
    char *scratch,
    long long scratch_capacity,
    const char **out
) {
    /* R-142: never return NULL (or uninitialized scratch) as a String. The native
     * serializer sets *out = NULL on EVERY failure — a null/non-mutable document,
     * or the realistic scratch-too-small path (sem_json_runtime.c: it returns
     * SS_JSON_ERR_SCRATCH_TOO_SMALL with *out still NULL) — and on the early
     * document guard it returns before even null-terminating scratch. The old
     * `out = scratch; serialize(&out); return out;` therefore handed that NULL
     * straight back, flowing a null String into downstream console/log/http binds
     * (a null deref or corrupted response). Fail safe to an empty, null-terminated
     * string, matching ss_json_read_string's never-NULL contract below, while this
     * status wrapper preserves the exact SS_JSON_ERR_* for SemanticScript catch
     * lowering. */
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = ss_json_empty_string(scratch, scratch_capacity);
    if (!ss_json_valid_document(document)) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    const char *native_out = NULL;
    if (scratch != NULL && scratch_capacity > 0) {
        scratch[0] = '\0';
    }
    int rc = ss_json_document_serialize(
        DOC(document), scratch, scratch_capacity, &native_out);
    if (rc == SS_JSON_OK && native_out != NULL) {
        *out = native_out;
    }
    return rc;
}

SS_EXPORT const char *ss_json_serialize(long long document, char *scratch,
                                        long long scratch_capacity) {
    const char *out = "";
    ss_json_serialize_status(document, scratch, scratch_capacity, &out);
    return out != NULL ? out : ss_json_empty_string(scratch, scratch_capacity);
}

SS_EXPORT int ss_json_set_field_string(long long document, long long cursor,
                                       const char *field_name, const char *value) {
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    return ss_json_set_object_field_string(DOC(document), cursor, field_name, value);
}

SS_EXPORT int ss_json_set_field_int64(long long document, long long cursor,
                                      const char *field_name, long long value) {
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    return ss_json_set_object_field_int64(DOC(document), cursor, field_name, value);
}

SS_EXPORT int ss_json_set_field_bool(long long document, long long cursor,
                                     const char *field_name, long long value) {
    /* Truthiness arrives as Int64 from both call sites (a Bool literal or a
     * sqlite 0/1 column), normalized here to the native int contract. */
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    return ss_json_set_object_field_bool(DOC(document), cursor, field_name,
                                         value != 0);
}

SS_EXPORT int ss_json_set_field_object_status(
    long long document,
    long long cursor,
    const char *field_name,
    long long *out
) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = -1;
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    int64_t native_out = -1;
    int rc = ss_json_set_object_field_object(DOC(document), cursor, field_name, &native_out);
    if (rc == SS_JSON_OK) *out = (long long)native_out;
    return rc;
}

SS_EXPORT long long ss_json_set_field_object(long long document, long long cursor,
                                             const char *field_name) {
    long long out = -1;
    return ss_json_set_field_object_status(document, cursor, field_name, &out) == SS_JSON_OK
        ? out
        : -1;
}

SS_EXPORT int ss_json_set_field_array_status(
    long long document,
    long long cursor,
    const char *field_name,
    long long *out
) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = -1;
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    int64_t native_out = -1;
    int rc = ss_json_set_object_field_array(DOC(document), cursor, field_name, &native_out);
    if (rc == SS_JSON_OK) *out = (long long)native_out;
    return rc;
}

SS_EXPORT long long ss_json_set_field_array(long long document, long long cursor,
                                            const char *field_name) {
    long long out = -1;
    return ss_json_set_field_array_status(document, cursor, field_name, &out) == SS_JSON_OK
        ? out
        : -1;
}

SS_EXPORT long long ss_json_append_object(long long document, long long cursor) {
    long long out = -1;
    return ss_json_append_object_status(document, cursor, &out) == SS_JSON_OK
        ? out
        : -1;
}

SS_EXPORT int ss_json_append_object_status(
    long long document,
    long long cursor,
    long long *out
) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = -1;
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    int64_t native_out = -1;
    int rc = ss_json_append_array_element_object(DOC(document), cursor, &native_out);
    if (rc == SS_JSON_OK) *out = (long long)native_out;
    return rc;
}

SS_EXPORT int ss_json_field_at_status(
    long long document,
    long long cursor,
    const char *field_name,
    long long *out
) {
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = -1;
    if (!ss_json_valid_document(document)) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    int64_t native_out = -1;
    int rc = ss_json_navigate_object_field(DOC(document), cursor, field_name, &native_out);
    if (rc == SS_JSON_OK) *out = (long long)native_out;
    return rc;
}

SS_EXPORT long long ss_json_field_at(long long document, long long cursor,
                                     const char *field_name) {
    long long out = -1;
    return ss_json_field_at_status(document, cursor, field_name, &out) == SS_JSON_OK
        ? out
        : -1;
}

SS_EXPORT long long ss_json_read_int64(long long document, long long cursor,
                                       long long missing_default) {
    if (!ss_json_valid_document(document)) return missing_default;
    return ss_json_cursor_int64(DOC(document), cursor, missing_default);
}

SS_EXPORT int ss_json_read_string_status(
    long long document,
    long long cursor,
    char *scratch,
    long long scratch_capacity,
    const char **out
) {
    /* Default to an empty string, never NULL: a missing/non-string field leaves
     * the value absent, and callers treat the read as a String default (e.g. an
     * optional `displayName` that lowers to a NOT NULL '' column). Returning NULL
     * here would propagate a null String into binds and crash/violate schema.
     * This status wrapper still returns the exact access error to caught call
     * sites, so empty data and access failure are distinguishable. */
    if (out == 0) return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    *out = ss_json_empty_string(scratch, scratch_capacity);
    if (!ss_json_valid_document(document)) {
        return SS_JSON_ERR_DOCUMENT_NOT_MUTABLE;
    }
    const char *native_out = NULL;
    if (scratch != NULL && scratch_capacity > 0) {
        scratch[0] = '\0';
    }
    int rc = ss_json_cursor_string(DOC(document), cursor, scratch, scratch_capacity, &native_out);
    if (rc == SS_JSON_OK && native_out != NULL) {
        *out = native_out;
    }
    return rc;
}

SS_EXPORT const char *ss_json_read_string(long long document, long long cursor,
                                          char *scratch, long long scratch_capacity) {
    const char *out = "";
    ss_json_read_string_status(document, cursor, scratch, scratch_capacity, &out);
    return out != NULL ? out : ss_json_empty_string(scratch, scratch_capacity);
}
