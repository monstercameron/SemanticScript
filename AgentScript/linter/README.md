# AgentScript Linter

Standalone AgentScript source linter.

Run one file:

```text
python AgentScript/linter/aslint.py AgentScript/as/fizzbuzz.as
```

Run the example corpus:

```text
python AgentScript/linter/aslint.py AgentScript/as --summary
```

Fail on warnings for CI:

```text
python AgentScript/linter/aslint.py AgentScript/as --strict
```

Emit JSON for editor integration:

```text
python AgentScript/linter/aslint.py AgentScript/as/fizzbuzz.as --format json
```

The linter is separate from `compiler/ascc.py`. It checks source-level laws
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
