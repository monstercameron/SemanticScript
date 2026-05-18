# Documentation and Language Maintenance

AgentScript has multiple moving parts. Keep them in lockstep or the language
will drift: compiler, syntax inventory, linter, editor, examples, docs.

## Change Protocol

For a new verb or changed schema:

1. Update `SYNTAX.md` with the exact schema and implementation status.
2. Update `AgentScript/compiler/ascc.py` parser handling.
3. Add or update lowering if the verb affects runtime behavior.
4. Add a focused file in `AgentScript/as/feature_tests/`.
5. Update `AgentScript/linter/aslint2.py` known verbs and checks.
6. Update `AgentScript/linter/aslint.py` if the current linter should enforce
   the behavior.
7. Update `vscode-agentscript` syntax, semantic roles, hovers, and symbol
   indexing.
8. Update the narrow docs file in `docs/language/`, `docs/toolchain/`, or
   `docs/reference/`.
9. Run the relevant tests.

Do not add only editor highlighting. Highlighting without parser/linter/docs
support creates false confidence.

## Status Vocabulary

Use the same status words everywhere:

| Status | Meaning |
|---|---|
| `lowered` | Current compiler emits behavior-changing LLVM/codegen for it. |
| `metadata` | Parser stores/indexes it; current codegen does not act on it. |
| `sync-fallback` | Runtime concept lowers to a defined single-thread behavior. |
| `partial` | Some behavior lowers; some remains metadata or external runtime work. |
| `proposed` | Research syntax, not committed compiler surface. |

`SYNTAX.md` uses `Impl'd`, `Partial`, `Not impl'd`, and `Proposed`. Keep the
meaning aligned when writing prose docs.

## Example Standards

Examples should be executable when the surrounding section is about current
lowering. If an example is metadata or future-runtime syntax, say so directly.

Good:

```agentscript
call sumCall math.addI64
arg sumCall left leftValue
arg sumCall right rightValue
run sumCall
bind sumValue I64 sumCall
```

Bad:

```agentscript
sumValue = leftValue + rightValue
```

The bad example is not AgentScript and teaches the wrong mental model.

## Naming Standards

Names should carry role and domain:

```text
accountLookupCall
accountLookupError
accountLookupRetryPolicy
validatedTaskTitle
rawRequestBody
consoleStdoutWriter
```

Avoid:

```text
tmp
res
data
handler
value
x
```

If a short name appears in a feature test to isolate compiler behavior, keep it
out of docs unless the brevity itself is being discussed.

## Docs Ownership

Use this ownership map:

| Change | Docs file |
|---|---|
| Tokenization, strings, comments | `language/lexical-model.md` |
| Project headers, imports, entries | `language/program-structure.md` |
| Types, constants, literals | `language/types-values.md` |
| Calls, vars, branches, returns | `language/operations-dataflow.md` |
| Errors, effects, capabilities | `language/errors-effects-capabilities.md` |
| Storage, shared state, pointer work | `language/memory-state.md` |
| Records, codecs, boundaries | `language/records-codecs-boundaries.md` |
| Async, retry, cleanup, concurrency | `language/concurrency-time-cleanup.md` |
| Primitive targets and c.* registry | `reference/call-targets.md` |
| CLI behavior | `toolchain/compiler.md` |
| Diagnostics | `toolchain/linter.md` |
| Extension behavior | `toolchain/vscode-extension.md` |

## Verification Checklist

Before considering a language-doc update done:

```powershell
python AgentScript/compiler/ascc.py AgentScript/as/feature_tests/<case>.as --parse-only
python AgentScript/linter/aslint2.py AgentScript/as/feature_tests/<case>.as --format human
cd vscode-agentscript
npm run check
```

Run broader compiler tests when lowering changed:

```powershell
cd AgentScript
python tests/test_compiler.py
python tests/as_compiler_parity.py
python tests/test_stdlib.py
```

