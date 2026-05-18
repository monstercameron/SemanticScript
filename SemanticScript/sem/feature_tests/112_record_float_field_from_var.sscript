# expect.stdout: 7.500000\n
# expect.exit: 0
project RecordFloatFromVar
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Sample layout row align 8
purpose Sample "A single CFloat64 measurement."
field Sample value CFloat64

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Build value via float var + math.addF64, then fieldSet from the float var."
invariant main "5.0 + 2.5 = 7.5, stored in Sample.value, read back, printed."
label startMain
const fiveF CFloat64 5.0
const twoAndHalfF CFloat64 2.5
var liveF CFloat64 fiveF
call addCall math.addF64
arg addCall left liveF
arg addCall right twoAndHalfF
run addCall
bind sumF CFloat64 addCall
set liveF sumF
new mySample Sample
fieldSet mySample value liveF
fieldGet finalF CFloat64 mySample value
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value finalF
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
