# taskforge-tui (SemanticScript port)

Full 1:1 SemanticScript port of `apps/taskforge-tui` (the v0.1 SemanticScript
heap-array keyboard todo app with JSON persistence).

## Parity

- **24 operations** — the keyboard reader, ANSI screen control (clear/hide/show),
  the bounded C-string/JSON buffer helpers, the fixed-offset JSON tokenizer, the
  table renderer + edit modal, scroll/selection math, JSON load/save, the
  todo-array mutators, and the interactive `main` state machine — matching the
  original op count exactly.
- Every `c.*` (malloc/free/memset/memmove/fopen/fgets/fprintf/fclose/printf/
  putchar/puts/fflush/terminalReadKey), `pointer.*` (loadByte/storeByte/offset/
  isNull), and `math.*` call is converted; **244 call entities** (the §20 split).

## Conversions / language differences

- The imperative mutable-state machine is expressed with the **`set` step**
  (README §12, added for this port): `set memory X V` → `set X V`. Counter
  rebinds whose value is a call result use the call's `out` instead. Module
  constants use the **single-line storage form** (`NAME is storage module
  immutable Int32 27`).
- `EnumName.equal` domain method → `compare.equalInt32` (SemanticScript enums are i32
  discriminants); the `SaveTodosStatus`/`ScreenMode` enums keep their cases.
- `authority ACTION PATH` → covering `capability`/`grants` + `uses` (§8).
- `branch if condition C target L` → `branch if C goto L`; `branch else target L`
  / `jump target L` → `goto L`; `label L` → `at L`.
- `main` returns `ExitCode` (console-entry ABI), so the v0.1 `Result ExitCode
  MainError` + `makeError`/`return error` become a nonzero exit code, and malloc
  failure is detected with `pointer.isNull` (uniform with the file open the app
  already null-checks). `CAllocationError`/`MainError` are dropped.
- The handle-less `defer … showCursor (deferRunOn all)` becomes a targeted
  `showCursor` on the quit path (the only path that hid the cursor); SemanticScript cleanups
  are handle-scoped (`cleans <handle>` required).

## Deferred execution

The keyboard adapter (`c.terminalReadKey`) and the interactive REPL loop have no
headless runtime, so the app parses + lints clean as `target console` but is not
run by the suite. File I/O (`c.fopen`/`fgets`/…) is real libc; only the
terminal-input + interactive loop gate execution. When a headless key source is
available, this source runs unchanged.
