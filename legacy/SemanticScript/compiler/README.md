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

Do not add business or application policy to `semsc.py`. Compiler target
branches should lower documented syntax, primitive IR, or native ABI adapters;
reusable behavior belongs in `SemanticScript/std/**`, and byte-level runtime
behavior belongs in `SemanticScript/runtime/**`.

Native runtime link inputs are registered in `_NATIVE_RUNTIME_LINK_REGISTRY` in
`semsc.py`. New compiler target branches must add their adapter there with an
owner string naming the stdlib module or compiler runtime surface responsible
for the ABI. Reserved surfaces should stay out of executable link inputs until
codegen lowers them and tests cover either the runtime symbols or the
intentional unsupported-target diagnostic. `standard.net` / `net.fetch*` is now
owned by the `native_http_client` registry entry, which links `native_async` as
its runtime dependency.

Review checklist for new target families: name the stdlib/runtime owner, add
the target or predicate to the runtime registry when executable sources are
needed, document whether unsupported rows are parse-only or compile-blocking,
and add a focused compiler test for the selected status.
