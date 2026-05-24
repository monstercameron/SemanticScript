# Toolchain Docs

Documentation for compiler, linter, and editor tooling.

## Contents

- `compiler.md` documents `semsc.py` behavior and CLI usage.
- `agent-workflows.md` documents validation, graph inspection, generated-doc,
  and ignored-artifact workflows for agents.
- `formatter.md` documents `semfmt.py` and canonical formatting defaults.
- `linter.md` documents `semlint.py`.
- `../language/project-layout-build-sem.md` documents project folder layout,
  `build.sem`, module registration, and compiler-managed artifact folders.
- `native-http-runtime.md` documents the current native HTTP adapter and planned
  H2O / `libh2o` backend.
- `native-async-runtime.md` documents the optional libuv async runtime
  experiment and continuation-frame await model.
- `vscode-extension.md` documents the VS Code extension surface.

## Current Status

Active toolchain documentation. It tracks the current Python reference compiler,
standalone linters, editor integration, and native runtime integration plans.

## Maintenance

Update this folder when CLI flags, diagnostics, linter rule families, or VS Code
extension behavior changes.
