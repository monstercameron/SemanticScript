# expect.stdout: 19\n
# expect.exit: 0
project RecordPointSum
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Point layout row align 8
purpose Point "A two-dimensional integer point."
field Point x I64
field Point y I64

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Build a Point record, set both fields, read them back, print x+y."
invariant main "Output is '19\\n' (7 + 12)."
label startMain
const xVal I64 7
const yVal I64 12
new myPoint Point
fieldSet myPoint x xVal
fieldSet myPoint y yVal
fieldGet xRead I64 myPoint x
fieldGet yRead I64 myPoint y
call sumCall math.addI64
arg sumCall left xRead
arg sumCall right yRead
run sumCall
bind sumResult I64 sumCall
var sumStore I64 0
set sumStore sumResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value sumStore
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
