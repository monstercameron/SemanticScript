#include "sem_http_client_runtime.h"

#include <ctype.h>
#include <stdlib.h>
#include <string.h>

#ifdef SEM_HTTP_CLIENT_WITH_CURL
#include <curl/curl.h>
#endif

#define SS_HTTP_CLIENT_MAX_HEADERS 32
#define SS_HTTP_CLIENT_DEFAULT_TIMEOUT_MS 30000ULL
#define SS_HTTP_CLIENT_DEFAULT_MAX_BODY_BYTES (1024U * 1024U)
#define SS_HTTP_CLIENT_DEFAULT_REDIRECT_LIMIT 5U

typedef struct SSHttpClientHeader {
    char *name;
    char *value;
} SSHttpClientHeader;

struct SSHttpClientRequest {
    char *method;
    char *url;
    SSHttpClientHeader headers[SS_HTTP_CLIENT_MAX_HEADERS];
    size_t header_count;
    unsigned char *body;
    size_t body_length;
    unsigned long long timeout_ms;
    size_t max_body_bytes;
    unsigned int redirect_limit;
};

struct SSHttpClientResponse {
    long status;
    SSHttpClientHeader headers[SS_HTTP_CLIENT_MAX_HEADERS];
    size_t header_count;
    char *body;
    size_t body_length;
    int error_code;
};

struct SSHttpFetchFuture {
    SSAsyncLoop *loop;
    SSHttpClientRequest *request;
    SSHttpClientResponse *response;
    SSAsyncTimer *timer;
    volatile int cancel_requested;
    volatile int timeout_requested;
    volatile int ready;
    int error_code;
};

typedef struct SSHttpWriteContext {
    SSHttpClientResponse *response;
    size_t max_body_bytes;
    volatile int *cancel_requested;
    volatile int *timeout_requested;
    int body_too_large;
} SSHttpWriteContext;

static char *copy_bytes_with_nul(const void *source, size_t length) {
    char *copy;

    if (source == NULL && length > 0) {
        return NULL;
    }
    if (length == (size_t)-1) {
        return NULL;
    }
    copy = (char *)malloc(length + 1);
    if (copy == NULL) {
        return NULL;
    }
    if (length > 0) {
        memcpy(copy, source, length);
    }
    copy[length] = '\0';
    return copy;
}

static char *copy_c_string(const char *source) {
    if (source == NULL) {
        return NULL;
    }
    return copy_bytes_with_nul(source, strlen(source));
}

static int ascii_case_equal(const char *left, const char *right) {
    while (*left != '\0' && *right != '\0') {
        if (tolower((unsigned char)*left) != tolower((unsigned char)*right)) {
            return 0;
        }
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

static int has_prefix_case_sensitive(const char *text, const char *prefix) {
    size_t prefix_len;

    if (text == NULL || prefix == NULL) {
        return 0;
    }
    prefix_len = strlen(prefix);
    return strncmp(text, prefix, prefix_len) == 0;
}

static int supported_scheme(const char *url) {
    return has_prefix_case_sensitive(url, "https://")
        || has_prefix_case_sensitive(url, "http://");
}

static int requires_tls(const char *url) {
    return has_prefix_case_sensitive(url, "https://");
}

static void clear_headers(SSHttpClientHeader *headers, size_t *header_count) {
    size_t index;

    if (headers == NULL || header_count == NULL) {
        return;
    }
    for (index = 0; index < *header_count; ++index) {
        free(headers[index].name);
        free(headers[index].value);
        headers[index].name = NULL;
        headers[index].value = NULL;
    }
    *header_count = 0;
}

int ss_http_client_request_create(SSHttpClientRequest **out_request) {
    SSHttpClientRequest *request;

    if (out_request == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    *out_request = NULL;

    request = (SSHttpClientRequest *)calloc(1, sizeof(*request));
    if (request == NULL) {
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    request->method = copy_c_string("GET");
    request->timeout_ms = SS_HTTP_CLIENT_DEFAULT_TIMEOUT_MS;
    request->max_body_bytes = SS_HTTP_CLIENT_DEFAULT_MAX_BODY_BYTES;
    request->redirect_limit = SS_HTTP_CLIENT_DEFAULT_REDIRECT_LIMIT;
    if (request->method == NULL) {
        free(request);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    *out_request = request;
    return SS_HTTP_CLIENT_OK;
}

void ss_http_client_request_free(SSHttpClientRequest *request) {
    if (request == NULL) {
        return;
    }
    free(request->method);
    free(request->url);
    clear_headers(request->headers, &request->header_count);
    free(request->body);
    free(request);
}

int ss_http_client_request_set_method(SSHttpClientRequest *request, const char *method) {
    char *copy;

    if (request == NULL || method == NULL || *method == '\0') {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    copy = copy_c_string(method);
    if (copy == NULL) {
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    free(request->method);
    request->method = copy;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_request_set_url(SSHttpClientRequest *request, const char *url) {
    char *copy;

    if (request == NULL || url == NULL || *url == '\0') {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (!supported_scheme(url)) {
        return SS_HTTP_CLIENT_ERR_UNSUPPORTED_SCHEME;
    }
    copy = copy_c_string(url);
    if (copy == NULL) {
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    free(request->url);
    request->url = copy;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_request_set_header(
    SSHttpClientRequest *request,
    const char *name,
    const char *value
) {
    char *name_copy;
    char *value_copy;
    size_t index;

    if (request == NULL || name == NULL || value == NULL || *name == '\0') {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    for (index = 0; index < request->header_count; ++index) {
        if (ascii_case_equal(request->headers[index].name, name)) {
            value_copy = copy_c_string(value);
            if (value_copy == NULL) {
                return SS_HTTP_CLIENT_ERR_BACKEND;
            }
            free(request->headers[index].value);
            request->headers[index].value = value_copy;
            return SS_HTTP_CLIENT_OK;
        }
    }
    if (request->header_count >= SS_HTTP_CLIENT_MAX_HEADERS) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    name_copy = copy_c_string(name);
    value_copy = copy_c_string(value);
    if (name_copy == NULL || value_copy == NULL) {
        free(name_copy);
        free(value_copy);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    request->headers[request->header_count].name = name_copy;
    request->headers[request->header_count].value = value_copy;
    ++request->header_count;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_request_set_body_text(SSHttpClientRequest *request, const char *body) {
    if (body == NULL) {
        return ss_http_client_request_set_body_bytes(request, NULL, 0);
    }
    return ss_http_client_request_set_body_bytes(request, body, strlen(body));
}

int ss_http_client_request_set_body_bytes(
    SSHttpClientRequest *request,
    const void *body,
    size_t body_length
) {
    unsigned char *copy;

    if (request == NULL || (body == NULL && body_length > 0)) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    copy = NULL;
    if (body_length > 0) {
        copy = (unsigned char *)malloc(body_length);
        if (copy == NULL) {
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
        memcpy(copy, body, body_length);
    }
    free(request->body);
    request->body = copy;
    request->body_length = body_length;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_request_set_timeout_ms(
    SSHttpClientRequest *request,
    unsigned long long timeout_ms
) {
    if (request == NULL || timeout_ms == 0) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    request->timeout_ms = timeout_ms;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_request_set_max_body_bytes(
    SSHttpClientRequest *request,
    size_t max_body_bytes
) {
    if (request == NULL || max_body_bytes == 0) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    request->max_body_bytes = max_body_bytes;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_request_set_redirect_limit(
    SSHttpClientRequest *request,
    unsigned int redirect_limit
) {
    if (request == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    request->redirect_limit = redirect_limit;
    return SS_HTTP_CLIENT_OK;
}

static SSHttpClientResponse *response_create(void) {
    return (SSHttpClientResponse *)calloc(1, sizeof(SSHttpClientResponse));
}

void ss_http_client_response_free(SSHttpClientResponse *response) {
    if (response == NULL) {
        return;
    }
    clear_headers(response->headers, &response->header_count);
    free(response->body);
    free(response);
}

static int response_add_header(
    SSHttpClientResponse *response,
    const char *name,
    size_t name_length,
    const char *value,
    size_t value_length
) {
    char *name_copy;
    char *value_copy;

    if (response == NULL || name == NULL || value == NULL || name_length == 0) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (response->header_count >= SS_HTTP_CLIENT_MAX_HEADERS) {
        return SS_HTTP_CLIENT_OK;
    }
    name_copy = copy_bytes_with_nul(name, name_length);
    value_copy = copy_bytes_with_nul(value, value_length);
    if (name_copy == NULL || value_copy == NULL) {
        free(name_copy);
        free(value_copy);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    response->headers[response->header_count].name = name_copy;
    response->headers[response->header_count].value = value_copy;
    ++response->header_count;
    return SS_HTTP_CLIENT_OK;
}

#ifdef SEM_HTTP_CLIENT_WITH_CURL
static int curl_supports_tls(void) {
    curl_version_info_data *version = curl_version_info(CURLVERSION_NOW);
    return version != NULL && (version->features & CURL_VERSION_SSL) != 0;
}

static size_t write_body_cb(char *ptr, size_t size, size_t count, void *user_data) {
    SSHttpWriteContext *context = (SSHttpWriteContext *)user_data;
    SSHttpClientResponse *response = context->response;
    size_t byte_count = size * count;
    char *next;

    if (context->cancel_requested != NULL && *context->cancel_requested) {
        return 0;
    }
    if (byte_count > context->max_body_bytes
            || response->body_length > context->max_body_bytes - byte_count) {
        context->body_too_large = 1;
        return 0;
    }
    next = (char *)realloc(response->body, response->body_length + byte_count + 1);
    if (next == NULL) {
        return 0;
    }
    memcpy(next + response->body_length, ptr, byte_count);
    response->body = next;
    response->body_length += byte_count;
    response->body[response->body_length] = '\0';
    return byte_count;
}

static size_t write_header_cb(char *ptr, size_t size, size_t count, void *user_data) {
    SSHttpClientResponse *response = (SSHttpClientResponse *)user_data;
    size_t byte_count = size * count;
    char *colon;
    char *line_end;
    char *value_start;
    size_t name_length;
    size_t value_length;

    if (byte_count == 0 || response == NULL) {
        return byte_count;
    }
    colon = memchr(ptr, ':', byte_count);
    if (colon == NULL) {
        return byte_count;
    }
    name_length = (size_t)(colon - ptr);
    value_start = colon + 1;
    while (value_start < ptr + byte_count
            && (*value_start == ' ' || *value_start == '\t')) {
        ++value_start;
    }
    line_end = ptr + byte_count;
    while (line_end > value_start
            && (line_end[-1] == '\r' || line_end[-1] == '\n'
                || line_end[-1] == ' ' || line_end[-1] == '\t')) {
        --line_end;
    }
    value_length = (size_t)(line_end - value_start);
    (void)response_add_header(response, ptr, name_length, value_start, value_length);
    return byte_count;
}

static int xferinfo_cb(
    void *user_data,
    curl_off_t download_total,
    curl_off_t download_now,
    curl_off_t upload_total,
    curl_off_t upload_now
) {
    SSHttpWriteContext *context = (SSHttpWriteContext *)user_data;
    (void)download_total;
    (void)download_now;
    (void)upload_total;
    (void)upload_now;
    return context->cancel_requested != NULL && *context->cancel_requested ? 1 : 0;
}

static int map_curl_error(CURLcode rc, const SSHttpWriteContext *context) {
    if (rc == CURLE_OK) {
        return SS_HTTP_CLIENT_OK;
    }
    if (context != NULL && context->body_too_large) {
        return SS_HTTP_CLIENT_ERR_BODY_TOO_LARGE;
    }
    if (rc == CURLE_OPERATION_TIMEDOUT) {
        return SS_HTTP_CLIENT_ERR_TIMEOUT;
    }
    if (rc == CURLE_ABORTED_BY_CALLBACK) {
        if (context != NULL
                && context->timeout_requested != NULL
                && *context->timeout_requested) {
            return SS_HTTP_CLIENT_ERR_TIMEOUT;
        }
        return SS_HTTP_CLIENT_ERR_CANCELLED;
    }
    if (rc == CURLE_UNSUPPORTED_PROTOCOL) {
        return SS_HTTP_CLIENT_ERR_UNSUPPORTED_SCHEME;
    }
    if (rc == CURLE_NOT_BUILT_IN) {
        return SS_HTTP_CLIENT_ERR_TLS_UNAVAILABLE;
    }
    return SS_HTTP_CLIENT_ERR_BACKEND;
}

static int execute_internal(
    const SSHttpClientRequest *request,
    SSHttpClientResponse **out_response,
    volatile int *cancel_requested
) {
    CURL *curl;
    CURLcode rc;
    struct curl_slist *header_list = NULL;
    SSHttpClientResponse *response;
    SSHttpWriteContext context;
    size_t index;

    if (request == NULL || request->url == NULL || out_response == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (!supported_scheme(request->url)) {
        return SS_HTTP_CLIENT_ERR_UNSUPPORTED_SCHEME;
    }
    if (requires_tls(request->url) && !curl_supports_tls()) {
        return SS_HTTP_CLIENT_ERR_TLS_UNAVAILABLE;
    }
    *out_response = NULL;

    response = response_create();
    if (response == NULL) {
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    curl = curl_easy_init();
    if (curl == NULL) {
        ss_http_client_response_free(response);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    memset(&context, 0, sizeof(context));
    context.response = response;
    context.max_body_bytes = request->max_body_bytes;
    context.cancel_requested = cancel_requested;
    context.timeout_requested = NULL;

    curl_easy_setopt(curl, CURLOPT_URL, request->url);
    curl_easy_setopt(curl, CURLOPT_FOLLOWLOCATION, 1L);
    curl_easy_setopt(curl, CURLOPT_MAXREDIRS, (long)request->redirect_limit);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, (long)request->timeout_ms);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, (long)request->timeout_ms);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYPEER, 1L);
    curl_easy_setopt(curl, CURLOPT_SSL_VERIFYHOST, 2L);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_body_cb);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &context);
    curl_easy_setopt(curl, CURLOPT_HEADERFUNCTION, write_header_cb);
    curl_easy_setopt(curl, CURLOPT_HEADERDATA, response);
    curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
    curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, xferinfo_cb);
    curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &context);

    if (!ascii_case_equal(request->method, "GET")) {
        if (ascii_case_equal(request->method, "POST")) {
            curl_easy_setopt(curl, CURLOPT_POST, 1L);
        } else {
            curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, request->method);
        }
    }
    if (request->body != NULL || request->body_length > 0) {
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, request->body);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE_LARGE, (curl_off_t)request->body_length);
    }

    for (index = 0; index < request->header_count; ++index) {
        size_t name_length = strlen(request->headers[index].name);
        size_t value_length = strlen(request->headers[index].value);
        char *line = (char *)malloc(name_length + value_length + 3);
        if (line == NULL) {
            curl_slist_free_all(header_list);
            curl_easy_cleanup(curl);
            ss_http_client_response_free(response);
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
        memcpy(line, request->headers[index].name, name_length);
        line[name_length] = ':';
        line[name_length + 1] = ' ';
        memcpy(line + name_length + 2, request->headers[index].value, value_length);
        line[name_length + value_length + 2] = '\0';
        header_list = curl_slist_append(header_list, line);
        free(line);
        if (header_list == NULL) {
            curl_easy_cleanup(curl);
            ss_http_client_response_free(response);
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
    }
    if (header_list != NULL) {
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, header_list);
    }

    rc = curl_easy_perform(curl);
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &response->status);
    response->error_code = map_curl_error(rc, &context);

    curl_slist_free_all(header_list);
    curl_easy_cleanup(curl);

    if (response->body == NULL) {
        response->body = copy_c_string("");
        if (response->body == NULL) {
            ss_http_client_response_free(response);
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
    }

    *out_response = response;
    return response->error_code;
}
#endif

int ss_http_client_execute_blocking(
    const SSHttpClientRequest *request,
    SSHttpClientResponse **out_response
) {
#ifdef SEM_HTTP_CLIENT_WITH_CURL
    return execute_internal(request, out_response, NULL);
#else
    (void)request;
    if (out_response != NULL) {
        *out_response = NULL;
    }
    return SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE;
#endif
}

int ss_http_client_fetch_text_blocking(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    SSHttpClientResponse **out_response
) {
    SSHttpClientRequest *request;
    int status;

    status = ss_http_client_request_create(&request);
    if (status != SS_HTTP_CLIENT_OK) {
        if (out_response != NULL) {
            *out_response = NULL;
        }
        return status;
    }
    status = ss_http_client_request_set_url(request, url);
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_timeout_ms(request, timeout_ms);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_max_body_bytes(request, max_body_bytes);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_execute_blocking(request, out_response);
    } else if (out_response != NULL) {
        *out_response = NULL;
    }
    ss_http_client_request_free(request);
    return status;
}

int ss_http_client_fetch_text_copy(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    char **out_body,
    long long *out_status
) {
    SSHttpClientResponse *response = NULL;
    int status;

    if (out_body == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    *out_body = NULL;
    if (out_status != NULL) {
        *out_status = 0;
    }

    status = ss_http_client_fetch_text_blocking(
        url, timeout_ms, max_body_bytes, &response);
    if (response != NULL && out_status != NULL) {
        *out_status = (long long)response->status;
    }
    if (status == SS_HTTP_CLIENT_OK && response != NULL) {
        *out_body = copy_c_string(response->body != NULL ? response->body : "");
        if (*out_body == NULL) {
            status = SS_HTTP_CLIENT_ERR_BACKEND;
        }
    }
    ss_http_client_response_free(response);
    return status;
}

int ss_http_client_fetch_text_request_copy(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    unsigned int redirect_limit,
    char **out_body,
    long long *out_status
) {
    SSHttpClientRequest *request = NULL;
    SSHttpClientResponse *response = NULL;
    int status;

    if (out_body == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    *out_body = NULL;
    if (out_status != NULL) {
        *out_status = 0;
    }

    status = ss_http_client_request_create(&request);
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_url(request, url);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_timeout_ms(request, timeout_ms);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_max_body_bytes(request, max_body_bytes);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_redirect_limit(request, redirect_limit);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_execute_blocking(request, &response);
    }
    if (response != NULL && out_status != NULL) {
        *out_status = (long long)response->status;
    }
    if (status == SS_HTTP_CLIENT_OK && response != NULL) {
        *out_body = copy_c_string(response->body != NULL ? response->body : "");
        if (*out_body == NULL) {
            status = SS_HTTP_CLIENT_ERR_BACKEND;
        }
    }

    ss_http_client_response_free(response);
    ss_http_client_request_free(request);
    return status;
}

void ss_http_client_free_string(char *value) {
    free(value);
}

long ss_http_client_response_status(const SSHttpClientResponse *response) {
    return response == NULL ? 0 : response->status;
}

const char *ss_http_client_response_header(
    const SSHttpClientResponse *response,
    const char *name
) {
    size_t index;

    if (response == NULL || name == NULL) {
        return NULL;
    }
    for (index = 0; index < response->header_count; ++index) {
        if (ascii_case_equal(response->headers[index].name, name)) {
            return response->headers[index].value;
        }
    }
    return NULL;
}

const char *ss_http_client_response_body_text(const SSHttpClientResponse *response) {
    return response == NULL ? NULL : response->body;
}

const void *ss_http_client_response_body_bytes(const SSHttpClientResponse *response) {
    return response == NULL ? NULL : response->body;
}

size_t ss_http_client_response_body_length(const SSHttpClientResponse *response) {
    return response == NULL ? 0 : response->body_length;
}

int ss_http_client_response_error_code(const SSHttpClientResponse *response) {
    return response == NULL ? SS_HTTP_CLIENT_ERR_CONFIG : response->error_code;
}

static void fetch_timeout_cb(void *user_data) {
    SSHttpFetchFuture *future = (SSHttpFetchFuture *)user_data;
    future->timeout_requested = 1;
    future->cancel_requested = 1;
}

static void fetch_work_cb(void *user_data) {
    SSHttpFetchFuture *future = (SSHttpFetchFuture *)user_data;

#ifdef SEM_HTTP_CLIENT_WITH_CURL
    future->error_code = execute_internal(
        future->request,
        &future->response,
        &future->cancel_requested);
    if (future->timeout_requested
            && future->error_code == SS_HTTP_CLIENT_ERR_CANCELLED) {
        future->error_code = SS_HTTP_CLIENT_ERR_TIMEOUT;
    }
#else
    future->error_code = SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE;
#endif
}

static void fetch_after_work_cb(void *user_data, int status) {
    SSHttpFetchFuture *future = (SSHttpFetchFuture *)user_data;

    if (future->timer != NULL) {
        ss_async_timer_cancel(future->timer);
        ss_async_timer_destroy(future->timer);
        future->timer = NULL;
    }
    if (status == SS_ASYNC_ERR_CANCELLED && future->error_code == SS_HTTP_CLIENT_OK) {
        future->error_code = SS_HTTP_CLIENT_ERR_CANCELLED;
    } else if (status != SS_ASYNC_OK && future->error_code == SS_HTTP_CLIENT_OK) {
        future->error_code = SS_HTTP_CLIENT_ERR_BACKEND;
    }
    future->ready = 1;
}

int ss_http_client_fetch_text_start(
    SSAsyncLoop *loop,
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    SSHttpFetchFuture **out_future
) {
    return ss_http_client_fetch_text_request_start(
        loop,
        url,
        timeout_ms,
        max_body_bytes,
        SS_HTTP_CLIENT_DEFAULT_REDIRECT_LIMIT,
        out_future
    );
}

int ss_http_client_fetch_text_request_start(
    SSAsyncLoop *loop,
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    unsigned int redirect_limit,
    SSHttpFetchFuture **out_future
) {
    SSHttpFetchFuture *future;
    int status;

    if (loop == NULL || url == NULL || out_future == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    *out_future = NULL;

    future = (SSHttpFetchFuture *)calloc(1, sizeof(*future));
    if (future == NULL) {
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    future->loop = loop;

    status = ss_http_client_request_create(&future->request);
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_url(future->request, url);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_timeout_ms(future->request, timeout_ms);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_max_body_bytes(future->request, max_body_bytes);
    }
    if (status == SS_HTTP_CLIENT_OK) {
        status = ss_http_client_request_set_redirect_limit(future->request, redirect_limit);
    }
    if (status != SS_HTTP_CLIENT_OK) {
        ss_http_client_fetch_free(future);
        return status;
    }

    status = ss_async_timer_start(loop, timeout_ms, fetch_timeout_cb, future, &future->timer);
    if (status != SS_ASYNC_OK) {
        ss_http_client_fetch_free(future);
        return status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE
            ? SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE
            : SS_HTTP_CLIENT_ERR_BACKEND;
    }

    status = ss_async_queue_work(loop, fetch_work_cb, fetch_after_work_cb, future);
    if (status != SS_ASYNC_OK) {
        ss_http_client_fetch_free(future);
        return status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE
            ? SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE
            : SS_HTTP_CLIENT_ERR_BACKEND;
    }

    *out_future = future;
    return SS_HTTP_CLIENT_OK;
}

int ss_http_client_fetch_text_await(SSAsyncLoop *loop, SSHttpFetchFuture *future) {
    if (loop == NULL || future == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    while (!future->ready) {
        int status = ss_async_loop_run_once(loop);
        if (status != SS_ASYNC_OK) {
            return status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE
                ? SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE
                : SS_HTTP_CLIENT_ERR_BACKEND;
        }
    }
    return future->error_code;
}

int ss_http_client_fetch_is_ready(const SSHttpFetchFuture *future) {
    return future != NULL && future->ready;
}

long ss_http_client_fetch_status(const SSHttpFetchFuture *future) {
    return future == NULL ? 0 : ss_http_client_response_status(future->response);
}

const char *ss_http_client_fetch_body_text(const SSHttpFetchFuture *future) {
    return future == NULL ? NULL : ss_http_client_response_body_text(future->response);
}

int ss_http_client_fetch_body_text_copy(
    const SSHttpFetchFuture *future,
    char **out_body
) {
    const char *body;

    if (future == NULL || out_body == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    *out_body = NULL;
    body = ss_http_client_fetch_body_text(future);
    if (body == NULL) {
        body = "";
    }
    *out_body = copy_c_string(body);
    return *out_body == NULL ? SS_HTTP_CLIENT_ERR_BACKEND : SS_HTTP_CLIENT_OK;
}

const void *ss_http_client_fetch_body_bytes(const SSHttpFetchFuture *future) {
    return future == NULL ? NULL : ss_http_client_response_body_bytes(future->response);
}

size_t ss_http_client_fetch_body_length(const SSHttpFetchFuture *future) {
    return future == NULL ? 0 : ss_http_client_response_body_length(future->response);
}

int ss_http_client_fetch_error_code(const SSHttpFetchFuture *future) {
    if (future == NULL) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    return future->error_code;
}

void ss_http_client_fetch_free(SSHttpFetchFuture *future) {
    if (future == NULL) {
        return;
    }
    if (future->timer != NULL) {
        ss_async_timer_cancel(future->timer);
        ss_async_timer_destroy(future->timer);
        future->timer = NULL;
    }
    ss_http_client_request_free(future->request);
    ss_http_client_response_free(future->response);
    free(future);
}
