# HTML Template Lab

First-class HTML syntax demo that renders a complete HTML document to stdout. This is the small, readable showcase for `html template`, `html hole`, `html body`, and module-split HTML fragments.

## Source Layout

```text
apps/html-template-lab/
  build.sem
  main.sem
  modules/
    shared/
    todo-domain/
    todo-components/
    todo-pages/
```

The app keeps reusable text helpers, todo data, row/card components, and page assembly in separate registered modules. It is intentionally a console executable so the generated HTML can be checked without running a browser or server.

## Build And Run

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python SemanticScript\compiler\semsc.py apps\html-template-lab\build.sem --emit-exe --quiet
.\apps\html-template-lab\build\html-template-lab.exe
```

Expected output starts with `<!doctype html>` and includes the `TaskForge TUI HTML Template Lab` page title.

## Why This Stays

- It is compact enough to read end to end.
- It shows the revised HTML hole model without the removed `html parameter` layer.
- It exercises multi-module build registration without the noise of HTTP, sqlite, or auth.
