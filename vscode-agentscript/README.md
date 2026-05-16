# AgentScript VSCode Extension

Local VSCode extension for AgentScript `.as` files.

It provides:

- language registration for `.as` and `.agentscript`
- TextMate token coloring for AgentScript verbs, types, strings, numbers, symbols, and comments
- semantic token coloring for declaration/context/action/control verbs
- AST-aware semantic coloring for primitive call targets, checked/domain-typed methods, error variants, opaque inputs, and role suffixes
- subtle whole-line segment colors for declaration, context, action, control, and comment lines
- hovers for implemented AST verbs, primitive targets, domain-typed methods, primitive types, opaque inputs, and call objects
- lint diagnostics from the standalone `aslint.py` CLI in the Problems panel
- a command: `AgentScript: Toggle Segment Colors`
- a command: `AgentScript: Run Linter`

The extension follows `../AgentScript/AST.md` and `../AgentScript/compiler/ascc.py` for the current parser/compiler vocabulary. Unknown verbs are intentionally left visible through the unknown-line segment color so spec drift is easy to spot.

Linting uses `../AgentScript/linter/aslint.py`. The extension auto-discovers
that file from the workspace root, the `AgentScript` folder, or ancestors of
the open `.as` file. Set `agentScript.linter.path` if your checkout layout is
different.

## Run Locally

Open this folder in VSCode:

```text
vscode-agentscript
```

Then press `F5` to launch an Extension Development Host.

Open an AgentScript file such as:

```text
../AgentScript/as/countdown.as
```

VSCode should assign the `AgentScript` language mode and color the code.

## Install Locally

From this repository root, copy or symlink the folder into your VSCode extensions directory:

```text
%USERPROFILE%\.vscode\extensions\agentscript-vscode
```

Then reload VSCode.

## Settings

```json
{
  "agentScript.segmentColors.enabled": true,
  "agentScript.segmentColors.colorMode": "background",
  "agentScript.linter.enabled": true,
  "agentScript.linter.run": "onSave",
  "agentScript.linter.pythonPath": "python",
  "agentScript.linter.path": ""
}
```

`colorMode` can be `background`, `overview`, or `both`.

`agentScript.linter.run` can be `onSave`, `onType`, or `manual`.
