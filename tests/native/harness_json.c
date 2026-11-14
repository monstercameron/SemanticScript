/*
 * harness_json.c — R-198 native-runtime safety harness for the JSON document
 * runtime (sem_json_runtime.c). Exercises the document lifecycle — including the
 * orderings that USED to be use-after-free / double-free before R-198 (double
 * destroyDocument, root/serialize/cursor read after destroy) — as NORMAL usage.
 * Built with ASAN+UBSAN by run_sanitizers.sh; a clean run must report ZERO
 * findings (including leaks: every created document is destroyed exactly once).
 *
 * Companion to harness_event.c (event runtime) on the "passes clean" side of the
 * native-safety suite.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../../semanticscript/runtime/native_json/sem_json_runtime.c"

static void append_text(char *buffer, size_t capacity, size_t *used, const char *text) {
    while (*text != '\0') {
        assert(*used + 1 < capacity);
        buffer[(*used)++] = *text++;
    }
    buffer[*used] = '\0';
}

static void make_nested_arrays(char *buffer, size_t capacity, int depth, const char *leaf) {
    size_t used = 0;
    buffer[0] = '\0';
    for (int i = 0; i < depth; ++i) {
        append_text(buffer, capacity, &used, "[");
    }
    append_text(buffer, capacity, &used, leaf);
    for (int i = 0; i < depth; ++i) {
        append_text(buffer, capacity, &used, "]");
    }
}

static void make_nested_objects(char *buffer, size_t capacity, int depth, const char *leaf) {
    size_t used = 0;
    buffer[0] = '\0';
    for (int i = 0; i < depth; ++i) {
        append_text(buffer, capacity, &used, "{\"k\":");
    }
    append_text(buffer, capacity, &used, leaf);
    for (int i = 0; i < depth; ++i) {
        append_text(buffer, capacity, &used, "}");
    }
}

static int parse_and_destroy(const char *json_text) {
    SSJsonDocument *doc = NULL;
    int rc = ss_json_document_create_from_text(
        json_text, (int64_t)strlen(json_text) + 128, &doc);
    if (rc == SS_JSON_OK) {
        assert(doc != NULL);
        ss_json_document_destroy(doc);
    } else {
        assert(doc == NULL);
    }
    return rc;
}

int main(void) {
    /* normal lifecycle: create an object document, set a field, read it back via
     * the root cursor, serialize, then destroy. */
    SSJsonDocument *doc = NULL;
    assert(ss_json_document_create_empty(4096, SS_JSON_NODE_OBJECT, &doc) == SS_JSON_OK);
    assert(doc != NULL);
    int64_t root = ss_json_document_root(doc);
    assert(root >= 0);
    assert(ss_json_set_object_field_int64(doc, root, "n", 42) == SS_JSON_OK);

    char scratch[256];
    const char *out = NULL;
    assert(ss_json_document_serialize(doc, scratch, (int64_t)sizeof(scratch), &out) == SS_JSON_OK);
    assert(out != NULL && strstr(out, "42") != NULL);

    ss_json_document_destroy(doc);

    /* R-198: a double destroy is a no-op (not a double free) — membership fails. */
    ss_json_document_destroy(doc);

    /* R-198: reads on a destroyed handle fail safe (no use-after-free of the freed
     * document/arena/nodes) — the live-document registry rejects the stale handle
     * before document_node_at touches node_count. */
    assert(ss_json_document_root(doc) < 0);                       /* root: error */
    assert(ss_json_cursor_int64(doc, 0, -7) == -7);               /* read: default */
    const char *dead_out = NULL;
    /* serialize must not dereference the freed document; a NULL/error result is
     * fine, a crash is not. */
    (void)ss_json_document_serialize(doc, scratch, (int64_t)sizeof(scratch), &dead_out);

    /* R-192: a backslash-u-0000 escape in a value must be REJECTED (it would
     * embed a NUL that truncates the NUL-terminated String), while an ordinary
     * BMP escape still parses. */
    SSJsonDocument *nul_doc = NULL;
    assert(ss_json_document_create_from_text("{\"k\":\"a\\u0000b\"}", 256, &nul_doc) != SS_JSON_OK);
    assert(nul_doc == NULL);  /* parse failed -> no document handed back */
    SSJsonDocument *esc_doc = NULL;
    assert(ss_json_document_create_from_text("{\"k\":\"a\\u0041b\"}", 256, &esc_doc) == SS_JSON_OK);
    assert(esc_doc != NULL);
    ss_json_document_destroy(esc_doc);

    /* R-189: document parsing enforces the runtime nesting-depth ceiling before
     * recursing deeper, while preserving valid input exactly at the limit. */
    char nested[512];
    make_nested_arrays(nested, sizeof(nested), SS_JSON_MAX_NESTING_DEPTH, "0");
    assert(parse_and_destroy(nested) == SS_JSON_OK);
    make_nested_arrays(nested, sizeof(nested), SS_JSON_MAX_NESTING_DEPTH + 1, "0");
    assert(parse_and_destroy(nested) == SS_JSON_ERR_CAPACITY_EXCEEDED);
    make_nested_objects(nested, sizeof(nested), SS_JSON_MAX_NESTING_DEPTH, "0");
    assert(parse_and_destroy(nested) == SS_JSON_OK);
    make_nested_objects(nested, sizeof(nested), SS_JSON_MAX_NESTING_DEPTH + 1, "0");
    assert(parse_and_destroy(nested) == SS_JSON_ERR_CAPACITY_EXCEEDED);
    make_nested_arrays(nested, sizeof(nested), SS_JSON_MAX_NESTING_DEPTH, "!");
    assert(parse_and_destroy(nested) == SS_JSON_ERR_MALFORMED_PATH);

    /* R-237/R-238: replacing an EXISTING object field / array element calls
     * document_add_node, which can realloc document->nodes and free the buffer
     * the parent node pointer was taken from. Replace in a tight loop so the node
     * count crosses every doubling boundary (16, 32, 64, ...): at each boundary
     * the replace's internal add reallocs WHILE the parent pointer is held, so a
     * stale read of old_child through it is a use-after-free (ASAN catches it).
     * Each replace nets +1 node (the new child; the old one is invalidated), so
     * the loop steps through every boundary rather than jumping past it. */
    SSJsonDocument *rdoc = NULL;
    assert(ss_json_document_create_empty(1 << 20, SS_JSON_NODE_OBJECT, &rdoc) == SS_JSON_OK);
    int64_t rroot = ss_json_document_root(rdoc);
    assert(rroot >= 0);
    int64_t seed_child = -1, seed_arr = -1, seed_elem = -1;
    assert(ss_json_set_object_field_object(rdoc, rroot, "t", &seed_child) == SS_JSON_OK);
    assert(ss_json_set_object_field_array(rdoc, rroot, "arr", &seed_arr) == SS_JSON_OK);
    assert(ss_json_append_array_element_object(rdoc, seed_arr, &seed_elem) == SS_JSON_OK);
    for (int i = 0; i < 300; ++i) {  /* R-237: replace existing object field */
        int64_t tmp = -1;
        assert(ss_json_set_object_field_object(rdoc, rroot, "t", &tmp) == SS_JSON_OK);
    }
    for (int i = 0; i < 300; ++i) {  /* R-238: replace existing array element */
        int64_t tmp = -1;
        assert(ss_json_replace_array_element_object(rdoc, seed_arr, 0, &tmp) == SS_JSON_OK);
    }
    ss_json_document_destroy(rdoc);

    /* a second document round-trips independently after the first is gone */
    SSJsonDocument *doc2 = NULL;
    assert(ss_json_document_create_empty(1024, SS_JSON_NODE_OBJECT, &doc2) == SS_JSON_OK);
    assert(ss_json_document_root(doc2) >= 0);
    ss_json_document_destroy(doc2);

    printf("harness_json: OK\n");
    return 0;
}
