# expect.stdout: a=1 b=2 c=3 d=4 e=5\n
# expect.exit: 0
project CPrintfSixArgs
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap auto
async main no
purpose main "Exercise c.printf with 6 args (format + 5 trailing i64 binds). Probes whether bootstrap dispatches 6-arg c.printf through the PlusFive emitter rather than falling to UNHANDLED."
invariant main "Output is 'a=1 b=2 c=3 d=4 e=5\\n'."
label startMain
const triggerSize CByteCount 1
call walkerTriggerCall c.malloc
arg walkerTriggerCall size triggerSize
run walkerTriggerCall
bind triggerBuffer COpaqueMemoryAddress walkerTriggerCall

const sixFormat CNullTerminatedByteString "a=%lld b=%lld c=%lld d=%lld e=%lld\n"
const oneVal CSignedInt64 1
const twoVal CSignedInt64 2
const threeVal CSignedInt64 3
const fourVal CSignedInt64 4
const fiveVal CSignedInt64 5

# Promote each constant to a bind via a no-op user op, so each arg is a bind
# (matches the PlusFive emitter's bind-only operand expectation).
call promoteOneCall identityI64
arg promoteOneCall n oneVal
run promoteOneCall
bindOk oneBind CSignedInt64 promoteOneCall

call promoteTwoCall identityI64
arg promoteTwoCall n twoVal
run promoteTwoCall
bindOk twoBind CSignedInt64 promoteTwoCall

call promoteThreeCall identityI64
arg promoteThreeCall n threeVal
run promoteThreeCall
bindOk threeBind CSignedInt64 promoteThreeCall

call promoteFourCall identityI64
arg promoteFourCall n fourVal
run promoteFourCall
bindOk fourBind CSignedInt64 promoteFourCall

call promoteFiveCall identityI64
arg promoteFiveCall n fiveVal
run promoteFiveCall
bindOk fiveBind CSignedInt64 promoteFiveCall

call sixPrintfCall c.printf
arg sixPrintfCall format sixFormat
arg sixPrintfCall a oneBind
arg sixPrintfCall b twoBind
arg sixPrintfCall c threeBind
arg sixPrintfCall d fourBind
arg sixPrintfCall e fiveBind
run sixPrintfCall
ignoreOk sixPrintfCall CSignedInt32

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode

operation identityI64
input identityI64 n CSignedInt64
output identityI64 Result CSignedInt64 Void
memory identityI64 heap no
async identityI64 no
purpose identityI64 "Return the input unchanged. Used to promote a const to a bind so subsequent operand dispatches treat it as a bind."
invariant identityI64 "Returns n."
label startIdentityI64
returnOk n
