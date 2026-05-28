# Errors, Effects, and Capabilities

SemanticScript treats failure and side effects as visible dataflow. A call that can
fail should expose a named error value and a branch decision. An operation that
touches the outside world should declare its effects.

## Error Domains

```semanticscript
error ConsoleWriteError
errorCase ConsoleWriteError ConsoleWriteFailed Int32
```

`error NAME` creates a typed error domain. `errorCase ERROR VARIANT [CAUSE]`
declares branchable variants. The optional cause type records the underlying
runtime value or failure category.

## Result-Shaped Outputs

```semanticscript
operation writeStandardOutputLine
input operation writeStandardOutputLine text String
output operation writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
purpose operation writeStandardOutputLine "Write one line and surface console failures"
```

`Result OK ERROR` is a type-level contract. In current LLVM lowering, the
success payload is the concrete return shape; the error predicate is carried by
call lowering where available. Linters enforce that the error leg is handled in
source.

## Fallible Call Pattern

```semanticscript
call writeLineCall console.writeLine
argument writeLineCall text String outputText
run writeLineCall
ignore ok source writeLineCall type Void
bind error writeLineError ConsoleWriteError writeLineCall
branch error source writeLineCall target writeLineFailed

storage local immutable successExitCode ExitCode 0
return ok successExitCode

label writeLineFailed
return error writeLineError
```

The call name is the bridge between execution, error binding, and branch:

```text
bind error ERROR_VALUE ERROR_TYPE CALL
branch error source CALL target LABEL
```

`semlint.py` checks hidden-failure patterns for known fallible targets such as
`console.writeLine`, heap allocation calls, and selected libc calls.

Strict compiler checking is intentionally incremental. Source-level
`languageMode strictExecutable` rejects misspelled executable rows; compiler
`--strict` promotes the current fallible-call disposition checks to fatal
diagnostics for known Result-shaped and explicit-disposition targets.
`runChecked CALL ok VALUE TYPE error ERROR TYPE else LABEL` is implemented as
the compact checked-call form for one prepared fallible call. Use it when the
success/error binds and failure branch are local to that call; use explicit
`run` plus `bind ok` / `bind error` / `branch error` when retry policy or more
complex control flow is involved.

## Constructing Domain Failures

```semanticscript
makeError validationFailure RequestError.InvalidJson rawDecodeError
return error validationFailure
```

Schemas:

```text
makeError NAME ERROR.VARIANT [SOURCE]
declareFailure NAME ERROR.VARIANT [SOURCE]
```

`makeError` constructs a named failure value. `declareFailure` registers a
named failure value for later return or grouping.

## Effects

```semanticscript
effect writeStandardOutputLine write console.stdout
effect loadConfigFile read filesystem.config
effect updateAccount write database.account
```

Schema:

```text
effect OPERATION ACTION EFFECT_PATH
```

Effects are source-level contracts. Compiler and linter checks can compare body
calls against declared effects. Current checks cover console writes and a set of
`c.*` / `pointer.*` effect requirements.

## Capabilities and Authority

```semanticscript
capability consoleStdoutWriter console.stdout write
useCapability writeStandardOutputLine consoleStdoutWriter

authority updateAccount write database.account
```

Schemas:

```text
capability NAME EFFECT_PATH ACCESS
useCapability TARGET CAPABILITY
authority TARGET ACCESS EFFECT_PATH
```

Note the column order differs between the two grant forms: `capability` is
path-first (`NAME EFFECT_PATH ACCESS`), while `authority` is access-first
(`TARGET ACCESS EFFECT_PATH`) — matching the `effect TARGET ACCESS EFFECT_PATH`
row it backs. `sem migrate-syntax` rewrites the old path-first `authority` form
to access-first.

Capabilities name grants. `useCapability` attaches a grant to an operation or
use site. `authority` is an inline grant form. Compiler strict lint and
`semlint.py` check for effect sites without capability coverage.

**Which one, and is `authority` required?** Every declared `effect` needs
*exactly one* backing grant — and either form satisfies it:

- a reusable **`capability` + `useCapability`** pair (declare the grant once,
  attach it to each operation that uses it), or
- an inline **`authority OP ACTION EFFECT_PATH`** row (a one-off grant on that
  operation).

So `authority` is **not** required *in addition* to a capability — it is an
*alternative* to one. An operation that declares `effect OP write console.stdout`
and a matching `useCapability` does **not** also need an `authority` row, and one
that uses an `authority` row does not need a capability. Use a shared
`capability` when the same grant recurs across operations; use an inline
`authority` for a single operation's one-off grant. An effect with *neither* is
the gap the coverage check (SS3104) flags.

Capability paths are hierarchical. A capability declared at `http.request read`
authorizes narrower reads such as `http.request.method`, `http.request.path`,
and `http.request.cancellationToken`. Use a narrower capability when the
operation should only inspect one request edge.

For the scoped 1.0 runtime, capabilities and inline `authority` rows are
compile-time and linter contracts only. Codegen does not emit capability token
values into binaries, and missing authority is reported as a compiler or linter
diagnostic rather than a runtime trap or typed runtime error. Runtime authority
tokens remain a future runtime feature.

## Dependency Contracts

```semanticscript
dependency postgresClient kind externalService
dependencyEffect postgresClient read database.account
dependencyExports postgresClient accountLookup
dependencyFunction postgresClient.lookupAccount
dependencyFunctionInput postgresClient.lookupAccount accountId AccountId
dependencyFunctionOutput postgresClient.lookupAccount Result AccountBalance AccountLookupError
dependencyFunctionEffect postgresClient.lookupAccount read database.account
dependencyFunctionAsync postgresClient.lookupAccount yes
```

Dependency declarations are metadata in current codegen. They are still
important because they give linters and agents explicit contract edges instead
of hiding behavior behind a dotted call target.
