project StdStddefSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <stddef.h>-style accessors.
#
# C's <stddef.h> is mostly typedefs (size_t, ptrdiff_t, etc.) and the
# NULL macro. AgentScript has those types natively (CByteCount,
# COpaqueMemoryAddress); this file exposes the few callable surfaces.
#
# Operations:
#   nullPointer            - returns the NULL pointer.
#   bytesInPointer         - sizeof(void*) on x86-64 = 8.
#   bytesInSignedInt32     - 4.
#   bytesInSignedInt64     - 8.
#   bytesInFloat64         - 8.
# ============================================================


operation nullPointer
output nullPointer Result COpaqueMemoryAddress Void
memory nullPointer heap no
async nullPointer no
purpose nullPointer "Returns the NULL pointer (i8* 0)."
label startNullPointer
# We synthesize NULL by allocating zero bytes? No — use c.malloc(0) which
# is implementation-defined. Cleaner: build via pointer arithmetic from
# a known global. Simplest: malloc(1), then free + reuse pattern is bad.
# AgentScript today doesn't have an explicit "null pointer literal" in
# the type system, so we lean on the c.* ABI: every c.* function that
# CAN return NULL exposes it. We use c.getenv with an obviously absent
# variable.
const absentVar CNullTerminatedByteString "AGENTSCRIPT_DEFINITELY_NOT_SET_4D7F00"
call envCall c.getenv
arg envCall name absentVar
run envCall
bind nullVal CNullTerminatedByteString envCall
# This SHOULD be NULL on every reasonable host. If it isn't (someone
# defined this oddly named env var) the caller's NULL check will not
# fire, which is a non-fatal smoke-test annoyance.
returnOk nullVal


operation bytesInPointer
output bytesInPointer Result CSignedInt64 Void
memory bytesInPointer heap no
async bytesInPointer no
purpose bytesInPointer "sizeof(void*) on the AgentScript target (x86-64 Windows): 8 bytes."
label startBytesInPointer
const v CSignedInt64 8
returnOk v


operation bytesInSignedInt32
output bytesInSignedInt32 Result CSignedInt64 Void
memory bytesInSignedInt32 heap no
async bytesInSignedInt32 no
purpose bytesInSignedInt32 "sizeof(int32_t) = 4."
label startBytesInSignedInt32
const v CSignedInt64 4
returnOk v


operation bytesInSignedInt64
output bytesInSignedInt64 Result CSignedInt64 Void
memory bytesInSignedInt64 heap no
async bytesInSignedInt64 no
purpose bytesInSignedInt64 "sizeof(int64_t) = 8."
label startBytesInSignedInt64
const v CSignedInt64 8
returnOk v


operation bytesInFloat64
output bytesInFloat64 Result CSignedInt64 Void
memory bytesInFloat64 heap no
async bytesInFloat64 no
purpose bytesInFloat64 "sizeof(double) = 8."
label startBytesInFloat64
const v CSignedInt64 8
returnOk v


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test the stddef accessors. Prints OK."

label startMain
call s1 bytesInPointer
run s1
bindOk s1Res CSignedInt64 s1
const eight CSignedInt64 8
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right eight
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1OkLabel
branch testFailed
label s1OkLabel

call s2 bytesInSignedInt32
run s2
bindOk s2Res CSignedInt64 s2
const four CSignedInt64 4
call s2Check math.equalI64
arg s2Check left s2Res
arg s2Check right four
run s2Check
bind s2Ok Bool s2Check
branchIf s2Ok s2OkLabel
branch testFailed
label s2OkLabel

const charO CSignedInt32 79
const charK CSignedInt32 75
const charNl CSignedInt32 10
call putO c.putchar
arg putO c charO
run putO
call putK c.putchar
arg putK c charK
run putK
call putNl c.putchar
arg putNl c charNl
run putNl

const exitOk ExitCode 0
returnOk exitOk

label testFailed
const exitFail CSignedInt32 1
makeError testFailure MainError.TestFailed exitFail
returnError testFailure
