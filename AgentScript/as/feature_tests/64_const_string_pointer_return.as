# expect.stdout: ok\n
# expect.exit: 0
project ConstStringPointerReturn
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation getOkLabel
output getOkLabel Result CNullTerminatedByteString Void
memory getOkLabel heap no
async getOkLabel no
purpose getOkLabel "Return a fixed string-const. Exercises pointer-returning user-op signature plus returnOk-of-string-const path that emits `ret i8* getelementptr inbounds`."
invariant getOkLabel "Used by main to print the returned message."
label startGetOkLabel
const okMessage CNullTerminatedByteString "ok"
returnOk okMessage

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Print the first byte of the message returned by the pointer-returning user op getOkLabel via c.putchar, plus a 'k' and newline."
invariant main "Uses c.putchar so the walker fires (the legacy string-replay path skips user-op definitions)."
label startMain
call getMessageCall getOkLabel
run getMessageCall
bindOk theMessage CNullTerminatedByteString getMessageCall
const zeroByteIndex I64 0
call firstByteCall pointer.loadByte
arg firstByteCall buffer theMessage
arg firstByteCall offset zeroByteIndex
run firstByteCall
bind firstByteValue I8 firstByteCall
call writeFirstCall c.putchar
arg writeFirstCall c firstByteValue
run writeFirstCall
const oneByteIndex I64 1
call secondByteCall pointer.loadByte
arg secondByteCall buffer theMessage
arg secondByteCall offset oneByteIndex
run secondByteCall
bind secondByteValue I8 secondByteCall
call writeSecondCall c.putchar
arg writeSecondCall c secondByteValue
run writeSecondCall
const newlineByte CSignedInt32 10
call writeNewlineCall c.putchar
arg writeNewlineCall c newlineByte
run writeNewlineCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
