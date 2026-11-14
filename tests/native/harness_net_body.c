/*
 * harness_net_body.c — R-204 native safety harness for net.fetchText body
 * ownership. It avoids real network I/O by exercising the response-body
 * extraction helper directly, then verifies freeTextBody rejects literal/foreign
 * and already-freed pointers while preserving valid owned body/free behavior.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#ifdef _WIN32
#include "../../semanticscript/runtime/ss_net.c"

int main(void) {
    char literal[] = "literal";
    char foreign[] = "foreign";

    /* R-204: freeTextBody must not pass non-net-owned strings to free(). */
    ss_net_free_text(literal);
    ss_net_free_text(foreign);
    assert(strcmp(literal, "literal") == 0);
    assert(strcmp(foreign, "foreign") == 0);

    /* Existing helper behavior: no header separator means the whole input is the
     * body, and normal HTTP wire text returns the content after CRLFCRLF. */
    char *plain = ss_net_response_body_from_wire("plain body");
    assert(plain != NULL);
    assert(ss_net_body_is_live(plain));
    assert(strcmp(plain, "plain body") == 0);
    ss_net_free_text(plain);
    assert(!ss_net_body_is_live(plain));
    ss_net_free_text(plain);  /* double free must fail closed */

    char *owned = ss_net_response_body_from_wire(
        "HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello");
    assert(owned != NULL);
    assert(ss_net_body_is_live(owned));
    assert(strcmp(owned, "hello") == 0);
    char *copy = owned;
    ss_net_free_text(owned);
    assert(!ss_net_body_is_live(copy));
    ss_net_free_text(copy);   /* copied stale body must fail closed */

    /* Existing fail-closed extraction behavior for unsupported chunked bodies:
     * no body allocation is returned, so cleanup remains a no-op. */
    char *chunked = ss_net_response_body_from_wire(
        "HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n");
    assert(chunked == NULL);
    ss_net_free_text(chunked);

    printf("harness_net_body: OK\n");
    return 0;
}
#else
int main(void) {
    printf("harness_net_body: SKIP (ss_net.c is WinSock-backed on this platform)\n");
    return 0;
}
#endif
