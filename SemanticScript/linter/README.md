# SemanticScript Linter

Standalone SemanticScript source linter.

## Contents

- `semlint.py` is the current stable standalone linter.
- `semlint2.py` is the structured/refined linter playground.
- `test_semlint2.py` contains golden assertion tests for `semlint2.py`.
- `__init__.py` marks the package for imports.

## Current Status

Active toolchain folder. `semlint.py` is the default editor/CLI linter surface;
`semlint2.py` explores richer diagnostics and additional refined-syntax checks.

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
- `Result ... Void` helper checks when no `returnError` path exists
- console effect declaration checks
- async timeout/cancellation and unawaited task-group checks
- cleanup hints for resource-like open/connect/acquire calls without a proven
  defer or explicit close call using the bound handle
- filesystem read/write effect precision using direct file I/O calls and
  `c.fopen`/`c.freopen` mode strings, plus file open/close effect checks
- terminal lifecycle cleanup checks for hidden cursor entry without a matching
  cursor restore call
- `printf`/`fprintf` integer format-width mismatch checks
- raw JSON `%s` interpolation checks for JSON-like string literals
- fixed-format parser contract checks for numeric `*ValueOffset` and
  `*FieldOffset` constants
- direct scalar-width drift checks for `set` between known 32-bit and 64-bit
  integer symbols
- group/endGroup comment balance checks
- duplicate string domain literal checks, relaxed under
  `mode capturedOutputReplay`
- abstraction purpose checks for contract-heavy declarations
- semantic comment prefix checks (`rationale:`, `invariant:`, `warning:`,
  `failure:`, `agent:`, `group`, `endGroup`, etc.)

Additional `semlint2.py` coverage:

- branch-aware dead-store analysis for failure labels that read the most recent
  stored error value
- hidden-failure diagnostics distinguish Result-shaped calls from C-style
  sentinel/status calls; C calls must bind or explicitly ignore the returned
  value instead of pretending they have `bindError` paths
- heap and file lifecycle checks accept either defer metadata or explicit
  cleanup calls that consume the bound allocation/handle
- opaque dependency inputs such as `console` are not treated as unused scalar
  parameters
- top-level `.sem` samples declaring `AgentRuntime 1.0` are checked for the
  current storage/memory forms and for an executable source tape instead of a
  constants-only fixture
