# Operations and Dataflow

An operation is the primary executable unit. It compiles to `main` when selected
by `entry console OPERATION`, or to a callable LLVM function when referenced by
another operation or when compiling library-style files.

## Operation Contract

```semanticscript
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

```semanticscript
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

```semanticscript
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

```semanticscript
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

```semanticscript
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
returnVoid
```

`branchIf` jumps when the condition is true and falls through otherwise.
Two-target branch syntax is legacy and should not be used.

Use `returnVoid` for operations declared `output OP Void` or `output OP CVoid`.
The user-operation ABI still lowers that path to the internal zero sentinel, but
the source no longer has to carry a fake `CSignedInt32` value just to satisfy the
ABI. `returnVoid` is rejected on non-Void outputs; non-Void operations should
continue to use `returnValue`, `returnOk`, or `returnError` as appropriate.

## JSON CRUD Dataflow

JSON document calls follow the same call lifecycle. Parse or create a
`JsonDocument`, bind the root cursor, navigate to child cursors with fallible
calls, branch on access errors before using the cursor, mutate the tree, then
serialize through caller-owned scratch storage.

```semanticscript
operation renameFirstTodoHandler
input renameFirstTodoHandler requestBody JsonText
input renameFirstTodoHandler scratch JsonScratchBuffer
output renameFirstTodoHandler Result JsonText JsonAccessError
effect renameFirstTodoHandler read json.document.tree
effect renameFirstTodoHandler write json.document.tree

const documentCapacity JsonCapacityBytes 4096
const scratchCapacity JsonCapacityBytes 4096
const todosPath JsonPath ".todos"
const firstTodoIndex I64 0
const titleField JsonFieldName "title"
const replacementTitle JsonStringValue "ship json"

call parseBodyCall json.createDocument
arg parseBodyCall jsonText requestBody
arg parseBodyCall capacityBytes documentCapacity
run parseBodyCall
bindOk document JsonDocument parseBodyCall
bindError parseError JsonAccessError parseBodyCall
branchIfError parseBodyCall parseFailed
defer destroyDocumentDefer json.destroyDocument document

call todosCursorCall json.cursorAtPath
arg todosCursorCall document document
arg todosCursorCall path todosPath
run todosCursorCall
bindOk todosCursor JsonCursor todosCursorCall
bindError todosCursorError JsonAccessError todosCursorCall
branchIfError todosCursorCall todosCursorFailed

call firstTodoCall json.arrayElementAt
arg firstTodoCall document document
arg firstTodoCall cursor todosCursor
arg firstTodoCall index firstTodoIndex
run firstTodoCall
bindOk firstTodoCursor JsonCursor firstTodoCall
bindError firstTodoError JsonAccessError firstTodoCall
branchIfError firstTodoCall firstTodoFailed

call setTitleCall json.setObjectFieldString
arg setTitleCall document document
arg setTitleCall cursor firstTodoCursor
arg setTitleCall fieldName titleField
arg setTitleCall value replacementTitle
run setTitleCall
ignoreOk setTitleCall CSignedInt32
bindError setTitleError JsonAccessError setTitleCall
branchIfError setTitleCall setTitleFailed

call serializeCall json.serializeDocument
arg serializeCall document document
arg serializeCall scratch scratch
arg serializeCall scratchCapacity scratchCapacity
run serializeCall
bindOk responseJson JsonText serializeCall
bindError serializeError JsonAccessError serializeCall
branchIfError serializeCall serializeFailed

returnOk responseJson

label parseFailed
returnError parseError

label todosCursorFailed
returnError todosCursorError

label firstTodoFailed
returnError firstTodoError

label setTitleFailed
returnError setTitleError

label serializeFailed
returnError serializeError
```

The important dataflow property is that every cursor produced by a fallible
navigator is guarded before use. After structural mutations such as
`removeArrayElementAt`, `clearObject`, or container-producing set/insert/replace
calls, re-read any descendant cursor before consuming it again. `semlint` checks
both patterns with `SS3620` and `SS3621`.

## Ignoring Results

Ignoring a value is explicit:

```semanticscript
ignoreOk writeGreetingCall Void
ignoreValue metricsFlushCall I64
```

Use these only when the discard is a real part of the contract. Fallible calls
should usually bind and branch on their error path instead.
