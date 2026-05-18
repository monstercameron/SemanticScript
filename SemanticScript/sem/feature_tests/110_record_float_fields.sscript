# expect.stdout: 4.500000\n
# expect.exit: 0
project RecordFloatField
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

record Measurement layout row align 8
purpose Measurement "A single measurement reading with two CFloat64 components."
field Measurement reading CFloat64
field Measurement scale CFloat64

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Build a Measurement record with float fields, sum the two fields, print the sum as a float."
invariant main "1.5 + 3.0 = 4.5 → '4.500000\\n'."
label startMain
const oneHalfF CFloat64 1.5
const threeF CFloat64 3.0
new myReading Measurement
fieldSet myReading reading oneHalfF
fieldSet myReading scale threeF
fieldGet readingF CFloat64 myReading reading
fieldGet scaleF CFloat64 myReading scale
call sumCall math.addF64
arg sumCall left readingF
arg sumCall right scaleF
run sumCall
bind sumF CFloat64 sumCall
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value sumF
run writeCall
ignoreOk writeCall Void
const okExit ExitCode 0
returnOk okExit
