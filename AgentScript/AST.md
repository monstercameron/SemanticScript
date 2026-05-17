# AgentScript syntax tree (refined)

## 12. The `c.*` standard library surface

The compiler exposes the C90/C99/C11 standard library through call targets
of the form `c.<funcName>`. The signature registry lives in
`compiler/libc_registry.py` and covers **466 function declarations across
15 hosted headers**: `<stdio.h>` (46), `<stdlib.h>` (46), `<string.h>` (33),
`<math.h>` (171, including the full `f`/`l` suffixed variants),
`<ctype.h>` (14), `<time.h>` (10), `<setjmp.h>` (2), `<signal.h>` (2),
`<locale.h>` (2), `<wchar.h>` (62), `<wctype.h>` (5), `<fenv.h>` (11),
`<complex.h>` (33), `<uchar.h>` (4), `<threads.h>` (25).

Headers and library facilities NOT in the registry (and the reason):

- `<assert.h>`, `<errno.h>`, `<stdarg.h>`, `<stdbool.h>`, `<stddef.h>`,
  `<stdint.h>`, `<stdalign.h>`, `<stdnoreturn.h>`, `<limits.h>`,
  `<float.h>`, `<iso646.h>`, `<inttypes.h>`, `<tgmath.h>`, `<stdatomic.h>`
  — macro-only or type-only headers. They don't bring callable
  externs into a program. AgentScript's equivalents are exposed via
  the type universe (`CSignedInt32`, `CByteCount`, `CMaxSignedInt`, …),
  `errno` is reachable via `c.errnoGet`, and `<stdarg.h>` is implicit at
  the call site for variadic libc functions.
- `<math.h>` macro classifiers (`isnan`, `isinf`, `isfinite`, `isnormal`,
  `signbit`, `fpclassify`) — these are C macros, not externs. AgentScript
  lowers them inline to native LLVM FP comparisons (see §16 below) so
  they remain reachable as `c.<name>` calls without a link dependency.

Each `c.*` call lowers directly to an LLVM `call` against an external
function declaration; there is no AgentScript-side wrapper, so the cost
matches a native C call to the same libc function. Math functions carry
`nounwind readnone` attributes (matching clang's `-fno-math-errno`), and
string-read functions carry `nounwind readonly`, so the LLVM optimizer
can hoist them out of loops the same way it does for C source.

The spec-compliant C-aligned type universe (each name carries signedness,
width, ABI role, or encoding contract per spec §6 + §10):

```
CSignedByte / CUnsignedByte                                            i8
CSignedInt16 / CUnsignedInt16                                          i16
CSignedInt32 / CUnsignedInt32 / ExitCode                               i32
CSignedInt64 / CUnsignedInt64                                          i64
CByteCount / CSignedByteCount                  (size_t / ssize_t)      i64
CAddressOffset                                  (ptrdiff_t)            i64
CUnixSecondsSinceEpoch                          (time_t)                i64
CCpuClockTicks                                  (clock_t)               i64
CFileByteOffset                                 (off_t)                 i64
CMaxSignedInt / CMaxUnsignedInt                 (intmax_t / uintmax_t)  i64
CFloat32                                                                f32
CFloat64                                                                f64
CNullTerminatedByteString                       (char *)                i8*
COpaqueMemoryAddress                            (void *)                i8*
CFileHandle                                     (FILE *)                i8*
CDecomposedTimeAddress                          (struct tm *)           i8*
CSetjmpRegisterBuffer                           (jmp_buf)               i8*
Void / CVoid                                                            void
```

Legacy short aliases (`CInt`, `CDouble`, `CSize`, `CString`, `CVoidPtr`,
`CFilePtr`, `CTm`, `CJmpBuf`, `CChar`, `CLong`, `CLongLong`, `CClock`,
`CTime`, `COff`, `CIntmax`, `CUintmax`, `CPtrdiff`, `CSsize`, `CShort`,
`CUshort`, `CSchar`, `CUchar`, `CByte`, `CUint`, `CFloat`) are still
accepted by `llvm_type_for` for backward compatibility, but new code
should use the spec-compliant names above so each declaration carries
its role at the site where it is read.

Example:

```
const helloFormatText CNullTerminatedByteString "Hello from c.printf! arg=%d\n"
const greetingArgument CSignedInt32 42

call helloPrintfCall c.printf
arg helloPrintfCall format helloFormatText
arg helloPrintfCall value greetingArgument
run helloPrintfCall
bindOk bytesWrittenByPrintf CSignedInt32 helloPrintfCall
```

## 13. Pointer primitives

Two minimum-viable pointer-arithmetic operations let AS programs observe
buffers returned by `c.malloc` / `c.memset` / etc. without escaping into
inline C:

```
call X pointer.loadByte
arg X buffer  someCOpaqueMemoryAddress
arg X offset  someI64
run X
bind result CSignedByte X

call X pointer.storeByte
arg X buffer  someCOpaqueMemoryAddress
arg X offset  someI64
arg X value   someCSignedByte
run X
```

These lower to `getelementptr inbounds` + `load i8` / `store i8`.

## 14. Floating-point arithmetic

```
math.addF64 / math.subtractF64 / math.multiplyF64 / math.divideF64
math.equalF64 / math.notEqualF64 / math.lessThanF64 / math.lessThanOrEqualF64
math.greaterThanF64 / math.greaterThanOrEqualF64
```

Lower to `fadd` / `fsub` / `fmul` / `fdiv` / `fcmp` respectively. Domain
type methods on `CFloat64.*` (or the legacy `CDouble.*`) lower through
`_DOMAIN_METHOD_TO_F64_PRIMITIVE`.

## 15. AOT compilation

`ascc.py --emit-exe path/to/out.exe` invokes clang on the post-codegen
LLVM IR with `-O<opt-level>` to produce a standalone native executable.
The runtime depends only on libc, so the same toolchain that builds C
links AS. Set `ASCC_CLANG` to override the clang location.

The performance harness at `bench/run_benchmarks.py` runs four
benchmarks at clang -O2 and reports the AS/C ratio. Results on the
reference machine (Windows, clang 22.1.4):

```
benchmark        C median   AS median   AS/C ratio   AS as % of C
arith                  44          44        1.000          100.0%
memset                179         180        1.006           99.4%
math                   39          39        1.000          100.0%
strlen                  0           0          inf       TOO FAST
```

`arith` is a Fibonacci-style data-dependency chain (200M iterations)
that the optimizer cannot fold to closed form. `memset` does 200K
writes to a 64 KiB buffer with `pointer.loadByte` observation. `math`
runs 5M sqrt+log+sin iterations into a CFloat64 accumulator. `strlen`
gets optimized to closed form by both languages because the input is
loop-invariant — TOO FAST is the correct verdict (equal performance,
both sub-millisecond).

## 16. Math classifier lowering

The C macros `isnan`, `isinf`, `isfinite`, `isnormal`, `signbit`, and
`fpclassify` are intercepted in the `c.*` dispatcher and lowered
directly to LLVM IR instead of routing through libc externs (most
platforms expose them as macros only, so a `c.isnan` extern call would
link-fail). The lowering:

```
c.isnan(x)        ->  fcmp uno x, x          (NaN compares unordered against itself)
c.isinf(x)        ->  fabs(x) ==  +inf
c.isfinite(x)     ->  fabs(x) <   +inf       (NaN < anything is false, so excluded)
c.isnormal(x)     ->  fabs(x) <   +inf  AND  fabs(x) >= DBL_MIN
c.signbit(x)      ->  bitcast(x, i64) lshr 63
c.fpclassify(x)   ->  chained selects returning MSVC FP_NAN/FP_INFINITE/
                       FP_ZERO/FP_SUBNORMAL/FP_NORMAL values
```

---



## 10. The `mode` declaration (closed set)

```
mode NAME
```

A top-level program may declare one or more `mode` values. The set is
closed; the parser rejects unknown values so a typo cannot quietly disable
a trust-boundary marker. Currently recognized:

- `capturedOutputReplay` — the program's stdout is a transcript captured
  from a sibling implementation (typically a Node.js benchmark) rather
  than the output of a re-run algorithm in AgentScript. This is the
  spec §2 law 19 trust-boundary marker for files whose algorithm cannot
  yet be expressed in the language. The linter relaxes
  `failureLabelAggregation` and `duplicatedDomainLiteral` for these
  files, because their consts are positional transcript rows whose role
  identity is the position, not the value.

## 11. User-defined operation calls

```
call CALL_NAME OPERATION_NAME
arg  CALL_NAME PARAM_NAME VALUE_NAME
run  CALL_NAME
bindOk      VALUE_NAME TYPE CALL_NAME      (when the op returns Result A B)
bindError   ERR_NAME ERR_TYPE CALL_NAME    (likewise)
branchIfError CALL_NAME LABEL              (or use the success-only `bind`)
```

A `call X opName` where `opName` matches a user-defined `operation` in the
same program lowers to an LLVM function call. The parameter list is derived
from the op's `input` lines, with opaque-dependency symbols (`console`,
`process`, `environment`, `httpRequest`, `databaseClient`, `clock`) filtered
out; those are documentation-only at the ABI boundary. The caller's `arg`
line names map to the operation's declared parameter names.

The return type is derived from the op's `output` line. `output OP Result A B`
returns the success payload type `A`; `output OP A` returns `A`; `Void` falls
back to an `i32` zero sentinel because LLVM still needs a concrete return slot
for the current ABI. `returnOk`, `returnError`, and `returnValue` are coerced
to that LLVM return type when possible. `branchIfError` uses the call's
recorded error predicate: integer returns compare `!= 0`, pointer returns
compare `!= null`, and float returns compare `!= 0.0`.

The canonical example is the `writeStandardOutputLine` helper used by the
captured-output-replay programs:

```
operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
purpose writeStandardOutputLine "Emit one newline-terminated text line to standard output via console.writeLine and surface a typed ConsoleWriteError on driver failure"

label startWriteStandardOutputLine
call writeStandardOutputLineConsoleWriteCall console.writeLine
arg writeStandardOutputLineConsoleWriteCall console console
arg writeStandardOutputLineConsoleWriteCall text text
run writeStandardOutputLineConsoleWriteCall
ignoreOk writeStandardOutputLineConsoleWriteCall Void
bindError writeStandardOutputLineConsoleWriteError ConsoleWriteError writeStandardOutputLineConsoleWriteCall
branchIfError writeStandardOutputLineConsoleWriteCall writeStandardOutputLineConsoleWriteFailed

const writeStandardOutputLineSuccessSentinel ExitCode 0
returnOk writeStandardOutputLineSuccessSentinel

label writeStandardOutputLineConsoleWriteFailed
returnError writeStandardOutputLineConsoleWriteError
```

Callers then write 5 lines per emit instead of 7:

```
call writeXLineCall writeStandardOutputLine
arg writeXLineCall text xLineText
run writeXLineCall
bindError writeXLineError ConsoleWriteError writeXLineCall
branchIfError writeXLineCall consoleWriteFailed
```

This is the spec §3 abstraction-admission-test pattern: the helper
declares purpose / effect / invariant / guarantee so the abstraction
carries more contract than the lines it replaces.

---



This document is the authoritative description of the AgentScript abstract
syntax tree as implemented by `compiler/ascc.py`. The tree is intentionally
flat: AgentScript source is a *line tape* (per spec §4), so the AST is mostly
a list of records, not a nested expression tree.

This revision incorporates the feedback that the prior version was too
IR-flavoured. Specifically:

- error types are first-class (`error` + `errorCase` + `makeError`) so the
  output contract `Result A B` is actually enforced
- `goto` is replaced by `branch` everywhere
- `branchIf` takes exactly one target label; the false leg falls through
- infallible calls use `bind`; fallible calls use `bindOk` + `bindError`
- names spend tokens to preserve local meaning
- math/console call targets use full English (`math.subtractI64`,
  `console.writeIntegerLine`, etc.)
- the `console` (and `process`, `environment`) dependency must be passed
  explicitly to any call that uses it

## 1. Lexical model

A source file is a sequence of physical lines. Each line is one of:

```
declaration line   declares a top-level entity (project, type, error, …)
context line       attaches typed metadata to an entity (effect, memory, …)
action line        performs work inside an operation (call, run, bind, …)
control line       moves the program counter (label, branch, branchIf*, return*)
comment line       starts with '#'; carries semantic context (rationale, …)
```

A line is tokenized by whitespace, with `"..."` string literals honored. The
first token is the **verb**; the remaining tokens are typed positional
arguments. There are no infix operators, no parentheses, no commas, no
nesting (spec §5).

## 2. Top-level AST

```
Program
├── projectName            : string
├── targets                : list<string>
├── runtime                : (name, version) | None
├── entry                  : (mode, opName) | None
├── imports                : list<(modulePath, alias)>          -- `importModule … as …`
├── dependencies           : list<Dependency>                    -- `dependency*` family
├── modules                : list<Module>
├── typeAliases            : map<AliasName, UnderlyingType>     -- `type ALIAS UNDERLYING`
├── typeMetadata           : map<TypeName, {invariant, trust, memory, layout, representation}>
├── errors                 : map<ErrorTypeName, list<ErrorCase>> -- `error` + `errorCase`
├── consts                 : map<ConstName, Const>
├── records                : map<RecordName, Record>            -- `record` + `field`
├── enums                  : map<EnumName, Enum>                -- `enum` + `enumCase`
├── codecs                 : map<CodecName, CodecMeta>          -- `codec`/`jsonCodec`/`schema`/…
├── validators             : map<ValidatorName, ValidatorMeta>  -- `validator` + `guarantee`
├── policies               : map<PolicyName, PolicyMeta>        -- `policy`/`retryPolicy`/`errorPolicy`/`timeoutBudget`
├── resources              : map<ResourceName, ResourceMeta>    -- `resource` + `resourceKey`/`resourceValue`/`resourceKind`
├── capabilities           : map<CapName, {effect, access}>     -- `capability NAME EFFECT_PATH ACCESS`
├── operations             : map<OpName, Operation>
├── webServers             : map<ServerName, WebServer>          -- `webServer`+`serverHost`+`serverPort`+`route`
├── hardMetadata           : map<TargetName, {guarantee, failure, security, timing, observability, authority, …}>
└── testCovers             : list<(testName, targetName)>
```

### 2.1 TypeAlias

```
type ALIAS UNDERLYING [extra-tokens]

TypeAlias
├── alias                  : PascalCase
└── underlying             : PascalCase | TypeName
```

Used for context: `type CountdownValue I64` lets every const/var/bind that
holds a countdown value advertise its role at the type level.

### 2.2 ErrorType

```
error NAME
errorCase NAME VARIANT_NAME [UNDERLYING_CAUSE_TYPE]

ErrorType
├── name                   : PascalCase
└── cases                  : list<ErrorCase>

ErrorCase
├── variantName            : PascalCase
└── causeType              : PascalCase | None
```

The runtime encodes an error value as a small integer drawn from the variant
index (1-based) within its declaring error type. This is the value emitted
by `makeError` and consumed by `returnError`.

### 2.3 Dependency, Module, Record, WebServer

Same shape as the prior revision; the implementation parses them but does
not yet emit code for them. See spec §15, §17.

### 2.4 Const

```
const NAME TYPE VALUE

Const
├── name                   : camelCase
├── type                   : TypeName | alias
└── value                  : str | int
```

### 2.5 Operation

```
Operation
├── name                   : camelCase
├── inputs                 : list<(paramName, ParamType)>
├── output                 : TypeName | TypeExpr (e.g. "Result ExitCode MainError")
├── effects                : list<Effect>
├── memory                 : list<MemoryPolicy>     -- e.g. "stack max 16KiB"
├── async                  : "yes" | "no"
├── purpose                : string
├── invariants             : list<string>
├── warnings               : list<string>
└── body                   : list<Statement>
```

### 2.6 WebServer

```
WebServer
├── name                   : camelCase
├── host                   : string
├── port                   : int
├── routes                 : list<(method, path, handlerOp)>
├── middleware             : list<(routeName, middlewareOp)>
└── timeouts               : map<routeName, DurationSymbol>
```

### 2.7 Record / Field

```
Record
├── name                   : PascalCase
├── layout                 : "row" | "column" | "packed" | None
├── align                  : int | None
└── fields                 : list<(fieldName, fieldType)>
```

### 2.8 Enum / EnumCase

```
Enum
├── name                   : PascalCase
├── repr                   : underlying repr type | None
└── cases                  : list<(caseName, value | None)>
```

### 2.9 Codec / Validator / Policy / Resource

These are contract-heavy semantic nodes (spec §3.4). The parser stores
them as `{kind, attrs}` records keyed by name; their `guarantee`,
`schema`, `unknownFields`, `purpose`, etc. metadata are recorded in
`hardMetadata[name]` for tooling lookup.

```
codec NAME
jsonCodec NAME strict yes|no unknownFields reject|keep|ignore
schema CODEC_NAME RECORD_NAME
unknownFields CODEC_NAME reject|keep|ignore
validator NAME
mapper NAME
adapter NAME
boundary NAME
policy NAME …
retryPolicy NAME maxAttempts N initialDelay D maximumDelay D jitter yes|no
errorPolicy NAME …
timeoutBudget NAME DURATION
resource NAME kind KIND
resourceKey NAME TYPE
resourceValue NAME TYPE
```

### 2.10 Capability

```
capability NAME EFFECT_PATH ACCESS              -- e.g. capability stdoutWrite console.stdout write
useCapability OPERATION_OR_BODY CAPABILITY_NAME -- attaches a granted capability to a use site
authority OPERATION EFFECT_PATH ACCESS          -- inline authority declaration (top-level)
```

### 2.11 Type metadata

```
typeInvariant     TYPE "free text"        -- multi-valued
typeRepresentation TYPE UNDERLYING ARGS…  -- e.g. typeRepresentation EmailAddress SmallString 254
typeTrust         TYPE untrusted|trusted|sanitized|internal|public
typeMemory        TYPE inline|heap|arena
typeLayout        TYPE row|column|packed
```

### 2.12 Hard metadata at top level OR in an operation body

```
purpose       NAME "text"
invariant     NAME "text"
warning       NAME "text"
guarantee     NAME "text"
failure       NAME FAILURE_NAME "text"
security      NAME "text"
timing        NAME "text"
observability NAME "text"
testCovers    TEST_NAME TARGET_NAME    -- top-level only
```

`purpose`/`invariant`/`warning` are the established header verbs from V0.
`guarantee`/`failure`/`security`/`timing`/`observability` are the
additional hard-metadata verbs the spec calls for (spec §3.2 list of
contextual metadata kinds). They may attach to an operation, a codec, a
validator, a policy, etc.

## 3. Statement (body line) variants

Every executable line is one `Statement`. The discriminant is the verb. All
`Statement` nodes are flat — they carry only token-level arguments, never
nested expressions. Each statement records its source line for diagnostics.

### 3.1 Declaration-in-body statements

```
ConstStmt           const NAME TYPE VALUE
VarStmt             var NAME TYPE INITIAL_VALUE
LabelStmt           label NAME
```

### 3.2 Call lifecycle statements (spec §10)

```
CallStmt            call CALL_NAME TARGET_PATH
ArgStmt             arg CALL_NAME ARG_NAME VALUE_NAME
TimeoutStmt         timeout CALL_NAME DURATION_VALUE
CancelOnStmt        cancelOn CALL_NAME CANCELLATION_TOKEN
RunStmt             run CALL_NAME
StartStmt           start CALL_NAME        (parsed; lowered to a no-op when async)
AwaitStmt           await CALL_NAME        (parsed; in synchronous mode awaits the start)
```

### 3.3 Binding statements (spec §10, §12)

```
BindStmt            bind VALUE_NAME TYPE CALL_NAME       # infallible
BindOkStmt          bindOk VALUE_NAME TYPE CALL_NAME     # success leg
BindErrorStmt       bindError ERROR_NAME ERROR_TYPE CALL_NAME
IgnoreOkStmt        ignoreOk CALL_NAME TYPE              # explicitly discard success
```

**Rule:** if a call has a `bindError` line, it must also have a
`branchIfError` (linter law, spec §17). If a call is declared infallible
(none of the `math.*` arithmetic/comparison targets fail), it uses plain
`bind` and never `bindOk`/`bindError`.

`ignoreOk` exists so that a fallible call whose success value is `Void`
(e.g. `console.writeLine`) does not silently drop its success leg. The line
attests that the success result is intentionally not bound — this makes
"hidden behavior is illegal by default" (spec §2) hold for the discard
case, while keeping `bindError` + `branchIfError` mandatory for the
failure leg.

### 3.4 Error construction

```
MakeErrorStmt       makeError NAME ERRTYPE.VARIANT [SOURCE_VALUE]
```

### 3.4b Structured concurrency (parsed, reserved by codegen)

```
TaskGroupStmt           taskGroup NAME [maxTasks N] [cancelOnFirstError yes|no]
StartInGroupStmt        startInGroup CALL_NAME GROUP_NAME
AwaitGroupStmt          awaitGroup GROUP_NAME
BindGroupErrorStmt      bindGroupError ERROR_NAME ERROR_TYPE GROUP_NAME
BranchIfGroupErrorStmt  branchIfGroupError GROUP_NAME LABEL
```

### 3.4c Cleanup / defer (parsed, reserved by codegen)

```
DeferStmt           defer NAME TARGET_PATH ARGS…
DeferLogStmt        deferLog NAME TARGET_PATH ARGS…
DeferAwaitLogStmt   deferAwaitLog NAME TARGET_PATH ARGS…
DeferWhenExitLog    deferWhenExitLog NAME GUARD_VAR TARGET_PATH ARGS…
```

### 3.4d Record I/O (parsed, reserved by codegen)

```
NewStmt             new VALUE_NAME RECORD_NAME
FieldGetStmt        fieldGet OUT_NAME TYPE RECORD_VALUE FIELD_NAME
FieldSetStmt        fieldSet RECORD_VALUE FIELD_NAME VALUE_NAME
```

### 3.4e Channels, locks, select (parsed, reserved by codegen)

```
SendStmt            send CHANNEL_NAME VALUE
ReceiveStmt         receive OUT_NAME TYPE CHANNEL_NAME
BranchClosedStmt    branchIfChannelClosed CHANNEL_NAME LABEL
LockStmt            lock MUTEX_NAME
UnlockStmt          unlock MUTEX_NAME
SelectStmt          select NAME
SelectCaseStmt      selectCase NAME CALL_OR_TOKEN BRANCH_NAME
RunSelectStmt       runSelect NAME
BranchSelectedStmt  branchSelected NAME BRANCH_NAME LABEL
```

### 3.4f Policy attachment (parsed, reserved by codegen)

```
UseRetryStmt        useRetry CALL_NAME RETRY_POLICY_NAME
UseCapabilityStmt   useCapability OPERATION_OR_CALL CAPABILITY_NAME
```

Creates a typed error value of type `ERRTYPE`. The optional `SOURCE_VALUE`
is the underlying error that caused the failure; the runtime carries it for
tooling but the wire representation is just the variant index.

### 3.5 Mutation

```
SetStmt             set VAR_NAME VALUE_NAME
```

### 3.6 Control flow (spec §9, §12) — refined

```
BranchStmt          branch LABEL_NAME                   # unconditional
BranchIfStmt        branchIf BOOL_VALUE LABEL_NAME      # jump if true, fall through if false
BranchIfErrorStmt   branchIfError CALL_NAME LABEL_NAME
ReturnOkStmt        returnOk VALUE_NAME
ReturnErrorStmt     returnError VALUE_NAME
ReturnValueStmt     returnValue VALUE_NAME
```

The single-target `branchIf` plus an immediately-following `branch` line is
preferred over the legacy two-target form, because each line then does
exactly one semantic thing (spec §4). The two-target form is still accepted
by the parser for legacy programs.

### 3.7 Metadata statements

`purpose`, `invariant`, `warning`, and `# rationale:` comments are also AST
nodes — they attach to the most recent operation/group rather than emitting
code. Tooling (per spec §7) preserves them; codegen ignores them.

## 4. Call-target whitelist

### 4.1 Primitive targets

```
console.writeLine            -> puts(text:i8*)                     returns i32
console.writeIntegerLine     -> printf("%lld\n", value:i64)        returns i32

math.addI64                  -> i64 (left + right)
math.subtractI64             -> i64 (left - right)        # alias: math.subI64
math.multiplyI64             -> i64 (left * right)        # alias: math.mulI64
math.divideI64               -> i64 (left sdiv right)     # alias: math.divI64
math.moduloI64               -> i64 (left srem right)     # alias: math.modI64

math.equalI64                -> i1                        # alias: math.eqI64
math.notEqualI64             -> i1                        # alias: math.neI64
math.lessThanI64             -> i1                        # alias: math.ltI64
math.lessThanOrEqualI64      -> i1                        # alias: math.leI64
math.greaterThanI64          -> i1                        # alias: math.gtI64
math.greaterThanOrEqualI64   -> i1                        # alias: math.geI64
math.intToFloat              -> f64 (signed i64 to double)
math.floatToInt              -> i64 (double to signed i64, round toward zero)
```

`console.writeLine` and `console.writeIntegerLine` are *line-emitting* calls
(they write a single line terminated by `\n`). They accept `console` as a
named argument; the compiler treats it as an opaque-dependency token —
required for the source to carry the dependency context, but not consumed by
codegen.

`math.*` calls are infallible (within the integer domain we support) and so
should use `bind`, not `bindOk`/`bindError`. The compiler does not enforce
this rule, but linters in tooling layer would (spec §17).

### 4.2 Domain-typed methods

A call target of the form `TypeName.methodName` lowers to a primitive
target based on the alias's underlying type. The recognized methods are:

Infallible (use plain `bind`):
```
add, addPositiveStep,
subtract, subtractStep, subtractPositiveStep,
multiply, multiplyByStep, multiplyByCounter,
divide, modulo, moduloBy,
equal, notEqual,
lessThan, lessThanOrEqual, greaterThan, greaterThanOrEqual,
square
```

Fallible (use `bindOk` + `bindError` + `branchIfError`):
```
checkedMultiply, checkedMultiplyByCounter, checkedMultiplyByStep
```

If `TypeName` resolves to underlying type `I64`, the infallible methods
lower to the matching `math.*I64` primitive, and the fallible methods
lower to `math.checkedMultiplyI64`, which is implemented via the
`llvm.smul.with.overflow.i64` intrinsic. The intrinsic returns a struct
`{i64, i1}` — element 0 is the product (bound by `bindOk`), element 1 is
the overflow flag (used as the `branchIfError` condition and bound by
`bindError`).

The point of the domain-typed forms is context: the source line
`FactorialAccumulator.checkedMultiplyByCounter` reads as a domain operation
that can overflow, not as raw integer multiplication, even though the
emitted IR is the same intrinsic call any other checked-multiply would
lower to.

Operand arguments may be named anything reasonable (`left`/`right`,
`a`/`b`, `value`/`step`, `counter`/`divisor`, `accumulator`/`counter`, …).
The dispatcher pulls the first two non-opaque-dependency args by
insertion order, so a call site is free to name its operands by their
domain role.

## 5. Type universe (codegen subset)

```
I64, DurationMilliseconds, MonotonicMilliseconds, UtcMilliseconds   64-bit int
I32, ExitCode                                                       32-bit int
Bool                                                                i1
F64, CFloat64, CDouble                                              f64
String                                                              null-terminated UTF-8 (i8*)
COpaqueMemoryAddress, CNullTerminatedByteString                     i8*
CSignedByte / CUnsignedByte                                         i8
CSignedInt16 / CUnsignedInt16                                       i16
CSignedInt32 / CUnsignedInt32                                       i32
CSignedInt64 / CUnsignedInt64 / CByteCount / CAddressOffset         i64
```

User-declared `type` aliases follow the chain (`type CountdownValue I64`,
`type CountdownStep I64`, etc.). Aliases are resolved transitively before
codegen, so the underlying LLVM type is one of the primitives above or one
of the C-aligned aliases listed in section 12.

Opaque PascalCase types used only in headers and dependency declarations
(`Console`, `Process`, `Environment`, `HttpRequest`, `DatabaseClient`,
`Clock`, …) are accepted at parse time and treated as opaque tokens. They
exist for documentation, agent context, and future static analysis.

The opaque symbols `console`, `process`, `environment`, `httpRequest`,
`databaseClient`, `clock` are *implicit operation inputs*: they may appear
as values in `arg` lines but never as values that flow into computation.

## 6. Invariants the AST enforces

1. **One verb per line.** Multi-statement lines are a syntax error.
2. **Stable identity.** Every call/value/label has a unique camelCase symbol
   that is referenced by name from every related line (`run callName`,
   `bindOk … callName`, `branchIfError callName …`).
3. **Failure must be branched.** A `bindError` for a call without a matching
   `branchIfError` is a compile-time warning (linter law, spec §17).
4. **Success must be explicit.** A fallible call whose success value is
   ignored must use `ignoreOk CALL_NAME TYPE`. Silently dropping success is
   "hidden behavior" and disallowed.
5. **Error contract.** When an operation's `output` is `Result A B`, the
   `returnError` value must have type `B`. Use `makeError` to build a `B`
   from a raw dependency error.
6. **Labels are first-class.** Every `label NAME` corresponds to a basic
   block; control flow can only enter/leave via explicit `branch`,
   `branchIf`, `branchIfError`, `return*` verbs.
7. **Branching is single-target.** `branchIf cond label` jumps to `label`
   on true and falls through on false; pair it with a following `branch`
   line when an else target is needed.
8. **Domain literals belong in consts.** If a named const carries the
   semantic role of a value, the literal must not be repeated elsewhere
   (e.g. `var x T constName` rather than `var x T 5` when
   `const constName T 5` already exists). This is the
   `duplicatedDomainLiteral` linter check.

## 7. Mapping to LLVM IR

| AST node              | LLVM construct                                         |
|-----------------------|--------------------------------------------------------|
| Operation `main`      | `define i32 @main()`                                   |
| LabelStmt             | `BasicBlock`                                           |
| ConstStmt (String)    | Internal `[N x i8]` global + `getelementptr inbounds`  |
| ConstStmt (I64)       | LLVM `i64` constant                                    |
| VarStmt               | `alloca` in entry block, init via `store`              |
| SetStmt               | `store` to alloca                                      |
| CallStmt + RunStmt    | LLVM `call` to the resolved target function            |
| Bind / BindOk / BindError | SSA name bound to the call's return value         |
| MakeErrorStmt         | bind name to constant `i32` = (1-based variant index)  |
| Checked-multiply call | `llvm.smul.with.overflow.i64` → `extractvalue {i64,i1}, 0/1`; product is the call's `result`, overflow bit is its `error_cond` |
| BranchIfStmt          | `br i1 cond, true_bb, fallthrough_bb`                 |
| BranchIfErrorStmt     | conditional `br` using the call's recorded error predicate (`!= 0`, `!= null`, or `!= 0.0`) |
| BranchStmt            | unconditional `br`                                    |
| ReturnOk / ReturnError / ReturnValue | `ret <operation output LLVM type> value` |
| IgnoreOkStmt          | no instruction emitted (the call's SSA value already exists; the line just attests that no `bindOk` will consume it) |
| Domain method (`T.m`) | dispatched to underlying primitive (e.g. `math.subtractI64` for `CountdownValue.subtractPositiveStep`) |
| Reserved-soft verbs (`guarantee`, `failure`, `security`, `timing`, `observability`, `useCapability`, `importModule`) | stored in op.lines as metadata and skipped by codegen |
| Reserved-hard verbs (`taskGroup`, `defer*`, `send`/`receive`, `lock`/`unlock`, `select*`, `new`/`fieldGet`/`fieldSet`, `useRetry`) | parsed for inspection, but codegen raises `NotImplementedError` instead of silently dropping runtime behavior |

Each codegen row of this table is implemented in `compiler/ascc.py`. The
reserved rows are intentionally parser/tooling surface until their runtime
lowering exists.

## 8. Codegen vs. parse-only verb partition

The compiler distinguishes two kinds of body verbs:

- `BODY_VERBS_CODEGEN` — emits LLVM IR.
- `BODY_VERBS_RESERVED_SOFT` — parsed and recorded in the AST as pure
  metadata. Codegen skips these because they do not change runtime
  behavior.
- `BODY_VERBS_RESERVED_HARD` — parsed and recorded for `--parse-only`,
  linter, editor, and review tooling, but codegen raises
  `NotImplementedError` if a compiled program uses them. These verbs have
  runtime semantics in the spec, so silently dropping them would violate
  the hidden-behavior law.

This split is honest: the language surface is real, but the compiler
implementation is partial. A program can use hard-reserved verbs under
`--parse-only` to describe richer behavior (cleanup, concurrency,
channels, records) and still be inspectable by tooling. Normal compile
mode refuses those verbs until their runtime lowering exists.

## 9. Linter (agent-safety checks)

The compiler ships an `--lint` pass (mandatory under `--strict`) that
implements the spec's linter-class rules:

- `unbranchedFailure` — a call with a `bindError` but no matching
  `branchIfError` is flagged.
- `vagueCallName` — a call name that does not end with the `Call` role
  suffix is flagged (spec §6).
- `vagueErrorName` — an error binding that does not end with `Error`.
- `vagueFailureName` — a `makeError` target that does not end with
  `Failure`.
- `roleSuffixMismatch` — a failure-path label that does not end with
  `Failed` or a past-tense `-ed` form.

`--strict` escalates any warning to a non-zero exit, so CI can refuse
to ship programs that drift from the constitution.
