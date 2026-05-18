# Program Structure

An AgentScript file is a sequence of top-level declarations followed by one or
more `operation` bodies. The parser keeps a current operation pointer; after
`operation NAME`, operation-scope lines are appended to that operation until a
new `operation` starts.

## Project Header

Common executable console header:

```agentscript
project FizzBuzzProgram
target console
runtime native 1
module examples.fizzbuzz
entry console main
```

Line schemas:

```text
project NAME
target NAME
runtime NAME VERSION
module DOTTED.PATH
mode NAME
entry console OPERATION
```

`mode` is a closed set. The current recognized mode is:

```agentscript
mode capturedOutputReplay
```

That mode marks a source file whose output is a captured transcript rather than
a full algorithmic reimplementation. Linters use it to relax specific replay
diagnostics.

## Import Resolution

```agentscript
importModule standard.string as string
```

`ascc.py` resolves `importModule DOTTED.PATH [as ALIAS]` before parsing:

1. Convert dotted path to a path: `standard.string` -> `standard/string.as`.
2. Search relative to the source file's directory.
3. Search `AgentScript/stdlib_as/`.
4. Search the project root.
5. Inline imported content with cycle detection.

The alias is recorded but is not a namespace system yet.

## Library and Web Server Mode

If a source has no `entry` line, the compiler emits every operation as a
callable LLVM function and emits a stub `int main() { return 0; }`. This is how
library-like and declarative files can still compile and link.

`target webServer` plus `webServer` and `route` metadata follows this same
model today: route handlers become callable functions, but no HTTP dispatcher
runtime is wired into `ascc.py` yet.

## Operations

```agentscript
operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
memory writeStandardOutputLine noHeapAllocation
async writeStandardOutputLine no
purpose writeStandardOutputLine "Emit one newline-terminated text line"
```

Operation header lines repeat the owner operation name as their first argument.
The parser enforces that ownership for:

```text
input output effect memory async purpose invariant warning
guarantee failure security timing observability
```

Bad:

```agentscript
operation writeLine
purpose otherOperation "wrong owner"
```

Good:

```agentscript
operation writeLine
purpose writeLine "owner matches operation"
```

The repetition is deliberate. A single retrieved line is independently
checkable.

## Sections and Groups

`section` and `group*` lines are retrieval/indexing aids. They do not create a
lexical scope.

```agentscript
section validation
group requestValidation
groupPurpose requestValidation "Keep raw-to-trusted validation edges together"
groupInput requestValidation rawRequestBody
groupOutput requestValidation validatedTask
groupFailure requestValidation requestValidationFailure
```

Use sections for broad document structure. Use groups for named attention and
dataflow clusters that tooling can cite.

