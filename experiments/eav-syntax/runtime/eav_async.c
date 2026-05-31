/* eav_async.c — async runtime shim exposing the SemanticScript libuv-backed
 * event-loop async runtime (SemanticScript/runtime/native_async/, built with
 * SEM_ASYNC_WITH_LIBUV against third_party/libuv) to the EAV front end (eavc),
 * the home of the `standard.async` stdlib.
 *
 * This is the *libuv event-loop* concurrency model — NOT threads. A future is
 * created on the single process-wide loop; `eav_async_delay_start(ms, value)`
 * arms a libuv timer that, after `ms`, completes the future with `value`;
 * `eav_async_await(handle)` drives the loop (`ss_async_future_await` runs it)
 * until the future is ready, then returns the value. So the value is delivered
 * asynchronously, scheduled on and driven by the real libuv loop, with no thread.
 *
 * Each entry point is a plain `args -> single return` function so it binds
 * through the compiler's generic `body runtimeBinding <symbol>` seam. Handles
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

/* One process-wide loop, created lazily (matches semsc's single-loop model). */
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
} eav_async_job;

/* Loop callback: fires when the timer elapses, completing the future. */
static void eav_async_delay_resume(void *user_data) {
    eav_async_job *job = (eav_async_job *)user_data;
    ss_async_future_complete(job->future, SS_ASYNC_OK, &job->value);
}

/* Start an async future that completes with `value` after `delay_ms`,
 * scheduled on the libuv loop. Returns a job handle. Nothing fires until the
 * loop is driven (by `eav_async_await`). */
EAV_EXPORT void *eav_async_delay_start(int64_t delay_ms, int64_t value) {
    SSAsyncLoop *loop = eav_async_get_loop();
    eav_async_job *job = (eav_async_job *)malloc(sizeof(eav_async_job));
    if (!job) return NULL;
    job->value = value;
    job->future = ss_async_future_create(loop);
    SSAsyncTimer *timer = NULL;
    unsigned long long ms = delay_ms < 0 ? 0ULL : (unsigned long long)delay_ms;
    ss_async_timer_start(loop, ms, eav_async_delay_resume, job, &timer);
    return job;
}

/* Drive the libuv loop until the job's future is ready, then return its value. */
EAV_EXPORT int64_t eav_async_await(void *handle) {
    eav_async_job *job = (eav_async_job *)handle;
    if (!job) return 0;
    ss_async_future_await(eav_async_get_loop(), job->future);
    int64_t result = job->value;
    ss_async_future_destroy(job->future);
    free(job);
    return result;
}

/* Run one turn of the loop (non-blocking-ish); returns 0 on success. Exposed so
 * the stdlib can model `poll` / cooperative progress without awaiting. */
EAV_EXPORT int32_t eav_async_run_once(void) {
    return ss_async_loop_run_once(eav_async_get_loop());
}
