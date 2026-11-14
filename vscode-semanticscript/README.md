# SemanticScript VS Code Extension

Editor support for SemanticScript `.sem` files, driven by the refined compiler.

- **Highlighting.** `syntaxes/semanticscript.tm-language.json` is generated from
  the compiler's shape table with
  `python semanticscript/compiler/refined grammar --textmate --output vscode-semanticscript/syntaxes/semanticscript.tm-language.json`.
  Do not edit it by hand; CI fails if it is out of date.
- **Diagnostics.** On open and on save, the extension runs
  `refined check --json` on the file's project (the nearest directory above the
  file that holds `build.sem`) and shows every diagnostic with its code.
- **Commands.** SemanticScript: Check Project, Run Project, Test Project.
- **Snippets.** `operation`, `call`, and `test` insert the full skeleton.

Settings: `semanticScript.pythonPath`, `semanticScript.compilerPath` (found in
the workspace when empty), and `semanticScript.checkOnSave`.

Run `npm run check` to validate the extension. The package is local VSIX only
(`publisher: semanticscript-local`) until a Marketplace publisher is chosen.
