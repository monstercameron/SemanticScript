/*
 * R-208 focused HTTP URL/query decode policy test. Includes the runtime source
 * so the static query parser can be exercised directly without opening sockets.
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../../semanticscript/runtime/native_http/sem_http_runtime.c"

static void assert_url_decodes(const char *input, const char *expected) {
    char scratch[128];
    const char *decoded = ss_http_url_decode(input, scratch, sizeof(scratch));
    assert(decoded != NULL);
    assert(strcmp(decoded, expected) == 0);
}

static void parse_query(char *query, SSHttpRequest *request) {
    memset(request, 0, sizeof(*request));
    parse_query_params(query, request);
}

int main(void) {
    assert_url_decodes("hello+world", "hello world");
    assert_url_decodes("caf%C3%A9", "caf\xC3\xA9");
    assert(ss_http_url_decode("admin%00guest", (char[64]){0}, 64) == NULL);
    assert(ss_http_url_decode("line%0Abreak", (char[64]){0}, 64) == NULL);
    assert(ss_http_url_decode("del%7Fbyte", (char[64]){0}, 64) == NULL);
    assert(ss_http_url_decode("bad%ZZ", (char[64]){0}, 64) == NULL);
    assert(ss_http_url_decode("bad%", (char[64]){0}, 64) == NULL);

    SSHttpRequest request;

    char query_name_nul[] = "role%00x=admin&good=ok";
    parse_query(query_name_nul, &request);
    assert(ss_http_request_query_param(&request, "role") == NULL);
    assert(strcmp(ss_http_request_query_param(&request, "good"), "ok") == 0);

    char query_value_nul[] = "role=admin%00guest&good=ok";
    parse_query(query_value_nul, &request);
    assert(ss_http_request_query_param(&request, "role") == NULL);
    assert(strcmp(ss_http_request_query_param(&request, "good"), "ok") == 0);

    char query_control[] = "line=a%0Ab&del=x%7Fy&good=ok";
    parse_query(query_control, &request);
    assert(ss_http_request_query_param(&request, "line") == NULL);
    assert(ss_http_request_query_param(&request, "del") == NULL);
    assert(strcmp(ss_http_request_query_param(&request, "good"), "ok") == 0);

    char query_utf8[] = "name=caf%C3%A9+au+lait";
    parse_query(query_utf8, &request);
    assert(strcmp(ss_http_request_query_param(&request, "name"), "caf\xC3\xA9 au lait") == 0);

    char query_malformed[] = "bad=%ZZ&short=%&good=ok";
    parse_query(query_malformed, &request);
    assert(strcmp(ss_http_request_query_param(&request, "bad"), "%ZZ") == 0);
    assert(strcmp(ss_http_request_query_param(&request, "short"), "%") == 0);
    assert(strcmp(ss_http_request_query_param(&request, "good"), "ok") == 0);

    printf("http_url_decode_policy: OK\n");
    return 0;
}
