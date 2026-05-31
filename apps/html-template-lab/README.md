# html-template-lab (SemanticScript port) — COMPLETE (X-040 / X-047)

Full multi-module SemanticScript port of `apps/html-template-lab` (the v0.1
first-class HTML/SSX showcase), in the §28.2 project layout. It **JIT-runs and
builds to a native exe**, printing the complete server-rendered todo dashboard.

## Layout (README §28.2)

```
html-template-lab/
  build.sem            # project manifest: target console, entry main
  build.sem.lock
  src/
    main.sem           # console entrypoint op `main` — render the page, print it
    shared/main.sem    # 6 shared presentation constants (title, intro, row classes)
    todo-domain/main.sem    # 9 todo constants (titles/statuses/classes; classes alias shared)
    todo-components/main.sem # `renderTodoListFragment` + the TodoListTemplate htmlTemplate
    todo-pages/main.sem      # `renderTodoDashboardPage` + the TodoDashboardPageTemplate
```

## Parity — 3 operations across 5 modules, runs

Op-count matches the v0.1 source exactly (3 ops: `main`,
`renderTodoDashboardPage`, `renderTodoListFragment`). The composed project lints
clean (0 errors / 0 warnings) and JIT-runs:

- `main` (src/main.sem) calls `renderTodoDashboardPage` **across modules** and
  writes the hydrated `HtmlDocument` to stdout.
- `renderTodoDashboardPage` (todo-pages) calls `renderTodoListFragment`
  (todo-components) and nests the returned `HtmlFragment` into its page template
  as a **raw** hole — already-escaped markup is not double-escaped.
- `renderTodoListFragment` (todo-components) hydrates the fixed three-row list
  from explicit inputs via `html.render`.
- The todo-domain row classes are initialized by **aliasing** the shared row
  classes (cross-module storage initializer, README §12).

### semanticscript features this port exercised (each with a no-op-failing test)

- `html.render` nests `HtmlFragment`/`HtmlTrustedFragment` holes raw (escaping
  only plain-text holes) — `test_html_render_fragment_hole_inserted_raw`.
- A module-storage constant may alias another constant's value —
  `test_cross_module_storage_initializer_resolves`.

Validated end-to-end by `test_app_html_template_lab_jit_runs` (+ the native-exe
build test) and the X-047 parity guard.
