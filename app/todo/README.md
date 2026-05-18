# Todo TUI App

Small SemanticScript console todo app with a keyboard-driven terminal UI and JSON persistence.

Run commands from this folder so `todos.json` is read and written next to the executable.

## Quick Preview

![Todo TUI demo preview](../../docs/assets/todo-tui-preview.png)

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

- Up/Down: move through todo rows and the `(new note)` row.
- Enter or Space from the list: toggle the selected todo done.
- Right from the list: open the selected todo, or create a new todo from `(new note)`, in the edit modal.
- D from the list: delete the selected todo.
- Enter from the edit modal: save the edited title.
- Esc or Left from the edit modal: return to the list without saving.
- Esc from the list: save, clear the screen, and quit.

The app writes `todos.json` after changes and on quit. Active todos are loaded into heap-backed arrays, then saved as a JSON array of todo objects. Titles are escaped for double quotes and backslashes, and the loader expects the exact object key order emitted by the app.

Keyboard input uses the Windows `_getch` console primitive exposed to SemanticScript as `c.consoleGetch`.
