/*
 * harness_http_string.c - R-012/R-034 native safety harness for HTTP helper
 * String ownership. Exercises the direct URL/HTML string adapters and verifies
 * ss_http_free_str accepts only live runtime-owned buffers.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "../../semanticscript/runtime/native_http/sem_http_runtime.c"
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic pop
#endif
#include "../../semanticscript/runtime/ss_http.c"

int main(void) {
    char literal[] = "literal";
    char foreign[] = "foreign";

    /* Foreign/literal pointers must not be handed to free(). */
    ss_http_free_str(NULL);
    ss_http_free_str(literal);
    ss_http_free_str(foreign);
    assert(strcmp(literal, "literal") == 0);
    assert(strcmp(foreign, "foreign") == 0);

    const char *encoded = ss_http_url_encode_str("a b&c=d");
    assert(encoded != NULL);
    assert(ss_http_str_is_live(encoded));
    assert(strcmp(encoded, "a%20b%26c%3Dd") == 0);
    ss_http_free_str(encoded);
    assert(!ss_http_str_is_live(encoded));
    ss_http_free_str(encoded);  /* double free must fail closed */

    const char *decoded = ss_http_url_decode_str("a%20b%26c%3Dd");
    assert(decoded != NULL);
    assert(ss_http_str_is_live(decoded));
    assert(strcmp(decoded, "a b&c=d") == 0);
    const char *decoded_copy = decoded;
    ss_http_free_str(decoded);
    assert(!ss_http_str_is_live(decoded_copy));
    ss_http_free_str(decoded_copy);  /* copied stale pointer must fail closed */

    const char *escaped = ss_http_html_escape_str("<x&\"'>");
    assert(escaped != NULL);
    assert(ss_http_str_is_live(escaped));
    assert(strcmp(escaped, "&lt;x&amp;&quot;&#39;&gt;") == 0);
    ss_http_free_str(escaped);
    assert(!ss_http_str_is_live(escaped));

    const char *empty_from_null = ss_http_html_escape_str(NULL);
    assert(empty_from_null != NULL);
    assert(ss_http_str_is_live(empty_from_null));
    assert(strcmp(empty_from_null, "") == 0);
    ss_http_free_str(empty_from_null);

    printf("harness_http_string: OK\n");
    return 0;
}
