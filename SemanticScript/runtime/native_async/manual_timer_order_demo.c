#include "sem_async_runtime.h"

#include <stdio.h>
#include <string.h>

#define PROMISE_COUNT 3

typedef struct TimerPromise TimerPromise;

typedef struct DemoFrame {
    SSAsyncLoop *loop;
    TimerPromise *promises[PROMISE_COUNT];
    char completion_order[PROMISE_COUNT + 1];
    int completion_count;
    int failed;
} DemoFrame;

struct TimerPromise {
    DemoFrame *frame;
    SSFuture *future;
    SSAsyncTimer *timer;
    const char *label;
    unsigned long long delay_ms;
};

static void stop_if_done(DemoFrame *frame) {
    if (frame->failed || frame->completion_count == PROMISE_COUNT) {
        (void)ss_async_loop_stop(frame->loop);
    }
}

static void promise_ready(void *user_data) {
    TimerPromise *promise = (TimerPromise *)user_data;
    DemoFrame *frame = promise->frame;
    const char *label = (const char *)ss_async_future_result(promise->future);

    if (ss_async_future_status(promise->future) != SS_ASYNC_OK || label == NULL) {
        frame->failed = 1;
        stop_if_done(frame);
        return;
    }
    if (frame->completion_count < PROMISE_COUNT) {
        frame->completion_order[frame->completion_count] = label[0];
    }
    frame->completion_count += 1;
    printf("resolved %s after %llums\n", label, promise->delay_ms);
    stop_if_done(frame);
}

static void timer_elapsed(void *user_data) {
    TimerPromise *promise = (TimerPromise *)user_data;
    int status = ss_async_future_complete(
        promise->future,
        SS_ASYNC_OK,
        (void *)promise->label
    );
    if (status != SS_ASYNC_OK) {
        promise->frame->failed = 1;
        stop_if_done(promise->frame);
    }
}

static int start_timer_promise(
    DemoFrame *frame,
    TimerPromise *promise,
    const char *label,
    unsigned long long delay_ms
) {
    int status;

    promise->frame = frame;
    promise->future = ss_async_future_create(frame->loop);
    promise->timer = NULL;
    promise->label = label;
    promise->delay_ms = delay_ms;
    if (promise->future == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }

    status = ss_async_future_on_ready(promise->future, promise_ready, promise);
    if (status != SS_ASYNC_OK) {
        return status;
    }

    status = ss_async_timer_start(
        frame->loop,
        delay_ms,
        timer_elapsed,
        promise,
        &promise->timer
    );
    return status;
}

static void cleanup_frame(DemoFrame *frame) {
    int index;

    for (index = 0; index < PROMISE_COUNT; index += 1) {
        TimerPromise *promise = frame->promises[index];
        if (promise != NULL && promise->timer != NULL) {
            ss_async_timer_destroy(promise->timer);
            promise->timer = NULL;
        }
    }
    for (index = 0; index < PROMISE_COUNT + 1; index += 1) {
        (void)ss_async_loop_run_once(frame->loop);
    }
    for (index = 0; index < PROMISE_COUNT; index += 1) {
        TimerPromise *promise = frame->promises[index];
        if (promise != NULL && promise->future != NULL) {
            ss_async_future_destroy(promise->future);
            promise->future = NULL;
        }
    }
    ss_async_loop_destroy(frame->loop);
    frame->loop = NULL;
}

int main(void) {
    DemoFrame frame;
    TimerPromise first;
    TimerPromise second;
    TimerPromise third;
    int status;

    memset(&frame, 0, sizeof(frame));
    memset(&first, 0, sizeof(first));
    memset(&second, 0, sizeof(second));
    memset(&third, 0, sizeof(third));

    frame.promises[0] = &first;
    frame.promises[1] = &second;
    frame.promises[2] = &third;

    status = ss_async_loop_init(&frame.loop);
    if (status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE) {
        puts("manual timer order demo: libuv backend not enabled");
        return status;
    }
    if (status != SS_ASYNC_OK) {
        return status;
    }

    status = start_timer_promise(&frame, &first, "A", 90);
    if (status == SS_ASYNC_OK) {
        status = start_timer_promise(&frame, &second, "B", 20);
    }
    if (status == SS_ASYNC_OK) {
        status = start_timer_promise(&frame, &third, "C", 50);
    }
    if (status != SS_ASYNC_OK) {
        cleanup_frame(&frame);
        return status;
    }

    status = ss_async_loop_run(frame.loop);
    frame.completion_order[PROMISE_COUNT] = '\0';

    printf(
        "manual timer completion order: %c,%c,%c\n",
        frame.completion_order[0],
        frame.completion_order[1],
        frame.completion_order[2]
    );

    cleanup_frame(&frame);

    if (status != SS_ASYNC_OK || frame.failed) {
        return SS_ASYNC_ERR_ENGINE;
    }
    if (frame.completion_count != PROMISE_COUNT) {
        return SS_ASYNC_ERR_ENGINE;
    }
    return strcmp(frame.completion_order, "BCA") == 0 ? 0 : SS_ASYNC_ERR_ENGINE;
}
