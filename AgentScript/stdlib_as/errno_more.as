project StdErrnoMoreSelfTest
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError TestFailed CSignedInt32

# ============================================================
# AGENTSCRIPT STANDARD LIBRARY: extended POSIX errno values.
#
# Operations:
#   errEAGAIN, errEBADF, errEBUSY, errECHILD, errEDEADLK,
#   errEDOM, errEILSEQ, errELOOP, errEMLINK, errENAMETOOLONG,
#   errENODEV, errENOEXEC, errENOLCK, errENOSYS, errENOTBLK,
#   errENOTEMPTY, errENOTSOCK, errENOTTY, errEROFS, errEWOULDBLOCK,
#   errEXDEV, errEMSGSIZE, errENETUNREACH, errETIMEDOUT.
# ============================================================

operation errEAGAIN
output errEAGAIN Result CSignedInt32 Void
memory errEAGAIN heap no
async errEAGAIN no
purpose errEAGAIN "EAGAIN (11)."
label start
const v CSignedInt32 11
returnOk v

operation errEBADF
output errEBADF Result CSignedInt32 Void
memory errEBADF heap no
async errEBADF no
purpose errEBADF "EBADF (9)."
label start
const v CSignedInt32 9
returnOk v

operation errEBUSY
output errEBUSY Result CSignedInt32 Void
memory errEBUSY heap no
async errEBUSY no
purpose errEBUSY "EBUSY (16)."
label start
const v CSignedInt32 16
returnOk v

operation errECHILD
output errECHILD Result CSignedInt32 Void
memory errECHILD heap no
async errECHILD no
purpose errECHILD "ECHILD (10)."
label start
const v CSignedInt32 10
returnOk v

operation errEDEADLK
output errEDEADLK Result CSignedInt32 Void
memory errEDEADLK heap no
async errEDEADLK no
purpose errEDEADLK "EDEADLK (35)."
label start
const v CSignedInt32 35
returnOk v

operation errEDOM
output errEDOM Result CSignedInt32 Void
memory errEDOM heap no
async errEDOM no
purpose errEDOM "EDOM (33)."
label start
const v CSignedInt32 33
returnOk v

operation errEILSEQ
output errEILSEQ Result CSignedInt32 Void
memory errEILSEQ heap no
async errEILSEQ no
purpose errEILSEQ "EILSEQ (84)."
label start
const v CSignedInt32 84
returnOk v

operation errELOOP
output errELOOP Result CSignedInt32 Void
memory errELOOP heap no
async errELOOP no
purpose errELOOP "ELOOP (40)."
label start
const v CSignedInt32 40
returnOk v

operation errEMLINK
output errEMLINK Result CSignedInt32 Void
memory errEMLINK heap no
async errEMLINK no
purpose errEMLINK "EMLINK (31)."
label start
const v CSignedInt32 31
returnOk v

operation errENAMETOOLONG
output errENAMETOOLONG Result CSignedInt32 Void
memory errENAMETOOLONG heap no
async errENAMETOOLONG no
purpose errENAMETOOLONG "ENAMETOOLONG (36)."
label start
const v CSignedInt32 36
returnOk v

operation errENODEV
output errENODEV Result CSignedInt32 Void
memory errENODEV heap no
async errENODEV no
purpose errENODEV "ENODEV (19)."
label start
const v CSignedInt32 19
returnOk v

operation errENOEXEC
output errENOEXEC Result CSignedInt32 Void
memory errENOEXEC heap no
async errENOEXEC no
purpose errENOEXEC "ENOEXEC (8)."
label start
const v CSignedInt32 8
returnOk v

operation errENOLCK
output errENOLCK Result CSignedInt32 Void
memory errENOLCK heap no
async errENOLCK no
purpose errENOLCK "ENOLCK (37)."
label start
const v CSignedInt32 37
returnOk v

operation errENOSYS
output errENOSYS Result CSignedInt32 Void
memory errENOSYS heap no
async errENOSYS no
purpose errENOSYS "ENOSYS (38)."
label start
const v CSignedInt32 38
returnOk v

operation errENOTEMPTY
output errENOTEMPTY Result CSignedInt32 Void
memory errENOTEMPTY heap no
async errENOTEMPTY no
purpose errENOTEMPTY "ENOTEMPTY (39)."
label start
const v CSignedInt32 39
returnOk v

operation errENOTDIR
output errENOTDIR Result CSignedInt32 Void
memory errENOTDIR heap no
async errENOTDIR no
purpose errENOTDIR "ENOTDIR (20)."
label start
const v CSignedInt32 20
returnOk v

operation errEISDIR
output errEISDIR Result CSignedInt32 Void
memory errEISDIR heap no
async errEISDIR no
purpose errEISDIR "EISDIR (21)."
label start
const v CSignedInt32 21
returnOk v

operation errEMFILE
output errEMFILE Result CSignedInt32 Void
memory errEMFILE heap no
async errEMFILE no
purpose errEMFILE "EMFILE (24)."
label start
const v CSignedInt32 24
returnOk v

operation errENOTTY
output errENOTTY Result CSignedInt32 Void
memory errENOTTY heap no
async errENOTTY no
purpose errENOTTY "ENOTTY (25)."
label start
const v CSignedInt32 25
returnOk v

operation errEROFS
output errEROFS Result CSignedInt32 Void
memory errEROFS heap no
async errEROFS no
purpose errEROFS "EROFS (30)."
label start
const v CSignedInt32 30
returnOk v

operation errEXDEV
output errEXDEV Result CSignedInt32 Void
memory errEXDEV heap no
async errEXDEV no
purpose errEXDEV "EXDEV (18)."
label start
const v CSignedInt32 18
returnOk v

operation errETIMEDOUT
output errETIMEDOUT Result CSignedInt32 Void
memory errETIMEDOUT heap no
async errETIMEDOUT no
purpose errETIMEDOUT "ETIMEDOUT (110)."
label start
const v CSignedInt32 110
returnOk v

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Smoke-test extra errno accessors. Prints OK."
label startMain
call s1 errEAGAIN
run s1
bindOk s1Res CSignedInt32 s1
const eleven CSignedInt32 11
call s1Check math.equalI64
arg s1Check left s1Res
arg s1Check right eleven
run s1Check
bind s1Ok Bool s1Check
branchIf s1Ok s1Lbl
branch testFailed
label s1Lbl
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
