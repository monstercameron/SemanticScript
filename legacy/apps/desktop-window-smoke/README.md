# Desktop Window Smoke

Minimal Windows GUI smoke fixture for the declarative GUI surface.

This app exists to keep the GUI build path honest without competing with the
curated demos. It should stay small: `build.sem` declares the executable
metadata and `main.sem` exercises the smallest useful native window path.

## Check

```powershell
python SemanticScript\tools\sem.py check apps\desktop-window-smoke --quiet
python SemanticScript\tools\sem.py build apps\desktop-window-smoke --quiet
```
