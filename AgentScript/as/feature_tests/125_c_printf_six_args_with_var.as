# expect.stdout: a=1 b=2 c=3 d=4 e=5\n
# expect.exit: 0
project CPrintfSixArgsWithVar
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
purpose main "Exercise c.printf with 6 args (format + 5 trailing) where some args are vars (not binds). Probes whether PlusFive emits pre-call loads for var args."
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

# Use vars (mutable) instead of binds.
var aVar CSignedInt64 oneVal
var bVar CSignedInt64 twoVal
var cVar CSignedInt64 threeVal
var dVar CSignedInt64 fourVal
var eVar CSignedInt64 fiveVal

call sixPrintfCall c.printf
arg sixPrintfCall format sixFormat
arg sixPrintfCall a aVar
arg sixPrintfCall b bVar
arg sixPrintfCall c cVar
arg sixPrintfCall d dVar
arg sixPrintfCall e eVar
run sixPrintfCall
ignoreOk sixPrintfCall CSignedInt32

call freeCall c.free
arg freeCall ptr triggerBuffer
run freeCall
const successfulExitCode ExitCode 0
returnOk successfulExitCode
