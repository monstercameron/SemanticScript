# Native Async Runtime Adapter

This adapter is the SemanticScript-owned boundary for the post-1.0 async
runtime experiment. It wraps libuv behind a small C ABI so generated code does
not expose `uv_loop_t`, `uv_timer_t`, `uv_work_t`, or backend-specific handle
ownership.

The default CMake build compiles a stub library without libuv. Enable real
libuv behavior explicitly:

```powershell
cmake -S SemanticScript/runtime/native_async -B SemanticScript/runtime/native_async/build `
  -DSEM_ASYNC_WITH_LIBUV=ON
cmake --build SemanticScript/runtime/native_async/build
```

When libuv is not already installed, CMake fetches and builds pinned libuv
source by default. Pass `-DSEM_ASYNC_FETCH_LIBUV=OFF` to require a system
install instead.

The health demo proves two timers can resume the right frame state and complete
out of order. In stub mode it prints that libuv is not enabled and exits 0 so
source-only builds remain usable on machines without the native dependency.

Runtime model:

- `SSAsyncLoop` owns a libuv loop when the backend is enabled.
- `SSFuture` records completion status, result pointer, and registered
  continuations.
- `SSAsyncTimer` wraps a one-shot libuv timer.
- `ss_async_queue_work` maps blocking work to `uv_queue_work`.
- Generated `await` lowering should return to the event loop, not nested-run
  libuv from inside an existing route handler.

The first compiler integration should be opt-in through a build/runtime flag.
The 1.0 synchronous lowering for `start` and `await` remains the default until
the continuation-frame backend is selected.

Compiler status: this adapter is linked by the `standard.net` / `net.fetch*`
prototype because `native_http_client` depends on it. Real libuv behavior still
requires the opt-in runtime build; the 1.0 compiler's general `start` / `await`
lowering remains synchronous until the continuation-frame backend is selected.
