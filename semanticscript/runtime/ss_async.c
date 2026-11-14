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
 * flow through EAV as pointer-typed OpaquePointer values.
 */
#include "sem_async_runtime.h"
#include "ss_runtime_export.h"
#include <stdint.h>
#include <stdlib.h>

#define SS_ASYNC_OK 0
#define SS_ASYNC_TIMEOUT 1
#define SS_ASYNC_CANCELLED 2
#define SS_ASYNC_FAILED 3   /* R-146: loop/future/timer setup failed */

static SSAsyncLoop *g_ss_async_loop = NULL;

static SSAsyncLoop *ss_async_get_loop(void) {
    if (!g_ss_async_loop) {
        ss_async_loop_init(&g_ss_async_loop);
    }
    return g_ss_async_loop;
}

/*
 * R-195: liveness registries for the async handle families (the sqlite R-139 /
 * event R-196 / json R-198 tombstone pattern). future/channel/interval handles
 * are plain OpaquePointers freed on await/close, but the entry points only
 * NULL-checked the raw handle — so a double await/close or a use-after-close
 * dereferenced freed memory (j->future, c->closed, iv->period_ms). A separate
 * registry PER FAMILY tracks live handles; membership is checked by pointer VALUE
 * before any field is read, so a stale handle is rejected without touching freed
 * memory and without confusing a reused address across families. Single-threaded
 * libuv loop (no threads) — no lock needed.
 */
typedef struct { void **items; size_t count; size_t cap; } ss_async_registry;

static ss_async_registry g_async_jobs;
static ss_async_registry g_async_channels;
static ss_async_registry g_async_intervals;
static ss_async_registry g_async_mutexes;
static ss_async_registry g_async_worker_pools;

static int ss_async_track(ss_async_registry *r, void *handle) {
    if (r->count == r->cap) {
        size_t next = r->cap == 0 ? 8 : r->cap * 2;
        if (r->cap > SIZE_MAX / 2 || next > SIZE_MAX / sizeof(void *)) {
            return 0;
        }
        void **grown = (void **)realloc(r->items, next * sizeof(void *));
        if (!grown) return 0;
        r->items = grown;
        r->cap = next;
    }
    r->items[r->count++] = handle;
    return 1;
}

static int ss_async_is_live(const ss_async_registry *r, const void *handle) {
    for (size_t i = 0; i < r->count; i++) {
        if (r->items[i] == handle) return 1;
    }
    return 0;
}

static int ss_async_untrack(ss_async_registry *r, void *handle) {
    for (size_t i = 0; i < r->count; i++) {
        if (r->items[i] == handle) {
            r->items[i] = r->items[r->count - 1];
            r->count--;
            return 1;
        }
    }
    return 0;
}

typedef struct {
    SSFuture *future;
    int64_t value;
    int status;            /* SS_ASYNC_OK / TIMEOUT / CANCELLED */
    SSAsyncTimer *work;     /* the value-delivering timer */
    SSAsyncTimer *timeout;  /* optional timeout timer (NULL if none) */
} ss_async_job;

static void ss_async_cleanup(ss_async_job *j);  /* R-195: untracks + frees a job */

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
    /* R-146: a NULL loop (loop-init failed) would make every future un-drivable —
     * fail the setup now rather than hand back a job that await can never finish. */
    SSAsyncLoop *loop = ss_async_get_loop();
    if (!loop) return NULL;
    ss_async_job *j = (ss_async_job *)malloc(sizeof(ss_async_job));
    if (!j) return NULL;
    j->value = value;
    j->status = SS_ASYNC_OK;
    j->work = NULL;
    j->timeout = NULL;
    /* R-146: a failed future creation must not be awaited (it would never become
     * ready) — release the job and report setup failure. */
    j->future = ss_async_future_create(loop);
    if (!j->future) { free(j); return NULL; }
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    /* R-146: if the value timer cannot be armed, nothing will ever complete the
     * future and `await` would spin forever (ss_async_future_await only exits on a
     * broken loop, not a never-completing future). Complete it now with a terminal
     * FAILED status so the await returns deterministically and the error surfaces
     * through ss_async_await_result. */
    if (ss_async_timer_start(loop, ms, ss_async_work_cb, j, &j->work) != 0) {
        j->status = SS_ASYNC_FAILED;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_ENGINE, 0);
    }
    /* R-195: register before handing the handle out so await/cancel can validate
     * it. On registry-growth failure, tear the job down (cleanup is a no-op for
     * the untrack since we never tracked) and report setup failure. */
    if (!ss_async_track(&g_async_jobs, j)) {
        ss_async_cleanup(j);
        return NULL;
    }
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
    /* R-146: ss_async_new may have already completed the future (value-timer
     * setup failed) — don't arm a timeout on an already-resolved future. */
    if (ss_async_future_is_ready(j->future)) return j;
    unsigned long long ms = timeout_ms < 0 ? 0ULL : (unsigned long long)timeout_ms;
    /* R-146: if the timeout timer cannot be armed, the timeout bound this wrapper
     * promises cannot be honored — resolve as a terminal FAILED setup error rather
     * than silently degrading to an unbounded wait on the value timer. */
    if (ss_async_timer_start(ss_async_get_loop(), ms, ss_async_timeout_cb, j,
                             &j->timeout) != 0) {
        j->status = SS_ASYNC_FAILED;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_ENGINE, 0);
    }
    return j;
}

/* Cancel a not-yet-ready future (e.g. fire-and-forget that is no longer wanted);
 * a later await resolves it as cancelled. */
SS_EXPORT int32_t ss_async_cancel(void *handle) {
    ss_async_job *j = (ss_async_job *)handle;
    /* R-195: reject a stale/freed future handle by membership before deref. */
    if (j && ss_async_is_live(&g_async_jobs, j) && !ss_async_future_is_ready(j->future)) {
        j->status = SS_ASYNC_CANCELLED;
        ss_async_future_complete(j->future, SS_ASYNC_ERR_CANCELLED, 0);
        return SS_ASYNC_CANCELLED;
    }
    return SS_ASYNC_OK;
}

static void ss_async_cleanup(ss_async_job *j) {
    ss_async_untrack(&g_async_jobs, j);  /* R-195: tombstone before free */
    if (j->work) { ss_async_timer_cancel(j->work); ss_async_timer_destroy(j->work); }
    if (j->timeout) { ss_async_timer_cancel(j->timeout); ss_async_timer_destroy(j->timeout); }
    ss_async_future_destroy(j->future);
    free(j);
}

/* Drive the loop until ready; return the value (ignoring status — for the simple
 * delay case where timeout/cancel are not used). */
SS_EXPORT int64_t ss_async_await(void *handle) {
    ss_async_job *j = (ss_async_job *)handle;
    /* R-195: a stale handle (already awaited/freed, or bogus) returns 0 instead
     * of dereferencing freed memory or double-freeing via cleanup. */
    if (!j || !ss_async_is_live(&g_async_jobs, j)) return 0;
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
    /* R-195: a stale handle (already awaited/freed, or bogus) resolves as
     * cancelled instead of dereferencing freed memory or double-freeing. */
    if (!j || !ss_async_is_live(&g_async_jobs, j)) { if (out) *out = 0; return SS_ASYNC_CANCELLED; }
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

/* ---- standard.concurrent facade primitives ----
 * The current concurrency backend is a single libuv event loop. A mutex is
 * therefore a typed guard handle: lock/unlock validate liveness and ordering is
 * enforced statically by sharedState guardRank (SS3085), not by blocking a second
 * OS thread. Worker pools are a named facade over immediate futures until the
 * language can pass function pointers/work closures into libuv's threadpool.
 */
typedef struct {
    int locked;
} ss_concurrent_mutex;

SS_EXPORT void *ss_async_mutex_create(void) {
    ss_concurrent_mutex *m = (ss_concurrent_mutex *)calloc(1, sizeof(ss_concurrent_mutex));
    if (m && !ss_async_track(&g_async_mutexes, m)) { free(m); return NULL; }
    return m;
}

SS_EXPORT int32_t ss_async_mutex_lock(void *handle) {
    ss_concurrent_mutex *m = (ss_concurrent_mutex *)handle;
    if (!m || !ss_async_is_live(&g_async_mutexes, m)) return -1;
    m->locked = 1;
    return 0;
}

SS_EXPORT int32_t ss_async_mutex_unlock(void *handle) {
    ss_concurrent_mutex *m = (ss_concurrent_mutex *)handle;
    if (!m || !ss_async_is_live(&g_async_mutexes, m)) return -1;
    m->locked = 0;
    return 0;
}

SS_EXPORT int32_t ss_async_mutex_close(void *handle) {
    if (!handle || !ss_async_untrack(&g_async_mutexes, handle)) return 0;
    free(handle);
    return 0;
}

typedef struct {
    int64_t workers;
    int closed;
} ss_worker_pool;

SS_EXPORT void *ss_async_worker_pool_create(int64_t workers) {
    ss_worker_pool *p = (ss_worker_pool *)calloc(1, sizeof(ss_worker_pool));
    if (!p) return NULL;
    p->workers = workers < 1 ? 1 : workers;
    if (!ss_async_track(&g_async_worker_pools, p)) { free(p); return NULL; }
    return p;
}

SS_EXPORT void *ss_async_worker_submit_value(void *pool, int64_t value) {
    ss_worker_pool *p = (ss_worker_pool *)pool;
    if (!p || !ss_async_is_live(&g_async_worker_pools, p) || p->closed) return NULL;
    return ss_async_new(0, value);
}

SS_EXPORT int64_t ss_async_worker_join(void *future) {
    return ss_async_await(future);
}

SS_EXPORT int32_t ss_async_worker_pool_close(void *pool) {
    ss_worker_pool *p = (ss_worker_pool *)pool;
    if (!p || !ss_async_untrack(&g_async_worker_pools, p)) return 0;
    p->closed = 1;
    free(p);
    return 0;
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
    int closed;    /* R-138: set by close() while producers are still in flight */
    int pending;   /* R-138: scheduled-but-not-yet-fired producer timers */
} ss_channel;

typedef struct {
    ss_channel *chan;
    int64_t value;
    SSAsyncTimer *timer;
} ss_chan_producer;

SS_EXPORT void *ss_async_channel_create(void) {
    ss_channel *c = (ss_channel *)calloc(1, sizeof(ss_channel));
    /* R-195: register so produce/receive/close validate the handle by membership.
     * On registry-growth failure release the channel and fail. */
    if (c && !ss_async_track(&g_async_channels, c)) { free(c); return NULL; }
    return c;
}

static void ss_chan_produce_cb(void *ud) {
    ss_chan_producer *p = (ss_chan_producer *)ud;
    ss_channel *c = p->chan;
    /* R-138: a producer that fires after close() must not write into (or, as the
     * last in-flight producer, must free) the channel — close() deferred the
     * free to us precisely so the channel outlives every scheduled producer. */
    if (!c->closed && c->count < SS_CHAN_CAP) {
        c->buf[c->tail] = p->value;
        c->tail = (c->tail + 1) % SS_CHAN_CAP;
        c->count++;
    }
    c->pending--;
    if (c->closed && c->pending == 0) {
        ss_async_untrack(&g_async_channels, c);  /* R-195: tombstone before free */
        free(c);
    }
    free(p);
}

/* Schedule a send of `value` to the channel after `delay_ms` on the loop. */
SS_EXPORT int32_t ss_async_channel_produce(void *chan, int64_t delay_ms,
                                             int64_t value) {
    ss_channel *c = (ss_channel *)chan;
    /* R-195: reject a stale/closed channel by membership before deref. */
    if (!c || !ss_async_is_live(&g_async_channels, c) || c->closed) return -1;
    ss_chan_producer *p = (ss_chan_producer *)malloc(sizeof(ss_chan_producer));
    if (!p) return -1;
    p->chan = c;
    p->value = value;
    p->timer = NULL;
    c->pending++;  /* R-138: track in-flight producers so close() can defer free */
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    /* R-181: if the producer timer cannot be armed, its callback (which would
     * decrement `pending` and free `p`) never fires — leaving `pending` stuck
     * forever, so receive() spins and close() never frees the channel. Undo the
     * bookkeeping and report failure instead. */
    if (ss_async_timer_start(ss_async_get_loop(), ms, ss_chan_produce_cb, p,
                             &p->timer) != 0) {
        c->pending--;
        free(p);
        return -1;
    }
    return 0;
}

/* Receive the next value, driving the loop until one is available (FIFO). */
SS_EXPORT int64_t ss_async_channel_receive(void *chan) {
    ss_channel *c = (ss_channel *)chan;
    /* R-195: a stale/closed-and-freed channel returns the 0 sentinel instead of
     * dereferencing freed memory. */
    if (!c || !ss_async_is_live(&g_async_channels, c)) return 0;
    /* R-138: drive the loop only while a value could still arrive. If the channel
     * is empty with no in-flight producers (or is closed), nothing more is
     * coming — return a 0 sentinel instead of spinning forever. */
    while (c->count == 0 && c->pending > 0 && !c->closed) {
        ss_async_loop_run_once(ss_async_get_loop());
    }
    if (c->count == 0) {
        return 0;
    }
    int64_t v = c->buf[c->head];
    c->head = (c->head + 1) % SS_CHAN_CAP;
    c->count--;
    return v;
}

SS_EXPORT int32_t ss_async_channel_close(void *chan) {
    ss_channel *c = (ss_channel *)chan;
    /* R-195: a double close (or bogus handle) fails membership and is a no-op
     * instead of a double-free / use-after-free. */
    if (!c || !ss_async_is_live(&g_async_channels, c)) return 0;
    /* R-138: producers scheduled before close still hold this pointer; freeing
     * now would make their callbacks use-after-free. Mark closed and let the last
     * in-flight producer free it; free immediately only when none are pending. */
    c->closed = 1;
    if (c->pending == 0) {
        ss_async_untrack(&g_async_channels, c);  /* R-195: tombstone before free */
        free(c);
    }
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
    if (!iv) return NULL;
    iv->period_ms = period_ms;
    /* R-195: register so tick/close validate the handle by membership. */
    if (!ss_async_track(&g_async_intervals, iv)) { free(iv); return NULL; }
    return iv;
}

static void ss_interval_cb(void *ud) {
    ((ss_interval_wait *)ud)->fired = 1;
}

SS_EXPORT int64_t ss_async_interval_tick(void *handle) {
    ss_interval *iv = (ss_interval *)handle;
    /* R-195: reject a stale/closed interval by membership before deref. */
    if (!iv || !ss_async_is_live(&g_async_intervals, iv)) return 0;
    /* R-146: a NULL loop or a timer that fails to arm would leave `wait.fired`
     * permanently unset, and the drive loop below would spin forever. Bail with a
     * -1 failed-tick sentinel instead of hanging. */
    SSAsyncLoop *loop = ss_async_get_loop();
    if (!loop) return -1;
    ss_interval_wait wait;
    wait.fired = 0;
    SSAsyncTimer *timer = NULL;
    unsigned long long ms = iv->period_ms < 0 ? 0ULL : (unsigned long long)iv->period_ms;
    if (ss_async_timer_start(loop, ms, ss_interval_cb, &wait, &timer) != 0) {
        return -1;
    }
    /* R-146: bound the wait — ss_async_loop_run_once returns non-zero only when
     * the loop becomes unavailable, at which point the timer can never fire, so
     * stop rather than spin. */
    while (!wait.fired) {
        if (ss_async_loop_run_once(loop) != 0) break;
    }
    if (timer) { ss_async_timer_cancel(timer); ss_async_timer_destroy(timer); }
    if (!wait.fired) return -1;  /* loop died before the tick fired */
    iv->ticks++;
    return iv->ticks;
}

SS_EXPORT int32_t ss_async_interval_close(void *handle) {
    /* R-195: untrack first (membership by pointer value, no deref). A double close
     * or bogus handle fails membership and is a no-op instead of a double-free. */
    if (!handle || !ss_async_untrack(&g_async_intervals, handle)) {
        return 0;
    }
    free(handle);
    return 0;
}
