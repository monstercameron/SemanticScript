/*
 * R-180 focused outbound-client policy test. This includes the runtime sources so
 * the static response-body extraction helpers can be exercised without opening a
 * socket: Content-Length bodies pass through, Transfer-Encoding: chunked fails
 * closed, and malformed chunk frames are never exposed as body text.
 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../semanticscript/runtime/ss_net.c"
#include "../../semanticscript/runtime/native_http/sem_http_runtime.c"

static void assert_net_body(const char *wire, const char *expected) {
    char *body = ss_net_response_body_from_wire(wire);
    assert(body != NULL);
    assert(strcmp(body, expected) == 0);
    free(body);
}

static void assert_http_body(const char *wire, int status, const char *expected) {
    char *body = ss_http_client_response_body_from_wire(wire, status);
    assert(body != NULL);
    assert(strcmp(body, expected) == 0);
    free(body);
}

int main(void) {
    const char *content_length =
        "HTTP/1.1 200 OK\r\n"
        "Content-Length: 5\r\n"
        "Connection: close\r\n"
        "\r\n"
        "hello";
    const char *chunked =
        "HTTP/1.1 200 OK\r\n"
        "Transfer-Encoding: chunked\r\n"
        "\r\n"
        "5\r\nhello\r\n0\r\n\r\n";
    const char *chunked_list =
        "HTTP/1.1 200 OK\r\n"
        "Transfer-Encoding: gzip, Chunked\r\n"
        "\r\n"
        "5\r\nhello\r\n0\r\n\r\n";
    const char *malformed_chunked =
        "HTTP/1.1 200 OK\r\n"
        "Transfer-Encoding: chunked\r\n"
        "\r\n"
        "Z\r\nnot-a-valid-chunk\r\n";

    assert_net_body(content_length, "hello");
    assert_http_body(content_length, 200, "hello");

    assert(ss_net_response_body_from_wire(chunked) == NULL);
    assert(ss_http_client_response_body_from_wire(chunked, 200) == NULL);
    assert(ss_net_response_body_from_wire(chunked_list) == NULL);
    assert(ss_http_client_response_body_from_wire(chunked_list, 200) == NULL);
    assert(ss_net_response_body_from_wire(malformed_chunked) == NULL);
    assert(ss_http_client_response_body_from_wire(malformed_chunked, 200) == NULL);

    /* Preserve existing behavior outside the chunked case. */
    assert_net_body("plain body without headers", "plain body without headers");
    assert(ss_http_client_response_body_from_wire(content_length, 404) == NULL);

    printf("http_client_chunked_policy: OK\n");
    return 0;
}
