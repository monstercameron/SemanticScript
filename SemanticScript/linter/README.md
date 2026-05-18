# SemanticScript Linter

Standalone SemanticScript source linter.

Run one file:

```text
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript
```

Run the example corpus:

```text
python SemanticScript/linter/semlint.py SemanticScript/sem --summary
```

Fail on warnings for CI:

```text
python SemanticScript/linter/semlint.py SemanticScript/sem --strict
```

Emit JSON for editor integration:

```text
python SemanticScript/linter/semlint.py SemanticScript/sem/fizzbuzz.sscript --format json
```

The linter is separate from `compiler/semsc.py`. It checks source-level laws
without invoking LLVM codegen.

Current rule families:

- `unknownVerb`, `missingArgument`
- flat line-shape checks (`multipleSemanticActions`, `nestedSyntax`)
- naming checks (`vagueName`, `typeNameCase`, `operationNameCase`, role suffixes)
- call lifecycle and unknown-reference checks (`callNotExecuted`,
  `callRunMultipleTimes`, `unknownCallReference`)
- explicit failure and success dataflow (`unbranchedFailure`,
  `missingSuccessDisposition`, `hiddenFailure`)
- branch label existence, duplicate labels, and legacy two-target
  `branchIf` notices
- operation contract checks for purpose/output/memory/async/return
- console effect declaration checks
- async timeout/cancellation and unawaited task-group checks
- cleanup hints for resource-like open/connect/acquire calls
- group/endGroup comment balance checks
- duplicate string domain literal checks, relaxed under
  `mode capturedOutputReplay`
- abstraction purpose checks for contract-heavy declarations
- semantic comment prefix checks (`rationale:`, `invariant:`, `warning:`,
  `failure:`, `agent:`, `group`, `endGroup`, etc.)
