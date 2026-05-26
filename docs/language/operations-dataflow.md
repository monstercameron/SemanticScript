# Operations and Dataflow

An operation is the primary executable unit. It compiles to `main` when selected
by `entry console OPERATION`, or to a callable LLVM function when referenced by
another operation or when compiling library-style files.

## Operation Contract

```semanticscript
operation addInvoiceAmounts
input operation addInvoiceAmounts invoiceSubtotal Int64
input operation addInvoiceAmounts taxAmount Int64
output operation addInvoiceAmounts Int64
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
call invoiceTotalCall math.addInt64
argument invoiceTotalCall left Int64 invoiceSubtotal
argument invoiceTotalCall right Int64 taxAmount
run invoiceTotalCall
bind value invoiceTotal Int64 invoiceTotalCall
```

Lifecycle:

1. `call CALL TARGET` creates the call object.
2. `argument CALL ARG_NAME TYPE VALUE` attaches named argument edges.
3. `timeout`, `cancelOn`, or `useRetry` attach policies when needed.
4. `run CALL`, `start CALL`, or `submitWork WORK POOL` executes.
5. `bind value`, `bind ok`, `bind error`, `ignore ok`, `ignore value`, or
   `ignore void` accounts for
   the result.

The compiler records call result SSA by call name so later lines can bind or
branch on it.

## User Operation Calls

```semanticscript
operation addTwoValues
input operation addTwoValues leftValue Int64
input operation addTwoValues rightValue Int64
output operation addTwoValues Int64

call sumCall math.addInt64
argument sumCall left Int64 leftValue
argument sumCall right Int64 rightValue
run sumCall
bind value sumValue Int64 sumCall
return value sumValue

operation main
output operation main ExitCode

storage local immutable leftInput Int64 40
storage local immutable rightInput Int64 2
call answerCall addTwoValues
argument answerCall leftValue Int64 leftInput
argument answerCall rightValue Int64 rightInput
run answerCall
bind value answerValue Int64 answerCall
return value answerValue
```

For a same-file user operation call:

- parameter order comes from the callee's `input` lines;
- opaque inputs are skipped at the LLVM boundary;
- `output OP Result OK ERR` returns the OK payload type;
- `output OP TYPE` returns `TYPE`;
- `Void` currently uses an `i32` zero sentinel in ABI positions that need a
  concrete value.

## Mutable Storage

```semanticscript
storage local mutable runningTotal Int64 0

call nextTotalCall math.addInt64
argument nextTotalCall left Int64 runningTotal
argument nextTotalCall right Int64 stepAmount
run nextTotalCall
bind value nextTotal Int64 nextTotalCall
set local runningTotal nextTotal
```

`storage local mutable NAME TYPE VALUE` allocates a mutable local slot. Reading
the name loads its current value. `set local NAME VALUE` stores into that local
slot.

Prefer immutable storage unless mutation is the real behavior being expressed.

## Control Flow

Labels are named basic blocks.

```semanticscript
label loopStart

call doneCheckCall math.greaterThanInt64
argument doneCheckCall left Int64 currentIndex
argument doneCheckCall right Int64 finalIndex
run doneCheckCall
bind value isDone Bool doneCheckCall
branch if condition isDone target loopDone

# body...
jump target loopStart

label loopDone
return value currentIndex
```

Schemas:

```text
label NAME
jump target LABEL
branch if condition CONDITION target LABEL
branch error source CALL target LABEL
branch else target LABEL
return ok VALUE
return error VALUE
return value VALUE
return void
```

`branch if` jumps when the condition is true. Use `branch else` for the
explicit alternate target when a chain should not fall through.

Use `return void` for operations declared `output operation OP Void` or
`output operation OP Void`.
The user-operation ABI still lowers that path to the internal zero sentinel, but
the source no longer has to carry a fake `Int32` value just to satisfy the
ABI. `return void` is rejected on non-Void outputs; non-Void operations should
use `return value`, `return ok`, or `return error` as appropriate.

## JSON CRUD Dataflow

JSON document calls follow the same call lifecycle. Parse or create a
`JsonDocument`, bind the root cursor, navigate to child cursors with fallible
calls, branch on access errors before using the cursor, mutate the tree, then
serialize through caller-owned scratch storage.

```semanticscript
operation renameFirstTodoHandler
input operation renameFirstTodoHandler requestBody JsonText
input operation renameFirstTodoHandler scratch JsonScratchBuffer
output operation renameFirstTodoHandler Result JsonText JsonAccessError
effect renameFirstTodoHandler read json.document.tree
effect renameFirstTodoHandler write json.document.tree

storage local immutable documentCapacity JsonCapacityBytes 4096
storage local immutable scratchCapacity JsonCapacityBytes 4096
storage local immutable todosPath JsonPath ".todos"
storage local immutable firstTodoIndex Int64 0
storage local immutable titleField JsonFieldName "title"
storage local immutable replacementTitle JsonStringValue "ship json"

call parseBodyCall json.createDocument
argument parseBodyCall jsonText JsonText requestBody
argument parseBodyCall capacityBytes JsonCapacityBytes documentCapacity
run parseBodyCall
bind ok document JsonDocument parseBodyCall
bind error parseError JsonAccessError parseBodyCall
branch error source parseBodyCall target parseFailed
defer destroyDocumentDefer json.destroyDocument document

call todosCursorCall json.cursorAtPath
argument todosCursorCall document JsonDocument document
argument todosCursorCall path JsonPath todosPath
run todosCursorCall
bind ok todosCursor JsonCursor todosCursorCall
bind error todosCursorError JsonAccessError todosCursorCall
branch error source todosCursorCall target todosCursorFailed

call firstTodoCall json.arrayElementAt
argument firstTodoCall document JsonDocument document
argument firstTodoCall cursor JsonCursor todosCursor
argument firstTodoCall index Int64 firstTodoIndex
run firstTodoCall
bind ok firstTodoCursor JsonCursor firstTodoCall
bind error firstTodoError JsonAccessError firstTodoCall
branch error source firstTodoCall target firstTodoFailed

call setTitleCall json.setObjectFieldString
argument setTitleCall document JsonDocument document
argument setTitleCall cursor JsonCursor firstTodoCursor
argument setTitleCall fieldName JsonFieldName titleField
argument setTitleCall value JsonStringValue replacementTitle
run setTitleCall
ignore ok source setTitleCall type Int32
bind error setTitleError JsonAccessError setTitleCall
branch error source setTitleCall target setTitleFailed

call serializeCall json.serializeDocument
argument serializeCall document JsonDocument document
argument serializeCall scratch JsonScratchBuffer scratch
argument serializeCall scratchCapacity JsonCapacityBytes scratchCapacity
run serializeCall
bind ok serializedJsonText JsonText serializeCall
bind error serializeError JsonAccessError serializeCall
branch error source serializeCall target serializeFailed

return ok serializedJsonText

label parseFailed
return error parseError

label todosCursorFailed
return error todosCursorError

label firstTodoFailed
return error firstTodoError

label setTitleFailed
return error setTitleError

label serializeFailed
return error serializeError
```

The important dataflow property is that every cursor produced by a fallible
navigator is guarded before use. After structural mutations such as
`removeArrayElementAt`, `clearObject`, or container-producing set/insert/replace
calls, re-read any descendant cursor before consuming it again. `semlint` checks
both patterns with `SS3620` and `SS3621`.

## Ignoring Results

Ignoring a value is explicit:

```semanticscript
ignore ok source writeGreetingCall type Void
ignore value source metricsFlushCall type Int64
```

Use these only when the discard is a real part of the contract. Fallible calls
should usually bind and branch on their error path instead.
