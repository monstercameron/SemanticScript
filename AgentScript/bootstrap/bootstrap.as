project Bootstrap
target console
runtime AgentRuntime 0.1

entry console main

error MainError
errorCase MainError ConsoleWriteFailed CSignedInt32

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
memory main stack max 4KiB
async main no

purpose main "Self-host stage 1: an AgentScript program that emits LLVM IR for the canonical hello-world program to stdout, ready to be piped through clang into a native executable. Running clang on the output of this binary produces an exe equivalent to as/hello.as."
invariant main "Each c.puts call writes exactly one line of LLVM IR (plus the puts-added newline byte)"
invariant main "The emitted IR is self-contained: declares puts, defines main, exits zero on success"
guarantee main "The byte sequence written to stdout is valid input to `clang -O2 -x ir - -o hello.exe`"

label startMain

# LLVM IR for: print "Hello, World!" to stdout, return 0.
# AS string escapes: \" → "    \\ → \    so c\"…\\00\" becomes the C-style
# null-terminated string literal LLVM IR expects: c"…\00".
const irModuleBanner CNullTerminatedByteString "; ModuleID = 'AgentScriptSelfHosted'"
const irTargetTriple CNullTerminatedByteString "target triple = \"x86_64-pc-windows-msvc\""
const irGreetingConstant CNullTerminatedByteString "@.greetingText = private constant [14 x i8] c\"Hello, World!\\00\""
const irExternPuts CNullTerminatedByteString "declare i32 @puts(i8*)"
const irMainHeader CNullTerminatedByteString "define i32 @main() {"
const irPutsCall CNullTerminatedByteString "  %putsResult = call i32 @puts(i8* getelementptr inbounds ([14 x i8], [14 x i8]* @.greetingText, i32 0, i32 0))"
const irReturnZero CNullTerminatedByteString "  ret i32 0"
const irMainFooter CNullTerminatedByteString "}"

# rationale: One c.puts per IR line. puts() appends \n automatically so each
# AS string is exactly one line of source IR. The total output is the seven
# lines below in order, which clang accepts as a complete LLVM IR module.

call writeIrModuleBannerCall c.puts
arg writeIrModuleBannerCall text irModuleBanner
run writeIrModuleBannerCall
ignoreOk writeIrModuleBannerCall Void
bindError writeIrModuleBannerError CSignedInt32 writeIrModuleBannerCall
branchIfError writeIrModuleBannerCall irModuleBannerWriteFailed

call writeIrTargetTripleCall c.puts
arg writeIrTargetTripleCall text irTargetTriple
run writeIrTargetTripleCall
ignoreOk writeIrTargetTripleCall Void
bindError writeIrTargetTripleError CSignedInt32 writeIrTargetTripleCall
branchIfError writeIrTargetTripleCall irTargetTripleWriteFailed

call writeIrGreetingConstantCall c.puts
arg writeIrGreetingConstantCall text irGreetingConstant
run writeIrGreetingConstantCall
ignoreOk writeIrGreetingConstantCall Void
bindError writeIrGreetingConstantError CSignedInt32 writeIrGreetingConstantCall
branchIfError writeIrGreetingConstantCall irGreetingConstantWriteFailed

call writeIrExternPutsCall c.puts
arg writeIrExternPutsCall text irExternPuts
run writeIrExternPutsCall
ignoreOk writeIrExternPutsCall Void
bindError writeIrExternPutsError CSignedInt32 writeIrExternPutsCall
branchIfError writeIrExternPutsCall irExternPutsWriteFailed

call writeIrMainHeaderCall c.puts
arg writeIrMainHeaderCall text irMainHeader
run writeIrMainHeaderCall
ignoreOk writeIrMainHeaderCall Void
bindError writeIrMainHeaderError CSignedInt32 writeIrMainHeaderCall
branchIfError writeIrMainHeaderCall irMainHeaderWriteFailed

call writeIrPutsCallCall c.puts
arg writeIrPutsCallCall text irPutsCall
run writeIrPutsCallCall
ignoreOk writeIrPutsCallCall Void
bindError writeIrPutsCallError CSignedInt32 writeIrPutsCallCall
branchIfError writeIrPutsCallCall irPutsCallWriteFailed

call writeIrReturnZeroCall c.puts
arg writeIrReturnZeroCall text irReturnZero
run writeIrReturnZeroCall
ignoreOk writeIrReturnZeroCall Void
bindError writeIrReturnZeroError CSignedInt32 writeIrReturnZeroCall
branchIfError writeIrReturnZeroCall irReturnZeroWriteFailed

call writeIrMainFooterCall c.puts
arg writeIrMainFooterCall text irMainFooter
run writeIrMainFooterCall
ignoreOk writeIrMainFooterCall Void
bindError writeIrMainFooterError CSignedInt32 writeIrMainFooterCall
branchIfError writeIrMainFooterCall irMainFooterWriteFailed

const successfulExitCode ExitCode 0
returnOk successfulExitCode

label irModuleBannerWriteFailed
makeError irModuleBannerWriteFailure MainError.ConsoleWriteFailed writeIrModuleBannerError
returnError irModuleBannerWriteFailure

label irTargetTripleWriteFailed
makeError irTargetTripleWriteFailure MainError.ConsoleWriteFailed writeIrTargetTripleError
returnError irTargetTripleWriteFailure

label irGreetingConstantWriteFailed
makeError irGreetingConstantWriteFailure MainError.ConsoleWriteFailed writeIrGreetingConstantError
returnError irGreetingConstantWriteFailure

label irExternPutsWriteFailed
makeError irExternPutsWriteFailure MainError.ConsoleWriteFailed writeIrExternPutsError
returnError irExternPutsWriteFailure

label irMainHeaderWriteFailed
makeError irMainHeaderWriteFailure MainError.ConsoleWriteFailed writeIrMainHeaderError
returnError irMainHeaderWriteFailure

label irPutsCallWriteFailed
makeError irPutsCallWriteFailure MainError.ConsoleWriteFailed writeIrPutsCallError
returnError irPutsCallWriteFailure

label irReturnZeroWriteFailed
makeError irReturnZeroWriteFailure MainError.ConsoleWriteFailed writeIrReturnZeroError
returnError irReturnZeroWriteFailure

label irMainFooterWriteFailed
makeError irMainFooterWriteFailure MainError.ConsoleWriteFailed writeIrMainFooterError
returnError irMainFooterWriteFailure
