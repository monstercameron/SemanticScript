# Third-Party Licenses

SemanticScript itself is distributed under the terms in [`LICENSE`](LICENSE).
The compiler, the native-runtime build, and the frozen single-file binary
incorporate the third-party components below. Each retains its own license;
this file aggregates the attributions required when redistributing them.

## Vendored native runtime dependencies (`third_party/`)

These are compiled into the native runtime libraries on first use (see
`semanticscript/runtime/manifest.json`).

### SQLite — `third_party/sqlite/`
Public domain. The SQLite source carries the project's standard dedication
("The author disclaims copyright to this source code. … here is a blessing").
No attribution is required, but it is provided here for transparency.

### libuv — `third_party/libuv/`
MIT License — Copyright (c) 2015-present libuv project contributors.
Full text: [`third_party/libuv/LICENSE`](third_party/libuv/LICENSE) (plus
`LICENSE-docs` and `LICENSE-extra` for the documentation and bundled extras).

### crypt_blowfish (bcrypt) — `third_party/bcrypt/`
Public domain, with a fallback to a permissive (BSD-style) license, by Solar
Designer; based on the OpenBSD bcrypt by Niels Provos and David Mazières. See
[`third_party/bcrypt/README`](third_party/bcrypt/README) and the license comment
at the top of `third_party/bcrypt/crypt_blowfish.c`.

## Bundled into the frozen executable (PyInstaller)

The single-file binary produced by `semanticscript/packaging/package.py`
(`--collect-all llvmlite`, `--onefile`) also embeds:

### llvmlite
BSD 2-Clause License — Copyright (c) Anaconda, Inc. and contributors.
Provides the LLVM bindings used for JIT/codegen.

### LLVM
Apache License 2.0 WITH LLVM-exception. The LLVM shared libraries are shipped
inside the `llvmlite` wheel and are collected into the frozen binary.

### CPython
Python Software Foundation License. The PyInstaller `--onefile` bootloader
extracts a bundled CPython runtime at launch.

---

When cutting a binary release, ship this file alongside the artifacts (the
release workflow attaches it), and keep the in-tree `third_party/*/LICENSE`
files intact — they are the authoritative texts.
