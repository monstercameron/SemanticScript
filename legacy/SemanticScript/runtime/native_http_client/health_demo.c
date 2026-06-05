#include "sem_http_client_runtime.h"

#include <stdio.h>
#include <string.h>

static int expect_fetch(
    SSAsyncLoop *loop,
    const char *url,
    unsigned long long timeout_ms,
    int expected_status,
    long expected_http_status,
    const char *expected_body
) {
    SSHttpFetchFuture *future = NULL;
    int status;

    status = ss_http_client_fetch_text_start(
        loop,
        url,
        timeout_ms,
        1024 * 1024,
        &future);
    if (status != SS_HTTP_CLIENT_OK) {
        return status;
    }

    status = ss_http_client_fetch_text_await(loop, future);
    if (status != expected_status) {
        ss_http_client_fetch_free(future);
        return status == SS_HTTP_CLIENT_OK ? SS_HTTP_CLIENT_ERR_BACKEND : status;
    }
    if (expected_http_status != 0
            && ss_http_client_fetch_status(future) != expected_http_status) {
        ss_http_client_fetch_free(future);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    if (expected_body != NULL) {
        const char *body = ss_http_client_fetch_body_text(future);
        if (body == NULL || strcmp(body, expected_body) != 0) {
            ss_http_client_fetch_free(future);
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
        fputs(body, stdout);
    }

    ss_http_client_fetch_free(future);
    ss_async_loop_run_once(loop);
    return SS_HTTP_CLIENT_OK;
}

static int expect_blocking_fetch(
    const char *url,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    int expected_status,
    long expected_http_status,
    const char *expected_body
) {
    SSHttpClientResponse *response = NULL;
    int status = ss_http_client_fetch_text_blocking(
        url, timeout_ms, max_body_bytes, &response);

    if (status != expected_status) {
        ss_http_client_response_free(response);
        return status == SS_HTTP_CLIENT_OK ? SS_HTTP_CLIENT_ERR_BACKEND : status;
    }
    if (response != NULL && ss_http_client_response_error_code(response) != status) {
        ss_http_client_response_free(response);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    if (response != NULL && expected_http_status != 0
            && ss_http_client_response_status(response) != expected_http_status) {
        ss_http_client_response_free(response);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    if (expected_body != NULL) {
        const char *body = ss_http_client_response_body_text(response);
        size_t body_length = ss_http_client_response_body_length(response);
        if (body == NULL
                || strcmp(body, expected_body) != 0
                || body_length != strlen(expected_body)) {
            ss_http_client_response_free(response);
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
        if (ss_http_client_response_header(response, "content-type") == NULL) {
            ss_http_client_response_free(response);
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
    }

    ss_http_client_response_free(response);
    return SS_HTTP_CLIENT_OK;
}

static int expect_fetch_copy(
    const char *url,
    const char *expected_body,
    long long expected_http_status
) {
    char *body = NULL;
    long long http_status = 0;
    int status = ss_http_client_fetch_text_copy(
        url, 3000, 1024 * 1024, &body, &http_status);

    if (status != SS_HTTP_CLIENT_OK) {
        ss_http_client_free_string(body);
        return status;
    }
    if (http_status != expected_http_status
            || body == NULL
            || strcmp(body, expected_body) != 0) {
        ss_http_client_free_string(body);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    ss_http_client_free_string(body);
    return SS_HTTP_CLIENT_OK;
}

static int expect_fetch_request_copy(
    const char *url,
    unsigned int redirect_limit,
    const char *expected_body,
    long long expected_http_status
) {
    char *body = NULL;
    long long http_status = 0;
    int status = ss_http_client_fetch_text_request_copy(
        url, 3000, 1024 * 1024, redirect_limit, &body, &http_status);

    if (status != SS_HTTP_CLIENT_OK) {
        ss_http_client_free_string(body);
        return status;
    }
    if (http_status != expected_http_status
            || body == NULL
            || strcmp(body, expected_body) != 0) {
        ss_http_client_free_string(body);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    ss_http_client_free_string(body);
    return SS_HTTP_CLIENT_OK;
}

static int expect_unsupported_scheme(SSAsyncLoop *loop) {
    SSHttpFetchFuture *future = (SSHttpFetchFuture *)0x1;
    int status = ss_http_client_fetch_text_start(
        loop,
        "ftp://127.0.0.1/unsupported",
        3000,
        1024,
        &future);
    if (future != NULL) {
        ss_http_client_fetch_free(future);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }
    return status == SS_HTTP_CLIENT_ERR_UNSUPPORTED_SCHEME
        ? SS_HTTP_CLIENT_OK
        : status;
}

static int expect_parallel_fetches(SSAsyncLoop *loop) {
    SSHttpFetchFuture *first = NULL;
    SSHttpFetchFuture *second = NULL;
    int status;
    const char *first_body;
    const char *second_body;

    status = ss_http_client_fetch_text_start(
        loop, "http://127.0.0.1:8765/one", 3000, 1024 * 1024, &first);
    if (status != SS_HTTP_CLIENT_OK) {
        return status;
    }
    status = ss_http_client_fetch_text_start(
        loop, "http://127.0.0.1:8765/two", 3000, 1024 * 1024, &second);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_http_client_fetch_free(first);
        return status;
    }

    status = ss_http_client_fetch_text_await(loop, first);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_http_client_fetch_free(first);
        ss_http_client_fetch_free(second);
        return status;
    }
    status = ss_http_client_fetch_text_await(loop, second);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_http_client_fetch_free(first);
        ss_http_client_fetch_free(second);
        return status;
    }

    first_body = ss_http_client_fetch_body_text(first);
    second_body = ss_http_client_fetch_body_text(second);
    if (ss_http_client_fetch_status(first) != 200
            || ss_http_client_fetch_status(second) != 200
            || first_body == NULL
            || second_body == NULL
            || strcmp(first_body, "one\n") != 0
            || strcmp(second_body, "two\n") != 0) {
        ss_http_client_fetch_free(first);
        ss_http_client_fetch_free(second);
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    ss_http_client_fetch_free(first);
    ss_http_client_fetch_free(second);
    ss_async_loop_run_once(loop);
    return SS_HTTP_CLIENT_OK;
}

int main(void) {
    SSAsyncLoop *loop = NULL;
    int status;

    status = ss_async_loop_init(&loop);
    if (status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE) {
        puts("sem_http_client_health_demo: libuv backend not enabled");
        return 0;
    }
    if (status != SS_ASYNC_OK) {
        return status;
    }

    status = expect_unsupported_scheme(loop);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_fetch(
        loop,
        "http://127.0.0.1:8765/",
        3000,
        SS_HTTP_CLIENT_OK,
        200,
        "ok\n");
    if (status == SS_HTTP_CLIENT_ERR_RUNTIME_UNAVAILABLE) {
        puts("sem_http_client_health_demo: libcurl backend not enabled");
        ss_async_loop_destroy(loop);
        return 0;
    }
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_parallel_fetches(loop);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_fetch(
        loop,
        "http://127.0.0.1:8765/not-found",
        3000,
        SS_HTTP_CLIENT_OK,
        404,
        "missing\n");
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_blocking_fetch(
        "http://127.0.0.1:8765/one",
        3000,
        1024 * 1024,
        SS_HTTP_CLIENT_OK,
        200,
        "one\n");
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_blocking_fetch(
        "http://127.0.0.1:8765/large",
        3000,
        4,
        SS_HTTP_CLIENT_ERR_BODY_TOO_LARGE,
        0,
        NULL);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_fetch_copy(
        "http://127.0.0.1:8765/two",
        "two\n",
        200);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_fetch_request_copy(
        "http://127.0.0.1:8765/one",
        5,
        "one\n",
        200);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    status = expect_fetch(
        loop,
        "http://127.0.0.1:8765/slow",
        25,
        SS_HTTP_CLIENT_ERR_TIMEOUT,
        0,
        NULL);
    if (status != SS_HTTP_CLIENT_OK) {
        ss_async_loop_destroy(loop);
        return status;
    }

    ss_async_loop_destroy(loop);
    return SS_HTTP_CLIENT_OK;
}
