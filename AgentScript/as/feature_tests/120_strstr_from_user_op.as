# expect.stdout: found here\n
# expect.exit: 0
project StrstrPtr
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation findIn
input findIn haystack CNullTerminatedByteString
input findIn needle CNullTerminatedByteString
output findIn Result CNullTerminatedByteString Void
label startFind
call ssCall c.strstr
arg ssCall haystack haystack
arg ssCall needle needle
run ssCall
bind found CNullTerminatedByteString ssCall
returnOk found

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
label startMain
const text CNullTerminatedByteString "this is found here"
const what CNullTerminatedByteString "found"
call fc findIn
arg fc haystack text
arg fc needle what
run fc
bindOk res CNullTerminatedByteString fc
call w console.writeLine
arg w console console
arg w text res
run w
ignoreOk w Void
const okExit ExitCode 0
returnOk okExit
