# Compiler

Python reference compiler and C ABI registry for SemanticScript.

## Contents

- `semsc.py` parses, lints, lowers to LLVM IR, runs JIT execution, and emits native executables.
- `libc_registry.py` maps temporary `c.*` C ABI calls to signatures and aliases.

## Current Status

Active implementation. The compiler currently supports executable
SemanticScript plus some refined syntax metadata. Low-level `c.*` targets remain
as a backend interop layer while the top-level SemanticScript API is designed.

## Maintenance

Compiler changes should include focused tests under `SemanticScript/tests/` or
feature tests under `SemanticScript/sem/feature_tests/`. Do not edit generated
LLVM IR by hand.
