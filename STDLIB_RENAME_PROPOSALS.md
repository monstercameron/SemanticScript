# Standard Library Agent-Facing Rename Proposals

This document maps current `AgentScript/stdlib_as/*.as` operation signatures to proposed agent-facing names. It is a proposal document; no stdlib implementation was renamed in this pass.

The rename map covers one layer — the operation symbol — out of several the spec touches. Parameter names, output contracts, constant modeling, and domain-method dispatch are out of scope here and tracked under **Spec/AST gap review** below.

## Rules used for this pass

- Domain first: `string`, `memory`, `signal`, `errno`, `float64`, `signedInt64`, `ascii` leads the symbol so an attention-local read carries the type universe (spec §6, §27).
- Width, ownership, buffer, encoding, and side-effect context appear in the symbol when the old name hides them (constitutional law 2: repetition is acceptable when it preserves context).
- Operation names are verbs or verb phrases; the spec §6 role-suffix system (`Call`, `Error`, `Failed`, `Failure`, `Result`, `Option`, …) belongs to *value* names, not to operations.
- Keep raw C names only as `runtimeBinding` targets (AST §2.12.5 already defines the verb; AST §12 lists five real lowerings such as `runtime.cstring.byteLength`).
- Output types are preserved unchanged in this pass; their replacement is tracked under **Spec/AST gap review**.

## Naming collisions resolved by this pass

Today, `stdlib_as/*.as` are independent self-test projects (`assert.as` and `stdio.as` each declare their own `project Std*SelfTest`), so the in-source collisions below don't fire. Under the unified `standard.*` namespace that 1.0 needs, they would; the map separates them now:

- `putByte` in `assert.as` → `writeAssertionByteToStandardOutput`
- `putByte` in `stdio.as`  → `writeByteToStandardOutput`

No other duplicate proposed names.

## Spec/AST gap review

The rename map renames the operation symbol. Closing the gaps below is required before the renamed surface is a stable 1.0 public contract.

| Gap | Spec/AST anchor | What's actually missing |
|---|---|---|
| Parameter names violate the §6 vague-name law | spec §6; AST §9 `vagueCallName` / `vagueErrorName` linters | The map proposes `leftValue` / `rightValue` / `inputValue` / `targetValue` throughout. Spec §6 lists `value`, `result`, `data` as the canonical bad-name examples and the linter flags them. Parameters must carry domain meaning: `candidatePrime`, `byteToTest`, `dividendValue`, `divisorValue`. A second pass needs to rewrite ~290 rows. |
| Constants modeled as operations | AST §2.12.5 — `domainLiteral NAME TYPE VALUE` + `domainLiteralSource NAME ORIGIN` already exist | `piConstant() -> Result CFloat64 Void` is a workaround for missing module-scope const in `stdlib_as`. The verb that replaces it is already in the AST: `domainLiteral mathematicalPi CFloat64 3.14159…` + `domainLiteralSource mathematicalPi math.iso80000`. Renaming the operation freezes the workaround. |
| Predicates return `CSignedInt32` instead of `Bool` | AST §5 — `Bool` is i1 | The map preserves C-style int predicates (`isAsciiDigitCode`, `isSignedInt64Prime`, `cstringBeginsWithPrefix`). Spec/AST want `Bool`. Keep `CSignedInt32` only on the explicit C-compatibility layer. |
| `Result X Void` output shape on infallible operations | spec §11/§12; AST §3.3 — `bind` is for infallible calls | 283 of 290 proposed signatures return `Result X Void`. That's an infallible call wearing a fallible coat. Want plain output (`output stringByteLength CByteCount`) for infallible ops and real error domains for fallible ones. |
| Domain-method dispatch is ignored | AST §4.2 — `TypeName.methodName` lowers to primitives | Several renames belong on a type, not as free functions: `intSqrt(n)` → `SignedInt64.integerSquareRoot`; `fabsFloat` / `sqrtFloat` → `Float64.absolute` / `.squareRoot`; `strlen` → `CNullTerminatedByteString.byteLength`. The rename map locks in free-function form. |
| Memory ownership and capacity contracts | spec §2 boundary laws; spec §13 cleanup-next-to-acquisition | `copyCString(dest, src)` / `strcat(dest, src)` carry no capacity argument today; renaming preserves the unsafe shape. 1.0 surface needs `destinationCapacityBytes`, `byteCount`, and explicit overlap behavior. |
| Raw vs validated string types | spec §2 boundary-type examples (`RawSql` / `ParameterizedSql`, `RawHtml` / `SanitizedHtml`, …) | Most APIs accept `CNullTerminatedByteString` directly. Refined-syntax expects raw-to-validated trust transitions: `RawCStringPointer` → `validateCString` → `ValidatedText`. |
| Stable stdlib scope | spec §15, §27 | The list spans float approximations, random state, sorting, errno/signal extras, ISO646 helpers, and large constant catalogs. Tighten the 1.0 public set to: `bool`, `char`, `ctype`, `compare`, `convert`, `limits`, core integer `math`, `memory`, `stdio`, `stdlib` parsing/math, `string`, `time`, `process`. Mark the rest experimental. |
| Module namespace and dependency contracts | spec §15; AST §2 `imports` / `dependencies` | 1.0 needs paths like `standard.string.stringByteLength` plus full contract tapes per spec §15 (`dependencyFunctionInput`, `dependencyFunctionOutput`, `dependencyFunctionEffect`, `dependencyFunctionAsync`). |
| Whole-operation rename | spec §9 canonical operation structure | The map renames the operation symbol but not the surrounding `effect` / `memory` / `async` / `purpose` / `invariant` lines. Renamed parameters need matching effect references (e.g. `effect stringByteLength read sourceBuffer`). |
| Error and assertion API | spec §12; AST §3.4 `makeError` + `errorCase` | Assertions currently use raw `CSignedInt32` error payloads. Define `AssertionError` (typed variants) and use `Result Unit AssertionError`. The verbs already exist; stdlib_as just doesn't use them. |
| Lint and test enforcement | spec §17; AST §9 linter rules | Add checks: no public 1.0 name uses C abbreviations; no duplicate public names; all public predicates return `Bool`; all public memory APIs declare capacity and ownership; every `runtimeBinding` site has matching `runtimeBindingFailure`. |

Minimum-viable 1.0 stdlib: ship a smaller surface with all twelve gaps closed, rather than a broad surface with only the symbol layer renamed.

## `array.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `arraySumBytes(buf: CNullTerminatedByteString, count: CByteCount) -> Result CSignedInt64 Void` | `sumSignedByteValuesInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void` |
| `arrayMinByte(buf: CNullTerminatedByteString, count: CByteCount) -> Result CSignedInt64 Void` | `findMinimumSignedByteInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void` |
| `arrayMaxByte(buf: CNullTerminatedByteString, count: CByteCount) -> Result CSignedInt64 Void` | `findMaximumSignedByteInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void` |
| `arrayContainsByte(buf: CNullTerminatedByteString, count: CByteCount, value: CSignedInt32) -> Result CSignedInt32 Void` | `bufferContainsSignedByteValue(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount, targetValue: CSignedInt32) -> Result CSignedInt32 Void` |
| `arrayCountByte(buf: CNullTerminatedByteString, count: CByteCount, value: CSignedInt32) -> Result CSignedInt64 Void` | `countSignedByteValueInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount, targetValue: CSignedInt32) -> Result CSignedInt64 Void` |
| `arrayReverseInPlace(buf: COpaqueMemoryAddress, count: CByteCount) -> Result CByteCount Void` | `reverseBytesInBufferInPlace(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void` |

## `assert.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `putByte(c: CSignedInt32) -> Result CSignedInt32 Void` | `writeAssertionByteToStandardOutput(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `assertTrue(condition: CSignedInt64) -> Result CSignedInt32 CSignedInt32` | `requireConditionTrue(conditionValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32` |
| `assertEqual(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 CSignedInt32` | `requireSignedInt64ValuesEqual(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32` |
| `assertNotEqual(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 CSignedInt32` | `requireSignedInt64ValuesNotEqual(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32` |
| `assertGreaterThan(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 CSignedInt32` | `requireSignedInt64LeftGreaterThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32` |
| `assertLessThan(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 CSignedInt32` | `requireSignedInt64LeftLessThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32` |
| `assertInRange(x: CSignedInt64, lo: CSignedInt64, hi: CSignedInt64) -> Result CSignedInt32 CSignedInt32` | `requireSignedInt64ValueWithinInclusiveRange(inputValue: CSignedInt64, lowerBound: CSignedInt64, upperBound: CSignedInt64) -> Result CSignedInt32 CSignedInt32` |
| `assertNotNull(p: COpaqueMemoryAddress) -> Result CSignedInt32 CSignedInt32` | `requireOpaquePointerNotNull(pointerValue: COpaqueMemoryAddress) -> Result CSignedInt32 CSignedInt32` |

## `bit.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `bitShiftLeft(n: CSignedInt64, k: CSignedInt64) -> Result CSignedInt64 Void` | `shiftSignedInt64BitsLeft(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void` |
| `bitShiftRight(n: CSignedInt64, k: CSignedInt64) -> Result CSignedInt64 Void` | `shiftSignedInt64BitsRight(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void` |
| `testBit(n: CSignedInt64, k: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64BitSet(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt32 Void` |
| `setBit(n: CSignedInt64, k: CSignedInt64) -> Result CSignedInt64 Void` | `setSignedInt64Bit(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void` |
| `clearBit(n: CSignedInt64, k: CSignedInt64) -> Result CSignedInt64 Void` | `clearSignedInt64Bit(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void` |
| `flipBit(n: CSignedInt64, k: CSignedInt64) -> Result CSignedInt64 Void` | `toggleSignedInt64Bit(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void` |

## `bool.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `trueValue() -> Result CSignedInt32 Void` | `signedInt32BooleanTrueValue() -> Result CSignedInt32 Void` |
| `falseValue() -> Result CSignedInt32 Void` | `signedInt32BooleanFalseValue() -> Result CSignedInt32 Void` |
| `boolNot(x: CSignedInt32) -> Result CSignedInt32 Void` | `negateSignedInt32Boolean(inputValue: CSignedInt32) -> Result CSignedInt32 Void` |
| `boolAnd(a: CSignedInt32, b: CSignedInt32) -> Result CSignedInt32 Void` | `combineSignedInt32BooleansWithAnd(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void` |
| `boolOr(a: CSignedInt32, b: CSignedInt32) -> Result CSignedInt32 Void` | `combineSignedInt32BooleansWithOr(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void` |
| `boolXor(a: CSignedInt32, b: CSignedInt32) -> Result CSignedInt32 Void` | `combineSignedInt32BooleansWithExclusiveOr(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void` |
| `boolEquiv(a: CSignedInt32, b: CSignedInt32) -> Result CSignedInt32 Void` | `compareSignedInt32BooleansEquivalent(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void` |

## `char.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `nullChar() -> Result CSignedInt32 Void` | `asciiNullCharacterCode() -> Result CSignedInt32 Void` |
| `tabChar() -> Result CSignedInt32 Void` | `asciiHorizontalTabCharacterCode() -> Result CSignedInt32 Void` |
| `newlineChar() -> Result CSignedInt32 Void` | `asciiNewlineCharacterCode() -> Result CSignedInt32 Void` |
| `carriageReturnChar() -> Result CSignedInt32 Void` | `asciiCarriageReturnCharacterCode() -> Result CSignedInt32 Void` |
| `spaceChar() -> Result CSignedInt32 Void` | `asciiSpaceCharacterCode() -> Result CSignedInt32 Void` |
| `bellChar() -> Result CSignedInt32 Void` | `asciiBellCharacterCode() -> Result CSignedInt32 Void` |
| `backspaceChar() -> Result CSignedInt32 Void` | `asciiBackspaceCharacterCode() -> Result CSignedInt32 Void` |
| `escapeChar() -> Result CSignedInt32 Void` | `asciiEscapeCharacterCode() -> Result CSignedInt32 Void` |
| `deleteChar() -> Result CSignedInt32 Void` | `asciiDeleteCharacterCode() -> Result CSignedInt32 Void` |
| `doubleQuoteChar() -> Result CSignedInt32 Void` | `asciiDoubleQuoteCharacterCode() -> Result CSignedInt32 Void` |
| `singleQuoteChar() -> Result CSignedInt32 Void` | `asciiSingleQuoteCharacterCode() -> Result CSignedInt32 Void` |
| `backslashChar() -> Result CSignedInt32 Void` | `asciiBackslashCharacterCode() -> Result CSignedInt32 Void` |
| `periodChar() -> Result CSignedInt32 Void` | `asciiPeriodCharacterCode() -> Result CSignedInt32 Void` |
| `commaChar() -> Result CSignedInt32 Void` | `asciiCommaCharacterCode() -> Result CSignedInt32 Void` |
| `colonChar() -> Result CSignedInt32 Void` | `asciiColonCharacterCode() -> Result CSignedInt32 Void` |
| `semicolonChar() -> Result CSignedInt32 Void` | `asciiSemicolonCharacterCode() -> Result CSignedInt32 Void` |
| `slashChar() -> Result CSignedInt32 Void` | `asciiSlashCharacterCode() -> Result CSignedInt32 Void` |
| `asteriskChar() -> Result CSignedInt32 Void` | `asciiAsteriskCharacterCode() -> Result CSignedInt32 Void` |

## `compare.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `compareInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `compareSignedInt64Ordering(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isEqualInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `areSignedInt64ValuesEqual(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isLessInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64LeftLessThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isLessEqualInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64LeftLessThanOrEqualRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isGreaterInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64LeftGreaterThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isGreaterEqualInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64LeftGreaterThanOrEqualRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `compareFloat(a: CFloat64, b: CFloat64) -> Result CSignedInt32 Void` | `compareFloat64Ordering(leftValue: CFloat64, rightValue: CFloat64) -> Result CSignedInt32 Void` |
| `isCloseFloat(a: CFloat64, b: CFloat64, epsilon: CFloat64) -> Result CSignedInt32 Void` | `areFloat64ValuesWithinTolerance(leftValue: CFloat64, rightValue: CFloat64, tolerance: CFloat64) -> Result CSignedInt32 Void` |

## `constants.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `piConstant() -> Result CFloat64 Void` | `mathematicalPiFloat64() -> Result CFloat64 Void` |
| `twoPiConstant() -> Result CFloat64 Void` | `mathematicalTwoPiFloat64() -> Result CFloat64 Void` |
| `halfPiConstant() -> Result CFloat64 Void` | `mathematicalHalfPiFloat64() -> Result CFloat64 Void` |
| `quarterPiConstant() -> Result CFloat64 Void` | `mathematicalQuarterPiFloat64() -> Result CFloat64 Void` |
| `piSquaredConstant() -> Result CFloat64 Void` | `mathematicalPiSquaredFloat64() -> Result CFloat64 Void` |
| `eConstant() -> Result CFloat64 Void` | `mathematicalEulerNumberFloat64() -> Result CFloat64 Void` |
| `ln2Constant() -> Result CFloat64 Void` | `naturalLogOfTwoFloat64() -> Result CFloat64 Void` |
| `ln10Constant() -> Result CFloat64 Void` | `naturalLogOfTenFloat64() -> Result CFloat64 Void` |
| `log2EConstant() -> Result CFloat64 Void` | `logBaseTwoOfEulerNumberFloat64() -> Result CFloat64 Void` |
| `log10EConstant() -> Result CFloat64 Void` | `logBaseTenOfEulerNumberFloat64() -> Result CFloat64 Void` |
| `sqrtTwoConstant() -> Result CFloat64 Void` | `squareRootOfTwoFloat64() -> Result CFloat64 Void` |
| `sqrtHalfConstant() -> Result CFloat64 Void` | `squareRootOfOneHalfFloat64() -> Result CFloat64 Void` |
| `eulerMascheroniConstant() -> Result CFloat64 Void` | `eulerMascheroniFloat64() -> Result CFloat64 Void` |
| `goldenRatioConstant() -> Result CFloat64 Void` | `goldenRatioFloat64() -> Result CFloat64 Void` |
| `zeroFloatConstant() -> Result CFloat64 Void` | `zeroFloat64() -> Result CFloat64 Void` |
| `oneFloatConstant() -> Result CFloat64 Void` | `oneFloat64() -> Result CFloat64 Void` |
| `negativeOneFloatConstant() -> Result CFloat64 Void` | `negativeOneFloat64() -> Result CFloat64 Void` |

## `convert.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `int32ToInt64(n: CSignedInt32) -> Result CSignedInt64 Void` | `widenSignedInt32ToSignedInt64(inputValue: CSignedInt32) -> Result CSignedInt64 Void` |
| `int64ToInt32(n: CSignedInt64) -> Result CSignedInt32 Void` | `narrowSignedInt64ToSignedInt32(inputValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `byteToUnsignedInt(b: CSignedInt32) -> Result CSignedInt32 Void` | `convertByteValueToUnsignedInt32(signExtendedByteValue: CSignedInt32) -> Result CSignedInt32 Void` |
| `intToFloat(n: CSignedInt64) -> Result CFloat64 Void` | `convertSignedInt64ToFloat64(inputValue: CSignedInt64) -> Result CFloat64 Void` |
| `floatToInt(x: CFloat64) -> Result CSignedInt64 Void` | `convertFloat64ToSignedInt64(inputValue: CFloat64) -> Result CSignedInt64 Void` |
| `pointerToOffset(base: CNullTerminatedByteString, p: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `calculateCStringPointerOffset(baseValue: CNullTerminatedByteString, pointerValue: CNullTerminatedByteString) -> Result CSignedInt64 Void` |
| `pointerAdvance(base: COpaqueMemoryAddress, offset: CByteCount) -> Result COpaqueMemoryAddress Void` | `advanceOpaquePointerByByteOffset(baseValue: COpaqueMemoryAddress, byteOffset: CByteCount) -> Result COpaqueMemoryAddress Void` |

## `ctype.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `isdigit(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiDecimalDigitCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `islower(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiLowercaseLetterCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isupper(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiUppercaseLetterCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isalpha(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiLetterCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isalnum(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiLetterOrDigitCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isxdigit(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiHexDigitCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isspace(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiWhitespaceCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isblank(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiBlankCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `iscntrl(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiControlCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isprint(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiPrintableCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `isgraph(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiGraphicalCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `ispunct(c: CSignedInt32) -> Result CSignedInt32 Void` | `isAsciiPunctuationCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `toupper(c: CSignedInt32) -> Result CSignedInt32 Void` | `convertAsciiLetterCodeToUppercase(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `tolower(c: CSignedInt32) -> Result CSignedInt32 Void` | `convertAsciiLetterCodeToLowercase(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |

## `errno.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `errEPERM() -> Result CSignedInt32 Void` | `permissionDeniedErrorNumber() -> Result CSignedInt32 Void` |
| `errENOENT() -> Result CSignedInt32 Void` | `fileNotFoundErrorNumber() -> Result CSignedInt32 Void` |
| `errESRCH() -> Result CSignedInt32 Void` | `processNotFoundErrorNumber() -> Result CSignedInt32 Void` |
| `errEINTR() -> Result CSignedInt32 Void` | `interruptedSystemCallErrorNumber() -> Result CSignedInt32 Void` |
| `errEIO() -> Result CSignedInt32 Void` | `inputOutputErrorNumber() -> Result CSignedInt32 Void` |
| `errENOMEM() -> Result CSignedInt32 Void` | `outOfMemoryErrorNumber() -> Result CSignedInt32 Void` |
| `errEACCES() -> Result CSignedInt32 Void` | `accessDeniedErrorNumber() -> Result CSignedInt32 Void` |
| `errEFAULT() -> Result CSignedInt32 Void` | `badAddressErrorNumber() -> Result CSignedInt32 Void` |
| `errEEXIST() -> Result CSignedInt32 Void` | `fileAlreadyExistsErrorNumber() -> Result CSignedInt32 Void` |
| `errEINVAL() -> Result CSignedInt32 Void` | `invalidArgumentErrorNumber() -> Result CSignedInt32 Void` |
| `errENOSPC() -> Result CSignedInt32 Void` | `noSpaceLeftOnDeviceErrorNumber() -> Result CSignedInt32 Void` |
| `errEPIPE() -> Result CSignedInt32 Void` | `brokenPipeErrorNumber() -> Result CSignedInt32 Void` |
| `errERANGE() -> Result CSignedInt32 Void` | `resultOutOfRangeErrorNumber() -> Result CSignedInt32 Void` |
| `errorMessage(code: CSignedInt32) -> Result CNullTerminatedByteString Void` | `lookupErrnoMessageCString(errorNumber: CSignedInt32) -> Result CNullTerminatedByteString Void` |

## `errno_more.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `errEAGAIN() -> Result CSignedInt32 Void` | `tryAgainErrorNumber() -> Result CSignedInt32 Void` |
| `errEBADF() -> Result CSignedInt32 Void` | `badFileDescriptorErrorNumber() -> Result CSignedInt32 Void` |
| `errEBUSY() -> Result CSignedInt32 Void` | `resourceBusyErrorNumber() -> Result CSignedInt32 Void` |
| `errECHILD() -> Result CSignedInt32 Void` | `noChildProcessErrorNumber() -> Result CSignedInt32 Void` |
| `errEDEADLK() -> Result CSignedInt32 Void` | `deadlockWouldOccurErrorNumber() -> Result CSignedInt32 Void` |
| `errEDOM() -> Result CSignedInt32 Void` | `mathDomainErrorNumber() -> Result CSignedInt32 Void` |
| `errEILSEQ() -> Result CSignedInt32 Void` | `illegalByteSequenceErrorNumber() -> Result CSignedInt32 Void` |
| `errELOOP() -> Result CSignedInt32 Void` | `tooManySymbolicLinksErrorNumber() -> Result CSignedInt32 Void` |
| `errEMLINK() -> Result CSignedInt32 Void` | `tooManyLinksErrorNumber() -> Result CSignedInt32 Void` |
| `errENAMETOOLONG() -> Result CSignedInt32 Void` | `nameTooLongErrorNumber() -> Result CSignedInt32 Void` |
| `errENODEV() -> Result CSignedInt32 Void` | `noSuchDeviceErrorNumber() -> Result CSignedInt32 Void` |
| `errENOEXEC() -> Result CSignedInt32 Void` | `execFormatErrorNumber() -> Result CSignedInt32 Void` |
| `errENOLCK() -> Result CSignedInt32 Void` | `noLockAvailableErrorNumber() -> Result CSignedInt32 Void` |
| `errENOSYS() -> Result CSignedInt32 Void` | `functionNotImplementedErrorNumber() -> Result CSignedInt32 Void` |
| `errENOTEMPTY() -> Result CSignedInt32 Void` | `directoryNotEmptyErrorNumber() -> Result CSignedInt32 Void` |
| `errENOTDIR() -> Result CSignedInt32 Void` | `notDirectoryErrorNumber() -> Result CSignedInt32 Void` |
| `errEISDIR() -> Result CSignedInt32 Void` | `isDirectoryErrorNumber() -> Result CSignedInt32 Void` |
| `errEMFILE() -> Result CSignedInt32 Void` | `tooManyOpenFilesErrorNumber() -> Result CSignedInt32 Void` |
| `errENOTTY() -> Result CSignedInt32 Void` | `inappropriateIoctlErrorNumber() -> Result CSignedInt32 Void` |
| `errEROFS() -> Result CSignedInt32 Void` | `readOnlyFileSystemErrorNumber() -> Result CSignedInt32 Void` |
| `errEXDEV() -> Result CSignedInt32 Void` | `crossDeviceLinkErrorNumber() -> Result CSignedInt32 Void` |
| `errETIMEDOUT() -> Result CSignedInt32 Void` | `operationTimedOutErrorNumber() -> Result CSignedInt32 Void` |

## `inttypes.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `imaxabs(n: CSignedInt64) -> Result CSignedInt64 Void` | `absoluteMaxWidthSignedInt(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `imaxdiv(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `divideMaxWidthSignedIntQuotient(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `imaxmodulus(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `divideMaxWidthSignedIntRemainder(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `parsePositiveBinary(s: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `parsePositiveBinaryCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void` |
| `parsePositiveOctal(s: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `parsePositiveOctalCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void` |

## `iso646.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `keywordAnd(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `evaluateIso646AndKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `keywordOr(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `evaluateIso646OrKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `keywordNot(x: CSignedInt64) -> Result CSignedInt32 Void` | `evaluateIso646NotKeyword(inputValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `keywordXor(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `evaluateIso646XorKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `keywordEq(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `evaluateIso646EqualKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `keywordNotEq(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt32 Void` | `evaluateIso646NotEqualKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void` |

## `limits.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `maxSignedInt8() -> Result CSignedInt64 Void` | `maximumSignedInt8Value() -> Result CSignedInt64 Void` |
| `minSignedInt8() -> Result CSignedInt64 Void` | `minimumSignedInt8Value() -> Result CSignedInt64 Void` |
| `maxUnsignedInt8() -> Result CSignedInt64 Void` | `maximumUnsignedInt8Value() -> Result CSignedInt64 Void` |
| `maxSignedInt16() -> Result CSignedInt64 Void` | `maximumSignedInt16Value() -> Result CSignedInt64 Void` |
| `minSignedInt16() -> Result CSignedInt64 Void` | `minimumSignedInt16Value() -> Result CSignedInt64 Void` |
| `maxUnsignedInt16() -> Result CSignedInt64 Void` | `maximumUnsignedInt16Value() -> Result CSignedInt64 Void` |
| `maxSignedInt32() -> Result CSignedInt64 Void` | `maximumSignedInt32Value() -> Result CSignedInt64 Void` |
| `minSignedInt32() -> Result CSignedInt64 Void` | `minimumSignedInt32Value() -> Result CSignedInt64 Void` |
| `maxUnsignedInt32() -> Result CSignedInt64 Void` | `maximumUnsignedInt32Value() -> Result CSignedInt64 Void` |
| `maxSignedInt64() -> Result CSignedInt64 Void` | `maximumSignedInt64Value() -> Result CSignedInt64 Void` |
| `bitsPerByte() -> Result CSignedInt64 Void` | `bitCountPerByte() -> Result CSignedInt64 Void` |

## `math.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `intSqrt(n: CSignedInt64) -> Result CSignedInt64 Void` | `integerSquareRootSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `factorial(n: CSignedInt64) -> Result CSignedInt64 Void` | `factorialSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `isPrime(n: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64Prime(inputValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isPowerOfTwo(n: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64PowerOfTwo(inputValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `nextPowerOfTwo(n: CSignedInt64) -> Result CSignedInt64 Void` | `nextPowerOfTwoForSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `countDecimalDigits(n: CSignedInt64) -> Result CSignedInt64 Void` | `countDecimalDigitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `isEven(n: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64Even(inputValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `isOdd(n: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64Odd(inputValue: CSignedInt64) -> Result CSignedInt32 Void` |
| `countSetBits(n: CSignedInt64) -> Result CSignedInt64 Void` | `countSetBitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `countTrailingZeros(n: CSignedInt64) -> Result CSignedInt64 Void` | `countTrailingZeroBitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `signumInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `signOfSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `absDiffInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `absoluteDifferenceBetweenSignedInt64Values(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `countLeadingZeros(n: CSignedInt64) -> Result CSignedInt64 Void` | `countLeadingZeroBitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `squareInt(x: CSignedInt64) -> Result CSignedInt64 Void` | `squareSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `cubeInt(x: CSignedInt64) -> Result CSignedInt64 Void` | `cubeSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `isInRangeInt(x: CSignedInt64, lo: CSignedInt64, hi: CSignedInt64) -> Result CSignedInt32 Void` | `isSignedInt64WithinInclusiveRange(inputValue: CSignedInt64, lowerBound: CSignedInt64, upperBound: CSignedInt64) -> Result CSignedInt32 Void` |

## `math_float.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `fabsFloat(x: CFloat64) -> Result CFloat64 Void` | `absoluteFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `sqrtFloat(x: CFloat64) -> Result CFloat64 Void` | `squareRootFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `expFloat(x: CFloat64) -> Result CFloat64 Void` | `exponentialBaseEFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `truncFloat(x: CFloat64) -> Result CFloat64 Void` | `truncateFloat64TowardZero(inputValue: CFloat64) -> Result CFloat64 Void` |
| `floorFloat(x: CFloat64) -> Result CFloat64 Void` | `floorFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `ceilFloat(x: CFloat64) -> Result CFloat64 Void` | `ceilingFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `fmodFloat(x: CFloat64, y: CFloat64) -> Result CFloat64 Void` | `floatingRemainderFloat64(dividendValue: CFloat64, divisorValue: CFloat64) -> Result CFloat64 Void` |
| `lnFloat(x: CFloat64) -> Result CFloat64 Void` | `naturalLogFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `powFloat(base: CFloat64, exponent: CFloat64) -> Result CFloat64 Void` | `powerFloat64(baseValue: CFloat64, exponentValue: CFloat64) -> Result CFloat64 Void` |
| `sinFloat(x: CFloat64) -> Result CFloat64 Void` | `sineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `cosFloat(x: CFloat64) -> Result CFloat64 Void` | `cosineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `tanFloat(x: CFloat64) -> Result CFloat64 Void` | `tangentRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `sinhFloat(x: CFloat64) -> Result CFloat64 Void` | `hyperbolicSineFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `coshFloat(x: CFloat64) -> Result CFloat64 Void` | `hyperbolicCosineFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `tanhFloat(x: CFloat64) -> Result CFloat64 Void` | `hyperbolicTangentFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `log2Float(x: CFloat64) -> Result CFloat64 Void` | `logBaseTwoFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `log10Float(x: CFloat64) -> Result CFloat64 Void` | `logBaseTenFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `expm1Float(x: CFloat64) -> Result CFloat64 Void` | `exponentialMinusOneFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `log1pFloat(x: CFloat64) -> Result CFloat64 Void` | `naturalLogOnePlusFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `hypotFloat(x: CFloat64, y: CFloat64) -> Result CFloat64 Void` | `hypotenuseFloat64(firstLegValue: CFloat64, secondLegValue: CFloat64) -> Result CFloat64 Void` |
| `atanFloat(x: CFloat64) -> Result CFloat64 Void` | `arctangentRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `asinFloat(x: CFloat64) -> Result CFloat64 Void` | `arcsineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `acosFloat(x: CFloat64) -> Result CFloat64 Void` | `arccosineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `fmaFloat(a: CFloat64, b: CFloat64, c: CFloat64) -> Result CFloat64 Void` | `fusedMultiplyAddFloat64(multiplicandValue: CFloat64, multiplierValue: CFloat64, addendValue: CFloat64) -> Result CFloat64 Void` |
| `fmaxFloat(a: CFloat64, b: CFloat64) -> Result CFloat64 Void` | `maximumFloat64(leftValue: CFloat64, rightValue: CFloat64) -> Result CFloat64 Void` |
| `fminFloat(a: CFloat64, b: CFloat64) -> Result CFloat64 Void` | `minimumFloat64(leftValue: CFloat64, rightValue: CFloat64) -> Result CFloat64 Void` |
| `fdimFloat(a: CFloat64, b: CFloat64) -> Result CFloat64 Void` | `positiveDifferenceFloat64(leftValue: CFloat64, rightValue: CFloat64) -> Result CFloat64 Void` |
| `copysignFloat(magnitude: CFloat64, signSource: CFloat64) -> Result CFloat64 Void` | `copySignFloat64(magnitudeValue: CFloat64, signSourceValue: CFloat64) -> Result CFloat64 Void` |
| `signumFloat(x: CFloat64) -> Result CFloat64 Void` | `signOfFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `roundFloat(x: CFloat64) -> Result CFloat64 Void` | `roundFloat64ToNearestInteger(inputValue: CFloat64) -> Result CFloat64 Void` |
| `cbrtFloat(x: CFloat64) -> Result CFloat64 Void` | `cubeRootFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `exp2Float(x: CFloat64) -> Result CFloat64 Void` | `exponentialBaseTwoFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |

## `memory.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `copyBytes(dest: COpaqueMemoryAddress, src: CNullTerminatedByteString, count: CByteCount) -> Result CByteCount Void` | `copyMemoryBytes(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CByteCount Void` |
| `moveBytes(dest: COpaqueMemoryAddress, src: CNullTerminatedByteString, count: CByteCount) -> Result CByteCount Void` | `moveMemoryBytesAllowOverlap(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CByteCount Void` |
| `fillBytes(buffer: COpaqueMemoryAddress, value: CSignedInt32, count: CByteCount) -> Result CByteCount Void` | `fillMemoryBytesWithValue(byteBuffer: COpaqueMemoryAddress, targetValue: CSignedInt32, byteCount: CByteCount) -> Result CByteCount Void` |
| `compareBytes(a: CNullTerminatedByteString, b: CNullTerminatedByteString, count: CByteCount) -> Result CSignedInt64 Void` | `compareMemoryByteRanges(leftValue: CNullTerminatedByteString, rightValue: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void` |
| `findByte(buffer: CNullTerminatedByteString, value: CSignedInt32, count: CByteCount) -> Result CSignedInt64 Void` | `findByteValueInMemoryRange(byteBuffer: CNullTerminatedByteString, targetValue: CSignedInt32, byteCount: CByteCount) -> Result CSignedInt64 Void` |
| `zeroBytes(buffer: COpaqueMemoryAddress, count: CByteCount) -> Result CByteCount Void` | `zeroMemoryBytes(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void` |
| `hashBytesFnv1a(buffer: CNullTerminatedByteString, count: CByteCount) -> Result CSignedInt64 Void` | `hashMemoryBytesWithFnv1a(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void` |

## `numeric.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `incrementInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `incrementSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `decrementInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `decrementSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `doubleInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `doubleSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `halveInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `halveSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `negateInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `negateSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `reciprocalFloat(x: CFloat64) -> Result CFloat64 Void` | `reciprocalFloat64(inputValue: CFloat64) -> Result CFloat64 Void` |
| `sumOneToN(n: CSignedInt64) -> Result CSignedInt64 Void` | `sumSignedInt64OneThroughN(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `sumSquaresOneToN(n: CSignedInt64) -> Result CSignedInt64 Void` | `sumSignedInt64SquaresOneThroughN(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `sumCubesOneToN(n: CSignedInt64) -> Result CSignedInt64 Void` | `sumSignedInt64CubesOneThroughN(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `triangularNumber(n: CSignedInt64) -> Result CSignedInt64 Void` | `triangularNumberSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `lcmInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `leastCommonMultipleSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |

## `process.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `exitWithCode(code: CSignedInt32) -> Result CSignedInt32 Void` | `exitProcessWithStatusCode(exitStatusCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `abortProcess() -> Result CSignedInt32 Void` | `abortCurrentProcess() -> Result CSignedInt32 Void` |

## `random.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `makeRandomState(seed: CSignedInt64) -> Result COpaqueMemoryAddress Void` | `createDeterministicRandomState(randomSeed: CSignedInt64) -> Result COpaqueMemoryAddress Void` |
| `freeRandomState(state: COpaqueMemoryAddress) -> Result CSignedInt32 Void` | `releaseDeterministicRandomState(randomState: COpaqueMemoryAddress) -> Result CSignedInt32 Void` |
| `loadUnsignedByte(buffer: COpaqueMemoryAddress, offset: CByteCount) -> Result CSignedInt64 Void` | `loadUnsignedByteFromBufferOffset(byteBuffer: COpaqueMemoryAddress, byteOffset: CByteCount) -> Result CSignedInt64 Void` |
| `readRandomState(state: COpaqueMemoryAddress) -> Result CSignedInt64 Void` | `readDeterministicRandomState(randomState: COpaqueMemoryAddress) -> Result CSignedInt64 Void` |
| `nextRandomInt(state: COpaqueMemoryAddress) -> Result CSignedInt64 Void` | `nextDeterministicRandomSignedInt64(randomState: COpaqueMemoryAddress) -> Result CSignedInt64 Void` |

## `signal.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `raiseSignal(signum: CSignedInt32) -> Result CSignedInt32 Void` | `raiseProcessSignalNumber(signalNumber: CSignedInt32) -> Result CSignedInt32 Void` |
| `sigSIGABRT() -> Result CSignedInt32 Void` | `abortSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGFPE() -> Result CSignedInt32 Void` | `floatingPointExceptionSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGILL() -> Result CSignedInt32 Void` | `illegalInstructionSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGINT() -> Result CSignedInt32 Void` | `interruptSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGSEGV() -> Result CSignedInt32 Void` | `segmentationViolationSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGTERM() -> Result CSignedInt32 Void` | `terminationSignalNumber() -> Result CSignedInt32 Void` |

## `signal_more.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `sigSIGHUP() -> Result CSignedInt32 Void` | `hangupSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGQUIT() -> Result CSignedInt32 Void` | `quitSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGTRAP() -> Result CSignedInt32 Void` | `traceTrapSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGBUS() -> Result CSignedInt32 Void` | `busErrorSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGKILL() -> Result CSignedInt32 Void` | `killSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGUSR1() -> Result CSignedInt32 Void` | `userSignalOneNumber() -> Result CSignedInt32 Void` |
| `sigSIGUSR2() -> Result CSignedInt32 Void` | `userSignalTwoNumber() -> Result CSignedInt32 Void` |
| `sigSIGPIPE() -> Result CSignedInt32 Void` | `brokenPipeSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGALRM() -> Result CSignedInt32 Void` | `alarmSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGCHLD() -> Result CSignedInt32 Void` | `childStatusChangedSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGCONT() -> Result CSignedInt32 Void` | `continueSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGSTOP() -> Result CSignedInt32 Void` | `stopSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGTSTP() -> Result CSignedInt32 Void` | `terminalStopSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGTTIN() -> Result CSignedInt32 Void` | `terminalInputSignalNumber() -> Result CSignedInt32 Void` |
| `sigSIGTTOU() -> Result CSignedInt32 Void` | `terminalOutputSignalNumber() -> Result CSignedInt32 Void` |

## `sort.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `bubbleSortBytes(buf: COpaqueMemoryAddress, count: CByteCount) -> Result CByteCount Void` | `sortBytesWithBubbleSortInPlace(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void` |
| `isSortedBytes(buf: CNullTerminatedByteString, count: CByteCount) -> Result CSignedInt32 Void` | `areBytesSortedAscending(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt32 Void` |
| `insertionSortBytes(buf: COpaqueMemoryAddress, count: CByteCount) -> Result CByteCount Void` | `sortBytesWithInsertionSortInPlace(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void` |

## `stddef.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `nullPointer() -> Result COpaqueMemoryAddress Void` | `nullOpaquePointerValue() -> Result COpaqueMemoryAddress Void` |
| `bytesInPointer() -> Result CSignedInt64 Void` | `byteSizeOfOpaquePointer() -> Result CSignedInt64 Void` |
| `bytesInSignedInt32() -> Result CSignedInt64 Void` | `byteSizeOfSignedInt32() -> Result CSignedInt64 Void` |
| `bytesInSignedInt64() -> Result CSignedInt64 Void` | `byteSizeOfSignedInt64() -> Result CSignedInt64 Void` |
| `bytesInFloat64() -> Result CSignedInt64 Void` | `byteSizeOfFloat64() -> Result CSignedInt64 Void` |

## `stdio.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `putByte(c: CSignedInt32) -> Result CSignedInt32 Void` | `writeByteToStandardOutput(characterCode: CSignedInt32) -> Result CSignedInt32 Void` |
| `putString(s: CNullTerminatedByteString) -> Result CByteCount Void` | `writeCStringToStandardOutput(inputText: CNullTerminatedByteString) -> Result CByteCount Void` |
| `putLine(s: CNullTerminatedByteString) -> Result CByteCount Void` | `writeCStringLineToStandardOutput(inputText: CNullTerminatedByteString) -> Result CByteCount Void` |
| `putIntegerDecimal(n: CSignedInt64) -> Result CByteCount Void` | `writeSignedInt64DecimalToStandardOutput(inputValue: CSignedInt64) -> Result CByteCount Void` |
| `putUnsignedDecimal(n: CSignedInt64) -> Result CByteCount Void` | `writeUnsignedInt64DecimalToStandardOutput(inputValue: CSignedInt64) -> Result CByteCount Void` |
| `putHex(n: CSignedInt64) -> Result CByteCount Void` | `writeSignedInt64HexToStandardOutput(inputValue: CSignedInt64) -> Result CByteCount Void` |

## `stdlib.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `parseDecimalInt(s: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `parseDecimalCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void` |
| `parseHexInt(s: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `parseHexCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void` |
| `absoluteInt(n: CSignedInt64) -> Result CSignedInt64 Void` | `absoluteSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `minInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `minimumSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `maxInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `maximumSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `powerInt(base: CSignedInt64, exponent: CSignedInt64) -> Result CSignedInt64 Void` | `powerSignedInt64(baseValue: CSignedInt64, exponentValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `gcdInt(a: CSignedInt64, b: CSignedInt64) -> Result CSignedInt64 Void` | `greatestCommonDivisorSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void` |
| `clampInt(x: CSignedInt64, lo: CSignedInt64, hi: CSignedInt64) -> Result CSignedInt64 Void` | `clampSignedInt64ToInclusiveRange(inputValue: CSignedInt64, lowerBound: CSignedInt64, upperBound: CSignedInt64) -> Result CSignedInt64 Void` |

## `string.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `strlen(s: CNullTerminatedByteString) -> Result CByteCount Void` | `stringByteLength(inputText: CNullTerminatedByteString) -> Result CByteCount Void` |
| `strcmp(a: CNullTerminatedByteString, b: CNullTerminatedByteString) -> Result CSignedInt32 Void` | `compareCString(leftValue: CNullTerminatedByteString, rightValue: CNullTerminatedByteString) -> Result CSignedInt32 Void` |
| `strncmp(a: CNullTerminatedByteString, b: CNullTerminatedByteString, n: CByteCount) -> Result CSignedInt32 Void` | `compareCStringPrefixBytes(leftValue: CNullTerminatedByteString, rightValue: CNullTerminatedByteString, maxByteCount: CByteCount) -> Result CSignedInt32 Void` |
| `strchr(s: CNullTerminatedByteString, c: CSignedInt32) -> Result CSignedInt64 Void` | `findFirstCharacterInCString(inputText: CNullTerminatedByteString, characterCode: CSignedInt32) -> Result CSignedInt64 Void` |
| `strrchr(s: CNullTerminatedByteString, c: CSignedInt32) -> Result CSignedInt64 Void` | `findLastCharacterInCString(inputText: CNullTerminatedByteString, characterCode: CSignedInt32) -> Result CSignedInt64 Void` |
| `strstr(haystack: CNullTerminatedByteString, needle: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `findSubstringInCString(searchText: CNullTerminatedByteString, targetSubstring: CNullTerminatedByteString) -> Result CSignedInt64 Void` |
| `strspn(s: CNullTerminatedByteString, accept: CNullTerminatedByteString) -> Result CByteCount Void` | `countInitialCStringBytesInAcceptSet(inputText: CNullTerminatedByteString, acceptedCharacters: CNullTerminatedByteString) -> Result CByteCount Void` |
| `copyCString(dest: COpaqueMemoryAddress, src: CNullTerminatedByteString) -> Result CByteCount Void` | `copyCStringToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString) -> Result CByteCount Void` |
| `strcat(dest: COpaqueMemoryAddress, src: CNullTerminatedByteString) -> Result CByteCount Void` | `appendCStringToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString) -> Result CByteCount Void` |
| `strncpy(dest: COpaqueMemoryAddress, src: CNullTerminatedByteString, n: CByteCount) -> Result CByteCount Void` | `copyCStringPrefixToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, maxByteCount: CByteCount) -> Result CByteCount Void` |
| `strcspn(s: CNullTerminatedByteString, reject: CNullTerminatedByteString) -> Result CByteCount Void` | `countInitialCStringBytesNotInRejectSet(inputText: CNullTerminatedByteString, rejectedCharacters: CNullTerminatedByteString) -> Result CByteCount Void` |
| `strpbrk(s: CNullTerminatedByteString, accept: CNullTerminatedByteString) -> Result CSignedInt64 Void` | `findFirstCStringByteInAcceptSet(inputText: CNullTerminatedByteString, acceptedCharacters: CNullTerminatedByteString) -> Result CSignedInt64 Void` |
| `strdup(s: CNullTerminatedByteString) -> Result COpaqueMemoryAddress Void` | `duplicateCStringIntoOwnedMemory(inputText: CNullTerminatedByteString) -> Result COpaqueMemoryAddress Void` |
| `strncat(dest: COpaqueMemoryAddress, src: CNullTerminatedByteString, n: CByteCount) -> Result CByteCount Void` | `appendCStringPrefixToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, maxByteCount: CByteCount) -> Result CByteCount Void` |
| `beginsWith(s: CNullTerminatedByteString, prefix: CNullTerminatedByteString) -> Result CSignedInt32 Void` | `cstringBeginsWithPrefix(inputText: CNullTerminatedByteString, prefixText: CNullTerminatedByteString) -> Result CSignedInt32 Void` |
| `endsWith(s: CNullTerminatedByteString, suffix: CNullTerminatedByteString) -> Result CSignedInt32 Void` | `cstringEndsWithSuffix(inputText: CNullTerminatedByteString, suffixText: CNullTerminatedByteString) -> Result CSignedInt32 Void` |

## `time.as`

| Current signature | Proposed AgentScript signature |
|---|---|
| `currentClock() -> Result CSignedInt64 Void` | `readProcessCpuClockTicks() -> Result CSignedInt64 Void` |
| `currentEpochSeconds() -> Result CSignedInt64 Void` | `readCurrentUnixEpochSeconds() -> Result CSignedInt64 Void` |
| `secondsToHours(s: CSignedInt64) -> Result CSignedInt64 Void` | `convertSecondsToWholeHours(secondCount: CSignedInt64) -> Result CSignedInt64 Void` |
| `secondsToMinutes(s: CSignedInt64) -> Result CSignedInt64 Void` | `convertSecondsToWholeMinutes(secondCount: CSignedInt64) -> Result CSignedInt64 Void` |
| `minutesToSeconds(m: CSignedInt64) -> Result CSignedInt64 Void` | `convertMinutesToSeconds(minuteCount: CSignedInt64) -> Result CSignedInt64 Void` |
| `hoursToSeconds(h: CSignedInt64) -> Result CSignedInt64 Void` | `convertHoursToSeconds(hourCount: CSignedInt64) -> Result CSignedInt64 Void` |
| `daysSinceEpoch(s: CSignedInt64) -> Result CSignedInt64 Void` | `convertUnixEpochSecondsToDays(epochSecondCount: CSignedInt64) -> Result CSignedInt64 Void` |
| `isLeapYear(y: CSignedInt64) -> Result CSignedInt32 Void` | `isGregorianLeapYear(candidateYear: CSignedInt64) -> Result CSignedInt32 Void` |
