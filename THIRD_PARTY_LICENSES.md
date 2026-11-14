# Third-Party Licenses

SemanticScript itself is distributed under the terms in [`LICENSE`](LICENSE).
The compiler depends on the components below at run time. Each keeps its own
license.

### llvmlite
BSD 2-Clause License. Copyright (c) Anaconda, Inc. and contributors. Provides
the LLVM bindings the compiler uses to generate and JIT-compile code.

### LLVM
Apache License 2.0 WITH LLVM-exception. Shipped inside the `llvmlite` wheel.

### CPython
Python Software Foundation License. The compiler runs on CPython.

The VS Code extension's development dependency `@vscode/vsce` (MIT) is used
only to package the extension and is not distributed with it.
