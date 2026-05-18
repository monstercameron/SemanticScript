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
const greetingText String "hello"
call writeGreetingCall console.writeLine
arg writeGreetingCall text greetingText
run writeGreetingCall
ignoreOk writeGreetingCall Void
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
```

Short aliases such as `math.subI64`, `math.mulI64`, `math.divI64`, `math.eqI64`,
and `math.ltI64` are normalized to canonical targets.

`math.checkedMultiplyI64` returns a product plus an overflow predicate
internally. Handle it like a fallible call:

```semanticscript
call multiplyCall math.checkedMultiplyI64
arg multiplyCall left leftValue
arg multiplyCall right rightValue
run multiplyCall
bindOk productValue I64 multiplyCall
bindError multiplyOverflow ArithmeticError multiplyCall
branchIfError multiplyCall overflowLabel
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
math.convertSignedInt64ToFloat64
math.convertFloat64ToSignedInt64
```

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

## Domain Methods

A target of the shape `TypeName.methodName` can lower to a primitive operation
when `TypeName` aliases an integer or floating type.

```semanticscript
type CountdownValue I64

call decrementCall CountdownValue.subtractPositiveStep
arg decrementCall left currentCountdownValue
arg decrementCall right decrementStep
run decrementCall
bind nextCountdownValue CountdownValue decrementCall
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
arg helperCall text outputText
run helperCall
bindError helperError ConsoleWriteError helperCall
branchIfError helperCall helperFailed
```

The argument names in `arg` lines must match the callee's input names for
maintainable source. The current compiler dispatches by callee input order.

## C Standard Library

`c.<function>` routes through `SemanticScript/compiler/libc_registry.py`.

```semanticscript
const byteCount CByteCount 64
call allocateBufferCall c.malloc
arg allocateBufferCall size byteCount
run allocateBufferCall
bind allocatedBuffer COpaqueMemoryAddress allocateBufferCall
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

