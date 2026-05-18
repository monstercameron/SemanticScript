# Todo TUI App

Small SemanticScript console todo app with a keyboard-driven terminal UI and JSON persistence.

Run the generated executable from `build/` so `todos.json` is read and written next to it.

## Quick Preview

![Todo TUI demo preview](../../docs/assets/todo-tui-preview.png)

## Contents

- `build.sem` is the experimental project build tape for the future
  SemanticScript project model. It declares project metadata, output policy,
  and the module registry.
- `main.sem` is the canonical app module source, default executable entry,
  and owner of the module import/export contract.
- `build/todo.exe` is the generated native executable.
- `build/todo.ll` is the optional persisted LLVM IR sidecar.
- `build/resources/` contains generated linker resources such as VERSIONINFO.
- `build/todos.json` is runtime data written beside the executable.

## Project Layout Lab

```text
app/todo/
  build.sem      # future project/build/comptime tape + module registry
  main.sem       # app.todo source + local imports/exports
  build/         # ignored compiler/app artifact directory
    todo.exe
    todo.ll
    resources/
    todos.json
```

This app is intentionally still a single root module. `build.sem` is the single
build point and registers `app.todo`; `main.sem` declares `module app.todo` and
keeps the export surface beside the source it describes. Later work can move
TUI, persistence, and todo domain operations into folder modules by registering
new module folders in `build.sem` and importing them from the module files.

## Current Status

Active sample app. It currently uses some low-level `c.*` bootstrap calls while
the top-level console/file/memory API is still being designed.

## Build

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python SemanticScript\compiler\semsc.py app\todo\build.sem --parse-only --lint
python SemanticScript\linter\semlint.py app\todo\build.sem --summary
python SemanticScript\compiler\semsc.py app\todo\build.sem --emit-exe
```

`build.sem` is the single build point for the project-layout lab. It owns the
project identity, target/runtime rows, embedded executable metadata, generated
artifact directory, and module registry. Module files own their own
`importModule` and explicit `export*` rows; exports must name symbols declared
by that same module source, never inferred reachable symbols.

## Run

```powershell
cd C:\Users\Cam\Desktop\AgentScript\app\todo\build
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
