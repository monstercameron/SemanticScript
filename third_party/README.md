# Third-Party Dependencies

This folder contains externally maintained source trees pinned through Git
submodules.

## H2O

- Path: `third_party/h2o`
- Upstream: https://github.com/h2o/h2o.git
- Purpose: native HTTP/1.x and HTTP/2 runtime candidate for SemanticScript
  `webServer` / `route` support.
- License: MIT, with TLS dependencies carrying their own licenses.
- Current pinned commit: see `git submodule status third_party/h2o`.

Clone/update with nested upstream dependencies:

```powershell
git submodule update --init --recursive third_party/h2o
```

Do not edit files inside the submodule directly. Put SemanticScript-specific
adapter code in the owning source tree, then link against the pinned H2O build.
