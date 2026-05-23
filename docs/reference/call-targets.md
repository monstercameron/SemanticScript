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
math.addI64
math.subtractI64
math.multiplyI64
math.divideI64
math.moduloI64
math.equalI64
math.notEqualI64
math.lessThanI64
math.lessThanOrEqualI64
math.greaterThanI64
math.greaterThanOrEqualI64
math.checkedMultiplyI64
math.equalCSignedInt32
math.notEqualCSignedInt32
math.lessThanCSignedInt32
math.lessThanOrEqualCSignedInt32
math.greaterThanCSignedInt32
math.greaterThanOrEqualCSignedInt32
```

Short aliases such as `math.subI64`, `math.mulI64`, `math.divI64`, `math.eqI64`,
and `math.ltI64` are normalized to canonical targets.

Math target names are width contracts. `math.*I64` requires I64-shaped
operands, and `math.*CSignedInt32` requires CSignedInt32-shaped operands. The
compiler does not widen or narrow these operands implicitly; use an explicit
conversion operation when the conversion is intended.

`math.checkedMultiplyI64` returns a product plus an overflow predicate
internally. Handle it like a fallible call:

```semanticscript
call multiplyCall math.checkedMultiplyI64
argument multiplyCall left I64 leftValue
argument multiplyCall right I64 rightValue
run multiplyCall
bind ok productValue I64 multiplyCall
bind error multiplyOverflow ArithmeticError multiplyCall
branch error source multiplyCall target overflowLabel
```

## Floating-Point Math

```text
math.addF64
math.subtractF64
math.multiplyF64
math.divideF64
math.equalF64
math.notEqualF64
math.lessThanF64
math.lessThanOrEqualF64
math.greaterThanF64
math.greaterThanOrEqualF64
```

Conversions:

```text
math.intToFloat
math.floatToInt
math.signExtendCSignedInt32ToCSignedInt64
math.truncateCSignedInt64ToCSignedInt32
math.convertSignedInt64ToFloat64
math.convertFloat64ToSignedInt64
math.convertSignedInt32ToSignedInt64
math.convertSignedInt64ToSignedInt32
```

F64 math requires F64-shaped operands. `math.intToFloat` accepts I64 input, and
`math.floatToInt` accepts F64 input. `math.signExtendCSignedInt32ToCSignedInt64`
and `math.truncateCSignedInt64ToCSignedInt32` are the explicit integer width
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
type CountdownValue I64

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
argument helperCall text CNullTerminatedByteString outputText
run helperCall
bind error helperError ConsoleWriteError helperCall
branch error source helperCall target helperFailed
```

The argument names in `argument` lines must match the callee's input names for
maintainable source. The current compiler dispatches by callee input order.

## C Standard Library

`c.<function>` routes through `SemanticScript/compiler/libc_registry.py`.

```semanticscript
storage local immutable byteCount CByteCount 64
call allocateBufferCall c.malloc
argument allocateBufferCall size CByteCount byteCount
run allocateBufferCall
bind value allocatedBuffer COpaqueMemoryAddress allocateBufferCall
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
