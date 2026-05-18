# expect.stdout: 25\n
# expect.exit: 0
project RecordFieldSetFromVar
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Counter layout row align 8
purpose Counter "A single I64 counter wrapped in a record."
field Counter value I64

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Mutate a local var (compute 25 via add), then store it into a record field via fieldSet."
invariant main "Counter.value ends at 25; print it."
label startMain
const fifteenC I64 15
const tenC I64 10
var localVal I64 fifteenC
call sumCall math.addI64
arg sumCall left localVal
arg sumCall right tenC
run sumCall
bind sumResult I64 sumCall
set localVal sumResult
new myCounter Counter
fieldSet myCounter value localVal
fieldGet readValue I64 myCounter value
var displayStore I64 0
set displayStore readValue
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value displayStore
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
