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

SS_EXPORT long long ss_json_create_empty(long long capacity_bytes, int root_kind) {
    SSJsonDocument *d = 0;
    if (ss_json_document_create_empty(capacity_bytes, root_kind, &d) != 0) return 0;
    return (long long)(intptr_t)d;
}

SS_EXPORT long long ss_json_from_text(const char *json_text, long long capacity_bytes) {
    SSJsonDocument *d = 0;
    if (ss_json_document_create_from_text(json_text, capacity_bytes, &d) != 0) return 0;
    return (long long)(intptr_t)d;
}

SS_EXPORT long long ss_json_root(long long document) {
    return ss_json_document_root(DOC(document));
}

SS_EXPORT void ss_json_destroy(long long document) {
    ss_json_document_destroy(DOC(document));
}

SS_EXPORT const char *ss_json_serialize(long long document, char *scratch,
                                        long long scratch_capacity) {
    /* R-142: never return NULL (or uninitialized scratch) as a String. The native
     * serializer sets *out = NULL on EVERY failure — a null/non-mutable document,
     * or the realistic scratch-too-small path (sem_json_runtime.c: it returns
     * SS_JSON_ERR_SCRATCH_TOO_SMALL with *out still NULL) — and on the early
     * document guard it returns before even null-terminating scratch. The old
     * `out = scratch; serialize(&out); return out;` therefore handed that NULL
     * straight back, flowing a null String into downstream console/log/http binds
     * (a null deref or corrupted response). Fail safe to an empty, null-terminated
     * string, matching ss_json_read_string's never-NULL contract below. (Surfacing
     * the exact SS_JSON_ERR_* through `catch` instead of an empty sentinel is a
     * separate json family-ABI change — see R-142.) */
    const char *out = NULL;
    if (scratch != NULL && scratch_capacity > 0) {
        scratch[0] = '\0';
    }
    ss_json_document_serialize(DOC(document), scratch, scratch_capacity, &out);
    if (out != NULL) {
        return out;
    }
    return (scratch != NULL && scratch_capacity > 0) ? scratch : "";
}

SS_EXPORT int ss_json_set_field_string(long long document, long long cursor,
                                       const char *field_name, const char *value) {
    return ss_json_set_object_field_string(DOC(document), cursor, field_name, value);
}

SS_EXPORT int ss_json_set_field_int64(long long document, long long cursor,
                                      const char *field_name, long long value) {
    return ss_json_set_object_field_int64(DOC(document), cursor, field_name, value);
}

SS_EXPORT int ss_json_set_field_bool(long long document, long long cursor,
                                     const char *field_name, long long value) {
    /* Truthiness arrives as Int64 from both call sites (a Bool literal or a
     * sqlite 0/1 column), normalized here to the native int contract. */
    return ss_json_set_object_field_bool(DOC(document), cursor, field_name,
                                         value != 0);
}

SS_EXPORT long long ss_json_set_field_object(long long document, long long cursor,
                                             const char *field_name) {
    int64_t out = 0;
    ss_json_set_object_field_object(DOC(document), cursor, field_name, &out);
    return out;
}

SS_EXPORT long long ss_json_set_field_array(long long document, long long cursor,
                                            const char *field_name) {
    int64_t out = 0;
    ss_json_set_object_field_array(DOC(document), cursor, field_name, &out);
    return out;
}

SS_EXPORT long long ss_json_append_object(long long document, long long cursor) {
    int64_t out = 0;
    ss_json_append_array_element_object(DOC(document), cursor, &out);
    return out;
}

SS_EXPORT long long ss_json_field_at(long long document, long long cursor,
                                     const char *field_name) {
    int64_t out = 0;
    ss_json_navigate_object_field(DOC(document), cursor, field_name, &out);
    return out;
}

SS_EXPORT long long ss_json_read_int64(long long document, long long cursor,
                                       long long missing_default) {
    return ss_json_cursor_int64(DOC(document), cursor, missing_default);
}

SS_EXPORT const char *ss_json_read_string(long long document, long long cursor,
                                          char *scratch, long long scratch_capacity) {
    /* Default to an empty string, never NULL: a missing/non-string field leaves
     * the value absent, and callers treat the read as a String default (e.g. an
     * optional `displayName` that lowers to a NOT NULL '' column). Returning NULL
     * here would propagate a null String into binds and crash/violate schema. */
    const char *out = scratch;
    if (scratch != NULL && scratch_capacity > 0) {
        scratch[0] = '\0';
    }
    ss_json_cursor_string(DOC(document), cursor, scratch, scratch_capacity, &out);
    return out != NULL ? out : (scratch != NULL ? scratch : "");
}
