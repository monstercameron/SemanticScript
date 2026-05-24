# Kilo Port Parity

Parity tracker for the SemanticScript port of Kilo.

## Baseline

- Upstream source: `experiments/kilo-port/upstream-kilo/`
- Upstream origin: `https://github.com/antirez/kilo.git`
- Baseline commit: `323d93b29bd89a2cb446de90c4ed4fea1764176e`
- Upstream entry point: `kilo.c`
- Port target: `experiments/kilo-port/build.sem` and `experiments/kilo-port/main.sem`

## Status Legend

- `[ ]` not started
- `[~]` partial or approximate parity
- `[x]` implemented and checked
- `[!]` known divergence

## Parity Checklist

### Build And Startup

- [x] SemanticScript project tape builds a native executable.
- [x] Executable accepts a filename argument through the generic terminal
  runtime. Fallbacks are `KILO_FILE`, then `kilo.txt`.
- [x] Empty-buffer startup opens an editable blank document.
- [x] Existing-file startup loads file contents into editor rows.
- [~] Startup errors are surfaced where the current native calls expose them.

### Terminal Lifecycle

- [x] Windows raw-ish console mode and VT processing are enabled by the generic
  native terminal runtime.
- [x] Normal quit restores terminal mode, shows the cursor, and clears the
  screen.
- [~] Fatal/error terminal restoration is best-effort; allocation failures
  happen before raw mode is enabled.
- [x] Window size is read from the console and the editor reserves two status
  rows, matching Kilo's layout model.
- [x] VT100 escape output is centralized in small SemanticScript operations.

### Rendering

- [x] Screen refresh clears and redraws the full editor view.
- [x] Welcome/help message appears when the buffer is empty.
- [x] File rows render with horizontal and vertical scrolling.
- [x] Status bar shows filename, modified marker, row count, and cursor row.
- [~] Message bar displays current status; time-expiry is still approximate.
- [x] Cursor position is restored after each refresh.

### Editing

- [x] Character insertion works at the cursor.
- [x] Enter splits rows or creates rows.
- [x] Backspace deletes before the cursor and joins rows at line start.
- [x] Delete follows the upstream move-right-then-backspace behavior.
- [x] Tab inserts a real tab byte and renders with Kilo-style tab stops.
- [x] Arrow keys move across rows and line boundaries.
- [x] Page Up and Page Down move by visible screen height.
- [x] Home and End move within the current row.
- [x] Dirty state is tracked after edits and cleared after save.

### File I/O

- [x] Save writes all rows with newline separators.
- [x] Save updates dirty state and status message.
- [x] Save reports open/write failures through status messages.
- [x] Open handles missing files as a new buffer.
- [~] Open reports read/allocation failures that the current native calls make
  distinguishable.

### Search

- [x] Ctrl-F opens a search prompt.
- [x] Search accepts typed query text and moves to a found row.
- [x] Live search updates while typing, arrow keys traverse next/previous
  matches, Esc restores the pre-search cursor/scroll state, and matches render
  with Kilo's blue overlay while search is active.
- [x] Enter accepts the current match.

### Syntax Highlighting

- [x] Strings with escaped quotes, `//` comments, cross-row `/* ... */` block
  comments, decimal digits, JavaScript declaration/control keywords, and
  JavaScript literal/type/global tokens are colored.
- [~] Full upstream C/C++ keyword DB is still approximate; the highlighter
  remains lightweight and also includes JavaScript tokens requested for this
  port.

### Quit Behavior

- [x] Ctrl-Q exits immediately when there are no unsaved changes.
- [x] Dirty Ctrl-Q requires three warning presses, then the fourth Ctrl-Q exits,
  matching upstream `KILO_QUIT_TIMES = 3`.
- [x] Quit clears the screen, shows the cursor, restores terminal mode, and
  exits.

### Runtime Boundary

- [x] Terminal behavior is implemented in the generic native terminal runtime,
  not as Kilo-specific compiler behavior.
- [x] Compiler changes are limited to generic symbol registration, effect
  linting, and automatic runtime linking for `terminal*` calls.

### Verification

- [x] `python SemanticScript\compiler\semsc.py experiments\kilo-port\build.sem --parse-only --lint --quiet`
  completes.
- [x] `python SemanticScript\compiler\semsc.py experiments\kilo-port\build.sem --emit-exe --quiet`
  emits `experiments/kilo-port/build/kilo_port.exe`.
- [x] Executable smoke: argv path, insert `abc`, Ctrl-S save, Ctrl-Q clean quit
  writes `abc\n`.
- [x] Executable smoke: 300-byte line saves intact through the two-byte row
  length table.
- [x] Executable smoke: Tab key saves a real `\t` byte and renders expanded
  spacing before save.
- [x] Executable smoke: JavaScript file rendering emits ANSI colors for
  keywords, literals/types, comments, and numbers.
- [x] Executable smoke: live search emits the blue search-match overlay and
  right-arrow traversal stays interactive.
- [x] Executable smoke: Page Down key is accepted and handled.
- [x] Executable smoke: `KILO_FILE` fallback path, insert `xy`, Ctrl-S save,
  Ctrl-Q clean quit writes `xy\n`.
- [x] Executable smoke: argv filename takes precedence over `KILO_FILE`.
- [x] Executable smoke: dirty buffer with only three Ctrl-Q presses remains
  running; fourth Ctrl-Q exits without saving.
- [x] Repeatable smoke coverage lives in `experiments/kilo-port/scripts/test_kilo_port.py`.
- [ ] Manual interactive parity pass against upstream C Kilo.
