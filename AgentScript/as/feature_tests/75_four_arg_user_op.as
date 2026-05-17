# expect.stdout: 14\n
# expect.exit: 0
project FourArgUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation fmaInt
input fmaInt a CSignedInt64
input fmaInt b CSignedInt64
input fmaInt c CSignedInt64
input fmaInt d CSignedInt64
output fmaInt Result CSignedInt64 Void
memory fmaInt heap no
async fmaInt no
purpose fmaInt "Compute a*b + c*d using four CSignedInt64 inputs. Exercises a 4-arg user-op call site emission path."
invariant fmaInt "All four inputs are i64."
label startFmaInt
call mulAbCall math.multiplyI64
arg mulAbCall left a
arg mulAbCall right b
run mulAbCall
bind ab CSignedInt64 mulAbCall
call mulCdCall math.multiplyI64
arg mulCdCall left c
arg mulCdCall right d
run mulCdCall
bind cd CSignedInt64 mulCdCall
call sumCall math.addI64
arg sumCall left ab
arg sumCall right cd
run sumCall
bind total CSignedInt64 sumCall
returnOk total

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "fmaInt(2,3,4,2) == 2*3 + 4*2 == 14."
invariant main "Exercises a 4-arg user-op call from main."
label startMain
const twoVal CSignedInt64 2
const threeVal CSignedInt64 3
const fourVal CSignedInt64 4
const anotherTwo CSignedInt64 2
call computeCall fmaInt
arg computeCall a twoVal
arg computeCall b threeVal
arg computeCall c fourVal
arg computeCall d anotherTwo
run computeCall
bindOk computedTotal CSignedInt64 computeCall
var totalStorage I64 0
set totalStorage computedTotal
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value totalStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
