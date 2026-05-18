# expect.stdout: 30\n
# expect.exit: 0
project MultiParamChained
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation addAndDouble
input addAndDouble a CSignedInt64
input addAndDouble b CSignedInt64
output addAndDouble Result CSignedInt64 Void
memory addAndDouble heap no
async addAndDouble no
purpose addAndDouble "(a + b) * 2."
invariant addAndDouble "Compose add and multiply inline."
label startAddAndDouble
const twoLit I64 2
call addCall math.addI64
arg addCall left a
arg addCall right b
run addCall
bind sumValue I64 addCall
call mulCall math.multiplyI64
arg mulCall left sumValue
arg mulCall right twoLit
run mulCall
bind doubledValue I64 mulCall
returnOk doubledValue

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Compute (5 + 10) * 2 = 30."
invariant main "Outputs 30."
label startMain
const fiveInitial I64 5
const tenInitial I64 10
var leftValue I64 fiveInitial
var rightValue I64 tenInitial
call computeCall addAndDouble
arg computeCall a leftValue
arg computeCall b rightValue
run computeCall
bindOk computeResult I64 computeCall
var outputVar I64 fiveInitial
set outputVar computeResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value outputVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
