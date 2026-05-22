#include "sem_async_runtime.h"

#include <stdio.h>

typedef struct DemoFrame {
    SSAsyncLoop *loop;
    SSAsyncTimer *first_timer;
    SSAsyncTimer *second_timer;
    int first_ready;
    int second_ready;
} DemoFrame;

static void first_timer_ready(void *user_data) {
    DemoFrame *frame = (DemoFrame *)user_data;
    frame->first_ready = 1;
    puts("first timer resumed");
    if (frame->second_ready) {
        ss_async_loop_stop(frame->loop);
    }
}

static void second_timer_ready(void *user_data) {
    DemoFrame *frame = (DemoFrame *)user_data;
    frame->second_ready = 1;
    puts("second timer resumed");
    if (frame->first_ready) {
        ss_async_loop_stop(frame->loop);
    }
}

int main(void) {
    DemoFrame frame;
    int status;

    frame.loop = NULL;
    frame.first_timer = NULL;
    frame.second_timer = NULL;
    frame.first_ready = 0;
    frame.second_ready = 0;

    status = ss_async_loop_init(&frame.loop);
    if (status == SS_ASYNC_ERR_RUNTIME_UNAVAILABLE) {
        puts("sem_async_health_demo: libuv backend not enabled");
        return 0;
    }
    if (status != SS_ASYNC_OK) {
        return status;
    }

    status = ss_async_timer_start(frame.loop, 10, first_timer_ready, &frame, &frame.first_timer);
    if (status != SS_ASYNC_OK) {
        ss_async_loop_destroy(frame.loop);
        return status;
    }
    status = ss_async_timer_start(frame.loop, 1, second_timer_ready, &frame, &frame.second_timer);
    if (status != SS_ASYNC_OK) {
        ss_async_timer_destroy(frame.first_timer);
        ss_async_loop_run_once(frame.loop);
        ss_async_loop_destroy(frame.loop);
        return status;
    }

    status = ss_async_loop_run(frame.loop);

    ss_async_timer_destroy(frame.first_timer);
    ss_async_timer_destroy(frame.second_timer);
    ss_async_loop_run_once(frame.loop);
    ss_async_loop_destroy(frame.loop);

    if (status != SS_ASYNC_OK) {
        return status;
    }
    return frame.first_ready && frame.second_ready ? 0 : SS_ASYNC_ERR_ENGINE;
}
