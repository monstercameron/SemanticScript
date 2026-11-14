# stage0 generators

stage0's larger modules are written by these scripts: the syntax is explicit
(about 12 rows per call, D-113), so each operation is described briefly in a
`.dsl` file and `build.py` writes every row. `refined check` validates the
output like any other source; the generated `.sem` files are the compiler.

Regenerate from this folder, with the compiler's Python environment:

    python build.py model subset emitc stage0
    python build.py samples

Regenerating must leave `git status` clean; a change to the compiler is a
change to a `.dsl`, `.header`, or script here followed by regeneration.
`semgen.py` finds the repository from this folder (or `SEMGEN_WT`).
