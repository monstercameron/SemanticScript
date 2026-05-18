# SemanticScript Optimization Guide

This guide collects optimization rules that preserve SemanticScript's main value: visible dataflow and explicit failure contracts. Performance work should not erase semantic context.

## Return Contracts

Do not let raw C return values escape an operation unless the operation's contract explicitly says that raw value is the result.

Many libc calls return useful counts on success:

```semanticscript
c.printf    # positive byte count on success, negative on failure
c.fprintf   # positive byte count on success, negative on failure
c.fread     # item count
c.fwrite    # item count
```

Those values are not canonical SemanticScript operation status codes. If an operation only needs to report success or failure, normalize the return:

```semanticscript
storage local immutable saveSucceededCode CSignedInt32 0
storage local immutable saveFailedCode CSignedInt32 1

call writeJsonCall c.fprintf
arg writeJsonCall stream saveFileHandle
arg writeJsonCall format saveFormat
run writeJsonCall
ignoreValue writeJsonCall CSignedInt32
returnValue saveSucceededCode
```

Avoid this shape:

```semanticscript
bind writeJsonResult CSignedInt32 writeJsonCall
returnValue writeJsonResult
```

That leaks a libc byte count into the operation boundary. A caller or backend may later interpret a nonzero scalar as failure-like control flow.

## Linter Guardrail

`semlint.py` reports `rawLibcReturnEscapesOperation` when an operation returns a binding produced by libc count/status calls such as `c.printf`, `c.fprintf`, `c.fread`, or `c.fwrite`.

The intended fix is one of:

- Map the raw value to an explicit domain status.
- Use `Result OkType ErrorType` and branch on the C call's real failure condition.
- Rename/retype the operation so the raw byte/count value is honestly the public result.

## App Boundary Rule

Treat `c.*` as a bootstrap/backend boundary, not as the normal application API.
Application code should call SemanticScript-facing operations once a matching
surface exists:

```text
console.readKey
console.readLineIntoBuffer
console.writeText
console.writeLine
console.clearScreen
file.openRead
file.openWrite
file.close
file.readLineIntoBuffer
file.writeText
file.writeBytes
memory.allocate
memory.free
memory.zero
memory.copy
```

Direct `c.*` calls are acceptable in low-level bootstrap/runtime modules,
stdlib implementation files, compiler smoke tests, and backend bring-up samples.
They should be avoided in top-level apps and user-facing examples unless the
top-level SemanticScript API is still missing.

This keeps the dependency direction clean: apps depend on SemanticScript
contracts, stdlib/runtime code owns the temporary C bootstrap, and the backend
can later replace libc with Win32, POSIX syscalls, or a custom runtime without
rewriting app code.

## Result vs Status

Use `Result` when the caller must distinguish success data from typed failure:

```semanticscript
output saveTodosToJson Result Void SaveTodosError
```

Use an explicit status type when the operation is intentionally status-only:

```semanticscript
type SaveStatus CSignedInt32
storage local immutable saveSucceededCode SaveStatus 0
storage local immutable saveOpenFailedCode SaveStatus 1
```

Do not use bare `CSignedInt32` as a dumping ground for byte counts, OS statuses, exit codes, and typed semantic status. If several meanings share the same primitive shape, create aliases so the source carries the distinction.

## Optimization Rule

Before optimizing a sequence, identify the semantic boundary:

1. Internal raw values may stay raw.
2. Operation outputs must be canonicalized or explicitly typed.
3. Failure-producing calls should either be handled locally or surfaced through `Result`.
4. A successful operation returning a scalar status should usually return zero.

This keeps optimized code patchable by agents and predictable for compiler lowering.
