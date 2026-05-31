/* eav_async.c — async runtime shim exposing the SemanticScript libuv-backed
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
#define EAV_EXPORT __declspec(dllexport)
#else
#define EAV_EXPORT __attribute__((visibility("default")))
#endif

#define EAV_ASYNC_OK 0
#define EAV_ASYNC_TIMEOUT 1
#define EAV_ASYNC_CANCELLED 2

static SSAsyncLoop *g_eav_async_loop = NULL;

static SSAsyncLoop *eav_async_get_loop(void) {
    if (!g_eav_async_loop) {
        ss_async_loop_init(&g_eav_async_loop);
    }
    return g_eav_async_loop;
}

typedef struct {
    SSFuture *future;
    int64_t value;
    int status;            /* EAV_ASYNC_OK / TIMEOUT / CANCELLED */
    SSAsyncTimer *work;     /* the value-delivering timer */
    SSAsyncTimer *timeout;  /* optional timeout timer (NULL if none) */
} eav_async_job;

static void eav_async_work_cb(void *ud) {
    eav_async_job *j = (eav_async_job *)ud;
    if (!ss_async_future_is_ready(j->future)) {
        ss_async_future_complete(j->future, SS_ASYNC_OK, &j->value);
    }
}

static void eav_async_timeout_cb(void *ud) {
    eav_async_job *j = (eav_async_job *)ud;
    if (!ss_async_future_is_ready(j->future)) {
        j->status = EAV_ASYNC_TIMEOUT;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_TIMEOUT, 0);
    }
}

static eav_async_job *eav_async_new(int64_t delay_ms, int64_t value) {
    SSAsyncLoop *loop = eav_async_get_loop();
    eav_async_job *j = (eav_async_job *)malloc(sizeof(eav_async_job));
    if (!j) return NULL;
    j->value = value;
    j->status = EAV_ASYNC_OK;
    j->work = NULL;
    j->timeout = NULL;
    j->future = ss_async_future_create(loop);
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    ss_async_timer_start(loop, ms, eav_async_work_cb, j, &j->work);
    return j;
}

/* Arm a future that completes with `value` after `delay_ms` on the libuv loop. */
EAV_EXPORT void *eav_async_delay_start(int64_t delay_ms, int64_t value) {
    return eav_async_new(delay_ms, value);
}

/* Like delay_start, but also arms a timeout: if `timeout_ms` elapses before the
 * value timer fires, the future resolves as timed-out instead. */
EAV_EXPORT void *eav_async_timeout_start(int64_t delay_ms, int64_t value,
                                         int64_t timeout_ms) {
    eav_async_job *j = eav_async_new(delay_ms, value);
    if (!j) return NULL;
    unsigned long long ms = timeout_ms < 0 ? 0ULL : (unsigned long long)timeout_ms;
    ss_async_timer_start(eav_async_get_loop(), ms, eav_async_timeout_cb, j,
                         &j->timeout);
    return j;
}

/* Cancel a not-yet-ready future (e.g. fire-and-forget that is no longer wanted);
 * a later await resolves it as cancelled. */
EAV_EXPORT int32_t eav_async_cancel(void *handle) {
    eav_async_job *j = (eav_async_job *)handle;
    if (j && !ss_async_future_is_ready(j->future)) {
        j->status = EAV_ASYNC_CANCELLED;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_CANCELLED, 0);
        return EAV_ASYNC_CANCELLED;
    }
    return EAV_ASYNC_OK;
}

static void eav_async_cleanup(eav_async_job *j) {
    if (j->work) { ss_async_timer_cancel(j->work); ss_async_timer_destroy(j->work); }
    if (j->timeout) { ss_async_timer_cancel(j->timeout); ss_async_timer_destroy(j->timeout); }
    ss_async_future_destroy(j->future);
    free(j);
}

/* Drive the loop until ready; return the value (ignoring status — for the simple
 * delay case where timeout/cancel are not used). */
EAV_EXPORT int64_t eav_async_await(void *handle) {
    eav_async_job *j = (eav_async_job *)handle;
    if (!j) return 0;
    ss_async_future_await(eav_async_get_loop(), j->future);
    int64_t result = j->value;
    eav_async_cleanup(j);
    return result;
}

/* Drive the loop until ready; write the value through `out` and return the
 * status (0 ok, 1 timeout, 2 cancelled) — the FFI out-param ABI shape, so a
 * non-zero status becomes the EAV call's fallible error. */
EAV_EXPORT int32_t eav_async_await_result(void *handle, int64_t *out) {
    eav_async_job *j = (eav_async_job *)handle;
    if (!j) { if (out) *out = 0; return EAV_ASYNC_CANCELLED; }
    ss_async_future_await(eav_async_get_loop(), j->future);
    int status = j->status;
    if (out) *out = (status == EAV_ASYNC_OK) ? j->value : 0;
    eav_async_cleanup(j);
    return status;
}

/* Run one turn of the loop without blocking; 0 on success. */
EAV_EXPORT int32_t eav_async_run_once(void) {
    return ss_async_loop_run_once(eav_async_get_loop());
}

/* ---- async channel: a bounded FIFO with loop-scheduled producers ----
 * A producer is a libuv timer that pushes a value after a delay; a consumer
 * `receive` drives the loop until an item is available, then pops it. So values
 * arrive in completion order on the single-threaded loop — a real async channel.
 */
#define EAV_CHAN_CAP 64

typedef struct {
    int64_t buf[EAV_CHAN_CAP];
    int head;
    int tail;
    int count;
} eav_channel;

typedef struct {
    eav_channel *chan;
    int64_t value;
    SSAsyncTimer *timer;
} eav_chan_producer;

EAV_EXPORT void *eav_async_channel_create(void) {
    eav_channel *c = (eav_channel *)calloc(1, sizeof(eav_channel));
    return c;
}

static void eav_chan_produce_cb(void *ud) {
    eav_chan_producer *p = (eav_chan_producer *)ud;
    eav_channel *c = p->chan;
    if (c->count < EAV_CHAN_CAP) {
        c->buf[c->tail] = p->value;
        c->tail = (c->tail + 1) % EAV_CHAN_CAP;
        c->count++;
    }
    free(p);
}

/* Schedule a send of `value` to the channel after `delay_ms` on the loop. */
EAV_EXPORT int32_t eav_async_channel_produce(void *chan, int64_t delay_ms,
                                             int64_t value) {
    eav_channel *c = (eav_channel *)chan;
    if (!c) return -1;
    eav_chan_producer *p = (eav_chan_producer *)malloc(sizeof(eav_chan_producer));
    if (!p) return -1;
    p->chan = c;
    p->value = value;
    p->timer = NULL;
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    ss_async_timer_start(eav_async_get_loop(), ms, eav_chan_produce_cb, p,
                         &p->timer);
    return 0;
}

/* Receive the next value, driving the loop until one is available (FIFO). */
EAV_EXPORT int64_t eav_async_channel_receive(void *chan) {
    eav_channel *c = (eav_channel *)chan;
    if (!c) return 0;
    while (c->count == 0) {
        ss_async_loop_run_once(eav_async_get_loop());
    }
    int64_t v = c->buf[c->head];
    c->head = (c->head + 1) % EAV_CHAN_CAP;
    c->count--;
    return v;
}

EAV_EXPORT int32_t eav_async_channel_close(void *chan) {
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
} eav_interval;

typedef struct {
    int fired;
} eav_interval_wait;

EAV_EXPORT void *eav_async_interval_create(int64_t period_ms) {
    eav_interval *iv = (eav_interval *)calloc(1, sizeof(eav_interval));
    if (iv) iv->period_ms = period_ms;
    return iv;
}

static void eav_interval_cb(void *ud) {
    ((eav_interval_wait *)ud)->fired = 1;
}

EAV_EXPORT int64_t eav_async_interval_tick(void *handle) {
    eav_interval *iv = (eav_interval *)handle;
    if (!iv) return 0;
    eav_interval_wait wait;
    wait.fired = 0;
    SSAsyncTimer *timer = NULL;
    unsigned long long ms = iv->period_ms < 0 ? 0ULL : (unsigned long long)iv->period_ms;
    ss_async_timer_start(eav_async_get_loop(), ms, eav_interval_cb, &wait, &timer);
    while (!wait.fired) {
        ss_async_loop_run_once(eav_async_get_loop());
    }
    if (timer) { ss_async_timer_cancel(timer); ss_async_timer_destroy(timer); }
    iv->ticks++;
    return iv->ticks;
}

EAV_EXPORT int32_t eav_async_interval_close(void *handle) {
    free(handle);
    return 0;
}
