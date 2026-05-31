# Feature Tests

Numbered SemanticScript feature corpus for compiler and runtime behavior.

## Contents

- `01_*.sscript` through `160_*.sscript` cover language and backend features.
- `_modules/` contains imported helper files and external literal fixtures.

## Current Status

Active regression corpus. Tests cover arithmetic, branching, calls, recursion,
pointers, strings, floats, records, imports, storage, concurrency-shaped verbs,
JSON primitives, literal sources, and low-level `c.*` backend behavior.

## Maintenance

Add new tests with the next available number and a descriptive suffix. Keep each
test focused on one behavior so failures point directly at a compiler feature.
