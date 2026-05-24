# VS Code Extension

The extension lives in `vscode-semanticscript/`. It is editor tooling, not a
compiler. It recognizes both executable SemanticScript and refined syntax so the
source remains inspectable while the runtime catches up.

## Responsibilities

The extension should provide:

```text
language registration for .sscript and .sem
extension and file icons for SemanticScript sources
TextMate highlighting
semantic token roles
whole-line segment coloring
context-aware verb hovers
same-file operation metadata hovers
same-file identifier hovers
project-aware build-tape and import navigation
primitive target hovers
primitive type hovers
linter integration
linter related-span annotations
linter quick fixes for auto-applicable single-line fixes
manual linter command
direct compiler command integration
```

It should not claim a syntax form is executable just because it is highlighted.
Hover text should distinguish metadata, lowered behavior, and synchronous
fallback behavior.

## Hover Expectations

Hovers need to answer "what does this token mean here?", not "what grammar tag
matched?"

Useful hover for an immutable storage declaration:

```text
Storage: zeroValue
Type: Int32
Initial value: 0
Scope: local
Mutability: immutable
```

Useful hover for a call target:

```text
Call: checkNullCall -> math.equalInt64
Arguments:
  left: asciiNullCharacterCode
  right: zeroValue
Result binding:
  isNullCharacterCode Bool
```

Useful hover for a symbol use:

```text
Storage: currentOffset
Declared: line 42
Type: Int64
Scope: local
Mutability: mutable
Current use: argument value passed to scanByteCall.offset
```

Avoid generic wording like "SemanticScript verb: storage" when the line schema gives
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
  "semanticScript.linter.skipFutureSyntax": true,
  "semanticScript.compiler.pythonPath": "python",
  "semanticScript.compiler.path": "",
  "semanticScript.compiler.buildProfile": "dev",
  "semanticScript.compiler.runtimeChecks": "default",
  "semanticScript.compiler.persistLlvmIr": "auto",
  "semanticScript.compiler.optLevel": "default",
  "semanticScript.compiler.emitLlvmIr": false,
  "semanticScript.compiler.emitOptimizedLlvmIr": false
}
```

Accepted values:

```text
semanticScript.segmentColors.colorMode: background | overview | both
semanticScript.linter.engine: semlint
semanticScript.linter.run: onSave | onType | manual
semanticScript.compiler.buildProfile: dev | prod
semanticScript.compiler.runtimeChecks: default | off | traps | panic
semanticScript.compiler.persistLlvmIr: auto | yes | no
semanticScript.compiler.optLevel: default | 0 | 1 | 2 | 3
```

`semanticScript.compiler.emitLlvmIr` passes `--emit-ir`.

`semanticScript.compiler.emitOptimizedLlvmIr` passes `--emit-optimized-ir`.

## Coverage Notes

The extension should stay aligned with the executable toolchain and the active
experiments, not just the stable demo files.

Recent coverage includes:

```text
routeNotFound and routeMethodNotAllowed web-server declarations
runtimeBindingAsyncStart and runtimeBindingAsyncAwait operation metadata
standard.http SSE, outbound client, and HTML-escape targets
standard.sqlite execStatus
standard.jwt signer, verifier, claim-reader, and auth-envelope helpers
standard.http and standard.jwt exported alias types used by the realtime auction arena
project-aware import navigation through the nearest build.sem
semlint related locations and auto-applicable quick fixes
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
../SemanticScript/sem/refined_syntax_demo.sscript
../SemanticScript/sem/syntax_sample_web_server.sscript
../SemanticScript/sem/feature_tests/147_worker_pool_submit_work_runs.sscript
../experiments/realtime-auction-arena/server/src/main.sem
../experiments/realtime-auction-arena/browser-sse-client/main.sem
```

## Packaging

```powershell
cd vscode-semanticscript
npm ci
npm run check
npm run package:vsix
```

The packaged `.vsix` is ignored by git. After installing a new VSIX, reload VS
Code or restart the extension host before checking hovers.

## Update Rule

When adding a language verb:

1. Add TextMate coverage in `syntaxes/semanticscript.tm-language.json`.
2. Add semantic classification in `extension.js`.
3. Add context-aware hover text for the concrete line schema.
4. Add identifier indexing if the verb declares or references a symbol.
5. Update `README.md` and the docs file that owns the verb family.
6. Package a new VSIX only after `npm run check` passes.

When changing extension icons, keep the file icon theme in
`vscode-semanticscript/icons/semanticscript-icon-theme.json` aligned with the
language extensions registered in `package.json`.
