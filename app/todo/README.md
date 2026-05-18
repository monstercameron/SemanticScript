# Todo TUI App

Small SemanticScript console todo app with a keyboard-driven terminal UI and JSON persistence.

Run commands from this folder so `todos.json` is read and written next to the executable.

## Contents

- `todo.sscript` is the app source.
- `todo.exe` is the generated native executable.
- `todos.json` is runtime data written beside the executable.

## Current Status

Active sample app. It currently uses some low-level `c.*` bootstrap calls while
the top-level console/file/memory API is still being designed.

## Build

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python SemanticScript\compiler\semsc.py app\todo\todo.sscript --parse-only --lint
python SemanticScript\linter\semlint.py app\todo\todo.sscript --summary
python SemanticScript\compiler\semsc.py app\todo\todo.sscript --emit-exe app\todo\todo.exe
```

## Run

```powershell
cd C:\Users\Cam\Desktop\AgentScript\app\todo
.\todo.exe
```

## Keys

- Up/Down: move through rows or action choices.
- Enter/Right: open the action menu or run the selected action.
- Esc/Left: go back from the action menu.
- Esc from the list: save and quit.

The app writes `todos.json` after changes and on quit. The file is a fixed three-item JSON array of todo objects, and todo titles should avoid double quotes.

Keyboard input uses the Windows `_getch` console primitive exposed to SemanticScript as `c.consoleGetch`.
