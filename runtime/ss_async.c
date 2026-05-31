/* ss_async.c — async runtime shim exposing the SemanticScript libuv-backed
 * event-loop async runtime (SemanticScript/runtime/native_async/, built with
 * SEM_ASYNC_WITH_LIBUV against third_party/libuv) to the EAV front end (semanticscript),
 * the home of the `standard.async` stdlib.
 *
 * libuv event-loop concurrency — NOT threads. A future is created on the single
 * process-wide loop; a libuv timer completes it with a value after a delay; a
 * second (timeout) timer or an explicit cancel can instead complete it with a
 * timeout/cancelled status. `await` drives the loop until the future is ready.
 *
 * Each entry point is a plain `args -> single return` (or out-param) function so
 * it binds through the compiler's `body runtimeBinding <symbol>` seam. Handles
 * flow through EAV as OpaquePointer (i64).
 */
#include "sem_async_runtime.h"
#include <stdint.h>
#include <stdlib.h>

#ifdef _WIN32
#define SS_EXPORT __declspec(dllexport)
#else
#define SS_EXPORT __attribute__((visibility("default")))
#endif

#define SS_ASYNC_OK 0
#define SS_ASYNC_TIMEOUT 1
#define SS_ASYNC_CANCELLED 2

static SSAsyncLoop *g_ss_async_loop = NULL;

static SSAsyncLoop *ss_async_get_loop(void) {
    if (!g_ss_async_loop) {
        ss_async_loop_init(&g_ss_async_loop);
    }
    return g_ss_async_loop;
}

typedef struct {
    SSFuture *future;
    int64_t value;
    int status;            /* SS_ASYNC_OK / TIMEOUT / CANCELLED */
    SSAsyncTimer *work;     /* the value-delivering timer */
    SSAsyncTimer *timeout;  /* optional timeout timer (NULL if none) */
} ss_async_job;

static void ss_async_work_cb(void *ud) {
    ss_async_job *j = (ss_async_job *)ud;
    if (!ss_async_future_is_ready(j->future)) {
        ss_async_future_complete(j->future, SS_ASYNC_OK, &j->value);
    }
}

static void ss_async_timeout_cb(void *ud) {
    ss_async_job *j = (ss_async_job *)ud;
    if (!ss_async_future_is_ready(j->future)) {
        j->status = SS_ASYNC_TIMEOUT;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_TIMEOUT, 0);
    }
}

static ss_async_job *ss_async_new(int64_t delay_ms, int64_t value) {
    SSAsyncLoop *loop = ss_async_get_loop();
    ss_async_job *j = (ss_async_job *)malloc(sizeof(ss_async_job));
    if (!j) return NULL;
    j->value = value;
    j->status = SS_ASYNC_OK;
    j->work = NULL;
    j->timeout = NULL;
    j->future = ss_async_future_create(loop);
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    ss_async_timer_start(loop, ms, ss_async_work_cb, j, &j->work);
    return j;
}

/* Arm a future that completes with `value` after `delay_ms` on the libuv loop. */
SS_EXPORT void *ss_async_delay_start(int64_t delay_ms, int64_t value) {
    return ss_async_new(delay_ms, value);
}

/* Like delay_start, but also arms a timeout: if `timeout_ms` elapses before the
 * value timer fires, the future resolves as timed-out instead. */
SS_EXPORT void *ss_async_timeout_start(int64_t delay_ms, int64_t value,
                                         int64_t timeout_ms) {
    ss_async_job *j = ss_async_new(delay_ms, value);
    if (!j) return NULL;
    unsigned long long ms = timeout_ms < 0 ? 0ULL : (unsigned long long)timeout_ms;
    ss_async_timer_start(ss_async_get_loop(), ms, ss_async_timeout_cb, j,
                         &j->timeout);
    return j;
}

/* Cancel a not-yet-ready future (e.g. fire-and-forget that is no longer wanted);
 * a later await resolves it as cancelled. */
SS_EXPORT int32_t ss_async_cancel(void *handle) {
    ss_async_job *j = (ss_async_job *)handle;
    if (j && !ss_async_future_is_ready(j->future)) {
        j->status = SS_ASYNC_CANCELLED;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_CANCELLED, 0);
        return SS_ASYNC_CANCELLED;
    }
    return SS_ASYNC_OK;
}

static void ss_async_cleanup(ss_async_job *j) {
    if (j->work) { ss_async_timer_cancel(j->work); ss_async_timer_destroy(j->work); }
    if (j->timeout) { ss_async_timer_cancel(j->timeout); ss_async_timer_destroy(j->timeout); }
    ss_async_future_destroy(j->future);
    free(j);
}

/* Drive the loop until ready; return the value (ignoring status — for the simple
 * delay case where timeout/cancel are not used). */
SS_EXPORT int64_t ss_async_await(void *handle) {
    ss_async_job *j = (ss_async_job *)handle;
    if (!j) return 0;
    ss_async_future_await(ss_async_get_loop(), j->future);
    int64_t result = j->value;
    ss_async_cleanup(j);
    return result;
}

/* Drive the loop until ready; write the value through `out` and return the
 * status (0 ok, 1 timeout, 2 cancelled) — the FFI out-param ABI shape, so a
 * non-zero status becomes the EAV call's fallible error. */
SS_EXPORT int32_t ss_async_await_result(void *handle, int64_t *out) {
    ss_async_job *j = (ss_async_job *)handle;
    if (!j) { if (out) *out = 0; return SS_ASYNC_CANCELLED; }
    ss_async_future_await(ss_async_get_loop(), j->future);
    int status = j->status;
    if (out) *out = (status == SS_ASYNC_OK) ? j->value : 0;
    ss_async_cleanup(j);
    return status;
}

/* Run one turn of the loop without blocking; 0 on success. */
SS_EXPORT int32_t ss_async_run_once(void) {
    return ss_async_loop_run_once(ss_async_get_loop());
}

/* ---- async channel: a bounded FIFO with loop-scheduled producers ----
 * A producer is a libuv timer that pushes a value after a delay; a consumer
 * `receive` drives the loop until an item is available, then pops it. So values
 * arrive in completion order on the single-threaded loop — a real async channel.
 */
#define SS_CHAN_CAP 64

typedef struct {
    int64_t buf[SS_CHAN_CAP];
    int head;
    int tail;
    int count;
} ss_channel;

typedef struct {
    ss_channel *chan;
    int64_t value;
    SSAsyncTimer *timer;
} ss_chan_producer;

SS_EXPORT void *ss_async_channel_create(void) {
    ss_channel *c = (ss_channel *)calloc(1, sizeof(ss_channel));
    return c;
}

static void ss_chan_produce_cb(void *ud) {
    ss_chan_producer *p = (ss_chan_producer *)ud;
    ss_channel *c = p->chan;
    if (c->count < SS_CHAN_CAP) {
        c->buf[c->tail] = p->value;
        c->tail = (c->tail + 1) % SS_CHAN_CAP;
        c->count++;
    }
    free(p);
}

/* Schedule a send of `value` to the channel after `delay_ms` on the loop. */
SS_EXPORT int32_t ss_async_channel_produce(void *chan, int64_t delay_ms,
                                             int64_t value) {
    ss_channel *c = (ss_channel *)chan;
    if (!c) return -1;
    ss_chan_producer *p = (ss_chan_producer *)malloc(sizeof(ss_chan_producer));
    if (!p) return -1;
    p->chan = c;
    p->value = value;
    p->timer = NULL;
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    ss_async_timer_start(ss_async_get_loop(), ms, ss_chan_produce_cb, p,
                         &p->timer);
    return 0;
}

/* Receive the next value, driving the loop until one is available (FIFO). */
SS_EXPORT int64_t ss_async_channel_receive(void *chan) {
    ss_channel *c = (ss_channel *)chan;
    if (!c) return 0;
    while (c->count == 0) {
        ss_async_loop_run_once(ss_async_get_loop());
    }
    int64_t v = c->buf[c->head];
    c->head = (c->head + 1) % SS_CHAN_CAP;
    c->count--;
    return v;
}

SS_EXPORT int32_t ss_async_channel_close(void *chan) {
    free(chan);
    return 0;
}

/* ---- async interval: a periodic tick driven by the loop ----
 * Each `tick` arms a one-shot libuv timer for the interval period and drives the
 * loop until it fires, then returns the running tick count. So N ticks take ~N
 * periods of real loop time — a cooperative interval, no thread.
 */
typedef struct {
    int64_t period_ms;
    int64_t ticks;
} ss_interval;

typedef struct {
    int fired;
} ss_interval_wait;

SS_EXPORT void *ss_async_interval_create(int64_t period_ms) {
    ss_interval *iv = (ss_interval *)calloc(1, sizeof(ss_interval));
    if (iv) iv->period_ms = period_ms;
    return iv;
}

static void ss_interval_cb(void *ud) {
    ((ss_interval_wait *)ud)->fired = 1;
}

SS_EXPORT int64_t ss_async_interval_tick(void *handle) {
    ss_interval *iv = (ss_interval *)handle;
    if (!iv) return 0;
    ss_interval_wait wait;
    wait.fired = 0;
    SSAsyncTimer *timer = NULL;
    unsigned long long ms = iv->period_ms < 0 ? 0ULL : (unsigned long long)iv->period_ms;
    ss_async_timer_start(ss_async_get_loop(), ms, ss_interval_cb, &wait, &timer);
    while (!wait.fired) {
        ss_async_loop_run_once(ss_async_get_loop());
    }
    if (timer) { ss_async_timer_cancel(timer); ss_async_timer_destroy(timer); }
    iv->ticks++;
    return iv->ticks;
}

SS_EXPORT int32_t ss_async_interval_close(void *handle) {
    free(handle);
    return 0;
}
