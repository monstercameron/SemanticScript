# WebAssembly Builds (Emscripten)

SemanticScript can target WebAssembly by lowering the same LLVM IR it already
generates and compiling it with Emscripten instead of the native clang/lld
path. This produces a `.wasm` module plus a `.js` loader that runs under Node
or in a browser.

## How It Works

The pipeline is `tape -> LLVM IR (semsc) -> emcc -> .wasm + .js`.

The only compiler change required is the target triple. `semsc` reads the
`SEMSC_TRIPLE` environment variable and, when set, uses it instead of the host
default. Setting it to `wasm32-unknown-emscripten`:

- skips host-only codegen (notably the Windows SEH crash filter), and
- emits POSIX `signal()` stubs plus libc calls (`puts`, `printf`/`snprintf`)
  that Emscripten's libc provides.

```powershell
$env:SEMSC_TRIPLE = "wasm32-unknown-emscripten"
python SemanticScript\compiler\semsc.py --emit-ir out.ll program.sem
```

## Toolchain Setup

Emscripten is vendored as the `third_party/emsdk` submodule, registered
`update = none` in `.gitmodules`. That makes it **opt-in**: a normal
`git clone` — and even `git clone --recursive` — skips it, so nobody who is not
building wasm pays the download. The submodule itself holds only the emsdk
scripts; the ~2GB toolchain is fetched on demand by `emsdk install` and is
excluded from git by emsdk's own `.gitignore`. Opt in once (note `--checkout`,
required to override `update = none`):

```powershell
git submodule update --init --checkout third_party/emsdk
python third_party/emsdk/emsdk.py install latest
python third_party/emsdk/emsdk.py activate latest
```

To reclaim the ~2GB later: `git submodule deinit third_party/emsdk`.

Activation writes `third_party/emsdk/.emscripten`, which the build helper passes
to `emcc` via `EM_CONFIG`.

## Building And Running

`SemanticScript/tools/build_wasm.py` wraps the full path:

```powershell
python SemanticScript\tools\build_wasm.py SemanticScript\sem\hello_world.sem -o out\hello.js --run
```

`--run` executes the result under Node and prints stdout. The end-to-end test
`SemanticScript/tests/test_wasm_build.py` builds several sample programs to wasm
and asserts their output matches the native JIT baseline; it skips
automatically when the toolchain is not installed.

## Browser DOM: `standard.document`

`standard.document` is the first-class browser DOM library for this target. It
wraps DOM read/mutation and events as ordinary operations over generic
`native.ss_dom_*` runtimeBinding symbols; the adapter is the emscripten
js-library `SemanticScript/std/document/native/ss_dom_runtime.js`, linked
automatically by `build_wasm.py` when a program imports the module.

```text
import document standard.document
dependency standard.document version 0.1 source standard
```

DOM nodes are referenced by opaque integer `DomHandle` values into an
adapter-owned node table (0 = no node), so source is correct on ILP32 wasm32.
Capabilities gate access over the `document.dom`, `document.event`, and
`document.script` effect resources.

### Events ride Asyncify, not the async-future runtime

`document.addEventListener` returns a `DomEventStreamHandle`; `document.nextEvent`
is an ordinary (SemanticScript-synchronous) call whose adapter import is declared
`__async` and calls `Asyncify.handleSleep`. On an Asyncify build the wasm stack
unwinds to the JS event loop while waiting and rewinds when the event fires —
real suspension, no busy-wait, and no SemanticScript async-future/libuv runtime
(which has no wasm backend). `build_wasm.py` auto-enables `-sASYNCIFY` and
`-sASYNCIFY_IMPORTS` when an adapter marks an import `__async`. After an event,
read it with `document.eventTarget` / `document.eventDetailInto`. Only one
`nextEvent` may be parked per stream; a second displaces the first with
`domStatusCancelled`. Release transient node handles with
`document.releaseHandle` to bound the table.

> JSPI: the adapter currently uses Asyncify-specific `handleSleep`, so only
> `-sASYNCIFY` is emitted today. A JSPI path (`-sJSPI` + Promise-returning
> imports) is a planned follow-up for browsers that support stack switching.

### Testing DOM programs

`SemanticScript/tests/test_wasm_dom.py` builds DOM programs to wasm and runs them
against a real jsdom DOM via `tests/wasm_dom/run_dom_harness.js` (built with
`-sMODULARIZE -sEXIT_RUNTIME=1`; completion is detected through `Module.onExit`,
since under Asyncify the factory promise resolves at suspend, not at main's
return). It covers sync mutation, event payload, repeated/Asyncify-suspended
events, evalScript, and a no-event blocking proof. jsdom is a dev dependency:

```powershell
cd SemanticScript\tests\wasm_dom; npm install
```

The suite skips automatically when the toolchain or jsdom is absent.

## Known Limitations

- **`size_t`/pointer width.** The IR currently emits 64-bit `size_t` for some
  libc symbols (e.g. `write`, `strlen`), so `wasm-ld` reports signature
  mismatches against wasm32's 32-bit libc. The sample programs run correctly,
  but this is incorrect for code that depends on those widths and should be
  fixed by making libc signatures triple-aware (wasm32 is ILP32).
- **Native runtimes do not port as-is.** The HTTP server (h2o + libuv +
  picotls) and the Win32/WinUI GUI bridge are native C and have no wasm build.
  Server and GUI programs need a different host integration before they target
  wasm.
- Console and compute programs (math, string/format, arithmetic) work today.
