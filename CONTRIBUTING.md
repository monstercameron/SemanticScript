# Contributing

SemanticScript is in an active migration and tooling-hardening phase. Keep
changes scoped, preserve unrelated working-tree edits, and prefer commands that
work from PowerShell on Windows as well as POSIX shells.

## Setup

Create an isolated Python environment and install the compiler dependency:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

On POSIX shells, use `. .venv/bin/activate` or call `.venv/bin/python`
directly.

The VS Code extension check uses Node.js. Install Node 20 or newer when working
on `vscode-semanticscript/`.

## Focused Validation

Run these before sending a narrow tooling or docs change:

```powershell
python -m compileall -q SemanticScript python
python -m unittest SemanticScript/formatter/test_semfmt.py -v
python SemanticScript/formatter/semfmt.py --check SemanticScript/tests/tiny.sem
python -m unittest SemanticScript/linter/test_semlint.py -v
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sscript --parse-only
python SemanticScript/compiler/semsc.py SemanticScript/tests/tiny.sem --parse-only
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sscript --summary
python SemanticScript/linter/semlint.py SemanticScript/tests/tiny.sem --summary
npm --prefix vscode-semanticscript run check
```

Use broader checks when changing compiler lowering, stdlib behavior, sample
programs, or source-file extension handling:

```powershell
python SemanticScript/tests/test_compiler.py
python SemanticScript/tests/test_stdlib.py
python SemanticScript/tests/compare.py
python SemanticScript/tests/sem_alias_parity.py
```

Some broader checks require Node.js, LLVM/clang, and a working native compiler
toolchain. Set `SEMSC_CLANG` if clang is not discoverable on PATH.

## Pull Request Notes

- Include the commands you ran and any skipped checks.
- Do not commit generated outputs such as `.exe`, `.ll`, `.pyc`, build folders,
  packaged `.vsix` files, or `__pycache__/`.
- Do not introduce public `.as` source-extension support.
- Do not change the project license without a release-owner decision.

## License

SemanticScript is distributed under the MIT License. See the root `LICENSE` file
for the full license text. Third-party code under `third_party/` keeps its own
upstream license terms.
