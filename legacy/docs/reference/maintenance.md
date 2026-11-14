# Documentation and Language Maintenance

SemanticScript has multiple moving parts. Keep them in lockstep or the language
will drift: compiler, syntax inventory, linter, editor, examples, docs.

## Change Protocol

For a new verb or changed schema:

1. Update `syntax-inventory.md` with the exact schema and implementation status.
2. Update `SemanticScript/compiler/semsc.py` parser handling.
3. Add or update lowering if the verb affects runtime behavior.
4. Add a focused file in `SemanticScript/sem/feature_tests/`.
5. Update `SemanticScript/linter/semlint.py` known verbs and checks.
6. Update `SemanticScript/linter/semlint.py` if the current linter should enforce
   the behavior.
7. Update `vscode-semanticscript` syntax, semantic roles, hovers, and symbol
   indexing.
8. Update the narrow docs file in `docs/language/`, `docs/toolchain/`, or
   `docs/reference/`.
9. Run the relevant tests.

Do not add only editor highlighting. Highlighting without parser/linter/docs
support creates false confidence.

For strict syntax hardening, prove compiler behavior separately from lint
behavior. A TODO item that says "compiler rejects" needs a negative
`semsc.py --parse-only` test that fails without `--lint`; a standalone
`semlint.py` failure is not enough. Keep proposed rows such as
`languageMode strictExecutable`, `runChecked`, `bindOwned`, and
`requireNonNull` in the research note until parser/compiler tests exist.

## Status Vocabulary

Use the same status words everywhere:

| Status | Meaning |
|---|---|
| `lowered` | Current compiler emits behavior-changing LLVM/codegen for it. |
| `metadata` | Parser stores/indexes it; current codegen does not act on it. |
| `sync-fallback` | Runtime concept lowers to a defined single-thread behavior. |
| `partial` | Some behavior lowers; some remains metadata or external runtime work. |
| `proposed` | Research syntax, not committed compiler surface. |

`syntax-inventory.md` uses `Impl'd`, `Partial`, `Not impl'd`, and `Proposed`. Keep the
meaning aligned when writing prose docs.

## Example Standards

Examples should be executable when the surrounding section is about current
lowering. If an example is metadata or future-runtime syntax, say so directly.

Good:

```semanticscript
call sumCall math.addInt64
argument sumCall left TYPE leftValue
argument sumCall right TYPE rightValue
run sumCall
bind value sumValue Int64 sumCall
```

Bad:

```semanticscript
sumValue = leftValue + rightValue
```

The bad example is not SemanticScript and teaches the wrong mental model.

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
python SemanticScript/compiler/semsc.py SemanticScript/sem/feature_tests/<case>.sscript --parse-only
python SemanticScript/linter/semlint.py SemanticScript/sem/feature_tests/<case>.sscript --format human
cd vscode-semanticscript
npm run check
```

Run broader compiler tests when lowering changed:

```powershell
cd SemanticScript
python tests/test_compiler.py
python tests/test_stdlib.py
```
