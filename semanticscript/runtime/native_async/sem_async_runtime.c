#include "sem_async_runtime.h"
#include "ss_platform_time.h"

#include <stdint.h>
#include <stdlib.h>

#define SS_ASYNC_CANCEL_TOKEN_MAGIC 0x53534354u

#ifdef SEM_ASYNC_WITH_LIBUV
#include <uv.h>
#endif
#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#include <time.h>
#include <unistd.h>
#endif

typedef struct SSFutureContinuation SSFutureContinuation;

struct SSAsyncLoop {
    int available;
    int stop_requested;
    SSFutureContinuation *ready_head;
    SSFutureContinuation *ready_tail;
    SSAsyncTimer *timers;
#ifdef SEM_ASYNC_WITH_LIBUV
    int closing_timer_count;
    uv_loop_t uv_loop;
#endif
};

struct SSFutureContinuation {
    SSFuture *owner_future;
    SSAsyncResumeFn resume;
    void *resume_user_data;
    struct SSFutureContinuation *next;
};

struct SSFuture {
    SSAsyncLoop *loop;
    int ready;
    int status;
    void *result;
    SSFutureContinuation *continuations;
    SSFutureContinuation *continuations_tail;
};

struct SSAsyncTimer {
    SSAsyncLoop *loop;
    int active;
    int closing;
    SSAsyncResumeFn callback;
    void *user_data;
    struct SSAsyncTimer *next;
#ifndef SEM_ASYNC_WITH_LIBUV
    unsigned long long deadline_ms;
#endif
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_timer_t timer;
#endif
};

struct SSAsyncCancelToken {
    volatile long magic;
    volatile long ref_count;
    volatile long cancelled;
    struct SSAsyncCancelToken *next_registry;
};

typedef struct SSAsyncWorkRequest {
    SSAsyncWorkFn work;
    SSAsyncAfterWorkFn after_work;
    void *user_data;
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_work_t request;
#endif
} SSAsyncWorkRequest;

static void async_timer_unlink(SSAsyncTimer *timer) {
    SSAsyncTimer **cursor;

    if (timer == NULL || timer->loop == NULL) {
        return;
    }
    cursor = &timer->loop->timers;
    while (*cursor != NULL) {
        if (*cursor == timer) {
            *cursor = timer->next;
            timer->next = NULL;
            return;
        }
        cursor = &(*cursor)->next;
    }
}

#ifdef SEM_ASYNC_WITH_LIBUV
static SSAsyncTimer *async_timer_from_handle(
    SSAsyncLoop *loop,
    uv_handle_t *handle
) {
    SSAsyncTimer *timer;

    if (loop == NULL || handle == NULL) {
        return NULL;
    }
    timer = loop->timers;
    while (timer != NULL) {
        if ((uv_handle_t *)&timer->timer == handle) {
            return timer;
        }
        timer = timer->next;
    }
    return NULL;
}

static void timer_close_cb(uv_handle_t *handle) {
    SSAsyncTimer *timer = (SSAsyncTimer *)handle->data;
    if (timer != NULL && timer->loop != NULL
            && timer->loop->closing_timer_count > 0) {
        timer->loop->closing_timer_count -= 1;
    }
    free(timer);
}

static void close_walk_cb(uv_handle_t *handle, void *user_data) {
    if (!uv_is_closing(handle)) {
        SSAsyncTimer *timer = async_timer_from_handle(
            (SSAsyncLoop *)user_data,
            handle
        );
        if (timer != NULL) {
            timer->closing = 1;
            async_timer_unlink(timer);
            timer->loop->closing_timer_count += 1;
            uv_close(handle, timer_close_cb);
        }
    }
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

static unsigned long long fallback_now_ms(void) {
    long long now = ss_platform_monotonic_ms();
    return now > 0 ? (unsigned long long)now : 0ULL;
}

static void fallback_sleep_one_tick(void) {
    ss_platform_sleep_ms(1);
}

static unsigned long long fallback_deadline_ms(unsigned long long timeout_ms) {
    unsigned long long now = fallback_now_ms();
    unsigned long long max_value = ~(unsigned long long)0;

    if (timeout_ms > max_value - now) {
        return max_value;
    }
    return now + timeout_ms;
}

#ifndef SEM_ASYNC_WITH_LIBUV
static int fallback_has_active_timers(SSAsyncLoop *loop);

static int fallback_run_due_timers(SSAsyncLoop *loop) {
    unsigned long long now;
    SSAsyncTimer *timer;
    int fired = 0;

    if (loop == NULL) {
        return 0;
    }
    now = fallback_now_ms();
    timer = loop->timers;
    while (timer != NULL) {
        if (timer->active && now >= timer->deadline_ms) {
            timer->active = 0;
            fired = 1;
            if (timer->callback != NULL) {
                timer->callback(timer->user_data);
            }
            timer = loop->timers;
            continue;
        }
        timer = timer->next;
    }
    return fired;
}

static int fallback_has_active_timers(SSAsyncLoop *loop) {
    SSAsyncTimer *timer;

    if (loop == NULL) {
        return 0;
    }
    timer = loop->timers;
    while (timer != NULL) {
        if (timer->active) {
            return 1;
        }
        timer = timer->next;
    }
    return 0;
}
#endif

static int ss_async_loop_has_ready(const SSAsyncLoop *loop) {
    return loop != NULL && loop->ready_head != NULL;
}

static int ss_async_loop_enqueue_continuation(
    SSAsyncLoop *loop,
    SSFutureContinuation *continuation
) {
    if (loop == NULL || !loop->available || continuation == NULL
            || continuation->resume == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    continuation->next = NULL;
    if (loop->ready_tail != NULL) {
        loop->ready_tail->next = continuation;
    } else {
        loop->ready_head = continuation;
    }
    loop->ready_tail = continuation;
    return SS_ASYNC_OK;
}

static int ss_async_loop_schedule_resume(
    SSAsyncLoop *loop,
    SSFuture *owner_future,
    SSAsyncResumeFn resume,
    void *user_data
) {
    SSFutureContinuation *continuation;

    if (loop == NULL || !loop->available || resume == NULL) {
        return SS_ASYNC_ERR_CONFIG;
    }
    continuation = (SSFutureContinuation *)calloc(1, sizeof(*continuation));
    if (continuation == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }
    continuation->owner_future = owner_future;
    continuation->resume = resume;
    continuation->resume_user_data = user_data;
    return ss_async_loop_enqueue_continuation(loop, continuation);
}

static void ss_async_loop_cancel_future_ready(SSAsyncLoop *loop, SSFuture *future) {
    SSFutureContinuation **cursor;
    SSFutureContinuation *previous = NULL;

    if (loop == NULL || future == NULL) {
        return;
    }
    cursor = &loop->ready_head;
    while (*cursor != NULL) {
        SSFutureContinuation *continuation = *cursor;
        if (continuation->owner_future == future) {
            *cursor = continuation->next;
            if (loop->ready_tail == continuation) {
                loop->ready_tail = previous;
            }
            free(continuation);
            continue;
        }
        previous = continuation;
        cursor = &continuation->next;
    }
    if (loop->ready_head == NULL) {
        loop->ready_tail = NULL;
    }
}

static int ss_async_loop_drain_ready(SSAsyncLoop *loop) {
    SSFutureContinuation *continuation;
    int ran = 0;

    if (loop == NULL || !loop->available) {
        return 0;
    }
    while (loop->ready_head != NULL) {
        continuation = loop->ready_head;
        loop->ready_head = continuation->next;
        if (loop->ready_head == NULL) {
            loop->ready_tail = NULL;
        }
        continuation->next = NULL;
        ran = 1;
        continuation->resume(continuation->resume_user_data);
        free(continuation);
        if (loop->stop_requested) {
            break;
        }
    }
    return ran;
}

static void ss_async_loop_clear_ready(SSAsyncLoop *loop) {
    SSFutureContinuation *continuation;

    if (loop == NULL) {
        return;
    }
    while (loop->ready_head != NULL) {
        continuation = loop->ready_head;
        loop->ready_head = continuation->next;
        free(continuation);
    }
    loop->ready_tail = NULL;
}

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
    loop->available = 1;
    *out_loop = loop;
    return SS_ASYNC_OK;
#endif
}

int ss_async_loop_run(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return SS_ASYNC_ERR_CONFIG;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    while (!loop->stop_requested
            && (ss_async_loop_has_ready(loop) || uv_loop_alive(&loop->uv_loop))) {
        int status = ss_async_loop_run_once(loop);
        if (status != SS_ASYNC_OK) {
            return status;
        }
    }
    loop->stop_requested = 0;
    return SS_ASYNC_OK;
#else
    while (!loop->stop_requested
            && (ss_async_loop_has_ready(loop) || fallback_has_active_timers(loop))) {
        int status = ss_async_loop_run_once(loop);
        if (status != SS_ASYNC_OK) {
            return status;
        }
        if (loop->stop_requested) {
            break;
        }
    }
    loop->stop_requested = 0;
    return SS_ASYNC_OK;
#endif
}

int ss_async_loop_run_once(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return SS_ASYNC_ERR_CONFIG;
    }
    if (loop->stop_requested) {
        loop->stop_requested = 0;
        return SS_ASYNC_OK;
    }
    if (ss_async_loop_drain_ready(loop)) {
        return SS_ASYNC_OK;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    (void)uv_run(&loop->uv_loop, UV_RUN_NOWAIT);
    if (loop->stop_requested) {
        return SS_ASYNC_OK;
    }
    if (ss_async_loop_drain_ready(loop)) {
        return SS_ASYNC_OK;
    }
    fallback_sleep_one_tick();
    (void)uv_run(&loop->uv_loop, UV_RUN_NOWAIT);
    if (loop->stop_requested) {
        return SS_ASYNC_OK;
    }
    (void)ss_async_loop_drain_ready(loop);
    return SS_ASYNC_OK;
#else
    if (fallback_run_due_timers(loop)) {
        if (loop->stop_requested) {
            return SS_ASYNC_OK;
        }
        (void)ss_async_loop_drain_ready(loop);
        return SS_ASYNC_OK;
    }
    fallback_sleep_one_tick();
    (void)fallback_run_due_timers(loop);
    if (loop->stop_requested) {
        return SS_ASYNC_OK;
    }
    (void)ss_async_loop_drain_ready(loop);
    return SS_ASYNC_OK;
#endif
}

int ss_async_loop_stop(SSAsyncLoop *loop) {
    if (loop == NULL || !loop->available) {
        return SS_ASYNC_ERR_CONFIG;
    }
    loop->stop_requested = 1;
#ifdef SEM_ASYNC_WITH_LIBUV
    uv_stop(&loop->uv_loop);
    return SS_ASYNC_OK;
#else
    return SS_ASYNC_OK;
#endif
}

void ss_async_loop_destroy(SSAsyncLoop *loop) {
    if (loop == NULL) {
        return;
    }
    ss_async_loop_clear_ready(loop);
#ifdef SEM_ASYNC_WITH_LIBUV
    if (loop->available) {
        int close_status;

        (void)uv_run(&loop->uv_loop, UV_RUN_NOWAIT);
        uv_walk(&loop->uv_loop, close_walk_cb, loop);
        while (loop->closing_timer_count > 0) {
            (void)uv_run(&loop->uv_loop, UV_RUN_NOWAIT);
            fallback_sleep_one_tick();
        }
        close_status = uv_loop_close(&loop->uv_loop);
        if (close_status == UV_EBUSY) {
            /* Native-handle users own non-runtime libuv handles. Avoid
               invalidating them; the caller may close those handles and retry
               destroying the same async loop. */
            return;
        }
    }
#else
    while (loop->timers != NULL) {
        SSAsyncTimer *timer = loop->timers;
        loop->timers = timer->next;
        timer->next = NULL;
        free(timer);
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
        return ss_async_loop_schedule_resume(
            future->loop, future, resume, user_data);
    }
    continuation = (SSFutureContinuation *)calloc(1, sizeof(*continuation));
    if (continuation == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }
    continuation->owner_future = future;
    continuation->resume = resume;
    continuation->resume_user_data = user_data;
    if (future->continuations_tail != NULL) {
        future->continuations_tail->next = continuation;
    } else {
        future->continuations = continuation;
    }
    future->continuations_tail = continuation;
    return SS_ASYNC_OK;
}

static int future_resume_all(SSFuture *future) {
    SSFutureContinuation *continuation;
    int status;

    while (future->continuations != NULL) {
        continuation = future->continuations;
        future->continuations = continuation->next;
        if (future->continuations == NULL) {
            future->continuations_tail = NULL;
        }
        status = ss_async_loop_enqueue_continuation(future->loop, continuation);
        if (status != SS_ASYNC_OK) {
            free(continuation);
            return status;
        }
    }
    return SS_ASYNC_OK;
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
    return future_resume_all(future);
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
    ss_async_loop_cancel_future_ready(future->loop, future);
    while (future->continuations != NULL) {
        continuation = future->continuations;
        future->continuations = continuation->next;
        free(continuation);
    }
    future->continuations_tail = NULL;
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
    timer = (SSAsyncTimer *)calloc(1, sizeof(*timer));
    if (timer == NULL) {
        return SS_ASYNC_ERR_ENGINE;
    }
    timer->loop = loop;
    timer->active = 1;
    timer->callback = callback;
    timer->user_data = user_data;
    timer->deadline_ms = fallback_deadline_ms(timeout_ms);
    timer->next = loop->timers;
    loop->timers = timer;
    *out_timer = timer;
    return SS_ASYNC_OK;
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
    timer->next = loop->timers;
    loop->timers = timer;
    if (uv_timer_start(&timer->timer, timer_cb, timeout_ms, 0) != 0) {
        timer->closing = 1;
        async_timer_unlink(timer);
        loop->closing_timer_count += 1;
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
    timer->active = 0;
    return SS_ASYNC_OK;
#endif
}

void ss_async_timer_destroy(SSAsyncTimer *timer) {
    if (timer == NULL) {
        return;
    }
#ifdef SEM_ASYNC_WITH_LIBUV
    if (timer->closing) {
        return;
    }
    timer->closing = 1;
    async_timer_unlink(timer);
    if (timer->active) {
        uv_timer_stop(&timer->timer);
        timer->active = 0;
    }
    timer->loop->closing_timer_count += 1;
    uv_close((uv_handle_t *)&timer->timer, timer_close_cb);
    return;
#else
    async_timer_unlink(timer);
    free(timer);
#endif
}

static SSAsyncCancelToken *ss_async_cancel_token_registry = NULL;

#ifdef _WIN32
static INIT_ONCE ss_async_cancel_token_mutex_once = INIT_ONCE_STATIC_INIT;
static CRITICAL_SECTION ss_async_cancel_token_mutex;

static BOOL CALLBACK ss_async_cancel_token_init_mutex_once(
    PINIT_ONCE init_once,
    PVOID parameter,
    PVOID *context
) {
    (void)init_once;
    (void)parameter;
    (void)context;
    InitializeCriticalSection(&ss_async_cancel_token_mutex);
    return TRUE;
}

static void ss_async_cancel_token_lock(void) {
    InitOnceExecuteOnce(
        &ss_async_cancel_token_mutex_once,
        ss_async_cancel_token_init_mutex_once,
        NULL,
        NULL
    );
    EnterCriticalSection(&ss_async_cancel_token_mutex);
}

static void ss_async_cancel_token_unlock(void) {
    LeaveCriticalSection(&ss_async_cancel_token_mutex);
}
#else
static pthread_mutex_t ss_async_cancel_token_mutex = PTHREAD_MUTEX_INITIALIZER;

static void ss_async_cancel_token_lock(void) {
    (void)pthread_mutex_lock(&ss_async_cancel_token_mutex);
}

static void ss_async_cancel_token_unlock(void) {
    (void)pthread_mutex_unlock(&ss_async_cancel_token_mutex);
}
#endif

static int ss_async_cancel_token_registered_locked(SSAsyncCancelToken *token) {
    SSAsyncCancelToken *cursor = ss_async_cancel_token_registry;

    while (cursor != NULL) {
        if (cursor == token) {
            return 1;
        }
        cursor = cursor->next_registry;
    }
    return 0;
}

static void ss_async_cancel_token_registry_add(SSAsyncCancelToken *token) {
    ss_async_cancel_token_lock();
    token->next_registry = ss_async_cancel_token_registry;
    ss_async_cancel_token_registry = token;
    ss_async_cancel_token_unlock();
}

static void ss_async_cancel_token_registry_remove_locked(SSAsyncCancelToken *token) {
    SSAsyncCancelToken **cursor = &ss_async_cancel_token_registry;

    while (*cursor != NULL) {
        if (*cursor == token) {
            *cursor = token->next_registry;
            token->next_registry = NULL;
            return;
        }
        cursor = &(*cursor)->next_registry;
    }
}

SSAsyncCancelToken *ss_async_cancel_token_create(void) {
    SSAsyncCancelToken *token = (SSAsyncCancelToken *)calloc(1, sizeof(*token));
    if (token == NULL) {
        return NULL;
    }
    token->magic = SS_ASYNC_CANCEL_TOKEN_MAGIC;
    token->ref_count = 1;
    ss_async_cancel_token_registry_add(token);
    return token;
}

static long ss_async_atomic_increment(volatile long *value) {
#ifdef _WIN32
    return InterlockedIncrement(value);
#else
    return __sync_add_and_fetch(value, 1);
#endif
}

static long ss_async_atomic_decrement(volatile long *value) {
#ifdef _WIN32
    return InterlockedDecrement(value);
#else
    return __sync_sub_and_fetch(value, 1);
#endif
}

static long ss_async_atomic_exchange(volatile long *value, long replacement) {
#ifdef _WIN32
    return InterlockedExchange(value, replacement);
#else
    return __sync_lock_test_and_set(value, replacement);
#endif
}

static long ss_async_atomic_load(volatile long *value) {
#ifdef _WIN32
    return InterlockedCompareExchange(value, 0, 0);
#else
    return __sync_add_and_fetch(value, 0);
#endif
}

static int ss_async_cancel_token_pointer_is_aligned(const void *token_handle) {
    return token_handle != NULL
        && (((uintptr_t)token_handle % (uintptr_t)sizeof(long)) == 0U);
}

void ss_async_cancel_token_cancel(SSAsyncCancelToken *token) {
    if (!ss_async_cancel_token_pointer_is_aligned(token)) {
        return;
    }
    ss_async_cancel_token_lock();
    if (!ss_async_cancel_token_registered_locked(token)
            || ss_async_atomic_load(&token->magic) != SS_ASYNC_CANCEL_TOKEN_MAGIC) {
        ss_async_cancel_token_unlock();
        return;
    }
    (void)ss_async_atomic_exchange(&token->cancelled, 1);
    ss_async_cancel_token_unlock();
}

int ss_async_cancel_token_is_cancelled(const void *token_handle) {
    const SSAsyncCancelToken *token = (const SSAsyncCancelToken *)token_handle;
    int cancelled;

    if (!ss_async_cancel_token_pointer_is_aligned(token_handle)) {
        return 0;
    }
    ss_async_cancel_token_lock();
    if (!ss_async_cancel_token_registered_locked((SSAsyncCancelToken *)token)
            || ss_async_atomic_load((volatile long *)&token->magic) != SS_ASYNC_CANCEL_TOKEN_MAGIC) {
        ss_async_cancel_token_unlock();
        return 0;
    }
    cancelled = ss_async_atomic_load((volatile long *)&token->cancelled) != 0;
    ss_async_cancel_token_unlock();
    return cancelled;
}

int ss_async_cancel_token_retain(void *token_handle) {
    SSAsyncCancelToken *token = (SSAsyncCancelToken *)token_handle;
    if (!ss_async_cancel_token_pointer_is_aligned(token_handle)) {
        return 0;
    }
    ss_async_cancel_token_lock();
    if (!ss_async_cancel_token_registered_locked(token)
            || ss_async_atomic_load(&token->magic) != SS_ASYNC_CANCEL_TOKEN_MAGIC) {
        ss_async_cancel_token_unlock();
        return 0;
    }
    (void)ss_async_atomic_increment(&token->ref_count);
    ss_async_cancel_token_unlock();
    return 1;
}

void ss_async_cancel_token_release(void *token_handle) {
    SSAsyncCancelToken *token = (SSAsyncCancelToken *)token_handle;
    int should_free = 0;

    if (!ss_async_cancel_token_pointer_is_aligned(token_handle)) {
        return;
    }
    ss_async_cancel_token_lock();
    if (!ss_async_cancel_token_registered_locked(token)
            || ss_async_atomic_load(&token->magic) != SS_ASYNC_CANCEL_TOKEN_MAGIC) {
        ss_async_cancel_token_unlock();
        return;
    }
    if (ss_async_atomic_decrement(&token->ref_count) == 0) {
        (void)ss_async_atomic_exchange(&token->magic, 0);
        ss_async_cancel_token_registry_remove_locked(token);
        should_free = 1;
    }
    ss_async_cancel_token_unlock();
    if (should_free) {
        free(token);
    }
}

void ss_async_cancel_token_destroy(SSAsyncCancelToken *token) {
    if (!ss_async_cancel_token_pointer_is_aligned(token)) {
        return;
    }
    ss_async_cancel_token_release(token);
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
    if (work != NULL) {
        work(user_data);
    }
    if (after_work != NULL) {
        after_work(user_data, SS_ASYNC_OK);
    }
    return SS_ASYNC_OK;
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
