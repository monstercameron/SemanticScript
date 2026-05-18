# ============================================================
# Fourth stdlib import smoke (runtime + I/O modules)
# ============================================================
#
# # rationale: closes the import-test coverage for the remaining
#   four modules: convert (numeric / pointer width adapters),
#   assert (typed AssertionError contracts), stdio (byte / string /
#   integer writers), and process (lifecycle terminators).
#   Together with the three earlier smoke tests, this completes
#   coverage of every stdlib_as module behind importModule —
#   28 of 28 modules verified importable + usable from a
#   downstream program.
#
# # invariant: convert/assert/stdio assertions hold; the process
#   module is only imported (not invoked) because its terminators
#   exitProcessWithStatusCode / abortCurrentProcess would kill the
#   test runner. The import succeeding is the unit test for
#   process — call sites are reachable through unreachable branches
#   so the linker still validates them.
#
# # security: writes through stdio land on stdout; assertions
#   may write a short 'assert!\n' banner on failure. Test passes
#   imply no failure banner is emitted.
#
# # timing: O(1) ops + a few stdio byte writes; entire test
#   runs in microseconds.
#
# # observability: prints exactly one line of output —
#   the stdio writer test prints '12345\n', then 'OK\n' on success.

project StdlibImportSmokeRuntime
target console
runtime AgentRuntime 0.1
entry console stdlibImportSmokeRuntimeMain

error MainError
errorCase MainError StdlibImportRuntimeSmokeAssertionFailed

# ----- imports under test (last four modules) -----
importModule convert
importModule assert
importModule stdio
importModule process

operation stdlibImportSmokeRuntimeMain
input stdlibImportSmokeRuntimeMain console Console
output stdlibImportSmokeRuntimeMain Result ExitCode MainError
effect stdlibImportSmokeRuntimeMain write console.stdout
memoryHeap stdlibImportSmokeRuntimeMain yes
async stdlibImportSmokeRuntimeMain no
purpose stdlibImportSmokeRuntimeMain "Verify the last four stdlib modules (convert / assert / stdio / process) are reachable through importModule. process is imported but not invoked because its terminators would kill the test."
invariant stdlibImportSmokeRuntimeMain "convert + assert + stdio all return their declared values. process imports cleanly. Exit 0; stdout includes the integer-writer output then 'OK\\n'."

label startStdlibImportSmokeRuntimeMain

# ---- convert: widenSignedInt32ToSignedInt64(-1) preserves the value ----
const negativeOneAsSignedInt32Import CSignedInt32 -1
const negativeOneAsSignedInt64Import CSignedInt64 -1
call assertWidenNegativeOneCall widenSignedInt32ToSignedInt64
arg assertWidenNegativeOneCall inputValue negativeOneAsSignedInt32Import
run assertWidenNegativeOneCall
bind widenNegativeOneResult CSignedInt64 assertWidenNegativeOneCall
call checkWidenNegativeOneCall math.equalI64
arg checkWidenNegativeOneCall left widenNegativeOneResult
arg checkWidenNegativeOneCall right negativeOneAsSignedInt64Import
run checkWidenNegativeOneCall
bind widenNegativeOneOk Bool checkWidenNegativeOneCall
branchIf widenNegativeOneOk widenNegativeOneHolds
branch stdlibImportRuntimeAssertionFailed
label widenNegativeOneHolds

# ---- convert: convertByteValueToUnsignedInt32(-1) == 255 ----
const expectedTwoFiftyFiveForByteCoerceImport CSignedInt32 255
call assertByteCoerceCall convertByteValueToUnsignedInt32
arg assertByteCoerceCall signExtendedByteValue negativeOneAsSignedInt32Import
run assertByteCoerceCall
bind byteCoerceResult CSignedInt32 assertByteCoerceCall
call checkByteCoerceCall math.equalI64
arg checkByteCoerceCall left byteCoerceResult
arg checkByteCoerceCall right expectedTwoFiftyFiveForByteCoerceImport
run checkByteCoerceCall
bind byteCoerceOk Bool checkByteCoerceCall
branchIf byteCoerceOk byteCoerceHolds
branch stdlibImportRuntimeAssertionFailed
label byteCoerceHolds

# ---- convert: convertFloat64ToSignedInt64(3.7) == 3 (truncate toward zero) ----
const threePointSevenForFloatToIntImport CFloat64 3.7
const threeExpectedForFloatToIntImport CSignedInt64 3
call assertFloatToIntCall convertFloat64ToSignedInt64
arg assertFloatToIntCall inputValue threePointSevenForFloatToIntImport
run assertFloatToIntCall
bind floatToIntResult CSignedInt64 assertFloatToIntCall
call checkFloatToIntCall math.equalI64
arg checkFloatToIntCall left floatToIntResult
arg checkFloatToIntCall right threeExpectedForFloatToIntImport
run checkFloatToIntCall
bind floatToIntOk Bool checkFloatToIntCall
branchIf floatToIntOk floatToIntHolds
branch stdlibImportRuntimeAssertionFailed
label floatToIntHolds

# ---- assert: requireConditionTrue(true) succeeds — branchIfError continues ----
const conditionTrueForAssertImport Bool true
call assertImportedConditionTrueCall requireConditionTrue
arg assertImportedConditionTrueCall conditionValue conditionTrueForAssertImport
run assertImportedConditionTrueCall
bindOk requireOkResult CSignedInt32 assertImportedConditionTrueCall
bindError requireErrResult CSignedInt32 assertImportedConditionTrueCall
branchIfError assertImportedConditionTrueCall stdlibImportRuntimeAssertionFailed

# ---- assert: requireSignedInt64ValuesEqual(42, 42) succeeds ----
const fortyTwoForRequireEqualImport CSignedInt64 42
call assertImportedRequireEqualCall requireSignedInt64ValuesEqual
arg assertImportedRequireEqualCall leftValue fortyTwoForRequireEqualImport
arg assertImportedRequireEqualCall rightValue fortyTwoForRequireEqualImport
run assertImportedRequireEqualCall
bindOk requireEqualOkResult CSignedInt32 assertImportedRequireEqualCall
bindError requireEqualErrResult CSignedInt32 assertImportedRequireEqualCall
branchIfError assertImportedRequireEqualCall stdlibImportRuntimeAssertionFailed

# ---- stdio: writeSignedInt64DecimalToStandardOutput(12345) writes the digits + newline.
# The byte count we get back should be 5 (digit count, not including newline).
const twelveThousandThreeHundredFortyFiveForStdioImport CSignedInt64 12345
const fiveExpectedDigitCountForStdioImport CByteCount 5
call assertStdioWriteIntegerCall writeSignedInt64DecimalToStandardOutput
arg assertStdioWriteIntegerCall inputValue twelveThousandThreeHundredFortyFiveForStdioImport
run assertStdioWriteIntegerCall
bind stdioWriteIntegerResult CByteCount assertStdioWriteIntegerCall
call checkStdioWriteIntegerCall math.equalI64
arg checkStdioWriteIntegerCall left stdioWriteIntegerResult
arg checkStdioWriteIntegerCall right fiveExpectedDigitCountForStdioImport
run checkStdioWriteIntegerCall
bind stdioWriteIntegerOk Bool checkStdioWriteIntegerCall
branchIf stdioWriteIntegerOk stdioWriteIntegerHolds
branch stdlibImportRuntimeAssertionFailed
label stdioWriteIntegerHolds

# ---- process: imports must resolve. We deliberately do NOT call
#      exitProcessWithStatusCode or abortCurrentProcess — both
#      terminate the process and would kill the test runner.
#      The unreachable branch below references both names so the
#      compiler links them, proving the import surface is wired up.
const zeroForProcessImport CSignedInt32 0
const importedFalseGuard Bool false
branchIf importedFalseGuard unreachableProcessSinkBranch
branch stdioWriteIntegerPostProcess
label unreachableProcessSinkBranch
call neverExitCall exitProcessWithStatusCode
arg neverExitCall exitStatusCode zeroForProcessImport
run neverExitCall
call neverAbortCall abortCurrentProcess
run neverAbortCall
branch stdioWriteIntegerPostProcess
label stdioWriteIntegerPostProcess

const runtimeImportSuccessMessage CNullTerminatedByteString "OK"
call writeRuntimeImportSuccessCall console.writeLine
arg writeRuntimeImportSuccessCall console console
arg writeRuntimeImportSuccessCall text runtimeImportSuccessMessage
run writeRuntimeImportSuccessCall
ignoreOk writeRuntimeImportSuccessCall Void
const runtimeImportExitOk ExitCode 0
returnOk runtimeImportExitOk

label stdlibImportRuntimeAssertionFailed
makeError stdlibImportRuntimeFailure MainError.StdlibImportRuntimeSmokeAssertionFailed
returnError stdlibImportRuntimeFailure
