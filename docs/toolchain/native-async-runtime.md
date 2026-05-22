# Native Async Runtime

`SemanticScript/runtime/native_async/` is the opt-in libuv experiment for
post-1.0 async lowering. The 1.0 compiler still lowers `start` and `await`
synchronously by default. The native HTTP client prototype can link this adapter
as a stub today; real libuv behavior must be selected explicitly with
`SEM_ASYNC_WITH_LIBUV=ON` while the continuation-frame compiler backend is still
experimental.

## Backend Choice

The experiment uses libuv 1.x as the portable event-loop backend:

- timers map to `uv_timer_t`;
- blocking or CPU work maps to `uv_queue_work`;
- future HTTP client work can later use `uv_poll_t` with libcurl's
  `multi_socket` API;
- the public SemanticScript ABI exposes only `SSAsyncLoop`, `SSFuture`, and
  `SSAsyncTimer`.

## Build

Stub build:

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

If libuv is missing, CMake fails when `SEM_ASYNC_WITH_LIBUV=ON`. The stub build
keeps source-only and CI builds working on machines that do not have native
async prerequisites.

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
the loop. `cancelOn CALL TOKEN` records the cancellation token watched by the
future; hard interruption depends on the backend, but the future must publish a
cancelled status before generated code resumes after `await`.

`select` should become a wait set over futures and timer tokens. The selected
case stores its branch in the frame before resume. `taskGroup`, `startInGroup`,
and `awaitGroup` should aggregate child futures, cancel siblings when requested
by group policy, and resume the parent only when the group is complete or its
error policy fires.

## Worker Pool

The first backend maps blocking or CPU work to `uv_queue_work` on libuv's default
worker pool. The worker callback must not touch generated SemanticScript frame
state directly. The after-work callback runs on the libuv loop thread, marks the
future ready, and schedules/resumes the generated continuation.

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
