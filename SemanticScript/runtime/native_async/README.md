# Native Async Runtime Adapter

This adapter is the SemanticScript-owned boundary for the post-1.0 async
runtime experiment. It wraps libuv behind a small C ABI so generated code does
not expose `uv_loop_t`, `uv_timer_t`, `uv_work_t`, or backend-specific handle
ownership.

The default CMake build compiles a deterministic same-thread fallback without
libuv. It supports futures, one-shot timers, and queued work on the calling
thread so source-only builds and generated smoke apps can run without native
dependency setup.

Enable real libuv behavior explicitly:

```powershell
cmake -S SemanticScript/runtime/native_async -B SemanticScript/runtime/native_async/build `
  -DSEM_ASYNC_WITH_LIBUV=ON
cmake --build SemanticScript/runtime/native_async/build
```

When libuv is not already installed, CMake fetches and builds pinned libuv
source by default. Pass `-DSEM_ASYNC_FETCH_LIBUV=OFF` to require a system
install instead.

The health demo proves two timers can resume the right frame state and complete
out of order. It runs on both the same-thread fallback and the libuv backend.

Runtime model:

- `SSAsyncLoop` owns a libuv loop when the backend is enabled, or a fallback
  timer list otherwise.
- `SSFuture` records completion status, result pointer, and registered
  continuations.
- `SSAsyncTimer` wraps a one-shot libuv timer or a fallback monotonic deadline.
- `SSAsyncCancelToken` is an optional ref-counted cancellation flag that native
  async bindings can retain while a future is pending.
- `ss_async_queue_work` maps blocking work to `uv_queue_work` with libuv, and
  runs same-thread in fallback mode.
- Generated `await` lowering should return to the event loop, not nested-run
  libuv from inside an existing route handler.

`standard.event` builds on this adapter. `openProcessStream` is replay-oriented
and may drop old retained events when its capacity is exceeded, while
`openProcessQueue` is command-queue oriented: `appendEvent` returns
`eventStatusQueueFull` until consumers `acknowledgeEvent` enough received
events to release strict capacity.

Current compiler integration lowers operations that declare
`runtimeBindingAsyncStart` and `runtimeBindingAsyncAwait` through this ABI.
Continuation-frame lowering for user operations remains separate future work.

Compiler status: this adapter is linked by native async runtime bindings such
as `standard.event`, and by the `standard.net` / `net.fetch*` prototype because
`native_http_client` depends on it. Real libuv behavior still requires the
opt-in runtime build; generated executables otherwise use the same-thread
fallback.
