# Samples

Source-language comparison samples used to compare SemanticScript examples
against familiar host-language implementations.

## Contents

- `javascript/` contains JavaScript versions of sample programs.
- `python/` contains Python concurrency and math API examples.

## Current Status

These files are reference material and comparison fixtures. They are not the
SemanticScript compiler or runtime implementation.

## Maintenance

When adding a SemanticScript sample that should be compared against another
language, place the host-language version under the matching language folder and
keep names aligned where practical.

`samples/python/` is the canonical Python comparison-sample tree for 1.0.
The top-level `python/` directory remains as a compatibility mirror; update both
trees when a mirrored Python sample changes.
