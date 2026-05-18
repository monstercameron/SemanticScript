# Todo Web App

Small SemanticScript web-server sample for the native HTTP runtime path.

## Contents

- `todo_web.sscript` declares a `target webServer` app.
- The root route returns a plain-text hello response.
- `test_todo_web.py` compiles the native executable, starts it, and performs
  real HTTP requests against it.

## Current Status

This app exercises the source-level web server API. The compiler can parse,
lint, emit a native webserver `main`, and link the SemanticScript HTTP runtime
adapter. The current adapter backend is blocking HTTP/1.1; H2O/HTTP2 remains
the planned production backend.

## Check

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python SemanticScript\compiler\semsc.py app\todo-web\todo_web.sscript --parse-only --lint
python SemanticScript\compiler\semsc.py app\todo-web\todo_web.sscript --emit-ir app\todo-web\todo_web.ll
python app\todo-web\test_todo_web.py
```

Expected HTTP response once the native HTTP backend is wired:

```text
hello from todo web
```
