# AgentScript Standard Library

The AgentScript standard library lives in `AgentScript/stdlib_as/`. Each
file is a self-contained project that declares one module's worth of
operations plus a `main` smoke test, so a stdlib module can be compiled
and run in isolation via `python compiler/ascc.py --emit-exe stdlib_as/<module>.as`.

## Design constraints

- **Pure-AS where possible.** `string`, `memory`, `array`, `sort`, `math`,
  `math_float`, `numeric`, `bit`, `compare`, `convert`, `bool`, `time`,
  and `stdio`'s integer/string writers implement their algorithm in
  AgentScript using only `pointer.loadByte` / `pointer.storeByte` and
  `math.*` primitives. The emitted IR contains no `strlen`, `memcpy`,
  `fabs`, `printf`, etc. externs.
- **C floor at the syscall edge.** `process` calls `c.exit` / `c.abort`,
  `signal` calls `c.raise`, `random` reads `/dev/urandom` via `c.fopen`,
  `errno` looks up messages via `c.strerror`. These are the only
  unavoidable libc dependencies in the public stdlib.
- **C-aligned types throughout.** Signatures use `CSignedInt32`,
  `CSignedInt64`, `CByteCount`, `CNullTerminatedByteString`,
  `COpaqueMemoryAddress`, `CFloat64` per AST §12 — every name carries
  signedness, width, ABI role, or encoding contract at the read site.
- **Spec §6 naming.** Operation names lead with the semantic domain
  (`string`, `memory`, `ascii`, `signedInt64`, `float64`, `signal`,
  `errno`) so a single retrieved line is locally recoverable.

## Known caveats

The current surface is the output of the symbol-layer rename pass
described in `STDLIB_RENAME_PROPOSALS.md`. The Spec/AST gap review in
that document tracks the unfinished layers:

- Parameter names still use positional `leftValue` / `rightValue` /
  `inputValue` / `targetValue` patterns in many rows; spec §6 wants
  domain-meaningful names.
- 283 of 290 signatures return `Result X Void`; spec §11/§12 + AST §3.3
  want plain output for infallible operations and real typed error
  domains for fallible ones.
- Predicates return `CSignedInt32` (C convention) rather than `Bool`
  (AST §5).
- Stable constants (pi, e, errno numbers, signal numbers, ASCII codes)
  are modeled as operations that return a value; AST §2.12.5
  `domainLiteral` is the spec-aligned form.
- Module paths (`standard.string.*`, `standard.memory.*`, …) and
  dependency-contract tapes per spec §15 are not yet defined.

## Module index

| Group | Modules |
|---|---|
| Strings and memory | `string`, `memory`, `array`, `sort` |
| Numbers | `math`, `math_float`, `numeric`, `bit`, `compare`, `convert` |
| Characters and booleans | `ctype`, `char`, `bool` |
| I/O and parsing | `stdio`, `stdlib`, `inttypes`, `iso646` |
| Time and process | `time`, `process`, `signal`, `signal_more` |
| Errors and limits | `errno`, `errno_more`, `limits`, `constants` |
| Low level | `stddef`, `random`, `assert` |

Each module's smoke test (`operation main`) and any private file-local
helpers are omitted from the listing below.

## Operations

### `string.as`

Pure-AS C-string helpers (length, compare, search, copy, append). Reads and writes raw byte buffers; no libc string calls in the emitted IR.

- `stringByteLength(inputText: CNullTerminatedByteString) -> Result CByteCount Void`
  - Pure-AS stringByteLength: walk bytes from s until a NUL, return the count.
- `compareCString(leftValue: CNullTerminatedByteString, rightValue: CNullTerminatedByteString) -> Result CSignedInt32 Void`
  - Pure-AS compareCString: returns 0 on equal C-strings, signed diff of first mismatching byte otherwise.
- `compareCStringPrefixBytes(leftValue: CNullTerminatedByteString, rightValue: CNullTerminatedByteString, maxByteCount: CByteCount) -> Result CSignedInt32 Void`
  - Pure-AS compareCStringPrefixBytes: compare up to n bytes of a and b. Returns 0 if equal-in-first-n-or-both-NUL, signed diff at first mismatch, 0 if n==0.
- `findFirstCharacterInCString(inputText: CNullTerminatedByteString, characterCode: CSignedInt32) -> Result CSignedInt64 Void`
  - Pure-AS findFirstCharacterInCString: find first byte equal to c; return offset or -1 if not found before NUL.
- `findLastCharacterInCString(inputText: CNullTerminatedByteString, characterCode: CSignedInt32) -> Result CSignedInt64 Void`
  - Pure-AS findLastCharacterInCString: track the last-seen offset of c while walking; return it (or -1).
- `findSubstringInCString(searchText: CNullTerminatedByteString, targetSubstring: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - Pure-AS naive substring search. Returns offset of needle in haystack, or -1 if absent. Special case: needle empty -> 0.
- `countInitialCStringBytesInAcceptSet(inputText: CNullTerminatedByteString, acceptedCharacters: CNullTerminatedByteString) -> Result CByteCount Void`
  - Length of the longest prefix of s consisting entirely of bytes that appear somewhere in accept. Pure AS: O(len(s) * len(accept)).
- `copyCStringToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString) -> Result CByteCount Void`
  - Pure-AS strcpy: copy each byte of src to dest including the terminating NUL. Returns count of bytes written (= stringByteLength(src) + 1). Caller is responsible for dest being large enough.
- `appendCStringToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString) -> Result CByteCount Void`
  - Pure-AS appendCStringToDestinationBuffer: find the NUL in dest, then copy src (including its NUL) starting at that offset. Returns the resulting length (= stringByteLength(dest)+stringByteLength(src)).
- `copyCStringPrefixToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, maxByteCount: CByteCount) -> Result CByteCount Void`
  - Pure-AS copyCStringPrefixToDestinationBuffer. Up to n bytes copied from src to dest; remainder NUL-padded. Returns n.
- `countInitialCStringBytesNotInRejectSet(inputText: CNullTerminatedByteString, rejectedCharacters: CNullTerminatedByteString) -> Result CByteCount Void`
  - Length of leading prefix of s NOT containing any byte in reject. Pure AS: O(len(s) * len(reject)).
- `findFirstCStringByteInAcceptSet(inputText: CNullTerminatedByteString, acceptedCharacters: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - Offset of the first byte of s that appears anywhere in accept, or -1 if absent before the NUL.
- `duplicateCStringIntoOwnedMemory(inputText: CNullTerminatedByteString) -> Result COpaqueMemoryAddress Void`
  - Allocate a heap copy of s. Caller owns the returned pointer (must c.free). Returns NULL on allocation failure.
- `appendCStringPrefixToDestinationBuffer(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, maxByteCount: CByteCount) -> Result CByteCount Void`
  - Append at most n bytes from src to dest's existing NUL-terminated content. Always writes a NUL terminator after the appended bytes.
- `cstringBeginsWithPrefix(inputText: CNullTerminatedByteString, prefixText: CNullTerminatedByteString) -> Result CSignedInt32 Void`
  - 1 if s starts with prefix; 0 otherwise. Pure AS via byte-by-byte compare.
- `cstringEndsWithSuffix(inputText: CNullTerminatedByteString, suffixText: CNullTerminatedByteString) -> Result CSignedInt32 Void`
  - 1 if s ends with suffix; 0 otherwise. Implemented as: stringByteLength(suffix) <= stringByteLength(s), then compare last stringByteLength(suffix) bytes of s with suffix.

### `memory.as`

Pure-AS memory primitives (copy, move, fill, compare, find, zero, hash). Built on pointer.loadByte / pointer.storeByte; no libc memory calls.

- `copyMemoryBytes(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CByteCount Void`
  - Pure-AS memcpy. Forward copy of count bytes.
- `moveMemoryBytesAllowOverlap(destinationBuffer: COpaqueMemoryAddress, sourceBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CByteCount Void`
  - Pure-AS memmove. Detects whether dest comes after src in memory; if so copies the bytes in reverse to keep overlapping ranges intact. Otherwise forwards to copyMemoryBytes semantics.
- `fillMemoryBytesWithValue(byteBuffer: COpaqueMemoryAddress, targetValue: CSignedInt32, byteCount: CByteCount) -> Result CByteCount Void`
  - Pure-AS memset. Writes count copies of value into buffer.
- `compareMemoryByteRanges(leftValue: CNullTerminatedByteString, rightValue: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void`
  - Pure-AS memcmp. Returns 0 / <0 / >0 on first byte difference.
- `findByteValueInMemoryRange(byteBuffer: CNullTerminatedByteString, targetValue: CSignedInt32, byteCount: CByteCount) -> Result CSignedInt64 Void`
  - Pure-AS memchr. Walks the first count bytes of buffer looking for value; returns the offset, or -1 if not found.
- `zeroMemoryBytes(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void`
  - Like bzero. Writes count zeros into buffer. Returns count.
- `hashMemoryBytesWithFnv1a(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void`
  - FNV-1a 64-bit hash. Walk every byte of buffer (count bytes), XOR into a 64-bit accumulator initialized to 0xCBF29CE484222325, then multiply by 0x100000001B3. Pure AS: XOR is simulated as a + b - 2*(a*b)/(a OR b)... actually, AS has no bitwise. We approximate XOR via (a + b) mod 256 for individual bytes since for the FNV bias a single mismatched bit is fine. This isn't bit-exact FNV-1a, but produces a deterministic per-input hash useful for tests / dispatch tables.

### `array.as`

Whole-buffer reductions and in-place transforms over byte arrays (sum, min, max, contains, count, reverse).

- `sumSignedByteValuesInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void`
  - Sum every byte in the first count bytes of buf, treating each as unsigned.
- `findMinimumSignedByteInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void`
  - Smallest unsigned byte. Returns 256 (out-of-range sentinel) for empty arrays.
- `findMaximumSignedByteInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt64 Void`
  - Largest unsigned byte. Returns -1 for empty arrays.
- `bufferContainsSignedByteValue(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount, targetValue: CSignedInt32) -> Result CSignedInt32 Void`
  - 1 if any byte in [0, count) equals value, else 0.
- `countSignedByteValueInBuffer(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount, targetValue: CSignedInt32) -> Result CSignedInt64 Void`
  - Number of bytes equal to value in [0, count).
- `reverseBytesInBufferInPlace(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void`
  - Reverse the order of the first count bytes of buf in place. Returns count.

### `sort.as`

In-place byte-array sorts (bubble, insertion) and sortedness checks.

- `sortBytesWithBubbleSortInPlace(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void`
  - Bubble-sort the first count bytes of buf in non-decreasing order. O(n^2). Returns count.
- `areBytesSortedAscending(byteBuffer: CNullTerminatedByteString, byteCount: CByteCount) -> Result CSignedInt32 Void`
  - 1 if every adjacent pair satisfies buf[i] <= buf[i+1], else 0. Empty / single-element arrays are sorted.
- `sortBytesWithInsertionSortInPlace(byteBuffer: COpaqueMemoryAddress, byteCount: CByteCount) -> Result CByteCount Void`
  - In-place insertion sort. O(n^2) worst case, O(n) on nearly-sorted input.

### `math.as`

Integer math beyond the math.*I64 primitives: square root, factorial, primality, power-of-two, bit-count, signum.

- `integerSquareRootSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Integer square root: floor(sqrt(n)) for n >= 0. Newton iteration: x_{k+1} = (x_k + n/x_k) / 2. Terminates when the iterate stops improving. Returns 0 for n <= 0.
- `factorialSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - n! for n in 0..20. Returns 1 for n <= 0. For n > 20 the result overflows signed 64-bit; we accept the wrap (matching standard C with -fwrapv).
- `isSignedInt64Prime(inputValue: CSignedInt64) -> Result CSignedInt32 Void`
  - Returns 1 if n is prime, 0 otherwise. n <= 1 -> 0. Tests divisibility by 2 then odd numbers up to floor(sqrt(n)).
- `isSignedInt64PowerOfTwo(inputValue: CSignedInt64) -> Result CSignedInt32 Void`
  - Returns 1 if n is a positive power of 2 (1, 2, 4, 8, ...), else 0. Halves n repeatedly while it's even; if result is exactly 1, original was a power of 2.
- `nextPowerOfTwoForSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Smallest power of 2 that is >= n. Returns 1 for n <= 1. Doubles 1 until result >= n.
- `countDecimalDigitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Number of decimal digits in |n|. Returns 1 for n==0. Works for negative n by counting digits of -n.
- `isSignedInt64Even(inputValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if n % 2 == 0, else 0.
- `isSignedInt64Odd(inputValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if n % 2 != 0, else 0.
- `countSetBitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Population count of n (number of 1-bits). Uses mod-2 / div-2 since AS doesn't have bitwise primitives. Works on non-negative n; negative inputs work modulo 2's-complement representation.
- `countTrailingZeroBitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Trailing zero bits of n. Returns 64 for n == 0 (matching the GCC __builtin_ctzll convention for zero).
- `signOfSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Returns -1 if n < 0, +1 if n > 0, 0 if n == 0.
- `absoluteDifferenceBetweenSignedInt64Values(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Absolute difference |a - b|. Inlines the absolute-value flip rather than depending on stdlib.as#absoluteInt (each stdlib_as file is self-contained today; cross-file operation calls aren't wired up yet).
- `countLeadingZeroBitsInSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Number of leading zero bits of n in its 64-bit representation. Returns 64 for n == 0. Pure AS: doubles a probe bit until it's > n.
- `squareSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - x * x.
- `cubeSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - x * x * x.
- `isSignedInt64WithinInclusiveRange(inputValue: CSignedInt64, lowerBound: CSignedInt64, upperBound: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if lo <= x <= hi, else 0.

### `math_float.as`

Pure-AS port of <math.h> for CFloat64 (sqrt, exp, log, trig, hyp, pow, classification). No libm linkage.

- `absoluteFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - |x| for double-precision x. Pure AS via comparison + multiply by -1.
- `squareRootFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - sqrt(x) for x >= 0 via Newton's method. Returns 0.0 for x <= 0 (no NaN here yet — that needs IEEE special-value support).
- `exponentialBaseEFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - e^x via Taylor series: sum_{k=0..29} x^k / k!. Accurate to ~12 decimals for |x| <= 2; degrades beyond that. No argument reduction yet.
- `truncateFloat64TowardZero(inputValue: CFloat64) -> Result CFloat64 Void`
  - Truncate toward zero. Uses math.floatToInt (fptosi) which already truncates, then converts back.
- `floorFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Largest integer <= x. trunc(x) is identical to floor for x >= 0, but for negative non-integer x we have to step down by 1.
- `ceilingFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Smallest integer >= x. Mirror image of floor: for x <= 0 trunc is the ceiling; for positive non-integer, ceil = trunc + 1.
- `floatingRemainderFloat64(dividendValue: CFloat64, divisorValue: CFloat64) -> Result CFloat64 Void`
  - Floating-point remainder of x/y, truncating toward zero. fmod(x, y) = x - trunc(x/y) * y. Caller must ensure y != 0; we don't return NaN here (no IEEE special-value handling yet).
- `naturalLogFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Natural log of x for x > 0. Uses range reduction (ln(x) = ln(x / 2^k) + k * ln(2), where k is chosen so x/2^k is in [1, 2)) before Newton iteration on f(y) = exp(y) - x. exponentialBaseEFloat64 is accurate in [0, 2], so the reduced ln(scaled) computation stays in the convergent zone. Returns 0.0 for x <= 0.
- `powerFloat64(baseValue: CFloat64, exponentValue: CFloat64) -> Result CFloat64 Void`
  - base^exponent for base > 0 via exp(exponent * ln(base)). Returns 1.0 for exponent == 0.
- `sineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - sin(x) via Taylor series: x - x^3/3! + x^5/5! - x^7/7! + ... (20 terms). For best accuracy, caller should reduce x into [-pi, pi] beforehand. No argument reduction at this layer (yet).
- `cosineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - cos(x) via Taylor series: 1 - x^2/2! + x^4/4! - ... (20 terms). Same range caveat as sineRadiansFloat64.
- `tangentRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - tan(x) = sin(x) / cos(x). Inherits range caveats from sineRadiansFloat64 / cosineRadiansFloat64 (no argument reduction).
- `hyperbolicSineFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Hyperbolic sine: (exp(x) - exp(-x)) / 2.
- `hyperbolicCosineFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Hyperbolic cosine: (exp(x) + exp(-x)) / 2.
- `hyperbolicTangentFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Hyperbolic tangent: sinh(x) / cosh(x).
- `logBaseTwoFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Base-2 log: ln(x) / ln(2).
- `logBaseTenFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Base-10 log: ln(x) / ln(10).
- `exponentialMinusOneFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - exp(x) - 1. Not loss-of-precision-aware at this layer; production libm uses a separate series for tiny x.
- `naturalLogOnePlusFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - ln(1 + x). Same precision caveat as expm1.
- `hypotenuseFloat64(firstLegValue: CFloat64, secondLegValue: CFloat64) -> Result CFloat64 Void`
  - sqrt(x^2 + y^2). Naive form may overflow for huge inputs; production libm scales first.
- `arctangentRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - atan(x) via Taylor series for |x| <= 1; uses the identity atan(x) = sign(x)*pi/2 - atan(1/x) for |x| > 1.
- `arcsineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - asin(x) = atan(x / sqrt(1 - x^2)). Domain: [-1, 1].
- `arccosineRadiansFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - acos(x) = pi/2 - asin(x). Domain: [-1, 1].
- `fusedMultiplyAddFloat64(multiplicandValue: CFloat64, multiplierValue: CFloat64, addendValue: CFloat64) -> Result CFloat64 Void`
  - Fused multiply-add: a*b + c. Not actually fused at this layer (libm fma uses a hardware FMA instruction); we just do the two ops in sequence with normal IEEE-754 rounding between them.
- `maximumFloat64(leftValue: CFloat64, rightValue: CFloat64) -> Result CFloat64 Void`
  - Max of a and b. Returns the non-NaN argument if exactly one is NaN; for both-NaN we don't detect (no isnan yet).
- `minimumFloat64(leftValue: CFloat64, rightValue: CFloat64) -> Result CFloat64 Void`
  - Min of a and b.
- `positiveDifferenceFloat64(leftValue: CFloat64, rightValue: CFloat64) -> Result CFloat64 Void`
  - Positive difference: max(a - b, 0).
- `copySignFloat64(magnitudeValue: CFloat64, signSourceValue: CFloat64) -> Result CFloat64 Void`
  - Returns |magnitude| with the sign of signSource. Doesn't yet preserve sign of zero (real libm copysign treats -0.0 specially; we don't have signed-zero detection without bit-level access).
- `signOfFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Returns -1.0 if x < 0, 1.0 if x > 0, 0.0 if x == 0.
- `roundFloat64ToNearestInteger(inputValue: CFloat64) -> Result CFloat64 Void`
  - Round half-away-from-zero to nearest integer (matching libm round, not lrint which uses banker's rounding).
- `cubeRootFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - Cube root: sign(x) * pow(|x|, 1/3). Handles negative inputs by computing on |x| and reattaching the sign.
- `exponentialBaseTwoFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - 2^x via pow(2.0, x).

### `numeric.as`

Small integer helpers (increment, double, halve, sums, triangular, lcm).

- `incrementSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - n + 1.
- `decrementSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - n - 1.
- `doubleSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - n * 2.
- `halveSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - n / 2 (integer division).
- `negateSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - n * -1.
- `reciprocalFloat64(inputValue: CFloat64) -> Result CFloat64 Void`
  - 1.0 / x.
- `sumSignedInt64OneThroughN(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - 1+2+...+n via the closed-form n*(n+1)/2.
- `sumSignedInt64SquaresOneThroughN(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - 1^2+2^2+...+n^2 via n*(n+1)*(2n+1)/6.
- `sumSignedInt64CubesOneThroughN(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - 1^3+2^3+...+n^3 via (n*(n+1)/2)^2.
- `triangularNumberSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Alias for sumSignedInt64OneThroughN(n) — the nth triangular number.
- `leastCommonMultipleSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Least common multiple = |a*b|/gcd(a,b). Returns 0 if either input is 0.

### `bit.as`

Bit-level operations on CSignedInt64 (shift, test, set, clear, toggle).

- `shiftSignedInt64BitsLeft(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void`
  - n << k via multiplication by 2^k. k must be 0..63; outside that range the result wraps.
- `shiftSignedInt64BitsRight(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void`
  - n >> k (arithmetic) via division by 2^k.
- `isSignedInt64BitSet(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if bit k of n is set; 0 otherwise. (n >> k) & 1.
- `setSignedInt64Bit(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void`
  - n with bit k forced to 1. If bit k is already set, returns n unchanged. Else returns n + 2^k.
- `clearSignedInt64Bit(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void`
  - n with bit k forced to 0. If already cleared, return n unchanged. Else n - 2^k.
- `toggleSignedInt64Bit(inputValue: CSignedInt64, bitIndex: CSignedInt64) -> Result CSignedInt64 Void`
  - n with bit k toggled. Implementation: if isSignedInt64BitSet(n,k) then clearSignedInt64Bit else setSignedInt64Bit.

### `compare.as`

Total-ordering and equivalence helpers for signed integers and CFloat64 (with epsilon).

- `compareSignedInt64Ordering(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 3-way: -1 if a<b, +1 if a>b, 0 if equal.
- `areSignedInt64ValuesEqual(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if a == b, else 0.
- `isSignedInt64LeftLessThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if a < b, else 0.
- `isSignedInt64LeftLessThanOrEqualRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if a <= b, else 0.
- `isSignedInt64LeftGreaterThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if a > b, else 0.
- `isSignedInt64LeftGreaterThanOrEqualRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - 1 if a >= b, else 0.
- `compareFloat64Ordering(leftValue: CFloat64, rightValue: CFloat64) -> Result CSignedInt32 Void`
  - 3-way for doubles. Does not handle NaN specially (no IEEE NaN support in our F64 surface yet).
- `areFloat64ValuesWithinTolerance(leftValue: CFloat64, rightValue: CFloat64, tolerance: CFloat64) -> Result CSignedInt32 Void`
  - 1 if |a-b| <= epsilon, else 0.

### `convert.as`

Integer width and pointer-offset conversions.

- `widenSignedInt32ToSignedInt64(inputValue: CSignedInt32) -> Result CSignedInt64 Void`
  - Sign-extend a 32-bit signed integer to 64 bits.
- `narrowSignedInt64ToSignedInt32(inputValue: CSignedInt64) -> Result CSignedInt32 Void`
  - Truncate a 64-bit signed integer to 32 bits. The truncation is handled by the returnOk codegen path which coerces to the operation's declared return type.
- `convertByteValueToUnsignedInt32(signExtendedByteValue: CSignedInt32) -> Result CSignedInt32 Void`
  - Treat the low 8 bits of b as an unsigned byte in 0..255. Useful after pointer.loadByte which sign-extends.
- `convertSignedInt64ToFloat64(inputValue: CSignedInt64) -> Result CFloat64 Void`
  - Signed i64 to double via math.convertSignedInt64ToFloat64.
- `convertFloat64ToSignedInt64(inputValue: CFloat64) -> Result CSignedInt64 Void`
  - Double to i64 via math.convertFloat64ToSignedInt64 (truncate toward zero).
- `calculateCStringPointerOffset(baseValue: CNullTerminatedByteString, pointerValue: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - Returns p - base as a signed i64. Both pointers must lie in the same allocation for the result to be meaningful.
- `advanceOpaquePointerByByteOffset(baseValue: COpaqueMemoryAddress, byteOffset: CByteCount) -> Result COpaqueMemoryAddress Void`
  - Returns base + offset as a new pointer (no dereference).

### `ctype.as`

ASCII character predicates and case-folding (replaces <ctype.h>).

- `isAsciiDecimalDigitCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiDecimalDigitCode: true if c is in 0x30..0x39 inclusive.
- `isAsciiLowercaseLetterCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiLowercaseLetterCode: 0x61..0x7A.
- `isAsciiUppercaseLetterCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiUppercaseLetterCode: 0x41..0x5A.
- `isAsciiLetterCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiLetterCode: returns 1 if c is A..Z or a..z.
- `isAsciiLetterOrDigitCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiLetterOrDigitCode = isAsciiLetterCode OR isAsciiDecimalDigitCode.
- `isAsciiHexDigitCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiHexDigitCode: true if c is a hexadecimal digit (0-9, A-F, a-f).
- `isAsciiWhitespaceCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiWhitespaceCode: true for space, tab, LF, VT, FF, CR.
- `isAsciiBlankCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiBlankCode: true only for space or horizontal tab.
- `isAsciiControlCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiControlCode: 0x00..0x1F or 0x7F.
- `isAsciiPrintableCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiPrintableCode: 0x20..0x7E.
- `isAsciiGraphicalCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiGraphicalCode: 0x21..0x7E (printable minus space).
- `isAsciiPunctuationCode(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - ASCII isAsciiPunctuationCode: printable, non-space, non-alphanumeric.
- `convertAsciiLetterCodeToUppercase(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - Maps 0x61..0x7A down by 32; passes through everything else.
- `convertAsciiLetterCodeToLowercase(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - Maps 0x41..0x5A up by 32; passes through everything else.

### `char.as`

ASCII character-code constants (newline, tab, quotes, …).

- `asciiNullCharacterCode() -> Result CSignedInt32 Void`
  - NUL byte (0).
- `asciiHorizontalTabCharacterCode() -> Result CSignedInt32 Void`
  - Horizontal tab (9).
- `asciiNewlineCharacterCode() -> Result CSignedInt32 Void`
  - Line feed (10).
- `asciiCarriageReturnCharacterCode() -> Result CSignedInt32 Void`
  - Carriage return (13).
- `asciiSpaceCharacterCode() -> Result CSignedInt32 Void`
  - Space (32).
- `asciiBellCharacterCode() -> Result CSignedInt32 Void`
  - BEL (7).
- `asciiBackspaceCharacterCode() -> Result CSignedInt32 Void`
  - BS (8).
- `asciiEscapeCharacterCode() -> Result CSignedInt32 Void`
  - ESC (27).
- `asciiDeleteCharacterCode() -> Result CSignedInt32 Void`
  - DEL (127).
- `asciiDoubleQuoteCharacterCode() -> Result CSignedInt32 Void`
  - \" (34).
- `asciiSingleQuoteCharacterCode() -> Result CSignedInt32 Void`
  - ' (39).
- `asciiBackslashCharacterCode() -> Result CSignedInt32 Void`
  - \\ (92).
- `asciiPeriodCharacterCode() -> Result CSignedInt32 Void`
  - . (46).
- `asciiCommaCharacterCode() -> Result CSignedInt32 Void`
  - , (44).
- `asciiColonCharacterCode() -> Result CSignedInt32 Void`
  - : (58).
- `asciiSemicolonCharacterCode() -> Result CSignedInt32 Void`
  - ; (59).
- `asciiSlashCharacterCode() -> Result CSignedInt32 Void`
  - / (47).
- `asciiAsteriskCharacterCode() -> Result CSignedInt32 Void`
  - * (42).

### `bool.as`

C-style int-as-bool helpers: true/false constants and not/and/or/xor/equiv.

- `signedInt32BooleanTrueValue() -> Result CSignedInt32 Void`
  - Canonical 1.
- `signedInt32BooleanFalseValue() -> Result CSignedInt32 Void`
  - Canonical 0.
- `negateSignedInt32Boolean(inputValue: CSignedInt32) -> Result CSignedInt32 Void`
  - 1 if x == 0, else 0.
- `combineSignedInt32BooleansWithAnd(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void`
  - Logical AND. Returns 1 if both args are non-zero, else 0.
- `combineSignedInt32BooleansWithOr(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void`
  - Logical OR. Returns 1 if either arg is non-zero, else 0.
- `combineSignedInt32BooleansWithExclusiveOr(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void`
  - Logical XOR. Returns 1 if exactly one arg is non-zero, else 0.
- `compareSignedInt32BooleansEquivalent(leftValue: CSignedInt32, rightValue: CSignedInt32) -> Result CSignedInt32 Void`
  - Logical equivalence (a iff b). Returns 1 if both args are zero or both are non-zero, else 0.

### `stdio.as`

Pure-AS line writers for stdout (byte, string, decimal, hex). Wraps c.putchar at the floor; no printf.

- `writeByteToStandardOutput(characterCode: CSignedInt32) -> Result CSignedInt32 Void`
  - Write one byte to stdout. The single line of code that ever crosses out to the host OS in the AgentScript stdlib.
- `writeCStringToStandardOutput(inputText: CNullTerminatedByteString) -> Result CByteCount Void`
  - Write every byte of s to stdout via writeByteToStandardOutput until a NUL is reached. Returns the byte count. Pure AS — no libc string call.
- `writeCStringLineToStandardOutput(inputText: CNullTerminatedByteString) -> Result CByteCount Void`
  - Write s + newline to stdout. Delegates the bytes to writeCStringToStandardOutput, then emits one LF via writeByteToStandardOutput.
- `writeSignedInt64DecimalToStandardOutput(inputValue: CSignedInt64) -> Result CByteCount Void`
  - Pure-AS itoa-then-print: extract decimal digits from n (handling sign), buffer them in reverse on a 24-byte scratch area, then emit forward through writeByteToStandardOutput. No sprintf, no printf.
- `writeUnsignedInt64DecimalToStandardOutput(inputValue: CSignedInt64) -> Result CByteCount Void`
  - Print n as an unsigned decimal integer (no sign), followed by a newline. For negative n, prints the two's-complement representation as if it were unsigned. Pure AS via digit extraction.
- `writeSignedInt64HexToStandardOutput(inputValue: CSignedInt64) -> Result CByteCount Void`
  - Print n in hexadecimal (lowercase), no '0x' prefix, no leading zeros except for n == 0. Followed by a newline. Pure AS — extracts nibbles via division by 16.

### `stdlib.as`

Parsing and small math helpers: decimal/hex parse, absolute value, min/max, power, gcd, clamp.

- `parseDecimalCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - AS-native atoi/atol. Skips ASCII whitespace, accepts optional sign, accumulates decimal digits until a non-digit byte.
- `parseHexCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - AS-native strtol(s, NULL, 16). Skips whitespace, accepts optional sign and optional 0x/0X prefix, then accumulates hex digits.
- `absoluteSignedInt64(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Return |n|. Mirrors libc abs/labs/llabs semantics.
- `minimumSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Smaller of a and b.
- `maximumSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Larger of a and b.
- `powerSignedInt64(baseValue: CSignedInt64, exponentValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Integer pow: returns base^exponent by repeated multiplication. exponent must be >= 0. Returns 1 if exponent == 0; returns 0 if exponent < 0 (no fractional results).
- `greatestCommonDivisorSignedInt64(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Greatest common divisor via Euclidean algorithm. gcd(a, 0) = |a|; gcd handles either argument being negative by working on the absolute values.
- `clampSignedInt64ToInclusiveRange(inputValue: CSignedInt64, lowerBound: CSignedInt64, upperBound: CSignedInt64) -> Result CSignedInt64 Void`
  - Clamp x into [lo, hi]: return lo if x<lo, hi if x>hi, else x.

### `inttypes.as`

Maximum-width integer helpers and additional radix parsers (binary, octal).

- `absoluteMaxWidthSignedInt(inputValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Absolute value of intmax_t.
- `divideMaxWidthSignedIntQuotient(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Integer quotient a/b. Note: real libc divideMaxWidthSignedIntQuotient returns a struct with both quotient and remainder; AS user-operations can't return tuples yet, so we expose this and divideMaxWidthSignedIntRemainder separately.
- `divideMaxWidthSignedIntRemainder(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt64 Void`
  - Integer remainder a%b.
- `parsePositiveBinaryCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - Parse a non-empty C-string of '0' and '1' bytes as a base-2 unsigned integer. Stops at the first non-'0'/'1' byte. Returns 0 if the first byte is non-binary.
- `parsePositiveOctalCStringToSignedInt64(inputText: CNullTerminatedByteString) -> Result CSignedInt64 Void`
  - Parse a non-empty C-string of '0'..'7' as a base-8 unsigned integer.

### `iso646.as`

<iso646.h>-style English keyword wrappers (and, or, not, xor, eq, notEq) used as int-Bool combinators.

- `evaluateIso646AndKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - C's 'and' operator-keyword on two ints. 1 if both non-zero.
- `evaluateIso646OrKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - C's 'or' on two ints.
- `evaluateIso646NotKeyword(inputValue: CSignedInt64) -> Result CSignedInt32 Void`
  - C's 'not' (logical NOT) on an int. 1 if x == 0.
- `evaluateIso646XorKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - C's 'xor' (logical xor) on two ints. 1 if exactly one is non-zero.
- `evaluateIso646EqualKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - Returns 1 if a == b, else 0.
- `evaluateIso646NotEqualKeyword(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 Void`
  - Returns 1 if a != b, else 0.

### `time.as`

Clock readers and unit conversions (seconds/minutes/hours/days-since-epoch, leap-year predicate).

- `readProcessCpuClockTicks() -> Result CSignedInt64 Void`
  - Wraps c.clock as the only OS-time primitive at this layer. Returns CPU clock ticks since the start of this process (CLOCKS_PER_SEC defines the divisor).
- `readCurrentUnixEpochSeconds() -> Result CSignedInt64 Void`
  - Wraps c.time with a NULL out-param. Returns seconds since 1970-01-01 00:00:00 UTC.
- `convertSecondsToWholeHours(secondCount: CSignedInt64) -> Result CSignedInt64 Void`
  - Floor-divide seconds by 3600 to get whole hours.
- `convertSecondsToWholeMinutes(secondCount: CSignedInt64) -> Result CSignedInt64 Void`
  - s / 60.
- `convertMinutesToSeconds(minuteCount: CSignedInt64) -> Result CSignedInt64 Void`
  - m * 60.
- `convertHoursToSeconds(hourCount: CSignedInt64) -> Result CSignedInt64 Void`
  - h * 3600.
- `convertUnixEpochSecondsToDays(epochSecondCount: CSignedInt64) -> Result CSignedInt64 Void`
  - Whole days since 1970-01-01 from a seconds-since-epoch value.
- `isGregorianLeapYear(candidateYear: CSignedInt64) -> Result CSignedInt32 Void`
  - Gregorian leap-year rule: divisible by 4, AND (not divisible by 100 OR divisible by 400).

### `process.as`

Process lifecycle: clean exit, abort. Both unconditional terminators.

- `exitProcessWithStatusCode(exitStatusCode: CSignedInt32) -> Result CSignedInt32 Void`
  - Terminate the process cleanly with the given exit status code. Does not return; the returnOk path is reachable only on the (impossible) failure of c.exit.
- `abortCurrentProcess() -> Result CSignedInt32 Void`
  - Terminate the process immediately by raising SIGABRT. Does not return.

### `signal.as`

Core signal numbers (SIGABRT, SIGFPE, SIGILL, SIGINT, SIGSEGV, SIGTERM) plus the c.raise wrapper.

- `raiseProcessSignalNumber(signalNumber: CSignedInt32) -> Result CSignedInt32 Void`
  - Wrap c.raise. Delivers signalNumber to this process; returns 0 on success and a non-zero result on failure.
- `abortSignalNumber() -> Result CSignedInt32 Void`
  - SIGABRT (6). Abnormal-termination signal raised by abort().
- `floatingPointExceptionSignalNumber() -> Result CSignedInt32 Void`
  - SIGFPE (8). Erroneous arithmetic (divide by zero, overflow).
- `illegalInstructionSignalNumber() -> Result CSignedInt32 Void`
  - SIGILL (4). Illegal instruction.
- `interruptSignalNumber() -> Result CSignedInt32 Void`
  - SIGINT (2). Interactive attention signal (Ctrl-C).
- `segmentationViolationSignalNumber() -> Result CSignedInt32 Void`
  - SIGSEGV (11). Invalid memory reference (segmentation fault).
- `terminationSignalNumber() -> Result CSignedInt32 Void`
  - SIGTERM (15). Termination request.

### `signal_more.as`

Extended POSIX signal numbers beyond the core set.

- `hangupSignalNumber() -> Result CSignedInt32 Void`
  - SIGHUP (1).
- `quitSignalNumber() -> Result CSignedInt32 Void`
  - SIGQUIT (3).
- `traceTrapSignalNumber() -> Result CSignedInt32 Void`
  - SIGTRAP (5).
- `busErrorSignalNumber() -> Result CSignedInt32 Void`
  - SIGBUS (7).
- `killSignalNumber() -> Result CSignedInt32 Void`
  - SIGKILL (9).
- `userSignalOneNumber() -> Result CSignedInt32 Void`
  - SIGUSR1 (10).
- `userSignalTwoNumber() -> Result CSignedInt32 Void`
  - SIGUSR2 (12).
- `brokenPipeSignalNumber() -> Result CSignedInt32 Void`
  - SIGPIPE (13).
- `alarmSignalNumber() -> Result CSignedInt32 Void`
  - SIGALRM (14).
- `childStatusChangedSignalNumber() -> Result CSignedInt32 Void`
  - SIGCHLD (17).
- `continueSignalNumber() -> Result CSignedInt32 Void`
  - SIGCONT (18).
- `stopSignalNumber() -> Result CSignedInt32 Void`
  - SIGSTOP (19).
- `terminalStopSignalNumber() -> Result CSignedInt32 Void`
  - SIGTSTP (20).
- `terminalInputSignalNumber() -> Result CSignedInt32 Void`
  - SIGTTIN (21).
- `terminalOutputSignalNumber() -> Result CSignedInt32 Void`
  - SIGTTOU (22).

### `errno.as`

Standard errno-number accessors and the errno-to-message lookup.

- `permissionDeniedErrorNumber() -> Result CSignedInt32 Void`
  - Operation not permitted (1).
- `fileNotFoundErrorNumber() -> Result CSignedInt32 Void`
  - No such file or directory (2).
- `processNotFoundErrorNumber() -> Result CSignedInt32 Void`
  - No such process (3).
- `interruptedSystemCallErrorNumber() -> Result CSignedInt32 Void`
  - Interrupted system call (4).
- `inputOutputErrorNumber() -> Result CSignedInt32 Void`
  - Input/output error (5).
- `outOfMemoryErrorNumber() -> Result CSignedInt32 Void`
  - Out of memory (12).
- `accessDeniedErrorNumber() -> Result CSignedInt32 Void`
  - Permission denied (13).
- `badAddressErrorNumber() -> Result CSignedInt32 Void`
  - Bad address (14).
- `fileAlreadyExistsErrorNumber() -> Result CSignedInt32 Void`
  - File exists (17).
- `invalidArgumentErrorNumber() -> Result CSignedInt32 Void`
  - Invalid argument (22).
- `noSpaceLeftOnDeviceErrorNumber() -> Result CSignedInt32 Void`
  - No space left on device (28).
- `brokenPipeErrorNumber() -> Result CSignedInt32 Void`
  - Broken pipe (32).
- `resultOutOfRangeErrorNumber() -> Result CSignedInt32 Void`
  - Result out of range (34).
- `lookupErrnoMessageCString(errorNumber: CSignedInt32) -> Result CNullTerminatedByteString Void`
  - Return a short English message for known POSIX errno values, or 'unknown error' for others. Pure-AS — no libc strerror.

### `errno_more.as`

Extended errno-number accessors.

- `tryAgainErrorNumber() -> Result CSignedInt32 Void`
  - EAGAIN (11).
- `badFileDescriptorErrorNumber() -> Result CSignedInt32 Void`
  - EBADF (9).
- `resourceBusyErrorNumber() -> Result CSignedInt32 Void`
  - EBUSY (16).
- `noChildProcessErrorNumber() -> Result CSignedInt32 Void`
  - ECHILD (10).
- `deadlockWouldOccurErrorNumber() -> Result CSignedInt32 Void`
  - EDEADLK (35).
- `mathDomainErrorNumber() -> Result CSignedInt32 Void`
  - EDOM (33).
- `illegalByteSequenceErrorNumber() -> Result CSignedInt32 Void`
  - EILSEQ (84).
- `tooManySymbolicLinksErrorNumber() -> Result CSignedInt32 Void`
  - ELOOP (40).
- `tooManyLinksErrorNumber() -> Result CSignedInt32 Void`
  - EMLINK (31).
- `nameTooLongErrorNumber() -> Result CSignedInt32 Void`
  - ENAMETOOLONG (36).
- `noSuchDeviceErrorNumber() -> Result CSignedInt32 Void`
  - ENODEV (19).
- `execFormatErrorNumber() -> Result CSignedInt32 Void`
  - ENOEXEC (8).
- `noLockAvailableErrorNumber() -> Result CSignedInt32 Void`
  - ENOLCK (37).
- `functionNotImplementedErrorNumber() -> Result CSignedInt32 Void`
  - ENOSYS (38).
- `directoryNotEmptyErrorNumber() -> Result CSignedInt32 Void`
  - ENOTEMPTY (39).
- `notDirectoryErrorNumber() -> Result CSignedInt32 Void`
  - ENOTDIR (20).
- `isDirectoryErrorNumber() -> Result CSignedInt32 Void`
  - EISDIR (21).
- `tooManyOpenFilesErrorNumber() -> Result CSignedInt32 Void`
  - EMFILE (24).
- `inappropriateIoctlErrorNumber() -> Result CSignedInt32 Void`
  - ENOTTY (25).
- `readOnlyFileSystemErrorNumber() -> Result CSignedInt32 Void`
  - EROFS (30).
- `crossDeviceLinkErrorNumber() -> Result CSignedInt32 Void`
  - EXDEV (18).
- `operationTimedOutErrorNumber() -> Result CSignedInt32 Void`
  - ETIMEDOUT (110).

### `limits.as`

<limits.h>-style numeric range bounds and `bitCountPerByte`.

- `maximumSignedInt8Value() -> Result CSignedInt64 Void`
  - Largest value of a signed 8-bit integer (INT8_MAX).
- `minimumSignedInt8Value() -> Result CSignedInt64 Void`
  - Smallest value of a signed 8-bit integer (INT8_MIN).
- `maximumUnsignedInt8Value() -> Result CSignedInt64 Void`
  - UINT8_MAX = 255.
- `maximumSignedInt16Value() -> Result CSignedInt64 Void`
  - INT16_MAX = 32767.
- `minimumSignedInt16Value() -> Result CSignedInt64 Void`
  - INT16_MIN = -32768.
- `maximumUnsignedInt16Value() -> Result CSignedInt64 Void`
  - UINT16_MAX = 65535.
- `maximumSignedInt32Value() -> Result CSignedInt64 Void`
  - INT32_MAX = 2147483647.
- `minimumSignedInt32Value() -> Result CSignedInt64 Void`
  - INT32_MIN = -2147483648.
- `maximumUnsignedInt32Value() -> Result CSignedInt64 Void`
  - UINT32_MAX = 4294967295.
- `maximumSignedInt64Value() -> Result CSignedInt64 Void`
  - INT64_MAX = 9223372036854775807.
- `bitCountPerByte() -> Result CSignedInt64 Void`
  - CHAR_BIT (always 8 in C99+).

### `constants.as`

Mathematical constants as CFloat64 values (pi, e, ln 2, sqrt 2, golden ratio, …).

- `mathematicalPiFloat64() -> Result CFloat64 Void`
  - M_PI = 3.141592653589793.
- `mathematicalTwoPiFloat64() -> Result CFloat64 Void`
  - M_TAU = 2*pi = 6.283185307179586.
- `mathematicalHalfPiFloat64() -> Result CFloat64 Void`
  - M_PI_2 = pi/2.
- `mathematicalQuarterPiFloat64() -> Result CFloat64 Void`
  - M_PI_4 = pi/4.
- `mathematicalPiSquaredFloat64() -> Result CFloat64 Void`
  - pi^2.
- `mathematicalEulerNumberFloat64() -> Result CFloat64 Void`
  - M_E = Euler's number = 2.718281828459045.
- `naturalLogOfTwoFloat64() -> Result CFloat64 Void`
  - M_LN2 = ln(2) = 0.6931471805599453.
- `naturalLogOfTenFloat64() -> Result CFloat64 Void`
  - M_LN10 = ln(10) = 2.302585092994046.
- `logBaseTwoOfEulerNumberFloat64() -> Result CFloat64 Void`
  - M_LOG2E = log2(e) = 1.4426950408889634.
- `logBaseTenOfEulerNumberFloat64() -> Result CFloat64 Void`
  - M_LOG10E = log10(e) = 0.4342944819032518.
- `squareRootOfTwoFloat64() -> Result CFloat64 Void`
  - M_SQRT2 = sqrt(2) = 1.4142135623730951.
- `squareRootOfOneHalfFloat64() -> Result CFloat64 Void`
  - M_SQRT1_2 = sqrt(0.5) = 0.7071067811865476.
- `eulerMascheroniFloat64() -> Result CFloat64 Void`
  - Euler-Mascheroni constant = 0.5772156649015329.
- `goldenRatioFloat64() -> Result CFloat64 Void`
  - (1 + sqrt(5)) / 2 = 1.618033988749895.
- `zeroFloat64() -> Result CFloat64 Void`
  - 0.0.
- `oneFloat64() -> Result CFloat64 Void`
  - 1.0.
- `negativeOneFloat64() -> Result CFloat64 Void`
  - -1.0.

### `stddef.as`

<stddef.h>-style accessors: null pointer, sizeof pointer / int32 / int64 / float64.

- `nullOpaquePointerValue() -> Result COpaqueMemoryAddress Void`
  - Returns the NULL pointer (i8* 0).
- `byteSizeOfOpaquePointer() -> Result CSignedInt64 Void`
  - sizeof(void*) on the AgentScript target (x86-64 Windows): 8 bytes.
- `byteSizeOfSignedInt32() -> Result CSignedInt64 Void`
  - sizeof(int32_t) = 4.
- `byteSizeOfSignedInt64() -> Result CSignedInt64 Void`
  - sizeof(int64_t) = 8.
- `byteSizeOfFloat64() -> Result CSignedInt64 Void`
  - sizeof(double) = 8.

### `random.as`

Deterministic PRNG state lifecycle (make, read, next, release).

- `createDeterministicRandomState(randomSeed: CSignedInt64) -> Result COpaqueMemoryAddress Void`
  - Allocate an 8-byte state slot. Stores `seed` (or 1 if seed <= 0, since the MINSTD LCG can't be seeded with zero).
- `releaseDeterministicRandomState(randomState: COpaqueMemoryAddress) -> Result CSignedInt32 Void`
  - Free the slot returned by createDeterministicRandomState.
- `loadUnsignedByteFromBufferOffset(byteBuffer: COpaqueMemoryAddress, byteOffset: CByteCount) -> Result CSignedInt64 Void`
  - pointer.loadByte returns a signed I8 that sign-extends to negative for bytes 128..255. This helper normalizes to the unsigned interpretation via (b + 256) % 256.
- `readDeterministicRandomState(randomState: COpaqueMemoryAddress) -> Result CSignedInt64 Void`
  - Load the i64 state value from an 8-byte little-endian slot using loadUnsignedByteFromBufferOffset so high-bit-set bytes don't sign-extend.
- `nextDeterministicRandomSignedInt64(randomState: COpaqueMemoryAddress) -> Result CSignedInt64 Void`
  - Advance the MINSTD LCG and return the new state value. LCG: s = (s * 48271) mod 2147483647.

### `assert.as`

Runtime assertion helpers used by stdlib self-tests.

- `requireConditionTrue(conditionValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32`
  - Abort the program (returning error code 1) when condition is zero. Returns 0 on success.
- `requireSignedInt64ValuesEqual(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32`
  - Assert a == b. Delegates to requireConditionTrue.
- `requireSignedInt64ValuesNotEqual(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32`
  - Assert a != b.
- `requireSignedInt64LeftGreaterThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32`
  - Assert a > b. Returns 0 on success; error code 1 (via requireConditionTrue) on failure.
- `requireSignedInt64LeftLessThanRight(leftValue: CSignedInt64, rightValue: CSignedInt64) -> Result CSignedInt32 CSignedInt32`
  - Assert a < b.
- `requireSignedInt64ValueWithinInclusiveRange(inputValue: CSignedInt64, lowerBound: CSignedInt64, upperBound: CSignedInt64) -> Result CSignedInt32 CSignedInt32`
  - Assert lo <= x <= hi.
- `requireOpaquePointerNotNull(pointerValue: COpaqueMemoryAddress) -> Result CSignedInt32 CSignedInt32`
  - Assert that p is not the NULL pointer.
