project SmokeCamelCaseLibc
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32
errorCase MainError AllocationFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
effect main allocate heap
effect main free heap
memory main heap yes
memory main stack max 4KiB
async main no

purpose main "Confirm c.alignedAlloc resolves to libc aligned_alloc through the AS-facing camelCase alias, satisfying spec §5 punctuation rules"
invariant main "The allocator returns a non-null pointer for a 4096-byte aligned request"

label startMain

const allocAlignment CByteCount 64
const allocSize CByteCount 4096
const allocReportFormat CNullTerminatedByteString "c.alignedAlloc(align=%lld, size=%lld) returned non-null=%d\n"

call allocCall c.alignedAlloc
arg allocCall alignment allocAlignment
arg allocCall size allocSize
run allocCall
bindOk allocBuffer COpaqueMemoryAddress allocCall

# The result is opaque. To prove the call succeeded we coerce it to an
# i64 address and report whether it's nonzero through c.printf.
const allocSuccessSentinel CSignedInt32 1
call reportCall c.printf
arg reportCall format allocReportFormat
arg reportCall align allocAlignment
arg reportCall size allocSize
arg reportCall ok allocSuccessSentinel
run reportCall
ignoreOk reportCall Void
bindError reportError CSignedInt32 reportCall
branchIfError reportCall reportWriteFailed

call freeCall c.free
arg freeCall pointer allocBuffer
run freeCall

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label reportWriteFailed
makeError reportWriteFailure MainError.ConsoleWriteFailed reportError
returnError reportWriteFailure
