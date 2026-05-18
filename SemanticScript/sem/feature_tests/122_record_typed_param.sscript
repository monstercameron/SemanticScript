# expect.stdout: 19\n
# expect.exit: 0
# Record-typed user-op parameter: pass a Point by value to sumPoint, which
# reads .x and .y via fieldGet on the param and returns their sum.
project RecordTypedParam
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

record Point layout row align 8
field Point x I64
field Point y I64

operation sumPoint
input sumPoint p Point
output sumPoint Result I64 Void
memory sumPoint heap no
async sumPoint no
purpose sumPoint "Return p.x + p.y. Exercises a record-typed input parameter: callee reads each field via fieldGet directly on the param name."
invariant sumPoint "Returns x + y."
label startSumPoint
fieldGet xVal I64 p x
fieldGet yVal I64 p y
call addCall math.addI64
arg addCall left xVal
arg addCall right yVal
run addCall
bind sumRes I64 addCall
returnOk sumRes

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap auto
async main no
purpose main "Construct a Point {x:7,y:12} and call sumPoint(p). Expect 19."
invariant main "Output is '19\\n'."
label startMain
new myPoint Point
const xInit I64 7
const yInit I64 12
fieldSet myPoint x xInit
fieldSet myPoint y yInit
call sumPointCall sumPoint
arg sumPointCall p myPoint
run sumPointCall
bind sumResult I64 sumPointCall
var sumVar I64 xInit
set sumVar sumResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value sumVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
