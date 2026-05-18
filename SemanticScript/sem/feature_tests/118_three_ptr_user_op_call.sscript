# expect.stdout: ok\n
# expect.exit: 0
project ThreePtrParams
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

operation pickFirstMatching
input pickFirstMatching needle CNullTerminatedByteString
input pickFirstMatching choice1 CNullTerminatedByteString
input pickFirstMatching choice2 CNullTerminatedByteString
output pickFirstMatching Result CNullTerminatedByteString Void
purpose pickFirstMatching "Return choice1 if needle==choice1 else choice2."
label startPick
call eqCall c.strcmp
arg eqCall left needle
arg eqCall right choice1
run eqCall
bind cmp CSignedInt64 eqCall
const zeroEq CSignedInt64 0
call isEqCall math.equalI64
arg isEqCall left cmp
arg isEqCall right zeroEq
run isEqCall
bind isEq Bool isEqCall
branchIf isEq returnChoice1
returnOk choice2
label returnChoice1
returnOk choice1

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
label startMain
const wanted CNullTerminatedByteString "ok"
const a CNullTerminatedByteString "ok"
const b CNullTerminatedByteString "no"
call pickCall pickFirstMatching
arg pickCall needle wanted
arg pickCall choice1 a
arg pickCall choice2 b
run pickCall
bindOk picked CNullTerminatedByteString pickCall
call w console.writeLine
arg w console console
arg w text picked
run w
ignoreOk w Void
const okExit ExitCode 0
returnOk okExit
