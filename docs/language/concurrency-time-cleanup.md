# Concurrency, Time, and Cleanup

The syntax already exposes concurrency and cleanup contracts. The reference
compiler currently targets a single-thread, single-process execution model, so
many constructs lower to synchronous or metadata-preserving behavior. That is
not a license to omit the contract lines; future runtimes depend on them.

## 1.0 Runtime Boundary

SemanticScript 1.0 does not ship a real scheduler, event loop, timer wheel, or
thread pool runtime. `async`, `start`, task groups, worker pools, intervals,
channels, select, and locks are contract syntax plus single-thread lowering.
They are useful because they pin down the future runtime contract, but they do
not create parallel execution, preemption, real event-loop scheduling, mutex
contention, or timer delays in the current compiler.

Do not describe these constructs as providing runtime concurrency in 1.0
programs. When an example relies on future scheduler behavior, add a `warning`
or rationale line that says the current lowering is synchronous.

## Start and Await

```semanticscript
call fetchAccountCall fetchAccount
arg fetchAccountCall accountId requestedAccountId
start fetchAccountCall
await fetchAccountCall
bindOk accountBalance AccountBalance fetchAccountCall
bindError accountLookupError AccountLookupError fetchAccountCall
```

Current lowering: `start CALL` executes like `run CALL`; `await CALL` is a
no-op because the work has already completed. This is the correct synchronous
fallback when no scheduler runtime is bound.

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
cleanup calls in reverse registration order before each `returnOk`,
`returnError`, `returnValue`, and fall-through return. Non-user-operation
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

Current lowering models channels as a single slot in the current operation. A
future runtime can replace this with a queue without changing the source
contract.

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

## Select

```semanticscript
select nextEventSelect
selectCase nextEventSelect taskReady taskReadyBranch
selectCase nextEventSelect timeoutElapsed timeoutBranch
runSelect nextEventSelect
branchSelected nextEventSelect taskReadyBranch handleTaskReady
```

Current lowering: selection metadata is preserved and the single-thread
execution path falls through. `semlint.py` checks selects without cases and
cases that reference unknown selects.

## Intervals

```semanticscript
interval heartbeatInterval every 1000ms
startInterval heartbeatInterval
awaitIntervalTick heartbeatInterval
```

Current lowering: interval handles are metadata; start and await tick are
no-ops without a timer runtime.

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
`awaitWork` binds the result that direct dispatch already produced.
