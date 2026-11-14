# stage0 generators

stage0's modules but the lexer are written by these scripts: the syntax is
explicit (about 12 rows per call, D-113), so each operation is described
briefly in a `.dsl` file and `build.py` writes every row. `refined check`
validates the output like any other source; the generated `.sem` files are the
compiler.

- `model.dsl`, `subset.dsl`, `emitc.dsl`, `stage0.dsl`: the modules, with
  their headers in `<module>.header` and their tests' headers in
  `<module>.test.header`. `subset.dsl` and `emitc.dsl` take their tables
  (types, predicates, standard library targets and their C spellings) from
  `build.py`, and `emitc.dsl` its C prelude from `prelude.c`.
- `syntax.sem` is written by hand but for `Rejection`, `rejectionWord`, and
  `rejectionMessage`, which `build.py` writes from its list of rejections.
- `tests_gen.py` and `macros.py` write the subset and emitc tests.
- `samples/*.dsl` are the sample programs; a folder under `samples/` is a
  sample of several modules (`SAMPLE_PROJECTS` in `build.py` gives their
  order).
- `usage.py` lists what stage0's own modules use (entity kinds, predicates,
  steps, and call targets) and checks each against what stage0 compiles.

Regenerate from this folder, with the compiler's Python environment:

    python build.py syntax model subset emitc stage0
    python build.py samples
    python usage.py

Regenerating must leave `git status` clean; a change to the compiler is a
change to a `.dsl`, `.header`, or script here followed by regeneration.
`semgen.py` finds the repository from this folder (or `SEMGEN_WT`).
