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

    /* a second document round-trips independently after the first is gone */
    SSJsonDocument *doc2 = NULL;
    assert(ss_json_document_create_empty(1024, SS_JSON_NODE_OBJECT, &doc2) == SS_JSON_OK);
    assert(ss_json_document_root(doc2) >= 0);
    ss_json_document_destroy(doc2);

    printf("harness_json: OK\n");
    return 0;
}
