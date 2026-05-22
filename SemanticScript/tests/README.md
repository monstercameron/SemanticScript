# Tests

Python test harnesses and small compiler fixtures.

## Contents

- `test_compiler.py` covers parser, codegen, diagnostics, and native emit behavior.
- `test_stdlib.py` compiles and runs stdlib modules.
- `compare.py` and `sem_alias_parity.py` support broader parity/coverage checks.
- `tiny.sem` and `tiny.sscript` are minimal source fixtures.
- `stdout_blocking.js` is a small host-language fixture.

## Current Status

Active verification surface for compiler and stdlib work. Some broader
coverage/parity scripts are more expensive than the focused unit-style checks.

## Maintenance

Run focused tests for narrow compiler changes, then broader parity/stdlib checks
when behavior touches imports, lowering, stdlib, or diagnostics.
Run `python SemanticScript/tests/sem_alias_parity.py` after updating sample
`.sem` equivalents; it verifies 1.0 source shape and JavaScript output parity.
