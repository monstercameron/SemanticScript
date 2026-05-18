# expect.stdout: 0\n
# expect.exit: 0
project TwoPtrParams
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation cmpStrs
input cmpStrs left CNullTerminatedByteString
input cmpStrs right CNullTerminatedByteString
output cmpStrs Result CSignedInt64 Void
purpose cmpStrs "Compare two strings via c.strcmp; return the result as i64."
label startCmp
call cmpCall c.strcmp
arg cmpCall left left
arg cmpCall right right
run cmpCall
bind cmpResult CSignedInt64 cmpCall
returnOk cmpResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
label startMain
const a CNullTerminatedByteString "hello"
const b CNullTerminatedByteString "hello"
call doCmp cmpStrs
arg doCmp left a
arg doCmp right b
run doCmp
bindOk cmpVal CSignedInt64 doCmp
var displayStore I64 0
set displayStore cmpVal
call w console.writeIntegerLine
arg w console console
arg w value displayStore
run w
ignoreOk w Void
const okExit ExitCode 0
returnOk okExit
