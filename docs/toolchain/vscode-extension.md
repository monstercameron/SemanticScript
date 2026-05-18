# VS Code Extension

The extension lives in `vscode-semanticscript/`. It is editor tooling, not a
compiler. It recognizes both executable SemanticScript and refined syntax so the
source remains inspectable while the runtime catches up.

## Responsibilities

The extension should provide:

```text
language registration for .sscript and .sscript
TextMate highlighting
semantic token roles
whole-line segment coloring
context-aware verb hovers
same-file operation metadata hovers
same-file identifier hovers
primitive target hovers
linter integration
manual linter command
```

It should not claim a syntax form is executable just because it is highlighted.
Hover text should distinguish metadata, lowered behavior, and synchronous
fallback behavior.

## Hover Expectations

Hovers need to answer "what does this token mean here?", not "what grammar tag
matched?"

Useful hover for a const declaration:

```text
Constant: zeroValue
Type: CSignedInt32
Initial value: 0
Scope: current operation
```

Useful hover for a call target:

```text
Call: checkNullCall -> math.equalI64
Arguments:
  left: asciiNullCharacterCode
  right: zeroValue
Result binding:
  isNullCharacterCode Bool
```

Useful hover for a symbol use:

```text
Variable: currentOffset
Declared: line 42
Type: I64
Mutable: local var
Current use: argument value passed to scanByteCall.offset
```

Avoid generic wording like "SemanticScript verb: const" when the line schema gives
the actual semantic object.

## Settings

```json
{
  "semanticScript.segmentColors.enabled": true,
  "semanticScript.segmentColors.colorMode": "background",
  "semanticScript.linter.enabled": true,
  "semanticScript.linter.engine": "semlint",
  "semanticScript.linter.run": "onSave",
  "semanticScript.linter.pythonPath": "python",
  "semanticScript.linter.path": "",
  "semanticScript.linter.skipFutureSyntax": true
}
```

Accepted values:

```text
semanticScript.segmentColors.colorMode: background | overview | both
semanticScript.linter.engine: semlint | semlint2
semanticScript.linter.run: onSave | onType | manual
```

## Local Development

Run the syntax check:

```powershell
cd vscode-semanticscript
npm run check
```

Launch an extension host:

```text
Open vscode-semanticscript in VS Code, then press F5.
```

Open representative files:

```text
../SemanticScript/sem/countdown.sscript
../SemanticScript/sem/feature_tests/147_worker_pool_submit_work_runs.sscript
../experiments/refined_syntax_example.sscript
```

## Packaging

```powershell
cd vscode-semanticscript
npm run check
npx --yes @vscode/vsce package
```

The packaged `.vsix` is ignored by git. After installing a new VSIX, reload VS
Code or restart the extension host before checking hovers.

## Update Rule

When adding a language verb:

1. Add TextMate coverage in `syntaxes/semanticscript.tmLanguage.json`.
2. Add semantic classification in `extension.js`.
3. Add context-aware hover text for the concrete line schema.
4. Add identifier indexing if the verb declares or references a symbol.
5. Update `README.md` and the docs file that owns the verb family.
6. Package a new VSIX only after `npm run check` passes.

