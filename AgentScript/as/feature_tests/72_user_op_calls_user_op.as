# expect.stdout: 6\n
# expect.exit: 0
project UserOpCallsUserOp
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation double
input double n CSignedInt64
output double Result CSignedInt64 Void
memory double heap no
async double no
purpose double "Return n * 2. Intentionally separate from the caller `tripleViaDouble` so the test exercises one user op invoking another."
invariant double "n is i64."
label startDouble
const two CSignedInt64 2
call mulCall math.multiplyI64
arg mulCall left n
arg mulCall right two
run mulCall
bind doubled CSignedInt64 mulCall
returnOk doubled

operation tripleViaDouble
input tripleViaDouble n CSignedInt64
output tripleViaDouble Result CSignedInt64 Void
memory tripleViaDouble heap no
async tripleViaDouble no
purpose tripleViaDouble "Compute n * 3 by doing double(n) + n."
invariant tripleViaDouble "Exercises user-op call from inside another user op."
label startTriple
call doubleCall double
arg doubleCall n n
run doubleCall
bindOk doubledValue CSignedInt64 doubleCall
call sumCall math.addI64
arg sumCall left doubledValue
arg sumCall right n
run sumCall
bind tripled CSignedInt64 sumCall
returnOk tripled

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Verify tripleViaDouble(2) == 6, exercising nested user-op calls."
invariant main "Output should be 6."
label startMain
const seed CSignedInt64 2
call tripleCall tripleViaDouble
arg tripleCall n seed
run tripleCall
bindOk tripledOutcome CSignedInt64 tripleCall
var resultStorage I64 0
set resultStorage tripledOutcome
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
