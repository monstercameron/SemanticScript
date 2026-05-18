# Types and Values

Types in SemanticScript are names with runtime lowering rules and semantic role
information. The compiler accepts aliases, primitive scalar types, C ABI role
types, pointer-shaped types, records, enums, and metadata-rich refined type
declarations.

## Type Aliases

```semanticscript
type ExitCode I32
type AccountId CNullTerminatedByteString
type AccountLookupResult Result AccountBalance AccountLookupError
```

`semsc.py` stores the full tail of a `type` declaration. Single-token aliases
resolve to the underlying type; parameterized aliases preserve their head and
parameters for tools.

## Primitive Lowering

| SemanticScript type names | LLVM shape |
|---|---|
| `Bool` | `i1` |
| `I8`, `CSignedByte`, `CUnsignedByte` | `i8` |
| `I16`, `CSignedInt16`, `CUnsignedInt16` | `i16` |
| `I32`, `ExitCode`, `CSignedInt32`, `CUnsignedInt32` | `i32` |
| `I64`, `CSignedInt64`, `CUnsignedInt64` | `i64` |
| `F32`, `CFloat32` | `float` |
| `F64`, `CFloat64` | `double` |
| `String`, `CNullTerminatedByteString` | `i8*` |
| `COpaqueMemoryAddress`, `CFileHandle`, `VoidPtr` | `i8*` |
| `Void`, `CVoid` | `void` where accepted |

C role types keep ABI intent visible at the call site:

```semanticscript
const bufferByteCount CByteCount 4096
const fileOffset CFileByteOffset 0
const monotonicDelay DurationMilliseconds 50
```

## Constants

```semanticscript
const retryLimit I64 3
const newlineText String "\n"
const useStrictJson Bool true
```

`const` can appear at top level or inside an operation. Operation-local consts
take precedence over module consts in that operation.

Boolean tokens accepted for `Bool` values:

```text
true false yes no 1 0
```

## Domain Literals

Domain literals are typed constants with additional metadata edges.

```semanticscript
domainLiteral signalKillNumber CSignedInt32 9
domainLiteralSource signalKillNumber posix.SIGKILL
domainLiteralTrust signalKillNumber trustedStaticLiteral
```

The compiler registers `domainLiteral NAME TYPE VALUE` as a module-scope const.
The metadata lines are preserved for tooling.

## External Literals

Large literals can be declared separately from their bytes:

```semanticscript
literal greetingTemplate CNullTerminatedByteString
literalSource greetingTemplate "fixtures/greeting.txt"
literalBytes greetingTemplate 128
literalDigest greetingTemplate sha256 e3b0c44298fc1c149afbf4c8996fb924
literalPreview greetingTemplate "Hello, ..."
literalTrust greetingTemplate trustedStaticLiteral
```

Between parse and codegen, `_load_external_literals` reads `literalSource`
paths. Resolution order is absolute path first, then relative to the source
file. If the file cannot be read, the literal remains a stub so the source can
still compile.

## Enums

```semanticscript
enum TaskPriority repr I32
enumCase TaskPriority TaskPriorityLow 0
enumCase TaskPriority TaskPriorityNormal 1
enumCase TaskPriority TaskPriorityHigh 2
```

Enums are parsed into the AST for tooling and linter checks. Current lowering
primarily treats enum values as named metadata unless they are also represented
through constants.

## Records

```semanticscript
record AccountBalanceResponse
recordLayout AccountBalanceResponse packed
recordAlign AccountBalanceResponse 8
field AccountBalanceResponse accountId AccountId
field AccountBalanceResponse balanceCents I64
field AccountBalanceResponse currencyCode String
```

The current compiler can parse record schemas and supports record field access
patterns used by feature tests. See
[records-codecs-boundaries.md](records-codecs-boundaries.md) for construction
and codec metadata.

## Type Metadata

Type metadata is source-level context for checkers and future runtimes:

```semanticscript
typeInvariant AccountId "Non-empty stable account identifier"
typeRepresentation AccountId CNullTerminatedByteString utf8 nullByte
typeTrust AccountId trustedInternal
typeMemory AccountId inline
typeLayout AccountId packed
typeParameter AccountLookupResult 0 AccountBalance
typeLiteralEncoding AccountId utf8
typeLiteralTerminator AccountId nullByte
```

Only some of this metadata affects current codegen. It should still be kept
accurate because linters, hovers, and downstream tooling use it as hard context.

