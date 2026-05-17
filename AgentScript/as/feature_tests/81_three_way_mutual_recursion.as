# expect.stdout: 9\n
# expect.exit: 0
project ThreeWayMutualRecursion
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError Placeholder CSignedInt32

# Mutual recursion across three operations. Walks a counter through
# three different "color" stages on each cycle. The cycle is:
#   red(n) -> if n == 0 return 0 else 1 + green(n - 1)
#   green(n) -> if n == 0 return 0 else 1 + blue(n - 1)
#   blue(n) -> if n == 0 return 0 else 1 + red(n - 1)
# Exercises three-way mutual recursion.

operation red
input red n CSignedInt64
output red Result CSignedInt64 Void
memory red heap no
async red no
purpose red "Recurse through green when n > 0."
invariant red "Total recursion depth across red/green/blue equals n."
label startRed
const zeroDepth CSignedInt64 0
const oneAccum CSignedInt64 1
call doneCheckRed math.equalI64
arg doneCheckRed left n
arg doneCheckRed right zeroDepth
run doneCheckRed
bind isDoneRed Bool doneCheckRed
branchIf isDoneRed redBaseCase
call decRed math.subtractI64
arg decRed left n
arg decRed right oneAccum
run decRed
bind decRedValue CSignedInt64 decRed
call recurseRed green
arg recurseRed n decRedValue
run recurseRed
bindOk recurseRedResult CSignedInt64 recurseRed
call addRed math.addI64
arg addRed left recurseRedResult
arg addRed right oneAccum
run addRed
bind redTotal CSignedInt64 addRed
returnOk redTotal
label redBaseCase
returnOk zeroDepth

operation green
input green n CSignedInt64
output green Result CSignedInt64 Void
memory green heap no
async green no
purpose green "Recurse through blue when n > 0."
invariant green "Mutual recursion middle leg."
label startGreen
const zeroDepth CSignedInt64 0
const oneAccum CSignedInt64 1
call doneCheckGreen math.equalI64
arg doneCheckGreen left n
arg doneCheckGreen right zeroDepth
run doneCheckGreen
bind isDoneGreen Bool doneCheckGreen
branchIf isDoneGreen greenBaseCase
call decGreen math.subtractI64
arg decGreen left n
arg decGreen right oneAccum
run decGreen
bind decGreenValue CSignedInt64 decGreen
call recurseGreen blue
arg recurseGreen n decGreenValue
run recurseGreen
bindOk recurseGreenResult CSignedInt64 recurseGreen
call addGreen math.addI64
arg addGreen left recurseGreenResult
arg addGreen right oneAccum
run addGreen
bind greenTotal CSignedInt64 addGreen
returnOk greenTotal
label greenBaseCase
returnOk zeroDepth

operation blue
input blue n CSignedInt64
output blue Result CSignedInt64 Void
memory blue heap no
async blue no
purpose blue "Recurse back into red when n > 0."
invariant blue "Mutual recursion third leg."
label startBlue
const zeroDepth CSignedInt64 0
const oneAccum CSignedInt64 1
call doneCheckBlue math.equalI64
arg doneCheckBlue left n
arg doneCheckBlue right zeroDepth
run doneCheckBlue
bind isDoneBlue Bool doneCheckBlue
branchIf isDoneBlue blueBaseCase
call decBlue math.subtractI64
arg decBlue left n
arg decBlue right oneAccum
run decBlue
bind decBlueValue CSignedInt64 decBlue
call recurseBlue red
arg recurseBlue n decBlueValue
run recurseBlue
bindOk recurseBlueResult CSignedInt64 recurseBlue
call addBlue math.addI64
arg addBlue left recurseBlueResult
arg addBlue right oneAccum
run addBlue
bind blueTotal CSignedInt64 addBlue
returnOk blueTotal
label blueBaseCase
returnOk zeroDepth

operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Verify red(9) == 9 (each step adds 1, three colors cycle three times)."
invariant main "Three-way mutual recursion preserves the count."
label startMain
const startDepth CSignedInt64 9
call runCall red
arg runCall n startDepth
run runCall
bindOk totalDepth CSignedInt64 runCall
var totalStorage I64 0
set totalStorage totalDepth
call writeCall console.writeIntegerLine
arg writeCall console console
arg writeCall value totalStorage
run writeCall
ignoreOk writeCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode
