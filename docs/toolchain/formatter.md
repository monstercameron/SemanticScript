# Formatter

`SemanticScript/formatter/semfmt.py` is the canonical formatter for `.sem` and
`.sscript` files.

## Commands

```powershell
python SemanticScript/formatter/semfmt.py apps/taskforge-tui/main.sem
python SemanticScript/formatter/semfmt.py --check SemanticScript/tests/tiny.sem
python SemanticScript/formatter/semfmt.py --diff "apps/**/*.sem"
python SemanticScript/tools/sem.py fmt --check apps/taskforge-tui
```

## Canonical Defaults

The formatter is intentionally conservative:

- one space between code tokens;
- trailing whitespace removed;
- quoted string spellings and escape sequences preserved byte-for-byte;
- inline comments separated from code by two spaces;
- full-line comments preserved, with optional cleanup for nested typed-comment
  headings such as `# # rationale:`;
- blank-line runs collapsed to one separator line;
- top-level declaration and operation-body rows left unindented;
- `html body template` and `jsonBody` indented islands preserved rather than normalized.

There is no maximum line width in the current canonical style. Long strings and
long metadata text stay on their original physical row; the formatter does not
wrap or split them.

The formatter preserves source order for metadata rows, executable rows, route
rows, and syntax islands. It does not reorder rows in the current canonical
style.

The formatter does not currently choose a newline mode beyond preserving the
input style or rewrite quote style. Those behaviors remain future configuration
work.
