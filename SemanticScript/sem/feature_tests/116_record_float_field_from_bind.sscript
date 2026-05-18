# expect.stdout: 12.500000\n
# expect.exit: 0
project FsetFloatBind
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Sample layout row align 8
field Sample value CFloat64

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Compute via math.addF64 → bind → fieldSet (no intermediate var)."
invariant main "10.0 + 2.5 = 12.5 stored directly from bind."
label startMain
const tenF CFloat64 10.0
const twoAndHalfF CFloat64 2.5
call addCall math.addF64
arg addCall left tenF
arg addCall right twoAndHalfF
run addCall
bind sumF CFloat64 addCall
new mySample Sample
fieldSet mySample value sumF
fieldGet readF CFloat64 mySample value
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value readF
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
