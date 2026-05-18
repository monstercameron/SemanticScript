# Language Guide

SemanticScript is a flat, line-oriented semantic tape. Every non-empty source line
starts with a verb, then a fixed schema of whitespace-separated tokens. There
is no expression tree, statement nesting, implicit call syntax, or block
syntax. The language spends source text to preserve context that compilers,
linters, editors, and agents can recover locally.

The current repository has two related surfaces:

- Executable SemanticScript: accepted by `SemanticScript/compiler/semsc.py` and used
  by `SemanticScript/sem/` and `SemanticScript/sem/feature_tests/`.
- Refined SemanticScript: accepted as parseable metadata or synchronous fallback
  by the reference compiler/linter/editor, but not always backed by a runtime
  service yet. `SYNTAX.md` is the status inventory.

Do not infer compiler support from VS Code highlighting alone. The editor
tracks syntax and hover semantics for both surfaces; the compiler is the
authority for executable lowering.

## Minimal Executable Program

```semanticscript
project HelloProgram
target console
runtime native 1
entry console main

operation main
output main ExitCode
effect main write console.stdout
purpose main "Print one greeting and exit successfully"

const greetingText String "hello from SemanticScript"
call writeGreetingCall console.writeLine
arg writeGreetingCall text greetingText
run writeGreetingCall
ignoreOk writeGreetingCall Void

const successExitCode ExitCode 0
returnValue successExitCode
```

The important details:

- `entry console main` chooses the operation named `main`.
- `operation main` starts the body tape for that operation.
- Operation header lines repeat the owning operation name.
- Calls are name-addressable objects: `call`, `arg`, `run`, then bind or
  ignore the result.
- The program declares its stdout effect before using `console.writeLine`.

## Design Invariants

SemanticScript source should remain:

- atomic: one semantic record per line;
- explicit: effects, failures, memory behavior, time, and cleanup are visible;
- addressable: meaningful things have stable names;
- checkable: metadata should be enforceable by compiler or linter when
  practical;
- boring: clever expression compression is a defect.

These docs describe the concrete schemas that make those invariants enforceable.

