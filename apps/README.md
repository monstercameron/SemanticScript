# SemanticScript Apps

Runnable SemanticScript demos and smoke fixtures.

## Showcase Demos

- `taskforge-tui/`: keyboard-driven terminal todo app with JSON persistence.
- `html-template-lab/`: first-class HTML template demo with module-split fragments and bare string holes.
- `http-runtime-gauntlet/`: native HTTP conformance harness covering routing, request reads, response writes, multipart, SSE, middleware, and failure paths.
- `taskforge-web/`: multi-user web app with HTML pages, static assets, bcrypt authentication, sqlite persistence, JSON APIs, sessions, and cookie flow.

## Smoke Fixtures

- `desktop-window-smoke/`: minimal Windows GUI build smoke for the declarative GUI surface.

The legacy one-file web demos were removed after their coverage was absorbed by `http-runtime-gauntlet` and `taskforge-web`.
The Kilo editor port now lives under `experiments/kilo-port` because it is useful as a stress port, but too large and specialized to sit in the curated app demo set.

## Standard Check

```powershell
cd C:\Users\Cam\Desktop\AgentScript
python -m unittest SemanticScript.tests.test_app_runtime_smoke -v
```

This builds or runs every curated app target that should remain healthy.
