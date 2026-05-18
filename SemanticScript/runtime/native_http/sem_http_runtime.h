#ifndef SEM_HTTP_RUNTIME_H
#define SEM_HTTP_RUNTIME_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSHttpRequest SSHttpRequest;
typedef struct SSHttpResponse SSHttpResponse;

typedef int (*SSHttpHandler)(SSHttpRequest *request, SSHttpResponse *response);

typedef struct SSHttpRoute {
    const char *method;
    const char *path;
    SSHttpHandler handler;
    SSHttpHandler middleware;
} SSHttpRoute;

typedef struct SSHttpServerConfig {
    const char *host;
    unsigned short port;
    const SSHttpRoute *routes;
    size_t route_count;
} SSHttpServerConfig;

enum {
    SS_HTTP_OK = 0,
    SS_HTTP_ERR_CONFIG = 1,
    SS_HTTP_ERR_RUNTIME_UNAVAILABLE = 2,
    SS_HTTP_ERR_ENGINE = 3
};

int ss_http_server_run(const SSHttpServerConfig *config);

int ss_http_response_text(
    SSHttpResponse *response,
    int status,
    const char *body,
    const char *content_type
);

int ss_http_response_bytes(
    SSHttpResponse *response,
    int status,
    const void *body,
    size_t body_length,
    const char *content_type
);

int ss_http_response_sse_event(
    SSHttpResponse *response,
    int status,
    const char *event_name,
    const char *event_data
);

const char *ss_http_request_method(const SSHttpRequest *request);
const char *ss_http_request_path(const SSHttpRequest *request);
const char *ss_http_request_header(const SSHttpRequest *request, const char *name);
const char *ss_http_request_query_param(const SSHttpRequest *request, const char *name);
const char *ss_http_request_body_text(const SSHttpRequest *request);
const void *ss_http_request_body_bytes(const SSHttpRequest *request);
size_t ss_http_request_body_length(const SSHttpRequest *request);

const char *ss_http_multipart_part_text(SSHttpRequest *request, const char *name);
const void *ss_http_multipart_part_bytes(SSHttpRequest *request, const char *name);
size_t ss_http_multipart_part_length(SSHttpRequest *request, const char *name);
const char *ss_http_multipart_part_filename(SSHttpRequest *request, const char *name);
const char *ss_http_multipart_part_content_type(SSHttpRequest *request, const char *name);

int ss_http_response_header(
    SSHttpResponse *response,
    const char *name,
    const char *value
);

#ifdef __cplusplus
}
#endif

#endif
