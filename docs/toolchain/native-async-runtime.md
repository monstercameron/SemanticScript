# Native Async Runtime

`SemanticScript/runtime/native_async/` is the async runtime adapter used by
native async runtime bindings. The default backend is a deterministic
same-thread fallback; real libuv behavior must be selected explicitly with
`SEM_ASYNC_WITH_LIBUV=ON` while the continuation-frame compiler backend is still
experimental.

## Backend Choice

The experiment uses libuv 1.x as the portable event-loop backend when the real
backend is enabled:

- timers map to `uv_timer_t`;
- blocking or CPU work maps to `uv_queue_work`;
- future HTTP client work can later use `uv_poll_t` with libcurl's
  `multi_socket` API;
- the public SemanticScript ABI exposes only `SSAsyncLoop`, `SSFuture`, and
  `SSAsyncTimer`.

## Build

Same-thread fallback build:

```powershell
cmake -S SemanticScript/runtime/native_async -B SemanticScript/runtime/native_async/build
cmake --build SemanticScript/runtime/native_async/build
```

Real libuv build:

```powershell
cmake -S SemanticScript/runtime/native_async -B SemanticScript/runtime/native_async/build `
  -DSEM_ASYNC_WITH_LIBUV=ON
cmake --build SemanticScript/runtime/native_async/build
```

If libuv is missing, CMake can fetch pinned libuv source when
`SEM_ASYNC_FETCH_LIBUV=ON` or fail fast when that option is disabled. The default
build keeps source-only and CI builds runnable by executing queued work
immediately on the caller thread and driving one-shot timers from monotonic time
during `ss_async_loop_run_once`. That fallback is a deterministic compatibility
path, not the nonblocking production backend.

## Await Model

An async operation is lowered to a heap-allocated frame and a resume function.
At `await`, generated code stores the next state in the frame, registers the
continuation with a future, and returns to the event loop. The original C stack
does not keep running. When the future completes, the runtime invokes the resume
function and the operation continues after the await point.

The first supported program class is a console program with one runtime-owned
loop. Native webserver handler integration comes later, after the server adapter
has a nonblocking handler model. GUI message loops, long-lived streaming
responses, and nested event-loop runs are unsupported for this experiment.

## Frame ABI

Generated async operations should allocate one frame per operation invocation.
The frame owns:

- a state discriminator used by the generated resume switch;
- spilled locals that remain live across an `await`;
- future/timer handles owned by the operation;
- result and error slots for fallible calls;
- cleanup flags used by `defer`, `deferLog`, and `deferAwaitLog`.

Before `await`, generated code copies live C-stack locals into the frame, records
the resume state, registers the resume function with the awaited future, and
returns to the runtime. On normal return, error return, or cancellation, generated
cleanup blocks run ordinary defers in reverse ownership order; async cleanup
uses the same frame/resume mechanism rather than blocking the loop.

## Future Boundaries

`timeout CALL DURATION` attaches a one-shot `SSAsyncTimer` to the call's future.
When the timer fires, the runtime marks the future timeout/cancel flag and wakes
the loop. `cancelOn CALL TOKEN` passes an optional native `SSAsyncCancelToken`;
runtime bindings that keep a pending future retain the token, poll it before
loop ticks, and publish a cancelled status before generated code resumes after
`await`.

`await WAIT_SET` with following `case CALL LABEL` rows and a `done LABEL` row is
the source-level wait set. Current console lowering polls the futures, runs one
libuv loop tick when none are ready, awaits/materializes the selected future,
marks the selected case consumed, and branches to that case label. Fetch futures
use `ss_http_client_fetch_is_ready`; generic user-operation futures use
`ss_async_future_is_ready`. Consumed-case slots are initialized once per
operation invocation, so the MVP shape drains one current batch; a later fresh
batch should use a fresh wait-set block. The future continuation-frame backend
should keep the same source shape but store selected case state in the frame
before resuming. `taskGroup`, `startInGroup`, and
`awaitGroup` should aggregate child futures, cancel siblings when requested by
group policy, and resume the parent only when the group is complete or its error
policy fires.

## Worker Pool

The libuv backend maps blocking or CPU work to `uv_queue_work` on libuv's
default worker pool. The worker callback must not touch generated
SemanticScript frame state directly. The after-work callback runs on the libuv
loop thread, marks the future ready, and schedules/resumes the generated
continuation. The fallback backend runs work and after-work callbacks
same-thread.

Worker-pool sizing uses libuv's `UV_THREADPOOL_SIZE` environment variable for
the experiment. A SemanticScript-owned pool can be added later if the runtime
needs per-program scheduling policy.

## Diagnostics

`semlint.py` warns when an awaited call has no matching `start`, when a started
call has no matching `await`, and when an awaited call lacks timeout/cancel
metadata. Compiler diagnostics for selecting the libuv backend while using an
unsupported async lowering path are still part of the continuation-frame backend
work.

Do not nested-run libuv inside native HTTP route handlers as the production
model. Native webserver async support should become event-loop based before
handlers perform nonblocking outbound fetches.
