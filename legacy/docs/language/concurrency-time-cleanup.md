# Concurrency, Time, and Cleanup

The syntax already exposes concurrency and cleanup contracts. The default
reference-compiler path still targets a single-thread, single-process execution
model for ordinary user-operation calls, so many source-level constructs lower
to synchronous or metadata-preserving behavior. The repository also ships an
experimental native async adapter and `standard.event` runtime bindings; use
the runtime-specific docs when a program depends on those executable async
surfaces.

## 1.0 Runtime Boundary

SemanticScript 1.0 does not guarantee a full language-level scheduler, timer
wheel, task group runtime, or mutex runtime for every `async` operation. The
native async adapter under `SemanticScript/runtime/native_async/` provides the
experimental C ABI for futures, one-shot timers, cancel tokens, queued work,
and optional libuv integration. `standard.event` builds on that ABI for process
streams, strict process queues, and durable local event streams.

Do not describe ordinary `async`, task group, channel, interval, worker-pool,
or lock rows as automatically providing runtime concurrency. When an example
relies on the native async adapter, `standard.event`, or wait-set lowering, say
that explicitly; otherwise the current source-level fallback is synchronous or
metadata-only.

## Start and Await

```semanticscript
call fetchAccountCall fetchAccount
argument fetchAccountCall accountId AccountId requestedAccountId
start fetchAccountCall
await fetchAccountCall
bind ok accountBalance AccountBalance fetchAccountCall
bind error accountLookupError AccountLookupError fetchAccountCall
```

Current ordinary user-operation fallback: `start CALL` executes like
`run CALL`; `await CALL` is a no-op because the work has already completed.
Runtime-backed stdlib/native calls can create futures through their
`runtimeBindingAsyncStart` / `runtimeBindingAsyncAwait` rows, and the libuv
console async path has dedicated wait-set lowering documented in
`docs/toolchain/native-async-runtime.md`.

## Retry

```semanticscript
retryPolicy accountLookupRetryPolicy
retryMaxAttempts accountLookupRetryPolicy 3
retryInitialDelay accountLookupRetryPolicy 50ms
retryMaximumDelay accountLookupRetryPolicy 500ms
retryJitter accountLookupRetryPolicy yes

useRetry accountLookupCall accountLookupRetryPolicy
run accountLookupCall
```

Current lowering wraps `run CALL` in a bounded retry loop using
`retryMaxAttempts`. If the policy omits a bound, the compiler uses a fallback
attempt count. Delay and jitter metadata are preserved for runtime integration.
`retryPolicy.delayForAttempt` is not a compiler runtimeBinding; implement delay
calculation as a normal SemanticScript operation body or in an explicit runtime.

## Defer and Cleanup

```semanticscript
defer metricsLockReleaseDefer releaseMetricsLock accountLookupGuardToken
deferRunOn metricsLockReleaseDefer all
deferOrder metricsLockReleaseDefer reverseRegistration
deferFailurePolicy metricsLockReleaseDefer logAndSuppress
deferConsumes metricsLockReleaseDefer accountLookupGuardToken
```

Supported cleanup forms:

```text
defer NAME TARGET ARGS...
deferLog NAME TARGET ARGS...
deferAwaitLog NAME TARGET ARGS...
deferWhenExitLog NAME GUARD TARGET ARGS...
```

Current lowering collects defers at parse/codegen time and emits user-operation
cleanup calls in reverse registration order before each `return ok`,
`return error`, `return value`, `return void`, and fall-through return. Non-user-operation
targets are accepted as metadata.

## Task Groups

```semanticscript
taskGroup accountLookupChildren
startInGroup fetchAccountCall accountLookupChildren
awaitGroup accountLookupChildren
bindGroupError childFailure AccountLookupError accountLookupChildren
branchIfGroupError accountLookupChildren accountLookupFailed
```

Current lowering: `startInGroup` executes synchronously, `awaitGroup` is a
no-op, group error binding registers a zero/empty value, and group-error branch
falls through unless individual calls expose errors.

## Channels

```semanticscript
channel taskChannel Task bounded 1
send taskChannel builtTask
receive receivedTask Task taskChannel
branchIfChannelClosed taskChannel channelClosed
```

Current lowering for the legacy `channel` / `send` / `receive` rows models a
single slot in the current operation. Use `standard.event.openProcessQueue`
when the program needs the executable bounded queue/backpressure runtime
surface.

## Locks

```semanticscript
mutex metricsLock
lock metricsLock
# critical section
unlock metricsLock
```

Current lowering: lock and unlock are no-ops in single-thread execution.
They do not provide runtime mutual exclusion until a multi-thread runtime is
bound. `semlint.py` checks for lock acquisition without cleanup so the source
still records the intended release path.

`metricsLock.acquire` and `metricsLock.release` are not compiler runtimeBinding
sentinels. Runtime-backed locks need explicit operations supplied by that
runtime; source-level `lock` / `unlock` rows remain the portable metadata shape.

## Select

```semanticscript
select nextEventSelect
selectCase nextEventSelect taskReady taskReadyBranch
selectCase nextEventSelect timeoutElapsed timeoutBranch
runSelect nextEventSelect
branchSelected nextEventSelect taskReadyBranch handleTaskReady
```

Current lowering for legacy `select` / `selectCase` rows preserves selection
metadata and the single-thread execution path falls through. The newer
`await WAIT_SET` / `case CALL LABEL` / `done LABEL` shape lowers for the libuv
console async path; use a fresh wait-set block for each await batch.

## Intervals

```semanticscript
interval heartbeatInterval every 1000ms
startInterval heartbeatInterval
awaitIntervalTick heartbeatInterval
```

Current lowering: interval handles are metadata; start and await tick are
no-ops without a timer runtime. Native one-shot timers exist in
`native_async`, but the source-level `interval` rows are still not wired to a
general timer producer.

## Worker Pools

```semanticscript
workerPool hashWorkerPool size 4
work hashFileWork target hashFile
workArg hashFileWork path inputFilePath
submitWork hashFileWork hashWorkerPool
awaitWork hashFileWork
```

Current lowering: worker-pool work dispatches directly on the same thread.
`submitWork` builds a synthetic call from `work target` and `workArg` lines;
`awaitWork` binds the result that direct dispatch already produced. The native
async adapter exposes `ss_async_queue_work` for runtimeBinding code, but the
source-level worker-pool rows are not yet a general scheduler surface.
