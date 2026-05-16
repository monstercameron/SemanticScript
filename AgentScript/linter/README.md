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
- call object lifecycle and reference checks
- explicit failure dataflow checks
- branch label existence and duplicate labels
- role suffix checks
- operation purpose/output/memory/async checks
- console effect declaration checks
- async timeout/cancellation checks
- group/endGroup balance checks
- duplicate string domain literal checks
- abstraction purpose checks
