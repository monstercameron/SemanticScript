# SemanticScript Samples

Runnable SemanticScript examples and smoke programs.

## Contents

- Small samples such as hello world, fizzbuzz, factorial, calculator, and countdown.
- Larger workflow examples such as checkout saga, inventory manager, todo list, and file inventory.
- `.sem` siblings for JavaScript-parity samples use the current 1.0 storage and
  memory syntax while preserving the matching `.sscript` behavior.
- Refined syntax variants for selected samples.
- `smoke_c_*` programs for low-level C bootstrap/ABI coverage.
- `stdlib_import_smoke*` programs for import and stdlib integration checks.
- `feature_tests/` contains the numbered compiler feature corpus.

## Current Status

This folder mixes user-facing examples, compiler smoke tests, and migration
samples. The `smoke_c_*` files intentionally exercise bootstrap-level `c.*`
targets; normal app-facing examples should move toward SemanticScript API calls.
The `.sem` sample siblings are verified by `SemanticScript/tests/sem_alias_parity.py`
against their JavaScript oracles and include a source-shape check so they do not
collapse into declaration-only fixtures.

## Maintenance

Keep example intent clear in filenames and purpose lines. Add new compiler
regressions to `feature_tests/` instead of overloading broad samples.
