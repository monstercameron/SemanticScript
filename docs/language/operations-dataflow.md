# Operations and Dataflow

An operation is the primary executable unit. It compiles to `main` when selected
by `entry console OPERATION`, or to a callable LLVM function when referenced by
another operation or when compiling library-style files.

## Operation Contract

```agentscript
operation addInvoiceAmounts
input addInvoiceAmounts invoiceSubtotal I64
input addInvoiceAmounts taxAmount I64
output addInvoiceAmounts I64
effect addInvoiceAmounts read memory.none
memory addInvoiceAmounts noHeapAllocation
async addInvoiceAmounts no
purpose addInvoiceAmounts "Return subtotal plus tax as a signed integer amount"
```

`input` lines define operation parameters. Opaque dependency inputs are kept as
source context but dropped from the LLVM ABI:

```text
console environment process httpRequest databaseClient clock
```

## Call Lifecycle

Every call is a named object.

```agentscript
call invoiceTotalCall math.addI64
arg invoiceTotalCall left invoiceSubtotal
arg invoiceTotalCall right taxAmount
run invoiceTotalCall
bind invoiceTotal I64 invoiceTotalCall
```

Lifecycle:

1. `call CALL TARGET` creates the call object.
2. `arg CALL ARG_NAME VALUE` attaches named argument edges.
3. `timeout`, `cancelOn`, or `useRetry` attach policies when needed.
4. `run CALL`, `start CALL`, or `submitWork WORK POOL` executes.
5. `bind`, `bindOk`, `bindError`, `ignoreOk`, or `ignoreValue` accounts for
   the result.

The compiler records call result SSA by call name so later lines can bind or
branch on it.

## User Operation Calls

```agentscript
operation addTwoValues
input addTwoValues leftValue I64
input addTwoValues rightValue I64
output addTwoValues I64

call sumCall math.addI64
arg sumCall left leftValue
arg sumCall right rightValue
run sumCall
bind sumValue I64 sumCall
returnValue sumValue

operation main
output main ExitCode

const leftInput I64 40
const rightInput I64 2
call answerCall addTwoValues
arg answerCall leftValue leftInput
arg answerCall rightValue rightInput
run answerCall
bind answerValue I64 answerCall
returnValue answerValue
```

For a same-file user operation call:

- parameter order comes from the callee's `input` lines;
- opaque inputs are skipped at the LLVM boundary;
- `output OP Result OK ERR` returns the OK payload type;
- `output OP TYPE` returns `TYPE`;
- `Void` currently uses an `i32` zero sentinel in ABI positions that need a
  concrete value.

## Variables

```agentscript
var runningTotal I64 0

call nextTotalCall math.addI64
arg nextTotalCall left runningTotal
arg nextTotalCall right stepAmount
run nextTotalCall
bind nextTotal I64 nextTotalCall
set local runningTotal nextTotal
```

`var NAME TYPE VALUE` allocates a mutable local slot. Reading the variable loads
its current value. `set local NAME VALUE` stores into that local slot.

Prefer `const` unless mutation is the real behavior being expressed.

## Control Flow

Labels are named basic blocks.

```agentscript
label loopStart

call doneCheckCall math.greaterThanI64
arg doneCheckCall left currentIndex
arg doneCheckCall right finalIndex
run doneCheckCall
bind isDone Bool doneCheckCall
branchIf isDone loopDone

# body...
branch loopStart

label loopDone
returnValue currentIndex
```

Schemas:

```text
label NAME
branch LABEL
branchIf CONDITION LABEL
branchIfError CALL LABEL
returnOk VALUE
returnError VALUE
returnValue VALUE
```

`branchIf` jumps when the condition is true and falls through otherwise.
Two-target branch syntax is legacy and should not be used.

## Ignoring Results

Ignoring a value is explicit:

```agentscript
ignoreOk writeGreetingCall Void
ignoreValue metricsFlushCall I64
```

Use these only when the discard is a real part of the contract. Fallible calls
should usually bind and branch on their error path instead.

