#ifndef SEM_HTTP_CLIENT_RUNTIME_H
#define SEM_HTTP_CLIENT_RUNTIME_H

#include <stddef.h>

#include "../native_async/sem_async_runtime.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSHttpClientRequest SSHttpClientRequest;
typedef struct SSHttpClientResponse SSHttpClientResponse;
typedef struct SSHttpFetchFuture SSHttpFetchFuture;

enum {
    SS_HTTP_CLIENT_OK = 0,
    SS_HTTP_CLIENT_ERR_CONFIG = 1,
    SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE = 2,
    SS_HTTP_CLIENT_ERR_BACKEND = 3,
    SS_HTTP_CLIENT_ERR_CANCELLED = 4,
    SS_HTTP_CLIENT_ERR_TIMEOUT = 5,
    SS_HTTP_CLIENT_ERR_BODY_TOO_LARGE = 6,
    SS_HTTP_CLIENT_ERR_TLS_UNAVAILABLE = 7,
    SS_HTTP_CLIENT_ERR_UNSUPPORTED_SCHEME = 8
};

int ss_http_client_request_create(SSHttpClientRequest **out_request);
void ss_http_client_request_free(SSHttpClientRequest *request);
int ss_http_client_request_set_method(SSHttpClientRequest *request, const char *method);
int ss_http_client_request_set_url(SSHttpClientRequest *request, const char *url);
int ss_http_client_request_set_header(
    SSHttpClientRequest *request,
    const char *name,
    const char *value
);
int ss_http_client_request_set_body_text(SSHttpClientRequest *request, const char *body);
int ss_http_client_request_set_body_bytes(
    SSHttpClientRequest *request,
    const void *body,
    size_t body_length
);
int ss_http_client_request_set_timeout_ms(
    SSHttpClientRequest *request,
    unsigned long long timeout_ms
);
int ss_http_client_request_set_max_body_bytes(
    SSHttpClientRequest *request,
    size_t max_body_bytes
);
int ss_http_client_request_set_redirect_limit(
    SSHttpClientRequest *request,
    unsigned int redirect_limit
);

int ss_http_client_execute_blocking(
    const SSHttpClientRequest *request,
    SSHttpClientResponse **out_response
);
int ss_http_client_fetch_text_blocking(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    SSHttpClientResponse **out_response
);
int ss_http_client_fetch_text_copy(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    char **out_body,
    long long *out_status
);
int ss_http_client_fetch_text_request_copy(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    unsigned int redirect_limit,
    char **out_body,
    long long *out_status
);
void ss_http_client_free_string(char *value);

long ss_http_client_response_status(const SSHttpClientResponse *response);
const char *ss_http_client_response_header(
    const SSHttpClientResponse *response,
    const char *name
);
const char *ss_http_client_response_body_text(const SSHttpClientResponse *response);
const void *ss_http_client_response_body_bytes(const SSHttpClientResponse *response);
size_t ss_http_client_response_body_length(const SSHttpClientResponse *response);
int ss_http_client_response_error_code(const SSHttpClientResponse *response);
void ss_http_client_response_free(SSHttpClientResponse *response);

int ss_http_client_fetch_text_start(
    SSAsyncLoop *loop,
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    SSHttpFetchFuture **out_future
);
int ss_http_client_fetch_text_await(SSAsyncLoop *loop, SSHttpFetchFuture *future);
long ss_http_client_fetch_status(const SSHttpFetchFuture *future);
const char *ss_http_client_fetch_body_text(const SSHttpFetchFuture *future);
const void *ss_http_client_fetch_body_bytes(const SSHttpFetchFuture *future);
size_t ss_http_client_fetch_body_length(const SSHttpFetchFuture *future);
int ss_http_client_fetch_error_code(const SSHttpFetchFuture *future);
void ss_http_client_fetch_free(SSHttpFetchFuture *future);

#ifdef __cplusplus
}
#endif

#endif
