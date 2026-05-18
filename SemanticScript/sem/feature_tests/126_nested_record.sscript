# expect.stdout: 15\n
# expect.exit: 0
# expect.xfail: nested records — `field Segment start Point` where Point is itself a record is treated as a flat i64 field (single alloca %mySegment_start). fieldSet/fieldGet with dotted paths (`start.x`) emit `%mySegment_start.x` which has no alloca. Requires (a) `new` walker to detect record-typed fields and recursively emit `%<var>_<outer>_<inner> = alloca <innerType>` per leaf field, and (b) fieldSet/fieldGet to translate dots to underscores when emitting SSA names. No corpus program currently uses nested records.
project NestedRecord
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError

record Point layout row align 8
field Point x I64
field Point y I64

record Segment layout row align 8
field Segment start Point
field Segment finish Point

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Construct Segment containing two nested Points, sum all four field values. 1+2+5+7 = 15."
invariant main "Output is '15\\n'."
label startMain
new mySegment Segment
const oneVal I64 1
const twoVal I64 2
const fiveVal I64 5
const sevenVal I64 7
fieldSet mySegment start.x oneVal
fieldSet mySegment start.y twoVal
fieldSet mySegment finish.x fiveVal
fieldSet mySegment finish.y sevenVal
fieldGet sx I64 mySegment start.x
fieldGet sy I64 mySegment start.y
fieldGet fx I64 mySegment finish.x
fieldGet fy I64 mySegment finish.y
call sum1Call math.addI64
arg sum1Call left sx
arg sum1Call right sy
run sum1Call
bind partial1 I64 sum1Call
call sum2Call math.addI64
arg sum2Call left fx
arg sum2Call right fy
run sum2Call
bind partial2 I64 sum2Call
call totalCall math.addI64
arg totalCall left partial1
arg totalCall right partial2
run totalCall
bind totalResult I64 totalCall
var totalVar I64 oneVal
set totalVar totalResult
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value totalVar
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
