project StdErrnoSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: <errno.h>-style codes.
#
# Standard POSIX errno values exposed as accessors. Mirrors the integer
# constants from the POSIX errno header.
#
# Operations (each returns the canonical numeric code):
#   errEPERM, errENOENT, errESRCH, errEINTR, errEIO, errENOMEM,
#   errEACCES, errEFAULT, errEEXIST, errENOTDIR, errEISDIR,
#   errEINVAL, errENFILE, errEMFILE, errENOSPC, errEPIPE,
#   errERANGE
#
# Plus errorMessage(code) -> CNullTerminatedByteString that returns a
# short message for the known codes (uses no libc strerror).
# ============================================================

operation errEPERM
output errEPERM Result CSignedInt32 Void
memory errEPERM heap no
async errEPERM no
purpose errEPERM "Operation not permitted (1)."
label startEPERM
const v CSignedInt32 1
returnOk v

operation errENOENT
output errENOENT Result CSignedInt32 Void
memory errENOENT heap no
async errENOENT no
purpose errENOENT "No such file or directory (2)."
label startENOENT
const v CSignedInt32 2
returnOk v

operation errESRCH
output errESRCH Result CSignedInt32 Void
memory errESRCH heap no
async errESRCH no
purpose errESRCH "No such process (3)."
label startESRCH
const v CSignedInt32 3
returnOk v

operation errEINTR
output errEINTR Result CSignedInt32 Void
memory errEINTR heap no
async errEINTR no
purpose errEINTR "Interrupted system call (4)."
label startEINTR
const v CSignedInt32 4
returnOk v

operation errEIO
output errEIO Result CSignedInt32 Void
memory errEIO heap no
async errEIO no
purpose errEIO "Input/output error (5)."
label startEIO
const v CSignedInt32 5
returnOk v

operation errENOMEM
output errENOMEM Result CSignedInt32 Void
memory errENOMEM heap no
async errENOMEM no
purpose errENOMEM "Out of memory (12)."
label startENOMEM
const v CSignedInt32 12
returnOk v

operation errEACCES
output errEACCES Result CSignedInt32 Void
memory errEACCES heap no
async errEACCES no
purpose errEACCES "Permission denied (13)."
label startEACCES
const v CSignedInt32 13
returnOk v

operation errEFAULT
output errEFAULT Result CSignedInt32 Void
memory errEFAULT heap no
async errEFAULT no
purpose errEFAULT "Bad address (14)."
label startEFAULT
const v CSignedInt32 14
returnOk v

operation errEEXIST
output errEEXIST Result CSignedInt32 Void
memory errEEXIST heap no
async errEEXIST no
purpose errEEXIST "File exists (17)."
label startEEXIST
const v CSignedInt32 17
returnOk v

operation errEINVAL
output errEINVAL Result CSignedInt32 Void
memory errEINVAL heap no
async errEINVAL no
purpose errEINVAL "Invalid argument (22)."
label startEINVAL
const v CSignedInt32 22
returnOk v

operation errENOSPC
output errENOSPC Result CSignedInt32 Void
memory errENOSPC heap no
async errENOSPC no
purpose errENOSPC "No space left on device (28)."
label startENOSPC
const v CSignedInt32 28
returnOk v

operation errEPIPE
output errEPIPE Result CSignedInt32 Void
memory errEPIPE heap no
async errEPIPE no
purpose errEPIPE "Broken pipe (32)."
label startEPIPE
const v CSignedInt32 32
returnOk v

operation errERANGE
output errERANGE Result CSignedInt32 Void
memory errERANGE heap no
async errERANGE no
purpose errERANGE "Result out of range (34)."
label startERANGE
const v CSignedInt32 34
returnOk v


# ============================================================
# errorMessage(code) -> short C-string description.
# Pure AS chain of code comparisons; no strerror() libc call.
# ============================================================
operation errorMessage
input errorMessage code CSignedInt32
output errorMessage Result CNullTerminatedByteString Void
memory errorMessage heap no
async errorMessage no
purpose errorMessage "Return a short English message for known POSIX errno values, or 'unknown error' for others. Pure-AS — no libc strerror."

label startErrorMessage
const msgEPERM CNullTerminatedByteString "operation not permitted"
const msgENOENT CNullTerminatedByteString "no such file or directory"
const msgESRCH CNullTerminatedByteString "no such process"
const msgEINTR CNullTerminatedByteString "interrupted system call"
const msgEIO CNullTerminatedByteString "input/output error"
const msgENOMEM CNullTerminatedByteString "out of memory"
const msgEACCES CNullTerminatedByteString "permission denied"
const msgEFAULT CNullTerminatedByteString "bad address"
const msgEEXIST CNullTerminatedByteString "file exists"
const msgEINVAL CNullTerminatedByteString "invalid argument"
const msgENOSPC CNullTerminatedByteString "no space left on device"
const msgEPIPE CNullTerminatedByteString "broken pipe"
const msgERANGE CNullTerminatedByteString "result out of range"
const msgUnknown CNullTerminatedByteString "unknown error"

const c1 CSignedInt32 1
const c2 CSignedInt32 2
const c3 CSignedInt32 3
const c4 CSignedInt32 4
const c5 CSignedInt32 5
const c12 CSignedInt32 12
const c13 CSignedInt32 13
const c14 CSignedInt32 14
const c17 CSignedInt32 17
const c22 CSignedInt32 22
const c28 CSignedInt32 28
const c32 CSignedInt32 32
const c34 CSignedInt32 34

call eq1 math.equalI64
arg eq1 left code
arg eq1 right c1
run eq1
bind is1 Bool eq1
branchIf is1 retEPERM
call eq2 math.equalI64
arg eq2 left code
arg eq2 right c2
run eq2
bind is2 Bool eq2
branchIf is2 retENOENT
call eq3 math.equalI64
arg eq3 left code
arg eq3 right c3
run eq3
bind is3 Bool eq3
branchIf is3 retESRCH
call eq4 math.equalI64
arg eq4 left code
arg eq4 right c4
run eq4
bind is4 Bool eq4
branchIf is4 retEINTR
call eq5 math.equalI64
arg eq5 left code
arg eq5 right c5
run eq5
bind is5 Bool eq5
branchIf is5 retEIO
call eq12 math.equalI64
arg eq12 left code
arg eq12 right c12
run eq12
bind is12 Bool eq12
branchIf is12 retENOMEM
call eq13 math.equalI64
arg eq13 left code
arg eq13 right c13
run eq13
bind is13 Bool eq13
branchIf is13 retEACCES
call eq14 math.equalI64
arg eq14 left code
arg eq14 right c14
run eq14
bind is14 Bool eq14
branchIf is14 retEFAULT
call eq17 math.equalI64
arg eq17 left code
arg eq17 right c17
run eq17
bind is17 Bool eq17
branchIf is17 retEEXIST
call eq22 math.equalI64
arg eq22 left code
arg eq22 right c22
run eq22
bind is22 Bool eq22
branchIf is22 retEINVAL
call eq28 math.equalI64
arg eq28 left code
arg eq28 right c28
run eq28
bind is28 Bool eq28
branchIf is28 retENOSPC
call eq32 math.equalI64
arg eq32 left code
arg eq32 right c32
run eq32
bind is32 Bool eq32
branchIf is32 retEPIPE
call eq34 math.equalI64
arg eq34 left code
arg eq34 right c34
run eq34
bind is34 Bool eq34
branchIf is34 retERANGE
returnOk msgUnknown

label retEPERM
returnOk msgEPERM
label retENOENT
returnOk msgENOENT
label retESRCH
returnOk msgESRCH
label retEINTR
returnOk msgEINTR
label retEIO
returnOk msgEIO
label retENOMEM
returnOk msgENOMEM
label retEACCES
returnOk msgEACCES
label retEFAULT
returnOk msgEFAULT
label retEEXIST
returnOk msgEEXIST
label retEINVAL
returnOk msgEINVAL
label retENOSPC
returnOk msgENOSPC
label retEPIPE
returnOk msgEPIPE
label retERANGE
returnOk msgERANGE


# ============================================================
# Smoke test
# ============================================================

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test errno accessors and errorMessage. Prints OK."

label startMain
call e1 errENOENT
run e1
bindOk e1Res CSignedInt32 e1
const two32 CSignedInt32 2
call e1Check math.equalI64
arg e1Check left e1Res
arg e1Check right two32
run e1Check
bind e1Ok Bool e1Check
branchIf e1Ok e1OkLabel
branch testFailed
label e1OkLabel

# errorMessage(2) should be a non-empty string.
call em1 errorMessage
arg em1 code two32
run em1
bindOk em1Res CNullTerminatedByteString em1

# Check that the first byte isn't NUL (i.e., the message is non-empty).
const zeroOffset CByteCount 0
call peekCall pointer.loadByte
arg peekCall buffer em1Res
arg peekCall offset zeroOffset
run peekCall
bind firstByte I8 peekCall
const zeroByteI64 I64 0
call notNullCall math.notEqualI64
arg notNullCall left firstByte
arg notNullCall right zeroByteI64
run notNullCall
bind isNonEmpty Bool notNullCall
branchIf isNonEmpty msgOkLabel
branch testFailed
label msgOkLabel

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
