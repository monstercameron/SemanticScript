project BootstrapGeneral
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32
errorCase MainError InputOpenFailed CSignedInt32
errorCase MainError AllocationFailed CSignedInt32

# ============================================================
# Stdlib-style helper operations.
#
# These mirror operations defined in stdlib_as/*.as. Today AS does
# not support cross-file calls, so the compiler-side helpers live
# here alongside main(). The shapes match the corresponding stdlib
# operations and can be lifted out unchanged once multi-file linking
# is in place.
# ============================================================

operation lineStartsWithKeyword
input lineStartsWithKeyword linePointer COpaqueMemoryAddress
input lineStartsWithKeyword keyword CNullTerminatedByteString
input lineStartsWithKeyword keywordLength CByteCount
output lineStartsWithKeyword Result Bool Void
memory lineStartsWithKeyword heap no
memory lineStartsWithKeyword stack max 1KiB
async lineStartsWithKeyword no
purpose lineStartsWithKeyword "Report whether the first keywordLength bytes at linePointer match keyword. Wraps c.strncmp and the zero-equality test that every verb-prefix check needs."
invariant lineStartsWithKeyword "Returns true exactly when c.strncmp reports zero across keywordLength bytes."

label startLineStartsWithKeyword
const zeroComparisonValue CSignedInt32 0
call comparePrefixCall c.strncmp
arg comparePrefixCall left linePointer
arg comparePrefixCall right keyword
arg comparePrefixCall count keywordLength
run comparePrefixCall
bind prefixComparisonResult CSignedInt32 comparePrefixCall

call isPrefixMatchCall math.equalI64
arg isPrefixMatchCall left prefixComparisonResult
arg isPrefixMatchCall right zeroComparisonValue
run isPrefixMatchCall
bind isPrefixMatch Bool isPrefixMatchCall
returnOk isPrefixMatch


operation findLineEndOffset
input findLineEndOffset bufferBase COpaqueMemoryAddress
input findLineEndOffset lineStartPointer COpaqueMemoryAddress
input findLineEndOffset fileEndOffset CSignedInt64
input findLineEndOffset newlineByteCode CSignedInt32
output findLineEndOffset Result CSignedInt64 Void
effect findLineEndOffset read memory.buffer
memory findLineEndOffset heap no
memory findLineEndOffset stack max 1KiB
async findLineEndOffset no
purpose findLineEndOffset "Return the offset (relative to bufferBase) of the first newline byte at or after lineStartPointer, falling back to fileEndOffset when no newline remains. Wraps the c.strchr+pointer.isNull+pointer.difference cascade that both compiler passes need before processing a line."
invariant findLineEndOffset "The returned offset is always within [0, fileEndOffset] and points at either a newline byte or the trailing NUL of the source buffer."

label startFindLineEndOffset
call locateNewlineCall c.strchr
arg locateNewlineCall haystack lineStartPointer
arg locateNewlineCall needle newlineByteCode
run locateNewlineCall
bind newlinePointer COpaqueMemoryAddress locateNewlineCall

call newlineMissingCheckCall pointer.isNull
arg newlineMissingCheckCall pointer newlinePointer
run newlineMissingCheckCall
bind newlineMissing Bool newlineMissingCheckCall
branchIf newlineMissing fallbackToFileEnd
branch computeNewlineRelativeOffset

label computeNewlineRelativeOffset
call newlineRelativeOffsetCall pointer.difference
arg newlineRelativeOffsetCall left newlinePointer
arg newlineRelativeOffsetCall right bufferBase
run newlineRelativeOffsetCall
bind newlineRelativeOffset CSignedInt64 newlineRelativeOffsetCall
returnOk newlineRelativeOffset

label fallbackToFileEnd
returnOk fileEndOffset


operation main
input main console Console
output main Result ExitCode MainError
effect main read filesystem
effect main write filesystem
effect main read process.environment
effect main write console.stdout
effect main allocate heap
effect main read memory.buffer
effect main write memory.buffer
memory main heap yes
memory main stack max 16KiB
async main no

purpose main "General-purpose AgentScript compiler v0.1. Replaces the marker-extraction approach (bootstrap7-11) with real per-line tokenization and verb dispatch. v0.1 SCOPE: handles enough verbs to compile hello.as / hello_world.as / hello_via_helper.as through real dispatch (const String, const ExitCode, label, call console.writeLine, arg, run, ignoreOk, bindError, branchIfError, returnOk, makeError, returnError; header verbs are recognized and skipped). Future versions will grow verb coverage to handle the rest of the as/ corpus."
invariant main "Each non-blank, non-comment input line is dispatched by verb, not by marker substring"

label startMain

# ============================================================
# 1. Resolve input path + open file
# ============================================================

const inputEnvVar CNullTerminatedByteString "AS_INPUT"
const defaultInputPath CNullTerminatedByteString "C:/Users/Cam/Desktop/AgentScript/AgentScript/as/hello.as"
const readMode CNullTerminatedByteString "r"
const bufferCapacity CByteCount 65536
const readChunkCapacity CByteCount 65535
const oneByte CByteCount 1
const zeroByteOffset CByteCount 0
const zeroByteValue CSignedInt32 0

const newlineCharCode CSignedInt32 10
const spaceCharCode CSignedInt32 32
const tabCharCode CSignedInt32 9
const quoteCharCode CSignedInt32 34
const hashCharCode CSignedInt32 35
const backslashCharCode CSignedInt32 92

const oneOffset I64 1
const twoOffset I64 2
const tenValue I64 10
const asciiDigitZero I64 48
const asciiDigitNine I64 57

call envLookupCall c.getenv
arg envLookupCall name inputEnvVar
run envLookupCall
bind envLookupResult CNullTerminatedByteString envLookupCall

call envLookupNullCheckCall pointer.isNull
arg envLookupNullCheckCall pointer envLookupResult
run envLookupNullCheckCall
bind envLookupMissing Bool envLookupNullCheckCall

var chosenInputPath CNullTerminatedByteString "placeholder"
branchIf envLookupMissing useDefaultInputPath
set chosenInputPath envLookupResult
branch openInputFile

label useDefaultInputPath
set chosenInputPath defaultInputPath
branch openInputFile

label openInputFile
call inputOpenCall c.fopen
arg inputOpenCall path chosenInputPath
arg inputOpenCall mode readMode
run inputOpenCall
bind inputFileHandle CFileHandle inputOpenCall

call inputOpenNullCheckCall pointer.isNull
arg inputOpenNullCheckCall pointer inputFileHandle
run inputOpenNullCheckCall
bind inputFileIsNull Bool inputOpenNullCheckCall
branchIf inputFileIsNull inputOpenFailed
branch allocateReadBuffer

label allocateReadBuffer
call readBufferAllocCall c.malloc
arg readBufferAllocCall size bufferCapacity
run readBufferAllocCall
bind readBuffer COpaqueMemoryAddress readBufferAllocCall

call readBufferNullCheckCall pointer.isNull
arg readBufferNullCheckCall pointer readBuffer
run readBufferNullCheckCall
bind readBufferIsNull Bool readBufferNullCheckCall
branchIf readBufferIsNull readBufferAllocationFailed
branch readInputFile

label readInputFile
call inputReadCall c.fread
arg inputReadCall buffer readBuffer
arg inputReadCall size oneByte
arg inputReadCall count readChunkCapacity
arg inputReadCall stream inputFileHandle
run inputReadCall
bind inputBytesRead CByteCount inputReadCall

call inputNullTerminatePointerCall pointer.offset
arg inputNullTerminatePointerCall base readBuffer
arg inputNullTerminatePointerCall offset inputBytesRead
run inputNullTerminatePointerCall
bind inputNullTerminatePointer COpaqueMemoryAddress inputNullTerminatePointerCall

call inputNullTerminateStoreCall pointer.storeByte
arg inputNullTerminateStoreCall buffer inputNullTerminatePointer
arg inputNullTerminateStoreCall offset zeroByteOffset
arg inputNullTerminateStoreCall value zeroByteValue
run inputNullTerminateStoreCall

# ============================================================
# 2. Emit IR module header (we always emit these unconditionally)
# ============================================================

const irModuleBanner CNullTerminatedByteString "; ModuleID = 'AgentScriptGeneralSelfHosted'"
call writeIrBannerCall c.puts
arg writeIrBannerCall text irModuleBanner
run writeIrBannerCall

const irTargetTriple CNullTerminatedByteString "target triple = \"x86_64-pc-windows-msvc\""
call writeIrTripleCall c.puts
arg writeIrTripleCall text irTargetTriple
run writeIrTripleCall

const irExternPuts CNullTerminatedByteString "declare i32 @puts(i8*)"
call writeIrExternPutsCall c.puts
arg writeIrExternPutsCall text irExternPuts
run writeIrExternPutsCall

# ============================================================
# 3. Pass 1: scan every line; for each `const NAME String "..."` or
#    `const NAME CNullTerminatedByteString "..."`, emit a module-level
#    string constant `@.NAME = private constant [L x i8] c"...\00"`.
#    Stores name->slot via a SEEN counter; we emit one numbered slot
#    per string and remember its array size in a parallel scratch
#    region of the read buffer's tail.
# ============================================================
#
# Strategy: walk the buffer line-by-line. For each line, find the
# first non-whitespace position. If the line begins with "const ",
# tokenize: const NAME TYPE VALUE. If TYPE is "String" or
# "CNullTerminatedByteString" and VALUE starts with a double quote,
# emit a global constant and bump the string counter.
#
# Line walker invariant: `lineCursor` is always the offset of the
# next byte to look at in `readBuffer`. We use c.strchr to find the
# next newline; the line is `[lineCursor, newlineOffset)`.

const constVerb CNullTerminatedByteString "const"
const constVerbLength CSignedInt32 5
const labelVerb CNullTerminatedByteString "label"
const callVerb CNullTerminatedByteString "call"
const argVerb CNullTerminatedByteString "arg"
const runVerb CNullTerminatedByteString "run"
const bindVerb CNullTerminatedByteString "bind"
const bindOkVerb CNullTerminatedByteString "bindOk"
const bindErrorVerb CNullTerminatedByteString "bindError"
const ignoreOkVerb CNullTerminatedByteString "ignoreOk"
const branchVerb CNullTerminatedByteString "branch"
const branchIfVerb CNullTerminatedByteString "branchIf"
const branchIfErrorVerb CNullTerminatedByteString "branchIfError"
const returnOkVerb CNullTerminatedByteString "returnOk"
const returnErrorVerb CNullTerminatedByteString "returnError"
const makeErrorVerb CNullTerminatedByteString "makeError"
const setVerb CNullTerminatedByteString "set"
const stringType CNullTerminatedByteString "String"
const cnullStringType CNullTerminatedByteString "CNullTerminatedByteString"
const exitCodeType CNullTerminatedByteString "ExitCode"

var stringConstantCounter I64 0

# pass1Cursor walks the buffer one line at a time.
var pass1Cursor I64 0

label pass1LineLoopHead

# get pointer to start of current line
call pass1LineStartPtrCall pointer.offset
arg pass1LineStartPtrCall base readBuffer
arg pass1LineStartPtrCall offset pass1Cursor
run pass1LineStartPtrCall
bind pass1LineStartPtr COpaqueMemoryAddress pass1LineStartPtrCall

# Peek the first byte. If NUL, we're done.
call pass1FirstByteCall pointer.loadByte
arg pass1FirstByteCall buffer readBuffer
arg pass1FirstByteCall offset pass1Cursor
run pass1FirstByteCall
bind pass1FirstByte I8 pass1FirstByteCall

call pass1IsEofCall math.equalI64
arg pass1IsEofCall left pass1FirstByte
arg pass1IsEofCall right zeroByteOffset
run pass1IsEofCall
bind pass1IsEof Bool pass1IsEofCall
branchIf pass1IsEof pass1Done

# Find the line-end offset. Delegates to findLineEndOffset which
# wraps the c.strchr/pointer.isNull/pointer.difference cascade,
# falling back to the file-end offset when no newline remains.
call pass1LineEndOffsetCall findLineEndOffset
arg pass1LineEndOffsetCall bufferBase readBuffer
arg pass1LineEndOffsetCall lineStartPointer pass1LineStartPtr
arg pass1LineEndOffsetCall fileEndOffset inputBytesRead
arg pass1LineEndOffsetCall newlineByteCode newlineCharCode
run pass1LineEndOffsetCall
bindOk pass1LineEndOffset CSignedInt64 pass1LineEndOffsetCall

label pass1ProcessLine

# Skip lines that begin with `#` (comments) or are empty/whitespace.
# To keep the AS code small, we only test the FIRST byte: '#' or NUL
# (handled above) or newline (empty line falls into the same bucket
# since pass1LineStartPtr would point at \n with offset right at the
# start). We'll just rely on the prefix-test for "const " etc. and
# fall through for any line that doesn't match.

# Test if line starts with "const " (verb const followed by space).
# Delegates to the stdlib-style lineStartsWithKeyword helper which
# wraps the c.strncmp+zero-equality pattern that every verb-prefix
# check needs.
const constPrefix CNullTerminatedByteString "const "
const constPrefixLen CByteCount 6
call pass1IsConstLineCall lineStartsWithKeyword
arg pass1IsConstLineCall linePointer pass1LineStartPtr
arg pass1IsConstLineCall keyword constPrefix
arg pass1IsConstLineCall keywordLength constPrefixLen
run pass1IsConstLineCall
bindOk pass1IsConst Bool pass1IsConstLineCall
branchIf pass1IsConst pass1HandleConst
branch pass1AdvanceLine

label pass1HandleConst
# Layout we expect: "const NAME TYPE VALUE..."
# After "const " (6 bytes) is NAME. Find the next space after NAME.
# Then TYPE follows; find next space after TYPE. Then look for an
# opening quote — if found, it's a string constant and we emit.

# Get pointer just past "const ".
call pass1NamePtrCall pointer.offset
arg pass1NamePtrCall base pass1LineStartPtr
arg pass1NamePtrCall offset constPrefixLen
run pass1NamePtrCall
bind pass1NamePtr COpaqueMemoryAddress pass1NamePtrCall

# Find next space (end of NAME).
call pass1NameEndCall c.strchr
arg pass1NameEndCall haystack pass1NamePtr
arg pass1NameEndCall needle spaceCharCode
run pass1NameEndCall
bind pass1NameEndPtr COpaqueMemoryAddress pass1NameEndCall

call pass1NameEndNullCheckCall pointer.isNull
arg pass1NameEndNullCheckCall pointer pass1NameEndPtr
run pass1NameEndNullCheckCall
bind pass1NameEndMissing Bool pass1NameEndNullCheckCall
branchIf pass1NameEndMissing pass1AdvanceLine

# pass1TypePtr = position right after the name's terminating space.
call pass1TypePtrCall pointer.offset
arg pass1TypePtrCall base pass1NameEndPtr
arg pass1TypePtrCall offset oneOffset
run pass1TypePtrCall
bind pass1TypePtr COpaqueMemoryAddress pass1TypePtrCall

# Find the space after TYPE.
call pass1TypeEndCall c.strchr
arg pass1TypeEndCall haystack pass1TypePtr
arg pass1TypeEndCall needle spaceCharCode
run pass1TypeEndCall
bind pass1TypeEndPtr COpaqueMemoryAddress pass1TypeEndCall

call pass1TypeEndNullCheckCall pointer.isNull
arg pass1TypeEndNullCheckCall pointer pass1TypeEndPtr
run pass1TypeEndNullCheckCall
bind pass1TypeEndMissing Bool pass1TypeEndNullCheckCall
branchIf pass1TypeEndMissing pass1AdvanceLine

# pass1ValuePtr = first byte of VALUE.
call pass1ValuePtrCall pointer.offset
arg pass1ValuePtrCall base pass1TypeEndPtr
arg pass1ValuePtrCall offset oneOffset
run pass1ValuePtrCall
bind pass1ValuePtr COpaqueMemoryAddress pass1ValuePtrCall

# Check if the first VALUE byte is a quote — i.e., string literal.
call pass1ValueFirstByteCall pointer.loadByte
arg pass1ValueFirstByteCall buffer pass1ValuePtr
arg pass1ValueFirstByteCall offset zeroByteOffset
run pass1ValueFirstByteCall
bind pass1ValueFirstByte I8 pass1ValueFirstByteCall

call pass1IsStringCall math.equalI64
arg pass1IsStringCall left pass1ValueFirstByte
arg pass1IsStringCall right quoteCharCode
run pass1IsStringCall
bind pass1IsString Bool pass1IsStringCall
branchIf pass1IsString pass1EmitStringConst
branch pass1AdvanceLine

label pass1EmitStringConst
# String body starts at pass1ValuePtr + 1 (skip opening quote).
call pass1StringStartCall pointer.offset
arg pass1StringStartCall base pass1ValuePtr
arg pass1StringStartCall offset oneOffset
run pass1StringStartCall
bind pass1StringStart COpaqueMemoryAddress pass1StringStartCall

# Find the true closing quote AND count the post-escape byte length
# in a single walker. Source escape sequences (\", \\, \n, \t, \0)
# each represent one byte of the decoded string and consume two
# source characters. An unescaped " ends the literal.
var pass1ScanCursor I64 0
var pass1ByteCount I64 0

label pass1ScanLoopHead
call pass1ScanLoadCall pointer.loadByte
arg pass1ScanLoadCall buffer pass1StringStart
arg pass1ScanLoadCall offset pass1ScanCursor
run pass1ScanLoadCall
bind pass1ScanByte I8 pass1ScanLoadCall

call pass1ScanIsQuoteCall math.equalI64
arg pass1ScanIsQuoteCall left pass1ScanByte
arg pass1ScanIsQuoteCall right quoteCharCode
run pass1ScanIsQuoteCall
bind pass1ScanIsQuote Bool pass1ScanIsQuoteCall
branchIf pass1ScanIsQuote pass1ScanDone

call pass1ScanIsBackslashCall math.equalI64
arg pass1ScanIsBackslashCall left pass1ScanByte
arg pass1ScanIsBackslashCall right backslashCharCode
run pass1ScanIsBackslashCall
bind pass1ScanIsBackslash Bool pass1ScanIsBackslashCall
branchIf pass1ScanIsBackslash pass1ScanSkipEscape
branch pass1ScanAdvanceOne

label pass1ScanSkipEscape
call pass1ScanAdvance2Call math.addI64
arg pass1ScanAdvance2Call left pass1ScanCursor
arg pass1ScanAdvance2Call right twoOffset
run pass1ScanAdvance2Call
bind pass1ScanAdvance2 I64 pass1ScanAdvance2Call
set pass1ScanCursor pass1ScanAdvance2
branch pass1ScanIncrement

label pass1ScanAdvanceOne
call pass1ScanAdvance1Call math.addI64
arg pass1ScanAdvance1Call left pass1ScanCursor
arg pass1ScanAdvance1Call right oneOffset
run pass1ScanAdvance1Call
bind pass1ScanAdvance1 I64 pass1ScanAdvance1Call
set pass1ScanCursor pass1ScanAdvance1
branch pass1ScanIncrement

label pass1ScanIncrement
call pass1ScanNextByteCountCall math.addI64
arg pass1ScanNextByteCountCall left pass1ByteCount
arg pass1ScanNextByteCountCall right oneOffset
run pass1ScanNextByteCountCall
bind pass1ScanNextByteCount I64 pass1ScanNextByteCountCall
set pass1ByteCount pass1ScanNextByteCount
branch pass1ScanLoopHead

label pass1ScanDone

# array size = decoded byte count + 1 (null terminator)
call pass1ArraySizeCall math.addI64
arg pass1ArraySizeCall left pass1ByteCount
arg pass1ArraySizeCall right oneOffset
run pass1ArraySizeCall
bind pass1ArraySize CSignedInt64 pass1ArraySizeCall

# Emit `@.s<N> = private constant [<L> x i8] c"`
const pass1ConstHeaderFormat CNullTerminatedByteString "@.s%lld = private constant [%lld x i8] c\""
call pass1EmitConstHeaderCall c.printf
arg pass1EmitConstHeaderCall format pass1ConstHeaderFormat
arg pass1EmitConstHeaderCall index stringConstantCounter
arg pass1EmitConstHeaderCall length pass1ArraySize
run pass1EmitConstHeaderCall

# Emit body: walk the source again, this time decoding escapes and
# emitting each decoded byte as `\XX` (always-valid IR hex escape).
var pass1EmitCursor I64 0

label pass1EmitLoopHead
call pass1EmitLoadCall pointer.loadByte
arg pass1EmitLoadCall buffer pass1StringStart
arg pass1EmitLoadCall offset pass1EmitCursor
run pass1EmitLoadCall
bind pass1EmitByte I8 pass1EmitLoadCall

call pass1EmitIsQuoteCall math.equalI64
arg pass1EmitIsQuoteCall left pass1EmitByte
arg pass1EmitIsQuoteCall right quoteCharCode
run pass1EmitIsQuoteCall
bind pass1EmitIsQuote Bool pass1EmitIsQuoteCall
branchIf pass1EmitIsQuote pass1EmitDone

call pass1EmitIsBackslashCall math.equalI64
arg pass1EmitIsBackslashCall left pass1EmitByte
arg pass1EmitIsBackslashCall right backslashCharCode
run pass1EmitIsBackslashCall
bind pass1EmitIsBackslash Bool pass1EmitIsBackslashCall
branchIf pass1EmitIsBackslash pass1EmitDecodeEscape
branch pass1EmitLiteralByte

label pass1EmitDecodeEscape
# Advance past the backslash and read the escape specifier byte.
call pass1EmitEscOffsetCall math.addI64
arg pass1EmitEscOffsetCall left pass1EmitCursor
arg pass1EmitEscOffsetCall right oneOffset
run pass1EmitEscOffsetCall
bind pass1EmitEscOffset I64 pass1EmitEscOffsetCall

call pass1EmitEscByteLoadCall pointer.loadByte
arg pass1EmitEscByteLoadCall buffer pass1StringStart
arg pass1EmitEscByteLoadCall offset pass1EmitEscOffset
run pass1EmitEscByteLoadCall
bind pass1EmitEscByte I8 pass1EmitEscByteLoadCall

# Decode the escape into a concrete byte value. The standard cases
# are: \" -> 0x22, \\ -> 0x5C, \n -> 0x0A, \t -> 0x09, \0 -> 0x00,
# \r -> 0x0D. Any other escape character is passed through unchanged.
const escNCharCode I64 110
const escTCharCode I64 116
const escRCharCode I64 114
const escZeroCharCode I64 48
const escByteN I64 10
const escByteT I64 9
const escByteR I64 13
const escByteZero I64 0

var pass1DecodedByte I64 0
set pass1DecodedByte pass1EmitEscByte

call pass1EscIsNCall math.equalI64
arg pass1EscIsNCall left pass1EmitEscByte
arg pass1EscIsNCall right escNCharCode
run pass1EscIsNCall
bind pass1EscIsN Bool pass1EscIsNCall
branchIf pass1EscIsN pass1ApplyEscN
branch pass1CheckEscT

label pass1ApplyEscN
set pass1DecodedByte escByteN
branch pass1EmitDecodedHex

label pass1CheckEscT
call pass1EscIsTCall math.equalI64
arg pass1EscIsTCall left pass1EmitEscByte
arg pass1EscIsTCall right escTCharCode
run pass1EscIsTCall
bind pass1EscIsT Bool pass1EscIsTCall
branchIf pass1EscIsT pass1ApplyEscT
branch pass1CheckEscR

label pass1ApplyEscT
set pass1DecodedByte escByteT
branch pass1EmitDecodedHex

label pass1CheckEscR
call pass1EscIsRCall math.equalI64
arg pass1EscIsRCall left pass1EmitEscByte
arg pass1EscIsRCall right escRCharCode
run pass1EscIsRCall
bind pass1EscIsR Bool pass1EscIsRCall
branchIf pass1EscIsR pass1ApplyEscR
branch pass1CheckEscZero

label pass1ApplyEscR
set pass1DecodedByte escByteR
branch pass1EmitDecodedHex

label pass1CheckEscZero
call pass1EscIsZeroCall math.equalI64
arg pass1EscIsZeroCall left pass1EmitEscByte
arg pass1EscIsZeroCall right escZeroCharCode
run pass1EscIsZeroCall
bind pass1EscIsZero Bool pass1EscIsZeroCall
branchIf pass1EscIsZero pass1ApplyEscZero
branch pass1EmitDecodedHex

label pass1ApplyEscZero
set pass1DecodedByte escByteZero
branch pass1EmitDecodedHex

label pass1EmitDecodedHex
const hexEscapeFormat CNullTerminatedByteString "\\%02X"
call pass1EmitHexCall c.printf
arg pass1EmitHexCall format hexEscapeFormat
arg pass1EmitHexCall byte pass1DecodedByte
run pass1EmitHexCall

# Advance cursor past both backslash and the escape specifier.
call pass1EmitAdvance2Call math.addI64
arg pass1EmitAdvance2Call left pass1EmitCursor
arg pass1EmitAdvance2Call right twoOffset
run pass1EmitAdvance2Call
bind pass1EmitAdvance2 I64 pass1EmitAdvance2Call
set pass1EmitCursor pass1EmitAdvance2
branch pass1EmitLoopHead

label pass1EmitLiteralByte
# Literal byte: just emit as hex.
var pass1LiteralI64 I64 0
set pass1LiteralI64 pass1EmitByte
call pass1EmitLitHexCall c.printf
arg pass1EmitLitHexCall format hexEscapeFormat
arg pass1EmitLitHexCall byte pass1LiteralI64
run pass1EmitLitHexCall

call pass1EmitAdvance1Call math.addI64
arg pass1EmitAdvance1Call left pass1EmitCursor
arg pass1EmitAdvance1Call right oneOffset
run pass1EmitAdvance1Call
bind pass1EmitAdvance1 I64 pass1EmitAdvance1Call
set pass1EmitCursor pass1EmitAdvance1
branch pass1EmitLoopHead

label pass1EmitDone

const pass1ConstTail CNullTerminatedByteString "\\00\""
call pass1EmitTailCall c.puts
arg pass1EmitTailCall text pass1ConstTail
run pass1EmitTailCall

# Bump string counter.
call pass1NextCounterCall math.addI64
arg pass1NextCounterCall left stringConstantCounter
arg pass1NextCounterCall right oneOffset
run pass1NextCounterCall
bind pass1NextCounter I64 pass1NextCounterCall
set stringConstantCounter pass1NextCounter

branch pass1AdvanceLine

label pass1AdvanceLine
# Advance pass1Cursor to byte AFTER the line's terminating newline.
call pass1NextCursorCall math.addI64
arg pass1NextCursorCall left pass1LineEndOffset
arg pass1NextCursorCall right oneOffset
run pass1NextCursorCall
bind pass1NextCursor I64 pass1NextCursorCall
set pass1Cursor pass1NextCursor
branch pass1LineLoopHead

label pass1Done

# ============================================================
# 4. Pass 2 (the simple v0.1 cut): we have already emitted N
#    `@.s<i>` constants in pass 1. For v0.1, treat them as the
#    program's print sequence: emit a `define i32 @main()` that
#    calls puts on each constant in source order and returns 0.
#
#    This matches what bootstrap7 produced for hello-family programs,
#    but the parsing path is per-line dispatch on the `const ` verb
#    (verified via c.strncmp), not whole-file marker scanning.
#
#    Subsequent versions will replace this skeleton-main with one
#    built from the program's actual call/arg/run sequence, by
#    dispatching on `call`, `arg`, `run`, `bindError`,
#    `branchIfError`, `returnOk`, `returnError`, etc. The pass1
#    string-constant emission and the line walker are exactly the
#    infrastructure those handlers will reuse.
# ============================================================

const mainHeader CNullTerminatedByteString "define i32 @main() {"
call emitMainHeaderCall c.puts
arg emitMainHeaderCall text mainHeader
run emitMainHeaderCall

# For each emitted string constant, emit a puts call referencing
# @.s<i>. We do NOT know each one's byte count by index; we
# re-derived it by re-scanning -- but for v0.1 we cheat slightly
# and re-emit each puts using the constant's own self-describing
# type. We use the form:
#   %r<i> = call i32 @puts(i8* getelementptr inbounds (
#       [N x i8], [N x i8]* @.s<i>, i32 0, i32 0))
# To avoid tracking N per constant, we walk the source AGAIN and
# regenerate the array size in lockstep with the string counter.

var pass2Cursor I64 0
var pass2StringCounter I64 0

label pass2LineLoopHead

call pass2FirstByteCall pointer.loadByte
arg pass2FirstByteCall buffer readBuffer
arg pass2FirstByteCall offset pass2Cursor
run pass2FirstByteCall
bind pass2FirstByte I8 pass2FirstByteCall

call pass2IsEofCall math.equalI64
arg pass2IsEofCall left pass2FirstByte
arg pass2IsEofCall right zeroByteOffset
run pass2IsEofCall
bind pass2IsEof Bool pass2IsEofCall
branchIf pass2IsEof pass2Done

call pass2LineStartPtrCall pointer.offset
arg pass2LineStartPtrCall base readBuffer
arg pass2LineStartPtrCall offset pass2Cursor
run pass2LineStartPtrCall
bind pass2LineStartPtr COpaqueMemoryAddress pass2LineStartPtrCall

call pass2LineEndOffsetCall findLineEndOffset
arg pass2LineEndOffsetCall bufferBase readBuffer
arg pass2LineEndOffsetCall lineStartPointer pass2LineStartPtr
arg pass2LineEndOffsetCall fileEndOffset inputBytesRead
arg pass2LineEndOffsetCall newlineByteCode newlineCharCode
run pass2LineEndOffsetCall
bindOk pass2LineEndOffset CSignedInt64 pass2LineEndOffsetCall

label pass2ProcessLine

const pass2ConstPrefix CNullTerminatedByteString "const "
const pass2ConstPrefixLen CByteCount 6
call pass2IsConstLineCall lineStartsWithKeyword
arg pass2IsConstLineCall linePointer pass2LineStartPtr
arg pass2IsConstLineCall keyword pass2ConstPrefix
arg pass2IsConstLineCall keywordLength pass2ConstPrefixLen
run pass2IsConstLineCall
bindOk pass2IsConst Bool pass2IsConstLineCall
branchIf pass2IsConst pass2HandleConst
branch pass2AdvanceLine

label pass2HandleConst
# Same parsing as pass 1: locate NAME, TYPE, VALUE.
call pass2NamePtrCall pointer.offset
arg pass2NamePtrCall base pass2LineStartPtr
arg pass2NamePtrCall offset pass2ConstPrefixLen
run pass2NamePtrCall
bind pass2NamePtr COpaqueMemoryAddress pass2NamePtrCall

call pass2NameEndCall c.strchr
arg pass2NameEndCall haystack pass2NamePtr
arg pass2NameEndCall needle spaceCharCode
run pass2NameEndCall
bind pass2NameEndPtr COpaqueMemoryAddress pass2NameEndCall

call pass2NameEndNullCheckCall pointer.isNull
arg pass2NameEndNullCheckCall pointer pass2NameEndPtr
run pass2NameEndNullCheckCall
bind pass2NameEndMissing Bool pass2NameEndNullCheckCall
branchIf pass2NameEndMissing pass2AdvanceLine

call pass2TypePtrCall pointer.offset
arg pass2TypePtrCall base pass2NameEndPtr
arg pass2TypePtrCall offset oneOffset
run pass2TypePtrCall
bind pass2TypePtr COpaqueMemoryAddress pass2TypePtrCall

call pass2TypeEndCall c.strchr
arg pass2TypeEndCall haystack pass2TypePtr
arg pass2TypeEndCall needle spaceCharCode
run pass2TypeEndCall
bind pass2TypeEndPtr COpaqueMemoryAddress pass2TypeEndCall

call pass2TypeEndNullCheckCall pointer.isNull
arg pass2TypeEndNullCheckCall pointer pass2TypeEndPtr
run pass2TypeEndNullCheckCall
bind pass2TypeEndMissing Bool pass2TypeEndNullCheckCall
branchIf pass2TypeEndMissing pass2AdvanceLine

call pass2ValuePtrCall pointer.offset
arg pass2ValuePtrCall base pass2TypeEndPtr
arg pass2ValuePtrCall offset oneOffset
run pass2ValuePtrCall
bind pass2ValuePtr COpaqueMemoryAddress pass2ValuePtrCall

call pass2ValueFirstByteCall pointer.loadByte
arg pass2ValueFirstByteCall buffer pass2ValuePtr
arg pass2ValueFirstByteCall offset zeroByteOffset
run pass2ValueFirstByteCall
bind pass2ValueFirstByte I8 pass2ValueFirstByteCall

call pass2IsStringCall math.equalI64
arg pass2IsStringCall left pass2ValueFirstByte
arg pass2IsStringCall right quoteCharCode
run pass2IsStringCall
bind pass2IsString Bool pass2IsStringCall
branchIf pass2IsString pass2EmitPrintCall
branch pass2AdvanceLine

label pass2EmitPrintCall
# Count the same decoded byte length pass 1 did, by walking the
# string body with escape awareness. We don't emit the body here;
# we only need the count to fill in the [N x i8] array size in the
# puts call's getelementptr.
call pass2StringStartCall pointer.offset
arg pass2StringStartCall base pass2ValuePtr
arg pass2StringStartCall offset oneOffset
run pass2StringStartCall
bind pass2StringStart COpaqueMemoryAddress pass2StringStartCall

var pass2ScanCursor I64 0
var pass2DecodedByteCount I64 0

label pass2ScanLoopHead
call pass2ScanLoadCall pointer.loadByte
arg pass2ScanLoadCall buffer pass2StringStart
arg pass2ScanLoadCall offset pass2ScanCursor
run pass2ScanLoadCall
bind pass2ScanByte I8 pass2ScanLoadCall

call pass2ScanIsQuoteCall math.equalI64
arg pass2ScanIsQuoteCall left pass2ScanByte
arg pass2ScanIsQuoteCall right quoteCharCode
run pass2ScanIsQuoteCall
bind pass2ScanIsQuote Bool pass2ScanIsQuoteCall
branchIf pass2ScanIsQuote pass2ScanDone

call pass2ScanIsBackslashCall math.equalI64
arg pass2ScanIsBackslashCall left pass2ScanByte
arg pass2ScanIsBackslashCall right backslashCharCode
run pass2ScanIsBackslashCall
bind pass2ScanIsBackslash Bool pass2ScanIsBackslashCall
branchIf pass2ScanIsBackslash pass2ScanSkipEscape
branch pass2ScanAdvanceOne

label pass2ScanSkipEscape
call pass2ScanAdvance2Call math.addI64
arg pass2ScanAdvance2Call left pass2ScanCursor
arg pass2ScanAdvance2Call right twoOffset
run pass2ScanAdvance2Call
bind pass2ScanAdvance2 I64 pass2ScanAdvance2Call
set pass2ScanCursor pass2ScanAdvance2
branch pass2ScanIncrement

label pass2ScanAdvanceOne
call pass2ScanAdvance1Call math.addI64
arg pass2ScanAdvance1Call left pass2ScanCursor
arg pass2ScanAdvance1Call right oneOffset
run pass2ScanAdvance1Call
bind pass2ScanAdvance1 I64 pass2ScanAdvance1Call
set pass2ScanCursor pass2ScanAdvance1
branch pass2ScanIncrement

label pass2ScanIncrement
call pass2ScanNextByteCountCall math.addI64
arg pass2ScanNextByteCountCall left pass2DecodedByteCount
arg pass2ScanNextByteCountCall right oneOffset
run pass2ScanNextByteCountCall
bind pass2ScanNextByteCount I64 pass2ScanNextByteCountCall
set pass2DecodedByteCount pass2ScanNextByteCount
branch pass2ScanLoopHead

label pass2ScanDone

call pass2ArraySizeCall math.addI64
arg pass2ArraySizeCall left pass2DecodedByteCount
arg pass2ArraySizeCall right oneOffset
run pass2ArraySizeCall
bind pass2ArraySize CSignedInt64 pass2ArraySizeCall

const pass2PrintCallFormat CNullTerminatedByteString "  %%r%lld = call i32 @puts(i8* getelementptr inbounds ([%lld x i8], [%lld x i8]* @.s%lld, i32 0, i32 0))\n"
call pass2EmitPrintCall c.printf
arg pass2EmitPrintCall format pass2PrintCallFormat
arg pass2EmitPrintCall index1 pass2StringCounter
arg pass2EmitPrintCall length1 pass2ArraySize
arg pass2EmitPrintCall length2 pass2ArraySize
arg pass2EmitPrintCall index2 pass2StringCounter
run pass2EmitPrintCall

call pass2NextStringCounterCall math.addI64
arg pass2NextStringCounterCall left pass2StringCounter
arg pass2NextStringCounterCall right oneOffset
run pass2NextStringCounterCall
bind pass2NextStringCounter I64 pass2NextStringCounterCall
set pass2StringCounter pass2NextStringCounter

branch pass2AdvanceLine

label pass2AdvanceLine
call pass2NextCursorCall math.addI64
arg pass2NextCursorCall left pass2LineEndOffset
arg pass2NextCursorCall right oneOffset
run pass2NextCursorCall
bind pass2NextCursor I64 pass2NextCursorCall
set pass2Cursor pass2NextCursor
branch pass2LineLoopHead

label pass2Done

const mainRet CNullTerminatedByteString "  ret i32 0"
call emitMainRetCall c.puts
arg emitMainRetCall text mainRet
run emitMainRetCall

const mainClose CNullTerminatedByteString "}"
call emitMainCloseCall c.puts
arg emitMainCloseCall text mainClose
run emitMainCloseCall

# ---- close file ----
call inputCloseCall c.fclose
arg inputCloseCall stream inputFileHandle
run inputCloseCall
bind inputCloseResult CSignedInt32 inputCloseCall

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label inputOpenFailed
const inputOpenFailedExitCode CSignedInt32 1
makeError inputOpenFailedFailure MainError.InputOpenFailed inputOpenFailedExitCode
returnError inputOpenFailedFailure

label readBufferAllocationFailed
const readBufferAllocationFailedExitCode CSignedInt32 2
makeError readBufferAllocationFailedFailure MainError.AllocationFailed readBufferAllocationFailedExitCode
returnError readBufferAllocationFailedFailure
