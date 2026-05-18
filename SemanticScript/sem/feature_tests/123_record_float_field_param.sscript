# expect.stdout: 5.500000\n
# expect.exit: 0
project RecordFloatFieldParam
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

record Measurement layout row align 8
field Measurement reading CFloat64
field Measurement scale CFloat64

operation scaleReading
input scaleReading m Measurement
output scaleReading Result CFloat64 Void
memory scaleReading heap no
async scaleReading no
purpose scaleReading "Return m.reading * m.scale. Probes whether the record-param call-site helpers handle CFloat64 fields."
invariant scaleReading "Returns reading * scale."
label startScaleReading
fieldGet readingVal CFloat64 m reading
fieldGet scaleVal CFloat64 m scale
call mulCall math.multiplyF64
arg mulCall left readingVal
arg mulCall right scaleVal
run mulCall
bind productResult CFloat64 mulCall
returnOk productResult

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap auto
async main no
purpose main "Construct Measurement {reading:2.2, scale:2.5} and call scaleReading(m). Expect 5.5."
invariant main "Output is '5.500000\\n'."
label startMain
new myMeasurement Measurement
const readingInit CFloat64 2.2
const scaleInit CFloat64 2.5
fieldSet myMeasurement reading readingInit
fieldSet myMeasurement scale scaleInit
call scaleReadingCall scaleReading
arg scaleReadingCall m myMeasurement
run scaleReadingCall
bind productResult CFloat64 scaleReadingCall
var productVar CFloat64 readingInit
set productVar productResult
call writeCall console.writeFloatLine
arg writeCall console console
arg writeCall value productVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
