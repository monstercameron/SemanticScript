# Errors, Effects, and Capabilities

SemanticScript treats failure and side effects as visible dataflow. A call that can
fail should expose a named error value and a branch decision. An operation that
touches the outside world should declare its effects.

## Error Domains

```semanticscript
error ConsoleWriteError
errorCase ConsoleWriteError ConsoleWriteFailed CSignedInt32
```

`error NAME` creates a typed error domain. `errorCase ERROR VARIANT [CAUSE]`
declares branchable variants. The optional cause type records the underlying
runtime value or failure category.

## Result-Shaped Outputs

```semanticscript
operation writeStandardOutputLine
input writeStandardOutputLine text String
output writeStandardOutputLine Result Void ConsoleWriteError
effect writeStandardOutputLine write console.stdout
purpose writeStandardOutputLine "Write one line and surface console failures"
```

`Result OK ERROR` is a type-level contract. In current LLVM lowering, the
success payload is the concrete return shape; the error predicate is carried by
call lowering where available. Linters enforce that the error leg is handled in
source.

## Fallible Call Pattern

```semanticscript
call writeLineCall console.writeLine
arg writeLineCall text outputText
run writeLineCall
ignoreOk writeLineCall Void
bindError writeLineError ConsoleWriteError writeLineCall
branchIfError writeLineCall writeLineFailed

const successExitCode ExitCode 0
returnOk successExitCode

label writeLineFailed
returnError writeLineError
```

The call name is the bridge between execution, error binding, and branch:

```text
bindError ERROR_VALUE ERROR_TYPE CALL
branchIfError CALL LABEL
```

`semlint2.py` checks hidden-failure patterns for known fallible targets such as
`console.writeLine`, heap allocation calls, and selected libc calls.

## Constructing Domain Failures

```semanticscript
makeError validationFailure RequestError.InvalidJson rawDecodeError
returnError validationFailure
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

authority updateAccount database.account write
```

Schemas:

```text
capability NAME EFFECT_PATH ACCESS
useCapability TARGET CAPABILITY
authority TARGET EFFECT_PATH ACCESS
```

Capabilities name grants. `useCapability` attaches a grant to an operation or
use site. `authority` is an inline grant form. The current compiler preserves
these as metadata; `semlint2.py` checks for effect sites without capability
coverage.

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

