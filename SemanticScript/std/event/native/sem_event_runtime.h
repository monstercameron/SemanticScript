#ifndef SEM_EVENT_RUNTIME_H
#define SEM_EVENT_RUNTIME_H

#include "../../../runtime/native_async/sem_async_runtime.h"

/*
 * SemanticScript-owned C ABI for standard.event.
 *
 * The ABI is deliberately small and generic: handles, strings, capacities, ids,
 * and status codes. Event-specific compiler lowering is not required.
 */

#ifdef __cplusplus
extern "C" {
#endif

enum {
    SS_EVENT_OK = 0,
    SS_EVENT_NO_EVENT = 0,
    SS_EVENT_ERR_CONFIG = -1,
    SS_EVENT_ERR_RUNTIME_UNAVAILABLE = -2,
    SS_EVENT_ERR_ENGINE = -3,
    SS_EVENT_ERR_QUEUE_FULL = -4,
    SS_EVENT_ERR_OUTPUT_TOO_SMALL = -5,
    SS_EVENT_ERR_SUBSCRIPTION_CLOSED = -6,
    SS_EVENT_ERR_CANCELLED = -7,
    SS_EVENT_ERR_TIMED_OUT = -8
};

void *ss_event_open_process_stream(const char *stream_name, int queue_capacity);
void *ss_event_open_process_queue(const char *stream_name, int queue_capacity);
void *ss_event_open_durable_stream(const char *stream_name, int queue_capacity);
int ss_event_close_stream(void *stream);
long long ss_event_append(
    void *stream,
    const char *event_type,
    const char *event_key,
    const char *payload_json
);
void *ss_event_subscribe(
    void *stream,
    const char *event_type,
    const char *event_key,
    long long after_event_id,
    int queue_capacity
);
long long ss_event_receive(
    void *subscription,
    char *out_event_type,
    int out_event_type_capacity,
    char *out_event_key,
    int out_event_key_capacity,
    char *out_payload_json,
    int out_payload_capacity
);
int ss_event_acknowledge(void *subscription, long long event_id);
int ss_event_close_subscription(void *subscription);

int ss_event_open_process_stream_start(
    SSAsyncLoop *loop,
    const char *stream_name,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
void *ss_event_open_process_stream_await(SSAsyncLoop *loop, void *future);
int ss_event_open_process_queue_start(
    SSAsyncLoop *loop,
    const char *stream_name,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
void *ss_event_open_process_queue_await(SSAsyncLoop *loop, void *future);
int ss_event_open_durable_stream_start(
    SSAsyncLoop *loop,
    const char *stream_name,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
void *ss_event_open_durable_stream_await(SSAsyncLoop *loop, void *future);
int ss_event_close_stream_start(
    SSAsyncLoop *loop,
    void *stream,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
int ss_event_close_stream_await(SSAsyncLoop *loop, void *future);
int ss_event_append_start(
    SSAsyncLoop *loop,
    void *stream,
    const char *event_type,
    const char *event_key,
    const char *payload_json,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
long long ss_event_append_await(SSAsyncLoop *loop, void *future);
int ss_event_subscribe_start(
    SSAsyncLoop *loop,
    void *stream,
    const char *event_type,
    const char *event_key,
    long long after_event_id,
    int queue_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
void *ss_event_subscribe_await(SSAsyncLoop *loop, void *future);
int ss_event_receive_start(
    SSAsyncLoop *loop,
    void *subscription,
    char *out_event_type,
    int out_event_type_capacity,
    char *out_event_key,
    int out_event_key_capacity,
    char *out_payload_json,
    int out_payload_capacity,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
long long ss_event_receive_await(SSAsyncLoop *loop, void *future);
int ss_event_acknowledge_start(
    SSAsyncLoop *loop,
    void *subscription,
    long long event_id,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
int ss_event_acknowledge_await(SSAsyncLoop *loop, void *future);
int ss_event_close_subscription_start(
    SSAsyncLoop *loop,
    void *subscription,
    unsigned long long timeout_ms,
    void *cancel_token,
    void **out_future
);
int ss_event_close_subscription_await(SSAsyncLoop *loop, void *future);

#ifdef __cplusplus
}
#endif

#endif
