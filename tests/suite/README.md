# Language test suite

Positive, negative, and edge cases for the refined language, checked by
`tests/test_suite.py`. The coverage map in [docs/test-suite.md](../../docs/test-suite.md)
lists every checklist item with its status and the cases that prove it.

```
python -m pytest tests/test_suite.py
```

## Layout

| Path | What it holds |
| --- | --- |
| `programs/<section>/<case>.sem` | A program case: one module, with an optional `<case>.test.sem` beside it |
| `programs/<section>/<case>/` | A multi-module case with its own `build.sem` |
| `mutations.py` | Negative cases: one mistake in a passing case, and the exact rule codes it must produce |
| `caselib.py` | Reads case headers, builds a project around a case, and evaluates it |
| `sembuild.py` | Writes entities with their full skeleton; used by the generated tests |
| `coverage_map.py` | The checklist, the notes for items without evidence, and the generator of `docs/test-suite.md` |

Sections follow the checklist: `01-variables` is section 1, and so on.

## Writing a program case

A case is a complete, ordinary program. Its first lines are comments that say
what it covers and what must happen; nothing about the expectation lives
anywhere else.

```
# covers: 4 While loops                  one row per checklist item, `<section> <item>` as in the map
# kind: positive                         positive, negative, or edge
# expect: run                            see the table below
# exit: 0
# stdout: 15                             one row per expected line
```

| `# expect:` | Passes when |
| --- | --- |
| `check ok` | the checker reports nothing |
| `check R301 R405` | the checker reports exactly these codes (as a set) |
| `run` | it checks clean, runs, and matches `# exit:`, `# stdout:` and (if present) `# stderr:` |
| `trap <text>` | it checks clean, exits with code 70, and stderr contains `<text>` |
| `test pass` | it checks clean and every test in the case passes |
| `test fail <text>` | at least one test fails or traps, mentioning `<text>` |
| `unsupported <text>` | it checks clean, and the backend refuses it with R901 naming `<text>` |

A single-file case is placed in a fresh project: `target console` with entry
`<module>.main` when the module exports `main`, otherwise `target library`.

An `unsupported` case records a feature the checker accepts but the backend
cannot run yet. When the backend learns it, the case fails: change it to `run`
and give its output.

## Writing a negative case

Prefer a mutation: pick a passing case, a line in it, and the smallest edit
that breaks exactly one rule. Add an entry to `mutations.py` with the codes the
checker must report. When the mistake also breaks something that depends on it
(an unreachable block after a removed branch, say), list those codes too; the
set is exact on purpose, so a rule that starts firing where it should not is
caught.

Write a separate program case with `# expect: check <codes>` only when a
one-line edit cannot express the mistake (a module named like a standard
module, an empty file).

## After adding cases

Every `# covers:` item must exist in the checklist. Regenerate the map and run
the suite:

```
python tests/suite/coverage_map.py --write
python -m pytest tests/test_suite.py
```

An item the cases do not cover needs a note in `coverage_map.py` saying why:
`by design` (absent on purpose, and what to write instead), `gap` (wanted, not
there yet), or `n/a`.
