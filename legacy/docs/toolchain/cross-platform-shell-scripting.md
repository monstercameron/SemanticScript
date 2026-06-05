# Cross-Platform Shell Scripting

Use Python harnesses for non-trivial cross-platform test automation. They avoid
PowerShell/Bash quoting drift, keep paths structured, and run the same way from
source checkouts and release `sem.exe` workflows.

## Writing SemanticScript Fragments

Prefer writing a complete fragment file and appending or copying that file as a
separate filesystem operation. This avoids heredoc delimiter and apostrophe
failures when SemanticScript text contains quoted SQL, HTML, JavaScript, or
English prose.

PowerShell:

```powershell
@'
operation appendTodo
purpose operation appendTodo "Append a user's todo"
return void
'@ | Set-Content -Path fragment.sem -Encoding utf8
Get-Content -Raw fragment.sem | Add-Content -Path main.sem -Encoding utf8
```

Bash:

```sh
cat > fragment.sem <<'SEM'
operation appendTodo
purpose operation appendTodo "Append a user's todo"
return void
SEM
cat fragment.sem >> main.sem
```

Do not inline large SemanticScript snippets directly into command arguments.
Use `sem eval --code` only for short smoke snippets; use a real file for
anything that contains quotes, braces, SQL, HTML, or multiple operations.

## Harness Format

Project runtime harnesses should be Python files under `tests/` or
`scripts/`. Invoke `sem` through `subprocess.run([...])` with argument arrays,
not shell strings. Use `Path` for filesystem joins, pass an explicit `cwd`, and
copy runtime assets beside the executable before launching a native app.

When a harness starts a long-running executable, always keep the `Popen` handle
and terminate it in `finally`. This keeps Windows rebuilds from being blocked by
an older process and avoids leaking server processes during failed tests.

```python
proc = subprocess.Popen([str(exe_path)], cwd=exe_path.parent)
try:
    # poll health endpoint or run client assertions
    ...
finally:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
```
