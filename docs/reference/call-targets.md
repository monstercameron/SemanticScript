# Call Targets

`call CALL TARGET` accepts built-in targets, same-file user operations, refined
generated targets, domain methods, and `c.*` C standard-library functions.

## Console Targets

| Target | Args | Lowering |
|---|---|---|
| `console.writeLine` | `text` | `puts(i8*)` |
| `console.writeIntegerLine` | `value` | `printf("%lld\n", i64)` |
| `console.writeFloatLine` | `value` | `printf("%f\n", double)` |

Example:

```semanticscript
storage local immutable greetingText String "hello"
call writeGreetingCall console.writeLine
argument writeGreetingCall text String greetingText
run writeGreetingCall
ignore ok source writeGreetingCall type Void
```

Declare the effect:

```semanticscript
effect main write console.stdout
```

## Integer Math

Canonical targets:

```text
math.addInt64
math.subtractInt64
math.multiplyInt64
math.divideInt64
math.moduloInt64
math.equalInt64
math.notEqualInt64
math.lessThanInt64
math.lessThanOrEqualInt64
math.greaterThanInt64
math.greaterThanOrEqualInt64
math.checkedMultiplyInt64
math.equalInt32
math.notEqualInt32
math.lessThanInt32
math.lessThanOrEqualInt32
math.greaterThanInt32
math.greaterThanOrEqualInt32
```

Short aliases such as `math.subInt64`, `math.mulInt64`, `math.divInt64`, `math.eqInt64`,
and `math.ltInt64` are normalized to canonical targets.

Math target names are width contracts. `math.*Int64` requires Int64-shaped
operands, and `math.*Int32` requires Int32-shaped operands. The
compiler does not widen or narrow these operands implicitly; use an explicit
conversion operation when the conversion is intended.

`math.checkedMultiplyInt64` returns a product plus an overflow predicate
internally. Handle it like a fallible call:

```semanticscript
call multiplyCall math.checkedMultiplyInt64
argument multiplyCall left Int64 leftValue
argument multiplyCall right Int64 rightValue
run multiplyCall
bind ok productValue Int64 multiplyCall
bind error multiplyOverflow ArithmeticError multiplyCall
branch error source multiplyCall target overflowLabel
```

## Floating-Point Math

```text
math.addFloat64
math.subtractFloat64
math.multiplyFloat64
math.divideFloat64
math.equalFloat64
math.notEqualFloat64
math.lessThanFloat64
math.lessThanOrEqualFloat64
math.greaterThanFloat64
math.greaterThanOrEqualFloat64
```

Conversions:

```text
math.convertInt64ToFloat64
math.convertFloat64ToInt64
math.signExtendInt32ToInt64
math.truncateInt64ToInt32
math.convertSignedInt64ToFloat64
math.convertFloat64ToSignedInt64
math.convertSignedInt32ToSignedInt64
math.convertSignedInt64ToSignedInt32
```

Float64 math requires Float64-shaped operands. `math.convertInt64ToFloat64` accepts Int64 input, and
`math.convertFloat64ToInt64` accepts Float64 input. `math.signExtendInt32ToInt64`
and `math.truncateInt64ToInt32` are the explicit integer width
conversion targets; the `math.convert*` names are normalized aliases.

C macro-style classifiers are available as `c.*` calls and lower inline:

```text
c.isnan
c.isinf
c.isfinite
c.isnormal
c.signbit
c.fpclassify
```

## Pointer Targets

```text
pointer.loadByte
pointer.storeByte
pointer.offset
pointer.difference
pointer.isNull
```

Pointer targets are low-level. Their effect requirements are known to the
linter:

```text
pointer.loadByte   read memory.buffer
pointer.storeByte  write memory.buffer
```

`pointer.offset`, `pointer.difference`, and `pointer.isNull` are pure pointer
arithmetic/check operations.

## Outbound Network Targets

The prototype runtime HTTP client surface lives under `standard.net` and
`net.fetch*` so it cannot collide with server-side `http.request*` and
`http.response*` APIs.

```text
net.fetchText
net.fetchBytes
```

`net.fetchText` is expected to take:

```text
request HttpGetRequest
```

and expose:

```text
Result HttpTextResponse HttpClientErrorCode
```

`HttpGetRequest` contains `url` and nested `policy.timeoutMillis`,
`policy.maxBodyBytes`, and `policy.redirectLimit` fields. `HttpTextResponse`
contains `status` and caller-owned `body`; release that body with
`net.freeTextBody` or an equivalent heap free after use.

The native prototype lives in `SemanticScript/runtime/native_http_client/` and
uses `SemanticScript/runtime/native_async/` when libuv is enabled. Application
source must declare `effect OP write network.http.client` for outbound fetch
work. Real network behavior still depends on the optional libcurl/libuv runtime
build; the source/API shape is intentionally separate from server-side
`standard.http`.

## Domain Methods

A target of the shape `TypeName.methodName` can lower to a primitive operation
when `TypeName` aliases an integer or floating type.

```semanticscript
type CountdownValue Int64

call decrementCall CountdownValue.subtractPositiveStep
argument decrementCall left CountdownValue currentCountdownValue
argument decrementCall right CountdownValue decrementStep
run decrementCall
bind value nextCountdownValue CountdownValue decrementCall
```

Common integer domain methods include:

```text
add subtract multiply divide modulo
equal notEqual lessThan lessThanOrEqual greaterThan greaterThanOrEqual
addPositiveStep subtractStep subtractPositiveStep multiplyByStep
multiplyByCounter moduloBy square checkedMultiply
```

Floating aliases support the core arithmetic and comparison methods.

## User Operations

When `TARGET` matches an `operation NAME` in the same program, the compiler
emits a direct LLVM call.

```semanticscript
call helperCall writeStandardOutputLine
argument helperCall text String outputText
run helperCall
bind error helperError ConsoleWriteError helperCall
branch error source helperCall target helperFailed
```

The argument names in `argument` lines must match the callee's input names for
maintainable source. The current compiler dispatches by callee input order.

## C Standard Library

`c.<function>` routes through `SemanticScript/compiler/libc_registry.py`.
Raw `c.*` is a compiler interop escape hatch, not the target shape agents should
grow in application code. Every registry entry carries a machine-readable
wrapper policy in `libc_registry.c_wrapper_policy_for()` and `sem docs get c.*`
under `target.wrapperPolicy`.

For heap allocation in new app code, prefer `standard.memory` wrappers:

```semanticscript
import memory standard.memory
call allocateBufferCall memory.allocateMemoryBytes
argument allocateBufferCall byteCount ByteCount requestedByteCount
run allocateBufferCall
bind ok allocatedBuffer OpaquePointer allocateBufferCall
bind error allocationError MemoryAllocationError allocateBufferCall
branch error source allocateBufferCall target allocationFailed
defer releaseBufferDefer memory.releaseMemoryBytes allocatedBuffer
```

```semanticscript
storage local immutable byteCount ByteCount 64
call allocateBufferCall c.malloc
argument allocateBufferCall size ByteCount byteCount
run allocateBufferCall
bind value allocatedBuffer OpaquePointer allocateBufferCall
```

The registry covers hosted C library functions across headers such as
`stdio.h`, `stdlib.h`, `string.h`, `math.h`, `ctype.h`, `time.h`, `wchar.h`,
`fenv.h`, `complex.h`, `uchar.h`, and `threads.h`.

C functions with underscores are exposed through SemanticScript-legal camelCase
aliases where needed:

```text
c.alignedAlloc      -> aligned_alloc
c.processExitWithoutCleanup -> _Exit
c.timespecGet       -> timespec_get
```

Varargs are supported for registry entries that declare `var_args=True`, such
as `c.printf`.

Wrapper-policy decisions:

- `stdlib-wrapper-planned`: add or prefer a real `standard.*` SemanticScript
  operation with effects, capabilities, failure handling, and cleanup rows.
- `native-adapter-required`: expose only after a portable native adapter owns
  the ABI shape; do not generate raw calls for normal app code.
- `compiler-runtime-owned`: use the owning standard module rather than calling
  adapter symbols directly.
- `no-public-wrapper`: intentionally unsafe or obsolete C API; keep behind the
  escape hatch and prefer a safer SemanticScript design.
- `abi-blocked`: current lowering cannot represent the ABI safely.
