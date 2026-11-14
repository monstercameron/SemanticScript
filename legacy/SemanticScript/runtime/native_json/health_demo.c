#include "sem_json_runtime.h"

#include <stdio.h>
#include <string.h>

/*
 * Smoke demo for the native_json adapter. Builds a small object,
 * round-trips it through the finder API, then exercises the mutable
 * document tree API with generic JSON navigation and CRUD operations.
 * Designed to fail loud on escape regressions, off-by-one comma
 * handling, cursor/path mistakes, and buffer mis-sizing.
 */

static int fail(const char *stage, int status) {
    fprintf(stderr, "sem_json_health_demo: %s failed status=%d\n", stage, status);
    return status;
}

static int require_ok(const char *stage, int status) {
    if (status != SS_JSON_OK) {
        return fail(stage, status);
    }
    return 0;
}

static int require_int64(const char *stage, long long got, long long expected) {
    if (got != expected) {
        fprintf(
            stderr,
            "sem_json_health_demo: %s mismatch got=%lld expected=%lld\n",
            stage,
            got,
            expected);
        return 1;
    }
    return 0;
}

static int require_cstring(const char *stage, const char *got, const char *expected) {
    if (got == NULL || strcmp(got, expected) != 0) {
        fprintf(
            stderr,
            "sem_json_health_demo: %s mismatch got=%s expected=%s\n",
            stage,
            got != NULL ? got : "<NULL>",
            expected);
        return 1;
    }
    return 0;
}

int main(void) {
    SSJsonBuilder *builder = ss_json_builder_create(SS_JSON_DEFAULT_BUILDER_CAPACITY);
    if (builder == NULL) {
        return fail("builder_create", 1);
    }

    int rc;
    rc = ss_json_builder_object_open(builder);
    if (rc != SS_JSON_OK) return fail("object_open", rc);

    rc = ss_json_builder_field_int64(builder, "id", 42);
    if (rc != SS_JSON_OK) return fail("field_int64(id)", rc);

    /* Force a multi-escape string so we exercise \" \\ \n \t plus a
     * ü-style escape in the unicode-control range. */
    rc = ss_json_builder_field_string(builder, "title", "hello \"json\"\\world\nline\t\x01");
    if (rc != SS_JSON_OK) return fail("field_string(title)", rc);

    rc = ss_json_builder_field_bool(builder, "done", 0);
    if (rc != SS_JSON_OK) return fail("field_bool(done)", rc);

    rc = ss_json_builder_field_double(builder, "ratio", 0.5);
    if (rc != SS_JSON_OK) return fail("field_double(ratio)", rc);

    rc = ss_json_builder_field_null(builder, "completedAt");
    if (rc != SS_JSON_OK) return fail("field_null(completedAt)", rc);

    rc = ss_json_builder_object_close(builder);
    if (rc != SS_JSON_OK) return fail("object_close", rc);

    const char *body = ss_json_builder_finish(builder);
    if (body == NULL) {
        ss_json_builder_destroy(builder);
        return fail("finish", 1);
    }

    printf("sem_json_health_demo: body=%s\n", body);

    /* Round-trip the integer + bool + null markers via the finders. */
    long long round_trip_id = ss_json_find_int64(body, "id", -1);
    int round_trip_done = ss_json_find_bool(body, "done", -1);
    int completed_present = ss_json_has_field(body, "completedAt");
    int missing_present = ss_json_has_field(body, "doesNotExist");

    char title_scratch[128];
    const char *recovered_title = ss_json_find_string(
        body, "title", title_scratch, sizeof(title_scratch));

    printf(
        "sem_json_health_demo: id=%lld done=%d completedAt_present=%d missing_present=%d title=%s\n",
        round_trip_id, round_trip_done, completed_present, missing_present,
        recovered_title != NULL ? recovered_title : "<NULL>");

    int round_trip_ok =
        (round_trip_id == 42)
        && (round_trip_done == 0)
        && (completed_present == 1)
        && (missing_present == 0)
        && (recovered_title != NULL)
        && (strcmp(recovered_title, "hello \"json\"\\world\nline\t\x01") == 0);

    if (!round_trip_ok) {
        ss_json_builder_destroy(builder);
        fprintf(stderr, "sem_json_health_demo: round-trip mismatch\n");
        return 1;
    }

    SSJsonDocument *document = NULL;
    rc = ss_json_document_create_from_text(body, 4096, &document);
    if (require_ok("document_create_from_text", rc)) {
        ss_json_builder_destroy(builder);
        return rc;
    }
    ss_json_builder_destroy(builder);

    int64_t root = ss_json_document_root(document);
    if (require_int64("document_root", root, 0)) return 1;

    int64_t title_cursor;
    rc = ss_json_cursor_at_path(document, ".title", &title_cursor);
    if (require_ok("cursor_at_path(.title)", rc)) return rc;

    char document_scratch[512];
    const char *cursor_title = NULL;
    rc = ss_json_cursor_string(
        document, title_cursor, document_scratch, sizeof(document_scratch), &cursor_title);
    if (require_ok("cursor_string(title)", rc)) return rc;
    if (require_cstring("cursor_string(title)", cursor_title, "hello \"json\"\\world\nline\t\x01")) {
        return 1;
    }

    int64_t id_cursor;
    rc = ss_json_navigate_object_field(document, root, "id", &id_cursor);
    if (require_ok("navigate_object_field(id)", rc)) return rc;
    if (require_int64("cursor_int64(id)", ss_json_cursor_int64(document, id_cursor, -1), 42)) {
        return 1;
    }

    rc = ss_json_set_object_field_string(document, root, "title", "updated");
    if (require_ok("set_object_field_string(title)", rc)) return rc;
    rc = ss_json_set_object_field_int64(document, root, "id", 43);
    if (require_ok("set_object_field_int64(id)", rc)) return rc;
    rc = ss_json_set_object_field_bool(document, root, "archived", 1);
    if (require_ok("set_object_field_bool(archived)", rc)) return rc;

    int64_t tags_cursor;
    rc = ss_json_set_object_field_array(document, root, "tags", &tags_cursor);
    if (require_ok("set_object_field_array(tags)", rc)) return rc;
    rc = ss_json_append_array_element_string(document, tags_cursor, "alpha");
    if (require_ok("append_array_element_string(tags)", rc)) return rc;
    rc = ss_json_append_array_element_int64(document, tags_cursor, 7);
    if (require_ok("append_array_element_int64(tags)", rc)) return rc;
    rc = ss_json_insert_array_element_string(document, tags_cursor, 1, "middle");
    if (require_ok("insert_array_element_string(tags)", rc)) return rc;
    rc = ss_json_replace_array_element_string(document, tags_cursor, 0, "first");
    if (require_ok("replace_array_element_string(tags)", rc)) return rc;
    rc = ss_json_remove_array_element_at(document, tags_cursor, 2);
    if (require_ok("remove_array_element_at(tags)", rc)) return rc;

    int64_t tags_length;
    rc = ss_json_cursor_array_length(document, tags_cursor, &tags_length);
    if (require_ok("cursor_array_length(tags)", rc)) return rc;
    if (require_int64("cursor_array_length(tags)", tags_length, 2)) return 1;

    int64_t meta_cursor;
    rc = ss_json_set_object_field_object(document, root, "meta", &meta_cursor);
    if (require_ok("set_object_field_object(meta)", rc)) return rc;
    rc = ss_json_set_object_field_double(document, meta_cursor, "score", 9.5);
    if (require_ok("set_object_field_double(meta.score)", rc)) return rc;
    rc = ss_json_set_object_field_null(document, meta_cursor, "note");
    if (require_ok("set_object_field_null(meta.note)", rc)) return rc;

    int64_t profile_cursor;
    rc = ss_json_set_object_field_json_text(
        document, root, "profile", "{\"enabled\":true,\"count\":2}", &profile_cursor);
    if (require_ok("set_object_field_json_text(profile)", rc)) return rc;

    int64_t count_cursor;
    rc = ss_json_cursor_at_path(document, ".profile.count", &count_cursor);
    if (require_ok("cursor_at_path(.profile.count)", rc)) return rc;
    if (require_int64("cursor_int64(profile.count)", ss_json_cursor_int64(document, count_cursor, -1), 2)) {
        return 1;
    }

    int64_t title_parent;
    rc = ss_json_cursor_parent(document, title_cursor, &title_parent);
    if (require_ok("cursor_parent(title)", rc)) return rc;
    if (require_int64("cursor_parent(title)", title_parent, root)) return 1;

    int removed = ss_json_remove_object_field(document, root, "completedAt");
    if (removed != 0) return fail("remove_object_field(completedAt)", removed);
    int absent_remove = ss_json_remove_object_field(document, root, "completedAt");
    if (absent_remove != 1) return fail("remove_object_field(absent completedAt)", absent_remove);

    char serialized[1024];
    const char *serialized_body = NULL;
    rc = ss_json_document_serialize(document, serialized, sizeof(serialized), &serialized_body);
    if (require_ok("document_serialize", rc)) return rc;

    const char *expected_body =
        "{\"id\":43,\"title\":\"updated\",\"done\":false,\"ratio\":0.5,"
        "\"archived\":true,\"tags\":[\"first\",\"middle\"],"
        "\"meta\":{\"score\":9.5,\"note\":null},"
        "\"profile\":{\"enabled\":true,\"count\":2}}";
    if (require_cstring("document_serialize", serialized_body, expected_body)) return 1;
    if (require_int64(
            "document_length",
            ss_json_document_length(document),
            (long long)strlen(expected_body))) {
        return 1;
    }

    rc = ss_json_clear_array(document, tags_cursor);
    if (require_ok("clear_array(tags)", rc)) return rc;
    rc = ss_json_cursor_array_length(document, tags_cursor, &tags_length);
    if (require_ok("cursor_array_length(cleared tags)", rc)) return rc;
    if (require_int64("cursor_array_length(cleared tags)", tags_length, 0)) return 1;
    rc = ss_json_clear_object(document, meta_cursor);
    if (require_ok("clear_object(meta)", rc)) return rc;

    ss_json_document_destroy(document);

    SSJsonDocument *empty = NULL;
    rc = ss_json_document_create_empty(128, SS_JSON_NODE_ARRAY, &empty);
    if (require_ok("document_create_empty(array)", rc)) return rc;
    int64_t empty_root = ss_json_document_root(empty);
    rc = ss_json_append_array_element_bool(empty, empty_root, 1);
    if (require_ok("append_array_element_bool(empty)", rc)) return rc;
    rc = ss_json_document_serialize(empty, serialized, sizeof(serialized), &serialized_body);
    if (require_ok("document_serialize(empty)", rc)) return rc;
    if (require_cstring("document_serialize(empty)", serialized_body, "[true]")) return 1;
    ss_json_document_destroy(empty);

    printf("sem_json_health_demo: ok\n");
    return 0;
}
