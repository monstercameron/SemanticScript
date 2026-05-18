# expect.stdout: 0\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet lower the refined-syntax `operationBody runtimeBinding` / `runtimeBinding NAME TARGET` to a libc call — so compareCString becomes a stub that crashes at runtime. Direct ascc.py compilation works correctly (`python compiler/ascc.py THIS_FILE --emit-ir /tmp/x.ll && clang /tmp/x.ll -o /tmp/x.exe && /tmp/x.exe` prints `0` and exits 0). Closing means propagating the runtimeBinding lowering into bootstrap.
project RefinedStrcmpRuntime
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

# Inline a minimal refined-syntax operation definition: compareCString is
# declared as a runtimeBinding to runtime.cstring.compare, which ascc.py
# now lowers to a real `call i32 @strcmp(...)` body. This test verifies
# that the wired binding actually executes strcmp at runtime, not just
# the compile-time stub.

error CStringCompareError
errorCase CStringCompareError InvalidCStringInput
errorCase CStringCompareError RuntimeCompareFailed

operation compareCString
input compareCString left CNullTerminatedByteString
input compareCString right CNullTerminatedByteString
output compareCString Result CSignedInt32 CStringCompareError
effect compareCString read left
effect compareCString read right
memoryHeap compareCString no
async compareCString no
operationBody compareCString runtimeBinding
purpose compareCString "Compare two null-terminated byte strings (strcmp wrapper via refined-syntax runtimeBinding)."
runtimeBinding compareCString runtime.cstring.compare

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Call compareCString with two identical strings and print the strcmp result (expected 0)."
invariant main "Output is '0\\n'."
label startMain
const leftText CNullTerminatedByteString "agent"
const rightText CNullTerminatedByteString "agent"
call cmpCall compareCString
arg cmpCall left leftText
arg cmpCall right rightText
run cmpCall
bindOk cmpResult CSignedInt32 cmpCall
var cmpVar I64 0
set cmpVar cmpResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value cmpVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
