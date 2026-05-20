# Agent Workflows

This page collects command paths that are stable enough for agents to use while
editing SemanticScript projects.

## Fast Validation

Run the smallest useful validation set before and after focused edits:

```powershell
python -m py_compile SemanticScript\compiler\semsc.py SemanticScript\linter\semlint.py SemanticScript\tools\sem.py
python SemanticScript\tools\sem.py check SemanticScript\tests\tiny.sem
python SemanticScript\tools\sem.py lint --engine semlint SemanticScript\tests\tiny.sem --summary
python SemanticScript\tools\sem.py fmt --check SemanticScript\tests\tiny.sem
```

Use the broader release commands in `RELEASE.md` when changing compiler,
runtime, stdlib, package, or editor behavior.

## Inspecting Project Graphs

Use structured tool output before patching behavior that touches routes,
effects, capabilities, or generated native ABI:

```powershell
python SemanticScript\tools\sem.py inspect-ir app\todo-web-pro\build.sem
python SemanticScript\tools\sem.py context --json app\todo-web-pro\build.sem
python SemanticScript\tools\sem.py symbols --json app\todo-web-pro\build.sem
python SemanticScript\tools\sem.py lint --engine semlint app\todo-web-pro\build.sem --format json
```

`context --json` is the quick project envelope: roots, entrypoints, tool
versions, runtime feature flags, syntax support counts, and known deferred
feature counts. `symbols --json` is the source graph: modules, imports,
operations, calls, inputs, outputs, effects, routes, source locations, and
unresolved references. `inspect-ir` is the source-to-LLVM and route/ABI view.
The linter JSON output remains the strictest current view for rule diagnostics,
fix candidates, export/import contracts, and warning edges.

## Updating Generated Docs

Generated documentation should be updated only by the tool that owns it. When no
generator exists, edit the source documentation directly and do not invent a
generated output file. Keep regenerated files in the same change as the source
that caused them to change.

## Ignored Artifacts

Do not patch ignored build output. Use a dry run before cleanup:

```powershell
python SemanticScript\tools\sem.py clean
```

Expected ignored locations include `build/`, `.semcache/`, native executable and
object output, LLVM IR output, packaged VSIX files, Python caches, and local app
data such as `app/todo/todos.json`. Pass `--force` only after reviewing the dry
run.
