# expect.stdout: 17\n
# expect.exit: 0
project TypeAliasInt
target console
runtime AgentRuntime 0.1
type SmallInt I64
type SmallStep I64
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "var x SmallInt + const SmallStep should print 17."
invariant main "Type aliases resolving to I64 work transparently."
label startMain
const tenInitial SmallInt 10
const sevenStep SmallStep 7
var x SmallInt tenInitial
call addCall math.addI64
arg addCall left x
arg addCall right sevenStep
run addCall
bind sumValue I64 addCall
var resultVar SmallInt tenInitial
set resultVar sumValue
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value resultVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
