# TaskForge TUI

Keyboard-driven terminal todo app with JSON persistence. This is the console app showcase: native executable output, resource metadata, icon assets, terminal input, dynamic rows, edit modal behavior, and file-backed state.

## Source Layout

```text
apps/taskforge-tui/
  build.sem      # typed BuildPlan data and executable metadata
  main.sem       # app.taskforge_tui module, terminal UI, persistence, and todo operations
  assets/icons/  # generated icon assets consumed by the build plan
  build/         # ignored compiler and runtime artifacts
```

`build.sem` is the single project entrypoint. `main.sem` owns the executable operation graph and keeps the module contract near the implementation.

## Build

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python SemanticScript\compiler\semsc.py apps\taskforge-tui\build.sem --parse-only --lint
python SemanticScript\linter\semlint.py apps\taskforge-tui\build.sem --summary
python SemanticScript\compiler\semsc.py apps\taskforge-tui\build.sem --emit-exe
```

## Run

```powershell
cd C:\Users\Cam\Desktop\AgentScript\apps\taskforge-tui\build
.\taskforge_tui.exe
```

Run from `build/` so `todos.json` is read and written beside the executable.

## Keys

- Up/Down: move through todo rows and the `(new note)` row.
- Enter or Space from the list: toggle the selected todo done.
- Right from the list: open the selected todo, or create a new todo from `(new note)`.
- D from the list: delete the selected todo.
- Enter from the edit modal: save the edited title.
- Esc or Left from the edit modal: return to the list without saving.
- Esc from the list: save, clear the screen, and quit.

## Notes

The app intentionally uses some low-level `c.*` bootstrap calls while the top-level console, file, and memory API surface is still being rounded out. That makes it a good pressure test for what the standard app API should eventually hide.
