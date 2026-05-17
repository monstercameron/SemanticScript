# expect.stdout: 12\n
# expect.exit: 0
project FiveArgUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation sumFive
input sumFive a CSignedInt64
input sumFive b CSignedInt64
input sumFive c CSignedInt64
input sumFive d CSignedInt64
input sumFive e CSignedInt64
output sumFive Result CSignedInt64 Void
memory sumFive heap no
async sumFive no
purpose sumFive "Add five CSignedInt64 inputs. Exercises the 5-arg user-op call site emission."
invariant sumFive "All five params are i64."
label startSumFive
call sumAbCall math.addI64
arg sumAbCall left a
arg sumAbCall right b
run sumAbCall
bind sumAb CSignedInt64 sumAbCall
call sumAbcCall math.addI64
arg sumAbcCall left sumAb
arg sumAbcCall right c
run sumAbcCall
bind sumAbc CSignedInt64 sumAbcCall
call sumAbcdCall math.addI64
arg sumAbcdCall left sumAbc
arg sumAbcdCall right d
run sumAbcdCall
bind sumAbcd CSignedInt64 sumAbcdCall
call sumAbcdeCall math.addI64
arg sumAbcdeCall left sumAbcd
arg sumAbcdeCall right e
run sumAbcdeCall
bind total CSignedInt64 sumAbcdeCall
returnOk total

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "sumFive(1,2,3,2,4) == 12."
invariant main "Exercises 5-arg user-op call from main."
label startMain
const valOne CSignedInt64 1
const valTwo CSignedInt64 2
const valThree CSignedInt64 3
const valFour CSignedInt64 2
const valFive CSignedInt64 4
call sumCall sumFive
arg sumCall a valOne
arg sumCall b valTwo
arg sumCall c valThree
arg sumCall d valFour
arg sumCall e valFive
run sumCall
bindOk total CSignedInt64 sumCall
var totalStorage I64 0
set totalStorage total
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value totalStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
