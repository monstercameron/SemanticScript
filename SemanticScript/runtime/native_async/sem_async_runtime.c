#include "sem_async_runtime.h"

#include <stdlib.h>

#ifdef SEM_ASYNC_WITH_LIBUV
#include <uv.h>
#endif

struct SSAsyncLoop {
    int available;
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_loop_t uv_loop;
#endif
};

typedef struct SSFutureContinuation {
    SSAsyncResumeFn resume;
    void *resume_user_data;
    struct SSFutureContinuation *next;
} SSFutureContinuation;

struct SSFuture {
    SSAsyncLoop *loop;
    int ready;
    int status;
    void *result;
    SSFutureContinuation *continuations;
};

struct SSAsyncTimer {
    SSAsyncLoop *loop;
    int active;
    int closing;
    SSAsyncResumeFn callback;
    void *user_data;
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_timer_t timer;
#endif
};

typedef struct SSAsyncWorkRequest {
    SSAsyncWorkFn work;
    SSAsyncAfterWorkFn after_work;
    void *user_data;
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_work_t request;
#endif
} SSAsyncWorkRequest;

#ifdef SEM_ASYNC_WITH_LIBUV
static void timer_close_cb(uv_handle_t *handle) {
    SSAsyncTimer *timer = (SSAsyncTimer *)handle->data;
    free(timer);
}

static void timer_cb(uv_timer_t *handle) {
    SSAsyncTimer *timer = (SSAsyncTimer *)handle->data;
    timer->active = 0;
    if (timer->callback != NULL) {
        timer->callback(timer->user_data);
    }
}

static void work_cb(uv_work_t *request) {
    SSAsyncWorkRequest *work = (SSAsyncWorkRequest *)request->data;
    if (work->work != NULL) {
        work->work(work->user_data);
    }
}

static void after_work_cb(uv_work_t *request, int status) {
    SSAsyncWorkRequest *work = (SSAsyncWorkRequest *)request->data;
    int mapped_status = status == UV_ECANCELED ? SS_ASYNC_ERR_CANCELLED : SS_ASYNC_OK;
    if (status != 0 && status != UV_ECANCELED) {
        mapped_status = SS_ASYNC_ERR_ENGINE;
    }
    if (work->after_work != NULL) {
        work->after_work(work->user_data, mapped_status);
    }
    free(work);
}
#endif

int ss_async_loop_init(SSAsyncLoop **out_loop) {
    SSAsyncLoop *loop;

    if (out_loop == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    *out_loop = NULL;

    loop = (SSAsyncLoop *)calloc(1, sizeof(*loop));
    if (loop == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }

#ifdef SEM_ASYNC_WITH_LIBUV
    if (uv_loop_init(&loop->uv_loop) != 0) {
        free(loop);
        return SS_ASYNC_ERR_ENGINE;
    }
    loop->available = 1;
    *out_loop = loop;
    return SS_ASYNC_OK;
#else
    free(loop);
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#endif
}

int ss_async_loop_run(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return SS_ASYNC_ERR_CONFIG;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    return uv_run(&loop->uv_loop, UV_RUN_DEFAULT) == 0 ? SS_ASYNC_OK : SS_ASYNC_ERR_ENGINE;
#else
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#endif
}

int ss_async_loop_run_once(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return SS_ASYNC_ERR_CONFIG;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    (void)uv_run(&loop->uv_loop, UV_RUN_ONCE);
    return SS_ASYNC_OK;
#else
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#endif
}

int ss_async_loop_stop(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return SS_ASYNC_ERR_CONFIG;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_stop(&loop->uv_loop);
    return SS_ASYNC_OK;
#else
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#endif
}

void ss_async_loop_destroy(SSAsyncLoop *loop) {
    if (loop == NULL) {
        return;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    if (loop->available) {
        (void)uv_run(&loop->uv_loop, UV_RUN_NOWAIT);
        (void)uv_loop_close(&loop->uv_loop);
    }
#endif
    free(loop);
}

void *ss_async_loop_native_handle(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return NULL;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    return &loop->uv_loop;
#else
    return NULL;
#endif
}

SSFuture *ss_async_future_create(SSAsyncLoop *loop) {
    SSFuture *future;

    if (loop == NULL || !loop->available) {
        return NULL;
    }
    future = (SSFuture *)calloc(1, sizeof(*future));
    if (future == NULL) {
        return NULL;
    }
    future->loop = loop;
    future->status = SS_ASYNC_OK;
    return future;
}

int ss_async_future_on_ready(
    SSFuture *future,
    SSAsyncResumeFn resume,
    void *user_data
) {
    SSFutureContinuation *continuation;

    if (future == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    if (resume == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    if (future->ready) {
        resume(user_data);
        return SS_ASYNC_OK;
    }
    continuation = (SSFutureContinuation *)calloc(1, sizeof(*continuation));
    if (continuation == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }
    continuation->resume = resume;
    continuation->resume_user_data = user_data;
    continuation->next = future->continuations;
    future->continuations = continuation;
    return SS_ASYNC_OK;
}

static void future_resume_all(SSFuture *future) {
    SSFutureContinuation *continuation;

    while (future->continuations != NULL) {
        continuation = future->continuations;
        future->continuations = continuation->next;
        continuation->resume(continuation->resume_user_data);
        free(continuation);
    }
}

int ss_async_future_complete(SSFuture *future, int status, void *result) {
    if (future == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    if (future->ready) {
        return SS_ASYNC_OK;
    }
    future->ready = 1;
    future->status = status;
    future->result = result;
    future_resume_all(future);
    return SS_ASYNC_OK;
}

int ss_async_future_cancel(SSFuture *future) {
    if (future == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    return ss_async_future_complete(future, SS_ASYNC_ERR_CANCELLED, NULL);
}

int ss_async_future_await(SSAsyncLoop *loop, SSFuture *future) {
    if (loop == NULL || future == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    while (!future->ready) {
        int status = ss_async_loop_run_once(loop);
        if (status != SS_ASYNC_OK) {
            return status;
        }
    }
    return future->status;
}

int ss_async_future_is_ready(const SSFuture *future) {
    return future != NULL && future->ready;
}

int ss_async_future_status(const SSFuture *future) {
    return future == NULL ? SS_ASYNC_ERR_CONFIG : future->status;
}

void *ss_async_future_result(const SSFuture *future) {
    return future == NULL ? NULL : future->result;
}

void ss_async_future_destroy(SSFuture *future) {
    SSFutureContinuation *continuation;

    if (future == NULL) {
        return;
    }
    while (future->continuations != NULL) {
        continuation = future->continuations;
        future->continuations = continuation->next;
        free(continuation);
    }
    free(future);
}

int ss_async_timer_start(
    SSAsyncLoop *loop,
    unsigned long long timeout_ms,
    SSAsyncResumeFn callback,
    void *user_data,
    SSAsyncTimer **out_timer
) {
    SSAsyncTimer *timer;

    if (loop == NULL || !loop->available || callback == NULL || out_timer == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    *out_timer = NULL;

#ifndef SEM_ASYNC_WITH_LIBUV
    (void)timeout_ms;
    (void)user_data;
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#else
    timer = (SSAsyncTimer *)calloc(1, sizeof(*timer));
    if (timer == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }
    timer->loop = loop;
    timer->callback = callback;
    timer->user_data = user_data;
    timer->timer.data = timer;
    if (uv_timer_init(&loop->uv_loop, &timer->timer) != 0) {
        free(timer);
        return SS_ASYNC_ERR_ENGINE;
    }
    if (uv_timer_start(&timer->timer, timer_cb, timeout_ms, 0) != 0) {
        uv_close((uv_handle_t *)&timer->timer, timer_close_cb);
        return SS_ASYNC_ERR_ENGINE;
    }
    timer->active = 1;
    *out_timer = timer;
    return SS_ASYNC_OK;
#endif
}

int ss_async_timer_cancel(SSAsyncTimer *timer) {
    if (timer == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    if (timer->active) {
        uv_timer_stop(&timer->timer);
        timer->active = 0;
    }
    return SS_ASYNC_OK;
#else
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#endif
}

void ss_async_timer_destroy(SSAsyncTimer *timer) {
    if (timer == NULL) {
        return;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    if (!timer->closing) {
        timer->closing = 1;
        if (timer->active) {
            uv_timer_stop(&timer->timer);
            timer->active = 0;
        }
        uv_close((uv_handle_t *)&timer->timer, timer_close_cb);
        return;
    }
#endif
    free(timer);
}

int ss_async_queue_work(
    SSAsyncLoop *loop,
    SSAsyncWorkFn work,
    SSAsyncAfterWorkFn after_work,
    void *user_data
) {
    SSAsyncWorkRequest *request;

    if (loop == NULL || !loop->available || work == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }

#ifndef SEM_ASYNC_WITH_LIBUV
    (void)after_work;
    (void)user_data;
    return SS_ASYNC_ERR_RUNTIME_UNAVAILABLE;
#else
    request = (SSAsyncWorkRequest *)calloc(1, sizeof(*request));
    if (request == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }
    request->work = work;
    request->after_work = after_work;
    request->user_data = user_data;
    request->request.data = request;
    if (uv_queue_work(&loop->uv_loop, &request->request, work_cb, after_work_cb) != 0) {
        free(request);
        return SS_ASYNC_ERR_ENGINE;
    }
    return SS_ASYNC_OK;
#endif
}
