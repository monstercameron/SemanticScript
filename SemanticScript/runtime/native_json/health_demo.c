#include "sem_json_runtime.h"

#include <stdio.h>
#include <string.h>

/*
 * Smoke demo for the native_json adapter. Builds a small object,
 * round-trips it through the finder API, and asserts the recovered
 * values match what went in. Designed to fail loud on any escape
 * regression, off-by-one in the comma handling, or buffer mis-sizing.
 */

static int fail(const char *stage, int status) {
    fprintf(stderr, "sem_json_health_demo: %s failed status=%d\n", stage, status);
    return status;
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

    ss_json_builder_destroy(builder);

    if (!round_trip_ok) {
        fprintf(stderr, "sem_json_health_demo: round-trip mismatch\n");
        return 1;
    }

    printf("sem_json_health_demo: ok\n");
    return 0;
}
