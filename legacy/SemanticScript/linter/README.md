# SemanticScript Linter

Standalone SemanticScript source linter.

## Contents

- `semlint.py` is the canonical linter — structured diagnostics under
  stable `SS<code>` identifiers, tiered model (T0 parse … T4 style),
  with `human`, `json`, `agent`, and `sem-record` output formats.
- `test_semlint.py` contains golden assertion tests for every rule.
- `__init__.py` marks the package for imports.

## Current Status

Active toolchain folder. `semlint.py` is the editor/CLI linter surface and
the source of truth for SS-coded diagnostics.

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

The linter is separate from `compiler/semsc.py`. It checks source-level
laws without invoking LLVM codegen.

Diagnostics are organised by tier:

- **T0 parse / grammar** — `SS00xx`, non-overridable errors.
- **T1 spec** — `SS01xx`, spec violations that block compilation.
- **T2 lowering** — `SS02xx`, lowering invariants.
- **T3 refinement** — `SS3xxx`, warning by default, configurable.
- **T4 style** — `SS4xxx`, info by default; the optimization-guide
  vocabulary lives here.

Each diagnostic carries a `kind` string (e.g. `styleDiscipline.duplicate`
`LocalImmutableAcrossOps`), citations to the operation's narrative
attachments (`purpose` / `invariant` / `warning` / `# rationale:`), one or
more `FixCandidate` rows with auto-applicable flags, and `confidence` /
`effort` workflow metadata. The full schema lives at the top of
`semlint.py` under the `Diagnostic` dataclass.

For rule-by-rule coverage and lowering examples see `docs/optimization-`
`guide.md` and `docs/toolchain/linter.md`.
