#include "sem_http_client_runtime.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef SEM_ASYNC_WITH_LIBUV
#include <uv.h>
#endif

#define DEFAULT_URL "http://127.0.0.1:8765/"
#define DEFAULT_REQUESTS 1000ULL
#define DEFAULT_CONCURRENCY 16ULL
#define DEFAULT_WARMUP_REQUESTS 64ULL
#define DEFAULT_TIMEOUT_MS 3000ULL
#define DEFAULT_MAX_BODY_BYTES (1024U * 1024U)
#define EXPECTED_BODY "ok\n"

#ifdef SEM_ASYNC_WITH_LIBUV
typedef struct BenchStats {
    double *batch_ms;
    size_t batch_count;
    size_t batch_capacity;
    unsigned long long requests_completed;
} BenchStats;

static double now_ms(void) {
    return (double)uv_hrtime() / 1000000.0;
}

static int compare_double(const void *left, const void *right) {
    double a = *(const double *)left;
    double b = *(const double *)right;
    if (a < b) {
        return -1;
    }
    if (a > b) {
        return 1;
    }
    return 0;
}

static int parse_ull_arg(
    const char *text,
    const char *name,
    unsigned long long min_value,
    unsigned long long *out_value
) {
    char *end = NULL;
    unsigned long long value;

    if (text == NULL || *text == '\0' || out_value == NULL) {
        return 0;
    }

    value = strtoull(text, &end, 10);
    if (end == text || *end != '\0' || value < min_value) {
        fprintf(stderr, "invalid %s: %s\n", name, text);
        return 0;
    }

    *out_value = value;
    return 1;
}

static int record_batch(BenchStats *stats, double elapsed_ms, size_t completed) {
    double *grown;
    size_t next_capacity;

    if (stats == NULL) {
        return 0;
    }
    if (stats->batch_count == stats->batch_capacity) {
        next_capacity = stats->batch_capacity == 0 ? 16 : stats->batch_capacity * 2;
        grown = (double *)realloc(stats->batch_ms, next_capacity * sizeof(*grown));
        if (grown == NULL) {
            return 0;
        }
        stats->batch_ms = grown;
        stats->batch_capacity = next_capacity;
    }

    stats->batch_ms[stats->batch_count++] = elapsed_ms;
    stats->requests_completed += (unsigned long long)completed;
    return 1;
}

static int validate_future(SSHttpFetchFuture *future) {
    const char *body;

    if (ss_http_client_fetch_status(future) != 200) {
        fprintf(stderr, "unexpected HTTP status: %ld\n", ss_http_client_fetch_status(future));
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    body = ss_http_client_fetch_body_text(future);
    if (body == NULL || strcmp(body, EXPECTED_BODY) != 0) {
        fprintf(stderr, "unexpected response body\n");
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    if (ss_http_client_fetch_body_length(future) != strlen(EXPECTED_BODY)) {
        fprintf(stderr, "unexpected response body length\n");
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    return SS_HTTP_CLIENT_OK;
}

static int run_batch(
    SSAsyncLoop *loop,
    const char *url,
    size_t count,
    unsigned long long timeout_ms,
    size_t max_body_bytes
) {
    SSHttpFetchFuture **futures;
    size_t index;
    size_t started = 0;
    int status = SS_HTTP_CLIENT_OK;

    futures = (SSHttpFetchFuture **)calloc(count, sizeof(*futures));
    if (futures == NULL) {
        return SS_HTTP_CLIENT_ERR_BACKEND;
    }

    for (index = 0; index < count; ++index) {
        status = ss_http_client_fetch_text_start(
            loop,
            url,
            timeout_ms,
            max_body_bytes,
            &futures[index]);
        if (status != SS_HTTP_CLIENT_OK) {
            fprintf(stderr, "fetch start failed at batch index %llu: %d\n",
                (unsigned long long)index,
                status);
            goto cleanup;
        }
        ++started;
    }

    for (index = 0; index < started; ++index) {
        status = ss_http_client_fetch_text_await(loop, futures[index]);
        if (status != SS_HTTP_CLIENT_OK) {
            fprintf(stderr, "fetch await failed at batch index %llu: %d\n",
                (unsigned long long)index,
                status);
            goto cleanup;
        }
        status = validate_future(futures[index]);
        if (status != SS_HTTP_CLIENT_OK) {
            goto cleanup;
        }
    }

cleanup:
    for (index = 0; index < started; ++index) {
        ss_http_client_fetch_free(futures[index]);
    }
    free(futures);
    (void)ss_async_loop_run_once(loop);
    return status;
}

static int run_requests(
    SSAsyncLoop *loop,
    const char *url,
    unsigned long long requests,
    unsigned long long concurrency,
    unsigned long long timeout_ms,
    size_t max_body_bytes,
    BenchStats *stats
) {
    unsigned long long remaining = requests;
    size_t batch_size;
    int status;
    double start_ms;
    double elapsed_ms;

    while (remaining > 0) {
        batch_size = (size_t)(remaining < concurrency ? remaining : concurrency);
        start_ms = now_ms();
        status = run_batch(loop, url, batch_size, timeout_ms, max_body_bytes);
        elapsed_ms = now_ms() - start_ms;
        if (status != SS_HTTP_CLIENT_OK) {
            return status;
        }
        if (stats != NULL && !record_batch(stats, elapsed_ms, batch_size)) {
            return SS_HTTP_CLIENT_ERR_BACKEND;
        }
        remaining -= (unsigned long long)batch_size;
    }

    return SS_HTTP_CLIENT_OK;
}

static double percentile(const double *values, size_t count, double pct) {
    size_t index;

    if (values == NULL || count == 0) {
        return 0.0;
    }
    index = (size_t)((pct / 100.0) * (double)(count - 1));
    return values[index];
}

static void print_stats(
    const char *url,
    unsigned long long requests,
    unsigned long long concurrency,
    unsigned long long warmup_requests,
    unsigned long long timeout_ms,
    const BenchStats *stats,
    double measured_ms
) {
    double min_ms = 0.0;
    double max_ms = 0.0;
    double total_batch_ms = 0.0;
    double avg_batch_ms;
    double rps;
    size_t index;

    if (stats->batch_count > 0) {
        min_ms = stats->batch_ms[0];
        max_ms = stats->batch_ms[stats->batch_count - 1];
    }
    for (index = 0; index < stats->batch_count; ++index) {
        total_batch_ms += stats->batch_ms[index];
    }
    avg_batch_ms = stats->batch_count == 0
        ? 0.0
        : total_batch_ms / (double)stats->batch_count;
    rps = measured_ms <= 0.0
        ? 0.0
        : ((double)stats->requests_completed * 1000.0) / measured_ms;

    printf("sem_http_client_bench_demo: backend=libuv+libcurl\n");
    printf("url=%s\n", url);
    printf("requests=%llu\n", requests);
    printf("warmup_requests=%llu\n", warmup_requests);
    printf("concurrency=%llu\n", concurrency);
    printf("timeout_ms=%llu\n", timeout_ms);
    printf("completed=%llu\n", stats->requests_completed);
    printf("failed=0\n");
    printf("measured_ms=%.3f\n", measured_ms);
    printf("throughput_rps=%.2f\n", rps);
    printf("batch_ms_min=%.3f\n", min_ms);
    printf("batch_ms_avg=%.3f\n", avg_batch_ms);
    printf("batch_ms_p50=%.3f\n", percentile(stats->batch_ms, stats->batch_count, 50.0));
    printf("batch_ms_p95=%.3f\n", percentile(stats->batch_ms, stats->batch_count, 95.0));
    printf("batch_ms_max=%.3f\n", max_ms);
}
#endif

int main(int argc, char **argv) {
#ifndef SEM_ASYNC_WITH_LIBUV
    (void)argc;
    (void)argv;
    puts("sem_http_client_bench_demo: libuv backend not enabled");
    return 0;
#else
    const char *url = DEFAULT_URL;
    unsigned long long requests = DEFAULT_REQUESTS;
    unsigned long long concurrency = DEFAULT_CONCURRENCY;
    unsigned long long warmup_requests = DEFAULT_WARMUP_REQUESTS;
    unsigned long long timeout_ms = DEFAULT_TIMEOUT_MS;
    SSAsyncLoop *loop = NULL;
    BenchStats stats;
    int status;
    double measured_start_ms;
    double measured_ms;

    if (argc > 1) {
        url = argv[1];
    }
    if (argc > 2 && !parse_ull_arg(argv[2], "requests", 1, &requests)) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (argc > 3 && !parse_ull_arg(argv[3], "concurrency", 1, &concurrency)) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (argc > 4 && !parse_ull_arg(argv[4], "warmup_requests", 0, &warmup_requests)) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (argc > 5 && !parse_ull_arg(argv[5], "timeout_ms", 1, &timeout_ms)) {
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }
    if (concurrency > 1024) {
        fprintf(stderr, "concurrency is capped at 1024 for this benchmark\n");
        return SS_HTTP_CLIENT_ERR_CONFIG;
    }

    memset(&stats, 0, sizeof(stats));

    status = ss_async_loop_init(&loop);
    if (status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE) {
        puts("sem_http_client_bench_demo: libuv backend not enabled");
        return 0;
    }
    if (status != SS_ASYNC_OK) {
        return status;
    }

    if (warmup_requests > 0) {
        status = run_requests(
            loop,
            url,
            warmup_requests,
            concurrency,
            timeout_ms,
            DEFAULT_MAX_BODY_BYTES,
            NULL);
        if (status != SS_HTTP_CLIENT_OK) {
            ss_async_loop_destroy(loop);
            return status;
        }
    }

    measured_start_ms = now_ms();
    status = run_requests(
        loop,
        url,
        requests,
        concurrency,
        timeout_ms,
        DEFAULT_MAX_BODY_BYTES,
        &stats);
    measured_ms = now_ms() - measured_start_ms;
    if (status != SS_HTTP_CLIENT_OK) {
        free(stats.batch_ms);
        ss_async_loop_destroy(loop);
        return status;
    }

    qsort(stats.batch_ms, stats.batch_count, sizeof(*stats.batch_ms), compare_double);
    print_stats(
        url,
        requests,
        concurrency,
        warmup_requests,
        timeout_ms,
        &stats,
        measured_ms);

    free(stats.batch_ms);
    ss_async_loop_destroy(loop);
    return SS_HTTP_CLIENT_OK;
#endif
}
