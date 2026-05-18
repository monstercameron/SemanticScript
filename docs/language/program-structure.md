# Program Structure

A SemanticScript file is a sequence of top-level declarations followed by one or
more `operation` bodies. The parser keeps a current operation pointer; after
`operation NAME`, operation-scope lines are appended to that operation until a
new `operation` starts.

## Project Header

Common executable console header:

```semanticscript
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

```semanticscript
mode capturedOutputReplay
```

That mode marks a source file whose output is a captured transcript rather than
a full algorithmic reimplementation. Linters use it to relax specific replay
diagnostics.

## Import Resolution

```semanticscript
importModule standard.string as string
```

`semsc.py` resolves `importModule DOTTED.PATH [as ALIAS]` before parsing:

1. Convert dotted path to a path: `standard.string` -> `standard/string.sscript`.
2. Search relative to the source file's directory.
3. Search `SemanticScript/stdlib_sem/`.
4. Search the project root.
5. Inline imported content with cycle detection.

The alias is recorded but is not a namespace system yet.

## Library and Web Server Mode

If a source has no `entry` line, the compiler emits every operation as a
callable LLVM function and emits a stub `int main() { return 0; }`. This is how
library-like and declarative files can still compile and link.

`target webServer` plus `webServer` and `route` metadata follows this same
model today: route handlers become callable functions, but no HTTP dispatcher
runtime is wired into `semsc.py` yet.

## Operations

```semanticscript
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

```semanticscript
operation writeLine
purpose otherOperation "wrong owner"
```

Good:

```semanticscript
operation writeLine
purpose writeLine "owner matches operation"
```

The repetition is deliberate. A single retrieved line is independently
checkable.

## Test Companion Files

A library-like source file `foo.sscript` exports operations for other programs to
consume. Its tests live in a sibling `foo.test.sscript` so the implementation file
is not crowded by smoke / unit-test prose.

```text
stdlib_sem/bit.sscript        # impl: project StdBit, no operation main, no smoke
stdlib_sem/bit.test.sscript   # tests: importModule bit + operation main + asserts
```

`foo.sscript` (impl):

```semanticscript
project StdBit
target console
runtime AgentRuntime 0.1
entry console shiftSignedInt64BitsLeft

# Pure-module file: operations only. The entry line points at the
# first exported operation rather than a removed `main` so the
# module still compiles and lints standalone.

domainLiteral ...
operation shiftSignedInt64BitsLeft
...
```

`foo.test.sscript` (companion):

```semanticscript
project StdBitTest
target console
runtime AgentRuntime 0.1
entry console main

importModule bit

error MainError
errorCase MainError BitSmokeAssertionFailed
errorCase MainError ConsoleWriteFailed

capability stdoutWriteCapability console.stdout write

operation main
input main console Console
output main Result ExitCode MainError
...
returnOk exitOkCode
```

Rules:

- `foo.test.sscript` lives in the same directory as `foo.sscript` and bears the suffix
  `.test.sscript` so tooling can identify it by filename alone.
- It has its own `project` block (`StdFooTest` by convention), `entry console
  main`, and `importModule foo` directive. The imported file's header lines
  are stripped by the import resolver, so the test owns the executable.
- Move every smoke-only declaration to the test: the `error MainError`
  domain, `errorCase` variants, and the `capability` declarations the smoke
  uses (`stdoutWriteCapability`, `heapAllocationCapability`, etc.).
- **Capabilities used by impl operations stay in `foo.sscript`.** If any
  non-`main` operation declares `useCapability X stdoutWriteCapability`, the
  module's writers need it themselves; keep the capability declaration in
  `foo.sscript` rather than moving it to the test. `stdio.sscript` and `assert.sscript`
  follow this rule.
- Module-level `error` domains referenced in operation signatures (e.g.
  `NumericArithmeticError` in `stdlib.sscript`) stay in `foo.sscript`.
- The `bind X Ordering …` form (or any type alias declared in `foo.sscript`) is
  not resolvable through the linter's per-file view of the test. Bind the
  underlying primitive instead — `bind X CSignedInt32 …` — when a test file
  consumes a typed alias from its imported module.

The harness `tests/test_stdlib.py` prefers `foo.test.sscript` over `foo.sscript` when
the test file exists, so adding a new companion does not require runner
changes. The legacy `foo.sscript` form (with smoke inline) is still supported
during migration: any module without a companion test file uses its own
inline smoke.

## Sections and Groups

`section` and `group*` lines are retrieval/indexing aids. They do not create a
lexical scope.

```semanticscript
section validation
group requestValidation
groupPurpose requestValidation "Keep raw-to-trusted validation edges together"
groupInput requestValidation rawRequestBody
groupOutput requestValidation validatedTask
groupFailure requestValidation requestValidationFailure
```

Use sections for broad document structure. Use groups for named attention and
dataflow clusters that tooling can cite.

