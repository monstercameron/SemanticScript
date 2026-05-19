# SemanticScript 1.0 Release TODO

This file tracks the release-readiness gaps found in the 2026-05-18 project
review. A task is only done when the linked command or artifact is clean.

## P0 - Todo Web Native Webserver Effort

- [x] Add a granular root TODO section for the Todo Web native webserver work.
- [x] Preserve existing release TODO items without marking unrelated work done.
- [x] Keep the Todo Web effort scoped away from unrelated dirty app files.
- [x] Review current `webServer`, `serverHost`, `serverPort`, and `route`
      parser support.
- [x] Review current `target webServer` codegen behavior.
- [x] Review current opaque input handling for `HttpRequest`.
- [x] Review current type lowering for `HttpRequest` and `HttpResponse`.
- [x] Review the native HTTP adapter ABI in `sem_http_runtime.h`.
- [x] Review the default runtime adapter implementation in
      `sem_http_runtime.c`.
- [x] Review native executable linking in `semsc.py`.
- [x] Add LLVM type support for `HttpRequest`.
- [x] Add LLVM type support for `HttpResponse`.
- [x] Preserve `HttpRequest` route-handler inputs in the webserver ABI.
- [x] Preserve `HttpResponse` route-handler inputs in the webserver ABI.
- [x] Keep ordinary opaque dependency inputs skipped outside the web ABI.
- [x] Detect routed `webServer` declarations during no-entry codegen.
- [x] Collect route handler operation names before declaring user op functions.
- [x] Validate that route handlers declare `HttpRequest` then `HttpResponse`.
- [x] Validate that route handlers return `CSignedInt32` / i32.
- [x] Emit a real native `main` for routed webserver programs.
- [x] Emit an in-memory route table from `route` metadata.
- [x] Emit native server config from `serverHost`, `serverPort`, and routes.
- [x] Emit handler function pointers into the route table.
- [x] Declare `ss_http_server_run` in generated LLVM.
- [x] Call `ss_http_server_run` from generated `main`.
- [x] Lower `http.responseText` to `ss_http_response_text`.
- [x] Lower `http.requestMethod` to `ss_http_request_method`.
- [x] Lower `http.requestPath` to `ss_http_request_path`.
- [x] Preserve content type defaulting in the runtime adapter.
- [x] Link `sem_http_runtime.c` automatically for routed webserver executables.
- [x] Link Winsock automatically for routed webserver executables on Windows.
- [x] Replace the runtime stub backend with a blocking HTTP/1.1 socket backend.
- [x] Validate route tables before binding a socket.
- [x] Bind the configured server host.
- [x] Bind the configured server port.
- [x] Listen with a fixed connection backlog.
- [x] Accept client connections in a blocking loop.
- [x] Parse the HTTP request line.
- [x] Extract request method.
- [x] Extract request path.
- [x] Strip query strings before exact-route matching.
- [x] Match route methods case-insensitively.
- [x] Match route paths exactly.
- [x] Dispatch matched routes to generated SemanticScript handlers.
- [x] Pass `SSHttpRequest` into handlers.
- [x] Pass `SSHttpResponse` into handlers.
- [x] Send handler-written text responses.
- [x] Send `400 bad request` for malformed request lines.
- [x] Send `404 not found` for missing routes.
- [x] Send `500 handler failed` for handler status failures.
- [x] Send `500 handler did not write a response` for empty handler responses.
- [x] Emit `Content-Type`.
- [x] Emit `Content-Length`.
- [x] Emit `Connection: close`.
- [x] Close client sockets after each response.
- [x] Update runtime CMake to link Winsock on Windows.
- [x] Update native HTTP runtime docs for the new fallback backend.
- [x] Update native HTTP language docs for real native `main` support.
- [x] Update Todo Web to use a less collision-prone local port.
- [x] Add a Todo Web HTTP test harness.
- [x] Test Todo Web parse and compiler lint.
- [x] Test Todo Web standalone linter summary.
- [x] Test Todo Web LLVM IR emission.
- [x] Inspect emitted IR for the route handler signature.
- [x] Inspect emitted IR for `ss_http_response_text`.
- [x] Inspect emitted IR for `ss_http_server_run`.
- [x] Test native executable emission.
- [x] Test server startup from the native executable.
- [x] Test `GET /` returns HTTP 200.
- [x] Test `GET /` returns `hello from todo web`.
- [x] Test `GET /?sample=1` still routes to `/`.
- [x] Test `GET /missing` returns HTTP 404.
- [x] Test 404 body is `not found`.
- [x] Test headers include `Content-Type`.
- [x] Test headers include correct `Content-Length`.
- [x] Test the server through Python `http.client`.
- [x] Test the server through external `curl.exe`.
- [x] Test runtime CMake build after socket backend changes.
- [x] Run compiler unit tests after codegen changes.

## P0 - Release Validation Must Be Green

- [x] Fix `python SemanticScript\tests\compare.py`.
  - [x] Fix `string_analyzer.sscript` parity: JS reports `characters: 104`
        and SemanticScript reports `characters: 101`; top-word ordering also
        differs (`favors` vs `semanticscript` in the fifth slot).
- [x] Fix `python SemanticScript\tests\sem_compiler_parity.py`.
  - [x] Fix `string_analyzer.sscript` parity under `bootstrap_general`.
  - [x] Fix `webserver_console.sscript` long-running parity under
        `bootstrap_general`.
- [x] Fix unexpected failures in `python SemanticScript\tests\feature_coverage.py`.
  - [x] `121_cross_file_import.sscript`: emitted IR contains
        `%addSevenCall_res = add i64 35, %`.
  - [x] `88_string_byte_scan_loop.sscript`: expected `14\n`, actual `17\n`.
  - [x] `89_pointer_returning_recursion.sscript`: expected `ipt\n`, actual
        `script\n`.
  - [x] `92_c_fopen_fclose.sscript`: expected `opened\n` and exit `0`, actual
        empty stdout and exit `1`.
- [x] Decide how to treat the 30 `expect.xfail` feature tests before 1.0.
  - [ ] Either close the bootstrap gaps and remove the xfail markers.
  - [x] Or explicitly scope 1.0 to the Python reference compiler and document
        `bootstrap_general.sscript` as experimental/self-hosting progress.

## P1 - Runtime And Syntax Scope

- [x] Resolve or explicitly defer the 7 `Partial` rows in `SYNTAX.md`.
  - [x] `codec NAME [ATTRS...]`.
  - [x] `jsonCodec NAME`.
  - [x] `webServer NAME`.
  - [x] `route SERVER METHOD PATH HANDLER`.
  - [x] `collectionOperation COLLECTION.OP`.
  - [x] `json.encode.RecordTypeName` / `json.decode.RecordTypeName`.
  - [x] `TaskList.append` / `TaskMap.get`.
- [x] Make the 1.0 support matrix explicit:
  - [x] Python reference compiler support.
  - [x] Self-hosting/bootstrap support.
  - [x] VS Code extension support.
  - [x] Refined syntax support.
  - [x] Web/HTTP runtime support.

## P1 - Declarative Windows GUI Target

This section tracks the declarative Windows desktop GUI surface. The design
goal is an English-aligned application graph in source, with Win32 handles,
message loops, `HWND`, `WPARAM`, and `LPARAM` hidden behind a native runtime
adapter the same way `HttpRequest` / `HttpResponse` hide HTTP runtime state.

Boundary decision after implementation review: keep `semsc.py` as a thin
bridge. `standard.gui` owns public GUI vocabulary, aliases, capabilities,
closed token sets, and semantic contracts; semlint owns rich misuse
diagnostics; the native GUI runtime owns platform behavior. The compiler may
accept `targetRuntime windowsGui`, discover the minimal metadata needed to
start a GUI executable, lower a small set of `gui.*` bridge calls, and link the
native adapter.

### Completed MVP

- [x] Added `targetRuntime PROJECT windowsGui` to compiler build-tape
      validation.
- [x] Added `targetRuntime PROJECT windowsGui` to semlint build-tape
      validation.
- [x] Kept `entry windowsGui` out of the first committed executable surface.
- [x] Kept `entry console` out of the `app/hello-gui` `windowsGui` build tape.
- [x] Added `standard.gui` as the canonical contract module.
- [x] Added GUI type aliases, enums, capabilities, token constants, and runtime
      target constants to `std/gui/main.sem`.
- [x] Added lightweight GUI awareness to semlint and VS Code syntax tooling.
- [x] Added a native Win32 GUI runtime adapter with a backend-neutral
      `ss_gui_*` ABI.
- [x] Added the compiler link hook for the native GUI adapter.
- [x] Added a minimal `app/hello-gui` sample.
- [x] Built `app/hello-gui/build/hello_gui.exe`.
- [x] Verified the executable renders a Windows top-level window titled
      `Hello GUI` and exits `0` after the window is closed.

### GUI Target And Entry Model

- [x] Add `target windowsGui` to the syntax inventory.
- [x] Add `targetRuntime PROJECT windowsGui` to the build-tape enum.
- [x] Keep `entry windowsGui OPERATION` out of the committed surface for the
      first version.
- [x] Document that `target windowsGui` selects codegen from a unique
      `guiApplication` declaration, parallel to routed `target webServer`
      discovery.
- [x] Reject `target windowsGui` programs with zero `guiApplication` rows.
- [x] Reject `target windowsGui` programs with more than one
      `guiApplication` row until multi-app binaries are deliberately designed.
- [ ] Reject `entry windowsGui ...` with a diagnostic that points users to
      `guiApplicationMainWindow`.
- [x] Reject `targetRuntime windowsGui` build tapes that still declare
      `entry console`.
- [ ] Decide whether `target windowsGui` may coexist with `target console` in
      one source, or reject mixed executable targets.
- [x] Define that closing the `guiApplicationMainWindow` ends the GUI message
      loop by default.
- [ ] Define how `guiApplicationOnExit` runs after the message loop exits.
- [ ] Define whether `guiApplicationOnExit` may cancel process exit or is
      cleanup-only.
- [x] Define default exit status when the main window closes cleanly.
- [ ] Define exit status behavior when a GUI event handler returns non-zero.
- [x] Add `windowsGui` support to compiler build-tape validation.
- [x] Add `windowsGui` support to standalone linter build-tape validation.

### Syntax Naming And Shape

- [ ] Use `guiApplication APP`, not bare `application APP`, to avoid future
      collisions with web, mobile, package, or process concepts.
- [ ] Use `guiWindow WINDOW`, not bare `window WINDOW`, so grep results are
      scoped to the GUI surface.
- [ ] Use per-kind control declarators such as `guiButton CONTROL` and
      `guiTextBox CONTROL`, not `guiControl CONTROL KIND`.
- [ ] Do not use `label CONTROL`; `label NAME` already owns control-flow
      labels. Use `guiTextLabel CONTROL`.
- [ ] Keep every GUI verb lower camelCase.
- [ ] Keep every GUI symbol value lower camelCase.
- [ ] Keep every GUI opaque type PascalCase with a `Gui` prefix.
- [ ] Keep all runtime call targets under the `gui.*` namespace.
- [ ] Add `standard.gui` as the canonical import module for GUI contracts.
- [ ] Reserve `importModule gui standard.gui` as the preferred GUI import
      shape.
- [ ] Decide whether legacy `importModule standard.gui as gui` remains accepted
      during the compatibility window.
- [ ] Add all committed GUI rows to `SYNTAX.md` with `Partial` status until
      parser, validation, codegen, and runtime are complete.
- [ ] Add GUI verbs to `docs/reference/verb-index.md`.
- [ ] Add GUI target notes to `docs/language/program-structure.md`.
- [ ] Add GUI build-tape notes to `docs/language/project-layout-build-sem.md`.

### Application Rows

- [ ] Add parser support for `guiApplication APP`.
- [ ] Add parser support for `guiApplicationTitle APP "text"`.
- [ ] Add parser support for `guiApplicationIcon APP ICON_GROUP`.
- [ ] Add parser support for `guiApplicationMainWindow APP WINDOW`.
- [ ] Add parser support for `guiApplicationOnExit APP OPERATION`.
- [ ] Store GUI application rows in a dedicated `Program.gui_applications`
      index.
- [ ] Reject duplicate `guiApplication APP` rows.
- [ ] Reject duplicate singleton rows for one application title.
- [ ] Reject duplicate singleton rows for one application icon.
- [ ] Reject duplicate singleton rows for one application main window.
- [ ] Reject duplicate singleton rows for one application exit handler.
- [ ] Validate that `guiApplicationMainWindow` names a declared `guiWindow`.
- [ ] Validate that the main window belongs to the same application.
- [ ] Validate that `guiApplicationOnExit` names a declared operation.
- [ ] Validate the `guiApplicationOnExit` operation output contract.
- [ ] Decide whether `guiApplicationIcon` accepts only icon groups with
      `iconRole applicationPrimary` or any declared icon group.
- [ ] Reuse existing icon registry validation for GUI application icons.

### Window Rows

- [ ] Add parser support for `guiWindow WINDOW`.
- [ ] Add parser support for `guiWindowApplication WINDOW APP`.
- [ ] Add parser support for `guiWindowTitle WINDOW "text"`.
- [ ] Add parser support for `guiWindowWidth WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowHeight WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowMinimumWidth WINDOW PIXELS`.
- [ ] Add parser support for `guiWindowMinimumHeight WINDOW PIXELS`.
- [ ] Add parser support for
      `guiWindowLayout WINDOW verticalStack|horizontalStack|grid|absolute`.
- [ ] Add parser support for `guiWindowResizable WINDOW yes|no`.
- [ ] Add parser support for `guiWindowEvent WINDOW EVENT OPERATION`.
- [ ] Store GUI window rows in a dedicated `Program.gui_windows` index.
- [ ] Reject duplicate `guiWindow WINDOW` rows.
- [ ] Reject a `guiWindowApplication` that names an unknown application.
- [ ] Reject a `guiWindowTitle` row that names an unknown window.
- [ ] Reject width, height, and minimum-size rows with non-integer values.
- [ ] Reject width, height, and minimum-size rows with zero or negative values.
- [ ] Reject a minimum width larger than the initial window width.
- [ ] Reject a minimum height larger than the initial window height.
- [ ] Reject unknown `guiWindowLayout` values.
- [ ] Auto-register a `GuiWindowLayout` enum for
      `verticalStack`, `horizontalStack`, `grid`, and `absolute`.
- [ ] Reject unknown `guiWindowResizable` boolean tokens.
- [ ] Define default `guiWindowResizable` behavior when the row is omitted.
- [ ] Define default layout behavior when `guiWindowLayout` is omitted.
- [ ] Decide whether multiple windows per application are supported in the
      first implementation or parsed as future metadata.

### Control Declarators

- [ ] Add parser support for `guiButton CONTROL`.
- [ ] Add parser support for `guiTextBox CONTROL`.
- [ ] Add parser support for `guiListBox CONTROL`.
- [ ] Add parser support for `guiCheckBox CONTROL`.
- [ ] Add parser support for `guiMenuItem CONTROL`.
- [ ] Add parser support for `guiStatusBar CONTROL`.
- [ ] Add parser support for `guiTextLabel CONTROL`.
- [ ] Store controls in a dedicated `Program.gui_controls` index keyed by
      control symbol.
- [ ] Record each control's declared kind.
- [ ] Reject duplicate control symbols across all GUI control declarator kinds.
- [ ] Reject control symbols that collide with declared windows,
      applications, operations, constants, or storage bindings.
- [ ] Define each declarator as a typed compile-time handle constant:
      `guiButton addTodoButton` creates `addTodoButton : GuiButton`.
- [ ] Define `guiTextBox newTaskTitleTextBox` as
      `newTaskTitleTextBox : GuiTextBox`.
- [ ] Define `guiListBox visibleTodosListBox` as
      `visibleTodosListBox : GuiListBox`.
- [ ] Define `guiWindow todoAppMainWindow` as
      `todoAppMainWindow : GuiWindow`.
- [ ] Decide whether all control handles also subtype or alias a common
      `GuiControl` type.
- [ ] Ensure generated compile-time GUI handles can be passed as values to
      `gui.*` runtime calls.

### Generic Control Rows

- [ ] Add parser support for `guiControlWindow CONTROL WINDOW`.
- [ ] Add parser support for `guiControlEnabled CONTROL yes|no`.
- [ ] Add parser support for `guiControlVisible CONTROL yes|no`.
- [ ] Add parser support for `guiControlTabIndex CONTROL N`.
- [ ] Add parser support for `guiControlAccessibleName CONTROL "text"`.
- [ ] Add parser support for `guiControlEvent CONTROL EVENT OPERATION`.
- [ ] Reject generic control rows that name an unknown control.
- [ ] Reject `guiControlWindow` rows that name an unknown window.
- [ ] Reject controls without a `guiControlWindow` row.
- [ ] Reject duplicate `guiControlWindow` rows for one control.
- [ ] Reject duplicate `guiControlTabIndex` rows for one control.
- [ ] Reject duplicate `guiControlAccessibleName` rows for one control.
- [ ] Reject invalid yes/no values for enabled and visible rows.
- [ ] Define default enabled behavior when `guiControlEnabled` is omitted.
- [ ] Define default visible behavior when `guiControlVisible` is omitted.
- [ ] Reject negative tab-index values.
- [ ] Warn on duplicate tab-index values within one window.
- [ ] Warn when interactive controls omit `guiControlAccessibleName`.
- [ ] Decide whether `guiControlAccessibleName` defaults from visible text for
      buttons, check boxes, and labels.

### Kind-Specific Control Rows

- [ ] Add parser support for `guiButtonText BUTTON "text"`.
- [ ] Add parser support for `guiButtonIsDefault BUTTON yes|no`.
- [ ] Add parser support for `guiTextBoxPlaceholder TEXTBOX "text"`.
- [ ] Add parser support for `guiTextBoxMaxLength TEXTBOX N`.
- [ ] Add parser support for
      `guiListBoxSelectionMode LISTBOX single|multiple`.
- [ ] Add parser support for `guiCheckBoxChecked CHECKBOX yes|no`.
- [ ] Add parser support for `guiTextLabelText LABEL "text"`.
- [ ] Reject `guiButtonText` for non-button controls.
- [ ] Reject `guiButtonIsDefault` for non-button controls.
- [ ] Reject `guiTextBoxPlaceholder` for non-text-box controls.
- [ ] Reject `guiTextBoxMaxLength` for non-text-box controls.
- [ ] Reject `guiListBoxSelectionMode` for non-list-box controls.
- [ ] Reject `guiCheckBoxChecked` for non-check-box controls.
- [ ] Reject `guiTextLabelText` for non-text-label controls.
- [ ] Reject text-box max length values less than one.
- [ ] Define max length default behavior when the row is omitted.
- [ ] Auto-register a `GuiListBoxSelectionMode` enum for `single` and
      `multiple`.
- [ ] Reject unknown list-box selection mode values.
- [ ] Decide whether buttons may omit `guiButtonText`.
- [ ] Decide whether text labels may omit `guiTextLabelText`.
- [ ] Add diagnostics for controls that are declared but visually empty.

### Event Model

- [ ] Add a built-in `GuiEventKind` enum, or equivalent closed token set, for
      GUI event rows.
- [ ] Include `click` in the committed event set.
- [ ] Include `valueChanged` in the committed event set.
- [ ] Include `selectionChanged` in the committed event set.
- [ ] Include `enterPressed` in the committed event set.
- [ ] Include `keyPressed` in the committed event set.
- [ ] Include `focusGained` in the committed event set.
- [ ] Include `focusLost` in the committed event set.
- [ ] Include `closeRequested` in the committed event set.
- [ ] Include `resized` in the committed event set.
- [ ] Include `shown` in the committed event set.
- [ ] Include `hidden` in the committed event set.
- [ ] Validate allowed control events by control kind.
- [ ] Validate allowed window events by window kind.
- [ ] Allow `guiButton` to handle `click`.
- [ ] Allow `guiButton` to handle `focusGained` and `focusLost`.
- [ ] Allow `guiTextBox` to handle `valueChanged`, `enterPressed`,
      `keyPressed`, `focusGained`, and `focusLost`.
- [ ] Allow `guiListBox` to handle `selectionChanged`, `focusGained`, and
      `focusLost`.
- [ ] Allow `guiCheckBox` to handle `valueChanged`, `click`, `focusGained`,
      and `focusLost`.
- [ ] Allow `guiWindow` to handle `closeRequested`, `resized`, `shown`, and
      `hidden`.
- [ ] Reject `selectionChanged` on buttons.
- [ ] Reject `click` on list boxes unless a future design explicitly supports
      item activation.
- [ ] Reject `closeRequested` on controls.
- [ ] Reject unknown event tokens.
- [ ] Reject event rows whose handler operation is missing.
- [ ] Reject duplicate event handlers for the same target/event pair unless
      ordered event pipelines are designed.
- [ ] Decide whether event handler order is source-order or intentionally
      unsupported for the first version.

### Handler ABI

- [ ] Auto-register `GuiSession` as an opaque handler input type.
- [ ] Auto-register `GuiEvent` as an opaque handler input type.
- [ ] Auto-register `GuiWindow` as an opaque declarative handle type.
- [ ] Auto-register `GuiControl` as an opaque common control handle type if a
      common supertype is adopted.
- [ ] Auto-register `GuiButton`.
- [ ] Auto-register `GuiTextBox`.
- [ ] Auto-register `GuiListBox`.
- [ ] Auto-register `GuiCheckBox`.
- [ ] Auto-register `GuiMenuItem`.
- [ ] Auto-register `GuiStatusBar`.
- [ ] Auto-register `GuiTextLabel`.
- [ ] Define GUI handler operations as
      `input HANDLER session GuiSession`,
      `input HANDLER event GuiEvent`,
      and `output HANDLER CSignedInt32`.
- [ ] Reject GUI event handlers with missing `GuiSession` input.
- [ ] Reject GUI event handlers with missing `GuiEvent` input.
- [ ] Reject GUI event handlers with extra native ABI inputs.
- [ ] Reject GUI event handlers whose output is not `CSignedInt32`.
- [ ] Define that handler return `0` means handled successfully.
- [ ] Define non-zero handler returns as runtime-level event failure.
- [ ] Decide whether non-zero handler returns close the window, log and
      continue, or trap in dev builds.
- [ ] Preserve `GuiSession` and `GuiEvent` as ABI parameters for GUI handlers,
      like `HttpRequest` and `HttpResponse` are preserved for route handlers.
- [ ] Continue dropping ordinary opaque dependency inputs outside the GUI and
      HTTP ABIs.

### Runtime Call Surface

- [ ] Add `gui.textBoxText`.
- [ ] Add `gui.textBoxSetText`.
- [ ] Add `gui.listBoxSelectedIndex`.
- [ ] Add `gui.listBoxAppendItem`.
- [ ] Add `gui.listBoxClear`.
- [ ] Add `gui.windowClose`.
- [ ] Add `gui.eventKeyCode`.
- [ ] Add `gui.eventSelectedIndex`.
- [ ] Add `gui.eventWindowWidth`.
- [ ] Add `gui.eventWindowHeight`.
- [ ] Add `gui.eventCancelClose` or explicitly defer cancellable close events.
- [ ] Define required args for every `gui.*` runtime call.
- [ ] Require `session GuiSession` on every GUI runtime call that touches
      live GUI state.
- [ ] Define whether declarative handles are passed as `control`, `button`,
      `textBox`, `listBox`, or kind-specific arg names.
- [ ] Reject passing a `GuiButton` handle to `gui.textBoxText`.
- [ ] Reject passing a `GuiTextBox` handle to `gui.listBoxAppendItem`.
- [ ] Lower declarative GUI handle symbols to runtime control IDs or handles.
- [ ] Define the lifetime of strings returned by `gui.textBoxText`.
- [ ] Define whether returned GUI strings are copied, borrowed, or valid only
      until the next GUI runtime call.
- [ ] Define list-box item encoding as null-terminated UTF-8 or a future
      UTF-16 aware string type.
- [ ] Decide whether the MVP runtime stores UTF-8 internally and converts to
      UTF-16 at the Win32 boundary.
- [ ] Add source-of-truth comments so `semsc.py`, `semlint.py`, `SYNTAX.md`,
      and `standard.gui` stay aligned on `gui.*` target names.

### Effects And Capabilities

- [ ] Define `gui.control.textBox.text read`.
- [ ] Define `gui.control.textBox.text write`.
- [ ] Define `gui.control.listBox.items read`.
- [ ] Define `gui.control.listBox.items write`.
- [ ] Define `gui.control.listBox.selection read`.
- [ ] Define `gui.control.checkBox.checked read`.
- [ ] Define `gui.control.checkBox.checked write`.
- [ ] Define `gui.window write`.
- [ ] Define `gui.event read`.
- [ ] Define `gui.event.close write` if close cancellation is supported.
- [ ] Add reusable `standard.gui` capability declarations such as
      `guiTextBoxReader`, `guiTextBoxWriter`, and `guiListBoxWriter`.
- [ ] Ensure existing effect/capability coverage checks work unchanged for
      hierarchical GUI paths.
- [ ] Add lint tests proving `gui.control.textBox.text read` is covered by
      `capability guiTextBoxReader gui.control.textBox.text read`.
- [ ] Add lint tests proving a coarse capability such as
      `gui.control read` covers narrower read paths only if hierarchical
      coverage semantics intentionally allow it.
- [ ] Warn on overbroad GUI capabilities in exported module APIs.
- [ ] Decide whether GUI event registration rows require capabilities or only
      handler bodies require capabilities.

### Compiler Parser And Program Model

- [ ] Add GUI model classes or dictionaries to `Program`.
- [ ] Add parse handlers for all committed `guiApplication*` rows.
- [ ] Add parse handlers for all committed `guiWindow*` rows.
- [ ] Add parse handlers for all committed GUI control declarator rows.
- [ ] Add parse handlers for all committed `guiControl*` rows.
- [ ] Add parse handlers for all committed kind-specific control rows.
- [ ] Preserve source line numbers for every GUI declaration.
- [ ] Preserve raw text for diagnostics and future docs generation.
- [ ] Add conflict checks for duplicate declarations during parse.
- [ ] Add post-parse validation for cross-reference checks that require the
      whole Program.
- [ ] Add GUI declarations to compiler parse-only success coverage.
- [ ] Add GUI declarations to compiler JSON diagnostics if diagnostics are
      expanded to include source spans for validation errors.

### Compiler Codegen

- [ ] Detect `target windowsGui` with a validated `guiApplication` during
      no-entry codegen.
- [ ] Collect GUI event handler operation names before declaring user op
      functions.
- [ ] Preserve `GuiSession` and `GuiEvent` handler inputs in the ABI.
- [ ] Declare all GUI event handler functions before emitting the GUI entry.
- [ ] Compile non-handler helper operations as normal user ops.
- [ ] Emit a native GUI application config table.
- [ ] Emit one config record for the application title and icon.
- [ ] Emit one config record for each window.
- [ ] Emit one config record for each control.
- [ ] Emit one config record for each event edge.
- [ ] Encode control kind in a stable runtime enum.
- [ ] Encode event kind in a stable runtime enum.
- [ ] Emit handler function pointers in the event-edge table.
- [ ] Declare `ss_gui_application_run` in generated LLVM.
- [ ] Emit `main` or `WinMain` bridge code that calls
      `ss_gui_application_run`.
- [ ] Decide whether the LLVM entry symbol remains `main` with `-mwindows`, or
      whether codegen emits a dedicated `WinMain` wrapper.
- [ ] Add Windows subsystem linker support for GUI executables.
- [ ] Pass `-mwindows` through clang for Windows GUI builds when using the GNU
      driver mode.
- [ ] Pass the MSVC-linker equivalent `/SUBSYSTEM:WINDOWS` when clang is in
      MSVC driver mode if `-mwindows` is not sufficient.
- [ ] Ensure console executables do not accidentally inherit GUI subsystem
      flags.
- [ ] Link the GUI runtime source automatically for `target windowsGui`.
- [ ] Link `user32` automatically on Windows GUI builds.
- [ ] Link `gdi32` automatically on Windows GUI builds.
- [ ] Link `comctl32` automatically if common controls are used.
- [ ] Link `shell32` only if shell icon or file-dialog helpers are added.
- [ ] Keep Linux/macOS builds parse-only or fail with a clear unsupported
      target diagnostic until non-Windows GUI backends exist.

### Native Win32 Runtime Adapter

- [ ] Add `SemanticScript/runtime/native_win32_gui/`.
- [ ] Add `sem_win32_gui_runtime.h`.
- [ ] Add `sem_win32_gui_runtime.c`.
- [ ] Add `CMakeLists.txt` for the native GUI runtime.
- [ ] Define stable C ABI structs for application config.
- [ ] Define stable C ABI structs for window config.
- [ ] Define stable C ABI structs for control config.
- [ ] Define stable C ABI structs for event-edge config.
- [ ] Define a stable handler function pointer type:
      `int32_t (*)(SSGuiSession *, SSGuiEvent *)`.
- [ ] Implement `ss_gui_application_run`.
- [ ] Register a Win32 window class.
- [ ] Create the main window from generated config.
- [ ] Create child controls from generated config.
- [ ] Implement `verticalStack` layout.
- [ ] Implement `horizontalStack` layout.
- [ ] Stub or explicitly reject `grid` layout until implemented.
- [ ] Stub or explicitly reject `absolute` layout until implemented.
- [ ] Handle `WM_COMMAND` for button clicks.
- [ ] Handle text-box enter key dispatch.
- [ ] Handle list-box selection changes.
- [ ] Handle `WM_CLOSE` as `closeRequested`.
- [ ] Handle `WM_SIZE` as `resized`.
- [ ] Dispatch events to generated SemanticScript handler function pointers.
- [ ] Create and pass a runtime-owned `SSGuiSession` token.
- [ ] Create and pass a runtime-owned `SSGuiEvent` token.
- [ ] Map declarative control IDs to `HWND` values in the session.
- [ ] Implement `ss_gui_text_box_text`.
- [ ] Implement `ss_gui_text_box_set_text`.
- [ ] Implement `ss_gui_list_box_selected_index`.
- [ ] Implement `ss_gui_list_box_append_item`.
- [ ] Implement `ss_gui_list_box_clear`.
- [ ] Implement `ss_gui_window_close`.
- [ ] Implement `ss_gui_event_key_code`.
- [ ] Implement `ss_gui_event_selected_index`.
- [ ] Implement `ss_gui_event_window_width`.
- [ ] Implement `ss_gui_event_window_height`.
- [ ] Implement or defer `ss_gui_event_cancel_close`.
- [ ] Define thread affinity: all GUI runtime calls must happen on the GUI
      thread unless future dispatch helpers are added.
- [ ] Define memory ownership for strings returned from the runtime.
- [ ] Define error codes for missing controls, wrong control kinds, allocation
      failures, and Win32 API failures.
- [ ] Add runtime health demo that opens a window and exits cleanly.

### Standard Library Module

- [ ] Add `SemanticScript/std/gui/main.sem`.
- [ ] Relay `standard.gui` from `SemanticScript/std/module.sem`.
- [ ] Add module metadata for `standard.gui`.
- [ ] Add type aliases for `GuiSession`.
- [ ] Add type aliases for `GuiEvent`.
- [ ] Add type aliases for `GuiWindow`.
- [ ] Add type aliases for `GuiControl` if adopted.
- [ ] Add type aliases for every committed control handle type.
- [ ] Add capability declarations for the committed GUI effect paths.
- [ ] Add constants for GUI module version metadata.
- [ ] Add documentation comments explaining that `gui.*` targets are
      compiler/runtime-owned intrinsics.
- [ ] Add import example using `importModule gui standard.gui`.

### Linter And Editor Tooling

- [ ] Add GUI verbs to standalone linter arity tables.
- [ ] Add GUI closed enum values to linter validation.
- [ ] Add diagnostics for missing `guiApplicationMainWindow`.
- [ ] Add diagnostics for controls missing `guiControlWindow`.
- [ ] Add diagnostics for invalid control-kind-specific rows.
- [ ] Add diagnostics for invalid event-kind/control-kind combinations.
- [ ] Add diagnostics for missing or malformed GUI handler ABI inputs.
- [ ] Add diagnostics for missing GUI handler output contract.
- [ ] Add diagnostics for GUI runtime calls missing required `session` args.
- [ ] Add `gui.*` runtime call signatures to semlint's built-in call table.
- [ ] Add `gui.*` effect requirements to semlint's effect table.
- [ ] Add VS Code grammar highlighting for GUI declaration verbs.
- [ ] Add VS Code hover descriptions for GUI declaration verbs.
- [ ] Add VS Code document symbol grouping for GUI applications, windows,
      controls, and event edges.
- [ ] Add snippets only after the surface stabilizes.

### Tests And Samples

- [ ] Add parser tests for the minimum GUI application shape.
- [ ] Add parser tests for every application row.
- [ ] Add parser tests for every window row.
- [ ] Add parser tests for every control declarator row.
- [ ] Add parser tests for every generic control row.
- [ ] Add parser tests for every kind-specific control row.
- [ ] Add parse-failure tests for duplicate GUI applications.
- [ ] Add parse-failure tests for duplicate controls.
- [ ] Add validation tests for missing main window.
- [ ] Add validation tests for missing control window.
- [ ] Add validation tests for invalid event/control combinations.
- [ ] Add validation tests for malformed GUI handler ABI.
- [ ] Add compiler IR tests proving GUI handler params are preserved.
- [ ] Add compiler IR tests proving `ss_gui_application_run` is declared.
- [ ] Add compiler IR tests proving GUI config tables are emitted.
- [ ] Add linker tests proving Windows GUI builds include subsystem flags.
- [ ] Add linker tests proving `user32` and `gdi32` link args are added.
- [ ] Add a smoke sample under `app/hello-gui`.
- [ ] Add a Todo GUI sample under `app/todo-gui` only after the hello sample
      proves the base runtime.
- [ ] Add a runtime health test that opens and closes a window on Windows CI
      if the runner supports desktop interaction.
- [ ] Add a headless compile-only fallback test for CI environments that
      cannot open desktop windows.
- [ ] Add docs explaining how to run GUI smoke tests locally on Windows.

### Documentation And Release Scope

- [ ] Add a GUI language doc under `docs/language/`.
- [ ] Add a native GUI runtime doc under `docs/toolchain/` or
      `SemanticScript/runtime/native_win32_gui/README.md`.
- [ ] Update `README.md` support matrix once the surface is implemented or
      explicitly preview.
- [ ] Update `docs/README.md` with links to GUI language/runtime docs.
- [ ] Update `docs/agents.md` with compact GUI syntax guidance.
- [ ] Update `docs/optimization-guide.md` with GUI effect/capability examples.
- [ ] Decide whether declarative Windows GUI support is in 1.0 scope,
      post-1.0 preview scope, or experimental-only scope.
- [ ] Mark every GUI row in `SYNTAX.md` with honest implementation status.
- [ ] Add migration guidance if early names change before the committed
      syntax freezes.

## P1 - Full 1.0 Product Surface Gap Backlog

This section tracks the larger "complete product surface" gaps. These are not
all blockers for the scoped 1.0 release unless the release definition changes
from "honest scoped compiler/tooling release" to "complete language/runtime
product".

### Compiler And Language Strictness

- [x] Decide whether self-hosting is a 1.0 requirement.
  - [ ] If yes, make the SemanticScript-written bootstrap compiler compile the
        full documented language.
  - [x] If no, keep documenting `semsc.py` as the production 1.0 compiler and
        bootstrap as preview.
- [x] Replace unknown/missing operation output fallback-to-`i32` with a stricter
      diagnostic for release-mode builds, or document the fallback as a scoped
      compiler compatibility behavior.
- [ ] Add module namespace enforcement beyond import inlining and metadata.
  - [x] Validate `module NAME` as a dotted namespace.
  - [x] Reject conflicting module declarations in one resolved source.
  - [ ] Detect duplicate operation names across imported modules.
  - [x] Detect ambiguous unqualified references when imports expose the same
        symbol.
  - [x] Define whether `importModule X as Y` creates a real namespace boundary.
- [x] Add runtime capability/authority enforcement, or explicitly keep
      capability enforcement as linter/spec-only for 1.0.
  - [x] Add strict lint/compiler diagnostics for missing capability or inline
        authority coverage.
  - [x] Document runtime authority enforcement as out of scope for scoped 1.0.
  - [ ] Decide how capability tokens are represented in generated binaries.
  - [ ] Decide whether authority failures are compile-time errors, runtime
        traps, or typed runtime errors.
  - [ ] Add tests proving unauthorized runtime effects cannot execute if runtime
        enforcement is in scope.
- [ ] Audit refined syntax rows that are parser/linter-only and ensure each one
      is marked metadata, synchronous fallback, partial, or implemented.

### Native HTTP / Webserver Completeness

- [ ] Wire the H2O / HTTP2 backend behind an explicit backend flag.
  - [ ] Build H2O reproducibly on Windows or document the supported toolchain.
  - [ ] Link H2O outputs from `semsc.py --emit-exe`.
  - [ ] Add HTTP/2 smoke coverage once TLS/ALPN setup exists.
- [x] Add request body APIs.
  - [x] Add source-level call targets for reading request body text and length.
  - [x] Preserve body lifetime and size limits in the native adapter.
  - [x] Add POST tests that inspect actual body content.
- [x] Add request header APIs.
  - [x] Add source-level call targets for header lookup.
  - [x] Preserve header names and values in the native adapter.
  - [ ] Add case-insensitive header lookup tests.
- [x] Add response header APIs.
  - [x] Add source-level call targets for setting headers.
  - [x] Add tests for `Allow`, `Content-Type`, and custom middleware headers.
- [x] Add query parameter APIs.
  - [x] Preserve raw query string while still matching routes by path.
  - [x] Add source-level call target for simple query parameter lookup.
  - [ ] Add decoding/validation rules for repeated and missing params.
- [ ] Add path parameter routing such as `/todos/:todoId`.
  - [ ] Define route precedence between exact routes and parameter routes.
  - [ ] Add tests for path parameter extraction and invalid routes.
- [x] Execute `routeMiddleware` metadata in the native runtime.
  - [x] Define one path-scoped middleware slot before the route handler.
  - [x] Define non-zero middleware status as a request failure.
  - [x] Add tests proving middleware can inspect request state and set headers.
- [ ] Enforce `routeTimeout` metadata in the native runtime.
  - [ ] Define timeout behavior for blocking handlers.
  - [ ] Add tests for timeout failure response or trap behavior.
- [ ] Add persistent web app state/storage helpers.
  - [ ] Define safe mutable process state for request handlers.
  - [ ] Add tests for sequential request state changes.
- [ ] Add first-class HTML/SSX server template syntax.
  - [x] Add `htmlTemplate NAME` declarations for named server-rendered HTML
        values.
  - [x] Add `htmlArg TEMPLATE ARG_NAME TYPE` declarations for explicit,
        typed template input edges.
  - [x] Add `htmlBody TEMPLATE` syntax islands that parse following indented
        HTML/SSX lines until the next column-0 SemanticScript line.
  - [x] Keep `htmlBody` as the only indentation-sensitive syntax exception;
        normal SemanticScript remains flat and line-oriented.
  - [x] Allow JSX-like tags, attributes, fragments, and dynamic holes inside
        `htmlBody` only.
  - [x] Restrict dynamic holes to declared `htmlArg` values, using
        `htmlArg.name` references instead of a generic `props` object.
  - [x] Reject arbitrary calls, mutation, request reads, and hidden state reads
        inside HTML dynamic holes.
  - [x] Type-check dynamic holes by core HTML sink context: text nodes, quoted
        attributes, class values, URL attributes, fragments, and full documents.
  - [x] Escape `HtmlText` during hydration for text and attribute sinks.
  - [ ] Extend HTML sink-context checks to boolean attributes and a complete
        HTML parser instead of the current narrow server-template scan.
  - [x] Define first-class HTML trust types such as `HtmlText`, `HtmlClass`,
        `SafeUrl`, `HtmlFragment`, `HtmlTrustedFragment`, and `HtmlDocument`.
  - [x] Lower template hydration through generated targets such as
        `html.hydrate.TodoPageTemplate`.
  - [x] Add `standard.html` as the official standard-library import module for
        first-class HTML templates.
  - [x] Resolve `standard.html` through `SemanticScript/std/html/main.sem`.
  - [x] Use the canonical `importModule html standard.html` form in the demo app.
  - [x] Add `standard.http` and `standard.json` metadata modules for the
        compiler-owned `http.*` and `json.*` intrinsic namespaces.
  - [x] Resolve `standard.http` and `standard.json` through
        `SemanticScript/std/http/main.sem` and `SemanticScript/std/json/main.sem`.
  - [x] Add `<module>/main.sem` canonical entries for every C-derived stdlib module.
  - [x] Add `SemanticScript/std/module.sem` as the top-level `standard` relay.
  - [ ] Add `http.responseHtml` as the explicit HTML response writer with
        `text/html; charset=utf-8` content type behavior.
  - [x] Add compiler diagnostics for malformed HTML islands, unknown
        `htmlArg` references, and mismatched component/template arguments.
  - [x] Add compiler diagnostics for unsafe dynamic HTML sinks covered by the
        core context checker.
  - [ ] Add compiler diagnostics for remaining unsafe dynamic HTML sinks once
        the complete HTML parser exists.
  - [ ] Add semlint checks proving untrusted request/query/header/body data
        cannot flow into HTML without an explicit escape or trust conversion.
  - [ ] Add formatter and VS Code grammar support for `htmlTemplate`,
        `htmlArg`, `htmlBody`, and embedded SSX syntax.
  - [ ] Add docs explaining why HTML symbols are a narrow grammar-island
        exception to the normal no-brace/no-angle/no-indentation rules.
  - [ ] Add webserver tests proving hydrated HTML responses preserve escaping,
        content type, content length, and route-handler failure behavior.
- [ ] Add static-file serving helper.
  - [ ] Define root directory safety and path traversal behavior.
  - [ ] Add MIME/content-length tests.
- [ ] Add graceful shutdown hook.
  - [ ] Define signal/control API.
  - [ ] Add tests that server processes stop without forced termination.

### Data, Codec, And Collection Runtime

- [ ] Implement real JSON codec runtime for records.
  - [ ] Lower `json.encode.RecordTypeName`.
  - [ ] Lower `json.decode.RecordTypeName`.
  - [ ] Enforce required fields, unknown-field policy, and limits.
  - [ ] Add tests for valid JSON, malformed JSON, missing fields, and escaping.
- [x] Implement generic `codec` runtime or keep it as explicit metadata-only
      syntax for 1.0.
- [ ] Implement typed collection runtime for `TaskList.append`, `TaskMap.get`,
      and related collection operations.
  - [ ] Define allocation ownership for list/map storage.
  - [ ] Define bounds and missing-key behavior.
  - [ ] Add tests for append/get/update failure paths.
- [ ] Replace dotted-target zero-result fallback for partial collection/codec
      calls with diagnostics when a source claims runtime behavior.
  - [x] Add semlint diagnostics for record JSON codec, generic codec, and
        typed collection runtime fallbacks.

### Concurrency, Async, And State Runtime

- [x] Decide whether a real scheduler/event loop is in scope for 1.0.
  - [ ] If yes, implement scheduler-backed `start`, `await`, groups, and worker
        pools.
  - [x] If no, keep synchronous lowering documented and tested.
- [x] Replace single-thread mutex no-op semantics with runtime locking, or keep
      them documented as single-thread fallback only.
- [x] Implement cross-process shared state, or explicitly scope `sharedState`
      to same-process globals for 1.0.
- [x] Add runtime guard-token ownership enforcement, or keep guard tokens as
      linter/spec contracts for 1.0.
- [x] Add tests that concurrency/time/cleanup docs match actual lowering.

## P1 - Project Layout, Build Tape, Modules, Imports, And Exports

This section captures the post-discussion direction for project structure:
no TOML manifest, `build.sem` as the project/build/comptime surface,
`main.sem` as the default executable entry, build-owned module registry,
module-owned import/export contracts, colocated `*.test.sem` files, Go-style
dependency fetching, and SemanticScript-native export/import contracts.

### Parallel Workstream Split For 6 Agents

Use these ownership boundaries when running this effort with six simultaneous
agents. Each workstream should update its owned files only, record completed
items in this section, and leave integration notes for the final coordinator.

#### Agent 1 - Build Tape And Project Discovery

Owned scope: `build.sem` grammar, project-root discovery, build configuration
validation, and compiler project-mode entry.

- [x] Define and implement the build-tape parser surface.
  - [x] Add parser support for `buildProject`.
  - [x] Add parser support for `modulePath`.
  - [x] Add parser support for `languageVersion`.
  - [x] Add parser support for `projectVersion`.
  - [x] Add parser support for `projectLicense`.
  - [x] Add parser support for `sourceRoot`.
  - [x] Add parser support for `mainFile`.
  - [x] Add parser support for `mainOperation`.
  - [x] Add parser support for `testPattern`.
  - [x] Add parser support for `dependency`.
  - [x] Add parser support for `dependencySource`.
  - [x] Add parser support for `dependencyIntegrity`.
  - [x] Add parser support for `buildProfile`.
  - [x] Add parser support for `optLevel`.
  - [x] Add parser support for `runtimeChecks`.
  - [x] Add parser support for `persistLlvmIr`.
  - [x] Add parser support for `nativeOutput`.
  - [x] Add parser support for `targetRuntime`.
  - [x] Reserve but do not execute `comptimeOperation`.
- [ ] Implement build project discovery.
  - [x] Search current directory and ancestors for `build.sem`.
  - [x] Support single-file mode when no `build.sem` exists.
  - [ ] Reject ambiguous nested project roots with a source-located diagnostic.
  - [x] Preserve source locations for every build-tape row.
- [ ] Implement build-tape validation.
  - [x] Require one active `buildProject`.
  - [x] Validate singleton rows.
  - [x] Validate source roots.
  - [x] Validate target runtime choices.
  - [x] Validate `mainFile` / `mainOperation` requirements per target.
  - [ ] Validate dependency aliases and module paths.
  - [ ] Validate release builds do not use floating dependency refs without a
        lock.
- [ ] Wire project mode into compiler/build flow.
  - [x] Add compiler project-mode entrypoint.
  - [x] Pass build profile from `build.sem` into existing compiler options.
  - [x] Pass runtime checks from `build.sem` into existing compiler options.
  - [x] Pass LLVM IR persistence from `build.sem` into existing compiler
        options.
  - [x] Resolve native output from `build.sem`.
  - [x] Add focused tests for valid and invalid build tapes.
- [ ] Agent 1 handoff notes.
  - [ ] Document public parser/validation helpers for Agent 2 and Agent 6.
  - [ ] List any build verbs intentionally parser-only for 1.x.

#### Agent 2 - Build-Owned Modules And Entry Rules

Owned scope: folder-owned module model declared in `build.sem`, root/main entry
resolution, and module metadata validation.

- [ ] Implement folder-module discovery.
  - [ ] Detect folders containing production `.sem` files.
  - [ ] Require each production source folder to be registered with
        `registerModule` in `build.sem`.
  - [x] Treat `*.test.sem` as test files, not production module triggers by
        themselves.
  - [ ] Normalize folder paths across Windows and POSIX.
- [ ] Enforce folder/module consistency.
  - [ ] Validate `moduleFolder MODULE_PATH PATH_TEXT`.
  - [ ] Validate folder module path equals root module path plus folder path
        unless explicit override is designed.
  - [ ] Reject conflicting module rows in `build.sem`.
  - [ ] Reject source files that declare a module different from the
        `build.sem` folder contract.
  - [ ] Decide and implement whether source files may repeat the exact folder
        module row for local context.
- [ ] Implement module metadata checks.
  - [x] Parse `modulePurpose`.
  - [x] Parse `moduleOwns`.
  - [x] Parse `moduleDoesNotOwn`.
  - [x] Parse `moduleDependency`.
  - [x] Parse `moduleWarning`.
  - [x] Parse `moduleInvariant`.
  - [x] Parse `moduleSecurity`.
  - [x] Parse `moduleObservability`.
  - [ ] Require `modulePurpose` for folder modules.
  - [ ] Warn when ownership context is missing.
  - [ ] Warn when declared module dependencies are unused.
  - [ ] Warn when used module dependencies are not declared.
- [ ] Implement entry rules.
  - [ ] Default to `main.sem` when `mainFile` is omitted.
  - [ ] Default to `operation main` when `mainOperation` is omitted.
  - [ ] Reject ambiguous multiple app entries.
  - [ ] Reject executable entry requirements for library targets.
  - [ ] Validate webserver target entry ambiguity.
- [ ] Add module/entry tests.
  - [ ] Missing module contract rows in `build.sem`.
  - [ ] Conflicting module declaration.
  - [ ] Root plus folder module happy path.
  - [ ] Default `main.sem` and `operation main`.
  - [ ] Explicit main file and operation.
  - [ ] Library target with no main.
  - [ ] Webserver target with ambiguous servers.
- [ ] Agent 2 handoff notes.
  - [ ] Document module index API for Agent 3 and Agent 4.
  - [ ] List any migration compatibility assumptions for Agent 6.

#### Agent 3 - Export Contract Tape

Owned scope: exports as public semantic contracts, contract extraction, export
validation, and diagnostics for public API quality.

- [x] Implement export rows.
  - [x] Add `exportType MODULE_PATH TYPE_NAME`.
  - [x] Add `exportError MODULE_PATH ERROR_TYPE`.
  - [x] Add `exportOperation MODULE_PATH OPERATION_NAME`.
  - [x] Add `exportCapability MODULE_PATH CAPABILITY_NAME`.
  - [x] Add `exportConstant MODULE_PATH CONSTANT_NAME`.
  - [x] Decide `exportRecord` / `exportEnum` are redundant; use `exportType`
        for aliases, records, and enums.
- [x] Enforce export visibility rules.
  - [x] Treat symbols as private unless exported.
  - [x] Restrict export rows to module source files.
  - [x] Require exported symbols to belong to the same registered module.
  - [x] Reject unknown exports.
  - [x] Reject duplicate exports.
  - [x] Reject mutable module storage exports.
  - [x] Reject local/shared state exports.
  - [x] Allow immutable module storage through `exportConstant`.
- [x] Build exported operation contracts.
  - [x] Extract inputs.
  - [x] Extract outputs.
  - [x] Extract effects.
  - [x] Extract capability or authority coverage.
  - [x] Extract failure types and error cases.
  - [x] Extract async/timing metadata.
  - [x] Extract memory metadata.
  - [x] Preserve source locations for every exported contract edge.
- [x] Build exported type/error/capability contracts.
  - [x] Extract record fields and invariants for exported record types.
  - [x] Extract enum cases for exported enum types.
  - [x] Extract error cases for exported error types.
  - [x] Extract capability effect path and access mode.
  - [x] Extract constant type and value/trust metadata.
- [x] Add export quality diagnostics.
  - [x] Warn when exported operations lack `purpose`.
  - [x] Warn when exported operations have hidden or undeclared effects.
  - [x] Warn when exported operations wrap dependency behavior without
        ownership/purpose context.
  - [x] Warn when exported names are overly generic.
- [x] Add export tests.
  - [x] Exported operation happy path.
  - [x] Private symbol rejected from external module.
  - [x] Exported immutable constant accepted.
  - [x] Mutable storage export rejected.
  - [x] Exported error cases visible to consumers.
  - [x] Exported capability visible to consumers.
- [x] Agent 3 handoff notes.
  - [x] Document contract tape shape for Agent 4 and Agent 5.
  - [x] Document export diagnostics for Agent 6 docs.

#### Agent 4 - Imports, Qualified Names, And Singular Imports

Owned scope: module imports, qualified access, singular import aliases, shadowing
rules, and imported contract lookup.

- [ ] Refine module import syntax.
  - [x] Decide compatibility path for current `importModule DOTTED.PATH [as
        ALIAS]`.
  - [x] Define preferred `importModule ALIAS MODULE_PATH` shape if adopted.
  - [ ] Require aliases for external dependency modules.
  - [x] Reject alias collisions.
  - [x] Reject imports not reachable from `build.sem`.
- [x] Implement qualified references.
  - [x] Resolve `moduleAlias.operationName` call targets.
  - [x] Resolve `moduleAlias.TypeName` type references.
  - [x] Resolve `moduleAlias.ErrorType` error references.
  - [x] Resolve `moduleAlias.CapabilityName` capability references.
  - [x] Reject qualified access to private symbols.
  - [x] Reject qualified access to mutable storage.
  - [x] Preserve qualified source names in diagnostics.
- [x] Implement singular import rows.
  - [x] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [x] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [x] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [x] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [x] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [x] Reject wildcard imports.
  - [x] Reject implicit singular imports.
- [x] Enforce alias and shadowing rules.
  - [x] Reject singular imports that shadow local declarations.
  - [x] Reject singular imports that shadow other imports.
  - [x] Reject ambiguous unqualified references.
  - [x] Warn when many singular imports from one module reduce clarity.
  - [x] Warn when local alias hides provider domain context.
- [x] Carry imported contracts through call checking.
  - [x] Imported operation calls use exported input contract.
  - [x] Imported operation calls use exported output contract.
  - [x] Imported operation calls expose exported effect contract.
  - [x] Imported types carry record/enum metadata.
  - [x] Imported errors carry error cases.
  - [x] Imported capabilities carry effect path/access metadata.
- [x] Add import tests.
  - [x] Qualified operation call happy path.
  - [x] Qualified type/error/capability references.
  - [x] Singular operation/type/error/capability/constant imports.
  - [x] Private symbol rejected.
  - [x] Alias collision rejected.
  - [x] Wildcard import rejected.
  - [x] Import cycle rejected.
- [x] Agent 4 handoff notes.
  - [x] Document import resolution API for Agent 5 dependency cache work.
  - [x] Document compatibility edge cases for Agent 6 migration docs.

#### Agent 5 - Dependency Fetching, Cache, Locking, And Cross-Module Authority

Owned scope: Go-style dependency fetching, `.semcache/`, lock behavior,
dependency contract loading, and cross-module effect/capability propagation.

- [ ] Define dependency fetch model.
  - [ ] Add `sem get MODULE_PATH@VERSION_OR_REF` design notes.
  - [ ] Define `sem get` as a tool-driver command, not a compiler backend
        phase.
  - [ ] Define `sem build` dependency preparation order: parse `build.sem`,
        resolve/fetch/cache dependencies, load dependency contracts, then call
        `semsc`.
  - [ ] Define whether direct `semsc build.sem` may fetch from the network or
        must remain validation/compile-only.
  - [ ] Define the source-level fetch API names: keep build-time dependency
        fetch as `dependencyFetch`; reserve runtime HTTP client calls for a
        separate `http.client*` or `net.fetch*` surface.
  - [x] Support GitHub module paths first.
  - [ ] Define GitHub archive URL construction from `OWNER/REPO REF`.
  - [ ] Define GitHub API calls needed to resolve a tag or branch to an exact
        commit.
  - [ ] Decide whether GitHub fetching uses anonymous HTTPS first and optional
        token auth later.
  - [ ] Keep grammar generic enough for non-GitHub Git paths.
  - [x] Support local path dependencies.
  - [x] Support pinned tags.
  - [x] Support pinned commits.
  - [ ] Distinguish immutable refs (`commit:<sha>`) from mutable refs
        (`main`, branch names, moving tags).
  - [ ] Reject floating branches in release builds unless explicitly allowed.
  - [ ] Define a dev-only override for intentionally floating dependency refs.
  - [ ] Define diagnostics when `dependencyFetch` exists without a matching
        `dependency` row.
- [ ] Implement dependency preparation before compile.
  - [ ] Add a dependency preparation module under the tooling layer, not inside
        LLVM/codegen.
  - [ ] Parse the active `buildProject` and collect `dependency`,
        `dependencyFetch`, `dependencyCache`, `dependencyLock`, and
        `dependencyIntegrity` rows.
  - [ ] Normalize dependency aliases and reject duplicate aliases before any
        network access.
  - [ ] Resolve local/path dependencies without network access.
  - [ ] Resolve GitHub dependencies through archive download or GitHub API.
  - [ ] Resolve generic HTTPS archive dependencies through direct download.
  - [ ] Materialize fetched sources into cache before compiler import
        resolution.
  - [ ] Return a structured dependency-resolution report for agent logs.
  - [ ] Ensure dependency preparation is idempotent for unchanged lock/cache
        state.
- [ ] Implement `.semcache/` behavior.
  - [ ] Store cloned dependencies outside source roots.
  - [ ] Define default project cache path as `.semcache/` beside `build.sem`.
  - [ ] Define exact cache directory layout for GitHub dependencies.
  - [ ] Store GitHub archive downloads under a content-addressed blob path.
  - [ ] Store extracted dependency source under a resolved-commit path.
  - [ ] Store local/path dependency entries as references, not copied source,
        unless vendoring is explicitly requested later.
  - [x] Keep `.semcache/` ignored by git.
  - [ ] Never mutate cached dependency source during normal builds.
  - [ ] Treat cached dependency source as read-only after extraction.
  - [ ] Write downloads to a temp file and atomically move them into cache.
  - [ ] Use per-dependency lock files to avoid two builds writing the same
        cache entry at once.
  - [ ] Detect cache corruption.
  - [ ] Recompute archive checksum before trusting a cached archive.
  - [ ] Recompute extracted tree checksum or manifest hash before trusting a
        cached source tree.
  - [ ] Delete or quarantine corrupt cache entries instead of compiling them.
  - [ ] Support cache refresh through explicit update commands.
  - [ ] Make normal builds reuse cache and lock data without refreshing.
  - [ ] Add a clear diagnostic when cache is missing and network is disabled.
- [ ] Define and implement lock data.
  - [x] Decide between `sem.lock`, `build.lock.sem`, or another SemanticScript
        lock tape.
  - [ ] Define `sem.lock` as a SemanticScript tape, not TOML/JSON/YAML.
  - [ ] Define top-level lock identity rows such as `lockProject`,
        `lockGeneratedBy`, and `lockFormatVersion`.
  - [ ] Define one locked dependency block per dependency alias.
  - [ ] Record module path.
  - [ ] Record requested version/ref.
  - [ ] Record resolved commit.
  - [ ] Record checksum.
  - [ ] Record dependency module root.
  - [ ] Record transitive dependencies.
  - [ ] Record fetch kind (`github`, `http`, or `local`).
  - [ ] Record source URL or GitHub `OWNER/REPO`.
  - [ ] Record archive URL used for the fetch.
  - [ ] Record archive SHA-256.
  - [ ] Record extracted source tree digest.
  - [ ] Record dependency `build.sem` path inside the cached source.
  - [ ] Record dependency language version and module path from its build tape.
  - [ ] Record lock timestamp only if it will not break reproducible diffs; if
        it is included, keep it in a clearly non-semantic metadata row.
  - [ ] Make locked builds avoid network access.
  - [ ] In prod/release profile, require lock rows before any remote fetch.
  - [ ] Fail if a locked dependency resolves to different bytes than the lock
        checksum.
  - [ ] Fail if a locked GitHub dependency resolves to a different commit.
  - [ ] Add a `--locked` or equivalent mode that forbids lock mutation.
  - [ ] Add an update mode that is explicitly allowed to mutate `sem.lock`.
- [ ] Load dependency contract tapes.
  - [ ] Read dependency `build.sem`.
  - [ ] Read dependency module registry rows from `build.sem`.
  - [ ] Read dependency module-source export rows and exported contract tape.
  - [ ] Support resolving registered dependency modules from the cached source
        root.
  - [ ] Merge dependency export contract indexes into import resolution without
        treating dependency private symbols as local project symbols.
  - [ ] Reject dependencies missing required module metadata.
  - [ ] Reject dependencies whose `modulePath` does not match the requested
        dependency module path.
  - [ ] Reject dependencies whose registered module source cannot be selected
        deterministically.
  - [ ] Surface dependency diagnostics with dependency source paths.
  - [ ] Include dependency alias, module path, requested ref, resolved commit,
        and cache path in diagnostics.
  - [ ] Ensure dependency diagnostics render cleanly in `--format agent`.
- [ ] Implement cross-module effect and authority propagation.
  - [x] Caller diagnostics cite imported operation effects.
  - [x] Caller declares effects triggered by imported calls.
  - [ ] Caller proves capability or authority coverage.
  - [ ] Imported capabilities preserve hierarchy.
  - [ ] Warn on broad capability re-export without rationale.
  - [x] Ensure file/network/database/observability effects do not disappear
        through wrappers.
- [ ] Add dependency/effect tests.
  - [ ] Local path dependency.
  - [ ] Local path dependency resolves without touching network.
  - [x] GitHub tag/commit dependency if network tests are allowed.
  - [ ] GitHub archive URL is constructed correctly.
  - [ ] GitHub tag resolves to exact commit.
  - [ ] GitHub commit ref skips mutable-ref resolution.
  - [ ] HTTPS archive dependency downloads and verifies checksum.
  - [ ] Locked build avoids network.
  - [ ] Locked prod build fails when lock is missing.
  - [ ] Locked build fails on checksum mismatch.
  - [ ] Cached archive corruption is detected.
  - [ ] Cached extracted tree corruption is detected.
  - [ ] Missing dependency `build.sem`.
  - [ ] Missing dependency module contract rows in `build.sem`.
  - [ ] Dependency `modulePath` mismatch diagnostic.
  - [ ] Dependency registered module source missing diagnostic.
  - [ ] Imported operation with filesystem effect.
  - [x] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
- [ ] Agent 5 handoff notes.
  - [x] Document lock format for Agent 6 docs.
  - [x] Document cache/authority APIs for final integration.

#### Agent 6 - Tests, Migration, Docs, VS Code, And Integration Harness

Owned scope: user-facing docs, migration guidance, colocated `*.test.sem`
behavior, VS Code syntax/tooling updates, and integration tests spanning all
workstreams.

- [ ] Define colocated test semantics.
  - [x] `*.test.sem` belongs to the same folder module as sibling source.
  - [x] Exclude `*.test.sem` from normal production builds.
  - [ ] Include `*.test.sem` in `sem test`.
  - [ ] Decide same-folder private symbol access for tests.
  - [ ] Reject test files with conflicting module declarations.
  - [ ] Ensure test-only helpers are excluded from production exports.
- [ ] Update documentation.
  - [ ] Update root `README.md` project layout section.
  - [x] Update `docs/language/program-structure.md`.
  - [x] Update `SYNTAX.md` rows for new verbs.
  - [x] Update `docs/reference/verb-index.md`.
  - [x] Add build/module/import/export examples.
  - [x] Document no-TOML/no-sidecar-manifest decision.
  - [x] Document migration from current `importModule` behavior.
- [ ] Update examples.
  - [x] Add minimal console project using `build.sem` and `main.sem`.
  - [ ] Add multi-module project with module registry in `build.sem` and
        contracts in module source files.
  - [ ] Add library export/import sample.
  - [ ] Add singular import sample.
  - [ ] Add dependency sample using a local path dependency.
  - [ ] Add colocated test sample.
- [x] Update VS Code extension.
  - [x] Highlight build-tape verbs.
  - [x] Highlight module metadata verbs.
  - [x] Highlight export/import verbs.
  - [x] Add hover text for new verbs.
  - [x] Add completions for new verbs.
  - [x] Add document symbols for `buildProject`, `module`, exports, and
        imports.
  - [x] Add linter/diagnostic support when new diagnostics exist.
- [ ] Add migration checks.
  - [ ] Audit existing `module` rows.
  - [ ] Audit existing `importModule` rows.
  - [ ] Identify samples needing `build.sem`.
  - [ ] Identify stdlib modules needing relay entries in `std/module.sem`.
  - [ ] Add staged compatibility warnings before hard errors.
- [ ] Build integration harness.
  - [x] End-to-end console project build.
  - [ ] End-to-end web project build.
  - [x] End-to-end module import/export build.
  - [x] End-to-end singular import build.
  - [ ] End-to-end colocated test run.
  - [ ] End-to-end dependency cache/lock run using local path dependency.
  - [x] VS Code extension `npm run check`.
- [ ] Agent 6 handoff notes.
  - [ ] Summarize changed docs and examples.
  - [ ] Summarize compatibility warnings users will see.
  - [ ] Provide final integration checklist for coordinator.

### Source Layout Contract

- [x] Define the canonical project layout in the language docs.
  - [x] Document `build.sem` as the required project build tape.
  - [x] Document `main.sem` as the default executable source entry file.
  - [x] Document `*.sem` as normal source files.
  - [x] Document `*.test.sem` as colocated test source files.
  - [x] Document that module folders are registered in `build.sem` and module
        contracts live in module source files.
  - [x] Document that separate `module.sem` files are intentionally not part of
        the application project model; `std/module.sem` is the library relay exception.
  - [x] Document `build/` as ignored build output.
  - [x] Document `.semcache/` as ignored dependency/build cache.
  - [x] Document that TOML/YAML/JSON manifests are intentionally not part of
        the SemanticScript project model.
- [ ] Add a project layout section to `README.md`.
  - [ ] Show a minimal console app tree.
  - [ ] Show a native web app tree.
  - [ ] Show a multi-module library tree.
  - [ ] Show colocated `*.test.sem` files beside the modules they test.
- [ ] Add a project layout section to `docs/language/program-structure.md`.
  - [x] Explain how root source files differ from folder modules.
  - [x] Explain how `main.sem` and `build.sem` interact.
  - [ ] Explain how tests are discovered from `*.test.sem`.
  - [ ] Explain how generated artifacts stay outside source control.
- [ ] Add examples under `samples/` or `app/`.
  - [x] Minimal `build.sem` plus `main.sem` console sample.
  - [ ] Multi-folder module sample with every module registered in `build.sem`.
  - [ ] Webserver sample using `build.sem`, `main.sem`, and folder modules.
  - [ ] Library sample with exports and import consumers.
  - [ ] Tests using `*.test.sem` next to the source folder they validate.

### `build.sem` Build Tape

- [x] Define the `build.sem` grammar as SemanticScript source, not a sidecar
      config format.
  - [x] Add `buildProject PROJECT_NAME`.
  - [x] Add `modulePath PROJECT_NAME MODULE_PATH`.
  - [x] Add `languageVersion PROJECT_NAME VERSION_TEXT`.
  - [x] Add `projectVersion PROJECT_NAME VERSION_TEXT`.
  - [x] Add `projectLicense PROJECT_NAME LICENSE_TEXT`.
  - [x] Add `sourceRoot PROJECT_NAME PATH_TEXT`.
  - [x] Add `mainFile PROJECT_NAME PATH_TEXT`.
  - [x] Add `mainOperation PROJECT_NAME OPERATION_NAME`.
  - [x] Add `testPattern PROJECT_NAME GLOB_TEXT`.
  - [x] Add `dependency PROJECT_NAME ALIAS MODULE_PATH VERSION_OR_REF`.
  - [x] Add `dependencySource PROJECT_NAME ALIAS SOURCE_KIND SOURCE_TEXT`.
  - [x] Add `dependencyIntegrity PROJECT_NAME ALIAS INTEGRITY_TEXT`.
  - [x] Add `buildProfile PROJECT_NAME dev|prod`.
  - [x] Add `optLevel PROJECT_NAME 0|1|2|3`.
  - [x] Add `runtimeChecks PROJECT_NAME off|traps|panic`.
  - [x] Add `persistLlvmIr PROJECT_NAME auto|yes|no`.
  - [x] Add `nativeOutput PROJECT_NAME PATH_TEXT`.
  - [x] Add `targetRuntime PROJECT_NAME nativeExe|webServer|library`.
  - [x] Reserve `comptimeOperation PROJECT_NAME OPERATION_NAME` for 2.0.
- [x] Decide whether `build.sem` accepts only build verbs or the full language.
  - [x] If restricted, reject executable body rows in `build.sem`.
  - [ ] If full language, define which rows execute at compile time.
  - [x] Document that 1.x treats `build.sem` as declarative build tape.
  - [x] Document that 2.0 can widen this into comptime execution.
- [ ] Implement `build.sem` discovery.
  - [x] Search current directory and ancestors for `build.sem`.
  - [ ] Stop at repository root if detectable.
  - [ ] Emit a clear diagnostic when multiple candidate project roots compete.
  - [x] Support single-file mode when no `build.sem` exists.
  - [x] Never silently create `build.sem`.
- [ ] Implement `build.sem` parsing.
  - [x] Add parser rows for every current build-tape verb.
  - [x] Preserve source locations for build diagnostics.
  - [ ] Reject unknown build-tape verbs with a suggestion.
  - [x] Reject missing project names.
  - [x] Reject duplicate `buildProject` names in one build file.
  - [x] Reject duplicate singleton rows such as `modulePath`, `mainFile`, and
        `mainOperation` unless overriding is explicitly designed.
  - [x] Validate paths without requiring referenced files to exist until the
        project discovery pass.
- [ ] Implement build-tape validation.
  - [x] Require exactly one `buildProject` for normal project builds.
  - [x] Require `modulePath`.
  - [x] Require `languageVersion` or define a default.
  - [x] Require `sourceRoot` or default to `"."`.
  - [x] Require `mainFile` only for executable targets.
  - [x] Require `mainOperation` or default to `main`.
  - [ ] Require dependency aliases to be valid identifiers.
  - [ ] Require dependency module paths to be canonical.
  - [ ] Require dependency versions/refs to be pinned for release builds.
  - [ ] Reject network dependency refs in prod/release builds unless locked.
- [ ] Integrate `build.sem` with `semsc.py`.
  - [x] Add `semsc.py build.sem --project-build` or equivalent project mode.
  - [x] Make `sem build` call compiler project mode once the `sem` driver
        exists.
  - [x] Resolve all source roots before parsing application modules.
  - [x] Resolve build profile from `build.sem`.
  - [x] Resolve runtime checks from `build.sem`.
  - [x] Resolve LLVM IR persistence from `build.sem`.
  - [x] Resolve native output path from `build.sem`.
  - [x] Emit diagnostics in terms of `build.sem` rows when build config fails.
- [ ] Add build-tape tests.
  - [x] Minimal valid `build.sem`.
  - [x] Missing `modulePath`.
  - [ ] Duplicate `mainFile`.
  - [ ] Invalid dependency alias.
  - [ ] Invalid module path.
  - [x] Missing `main.sem`.
  - [ ] Missing `operation main`.
  - [ ] Webserver target with route handlers.
  - [ ] Library target with no `main.sem`.

### `main.sem` Entry Rules

- [ ] Define default executable entry behavior.
  - [ ] If `mainFile` is omitted, look for `main.sem`.
  - [ ] If `mainOperation` is omitted, look for `operation main`.
  - [ ] Require explicit build rows when more than one plausible entry exists.
  - [ ] Reject accidental entry operations in library-only targets.
- [ ] Define root module behavior for `main.sem`.
  - [ ] Declare the root module in `build.sem`.
  - [ ] Decide whether `main.sem` may repeat the root module row for local
        context.
  - [ ] If repetition is allowed, require exact match with `build.sem`.
  - [ ] If repetition is not allowed, lint against source-level module rows in
        project mode.
  - [ ] Document the chosen rule with examples.
- [ ] Define webserver entry behavior.
  - [ ] Allow `main.sem` to declare the primary `webServer`.
  - [ ] Allow `build.sem` to select a webserver target.
  - [ ] Require exactly one routed webserver when target is `webServer` and no
        explicit server is selected.
  - [ ] Reject multiple webservers without an explicit selection row.
  - [ ] Validate route handlers after imports and module resolution.
- [ ] Add entry tests.
  - [ ] Default `main.sem` plus `operation main`.
  - [ ] Explicit `mainFile`.
  - [ ] Explicit `mainOperation`.
  - [ ] Missing main file.
  - [ ] Missing main operation.
  - [ ] Multiple candidate entries.
  - [ ] Webserver target with one server.
  - [ ] Webserver target with ambiguous servers.

### Folder-Owned Modules

- [ ] Make folders hard module boundaries.
  - [ ] Every folder containing production `.sem` files must be declared in
        `build.sem`.
  - [ ] Every production `.sem` file in a folder belongs to that folder's
        module.
  - [ ] Reject multiple module declarations for the same folder in `build.sem`.
  - [ ] Reject source files whose `module` row conflicts with the folder module
        declared in `build.sem`.
  - [ ] Decide whether source files may repeat the folder `module` row for
        local context.
  - [ ] If repetition is allowed, require exact match.
  - [ ] If repetition is not allowed, lint against duplicate module rows in
        source files.
- [ ] Define module path mapping.
  - [ ] Root `modulePath` from `build.sem` defines the project module path.
  - [ ] Folder module path must equal root module path plus folder path unless
        an explicit override row exists.
  - [ ] Reject `..` path escapes in `moduleFolder`.
  - [ ] Normalize slash direction across Windows and POSIX.
  - [ ] Preserve case-sensitivity rules in docs.
  - [ ] Decide whether folder names with hyphens map to module path segments.
- [ ] Add build-owned folder module metadata rows.
  - [ ] Add `moduleFolder MODULE_PATH PATH_TEXT`.
  - [ ] Add `modulePurpose MODULE_PATH TEXT`.
  - [ ] Add `moduleOwns MODULE_PATH TEXT`.
  - [ ] Add `moduleDoesNotOwn MODULE_PATH TEXT`.
  - [ ] Add `moduleDependency MODULE_PATH DEPENDENCY_ALIAS`.
  - [ ] Add `moduleWarning MODULE_PATH TEXT`.
  - [ ] Add `moduleInvariant MODULE_PATH TEXT`.
  - [ ] Add `moduleSecurity MODULE_PATH TEXT`.
  - [ ] Add `moduleObservability MODULE_PATH TEXT`.
- [ ] Enforce minimum module context.
  - [ ] Require `modulePurpose` for every folder module.
  - [ ] Require at least one `moduleOwns` or an explicit no-ownership rationale.
  - [ ] Warn when `moduleDoesNotOwn` is missing for public modules.
  - [ ] Warn when a module imports dependencies not listed by
        `moduleDependency`.
  - [ ] Warn when `moduleDependency` lists unused dependencies.
- [ ] Add module boundary tests.
  - [ ] Folder with missing module rows in `build.sem`.
  - [ ] Folder with conflicting module paths.
  - [ ] Root path plus folder path happy case.
  - [ ] Path normalization on Windows-style paths.
  - [ ] Duplicate module declarations.
  - [ ] Module metadata diagnostics.

### Exports As Public Semantic Contracts

- [x] Define export rows in module source files.
  - [x] Add `exportType MODULE_PATH TYPE_NAME`.
  - [x] Add `exportError MODULE_PATH ERROR_TYPE`.
  - [x] Add `exportOperation MODULE_PATH OPERATION_NAME`.
  - [x] Add `exportCapability MODULE_PATH CAPABILITY_NAME`.
  - [x] Add `exportConstant MODULE_PATH CONSTANT_NAME`.
  - [x] Decide `exportRecord` is redundant with `exportType`.
  - [x] Decide `exportEnum` is redundant with `exportType`.
- [ ] Define export visibility rules.
  - [x] Symbols are private unless exported.
  - [x] Export rows may only appear in module source files.
  - [x] Exported symbols must be declared in the same registered module.
  - [ ] Exported operations must have complete `input` and `output` contracts.
  - [x] Exported operations must declare all effects.
  - [x] Exported operations with effects must prove capability or authority
        coverage.
  - [x] Exported operations should have `purpose`.
  - [ ] Exported operations should have `warning` when they expose nullable,
        unsafe, or external runtime behavior.
  - [ ] Exported types should have invariants where useful.
  - [ ] Exported constants must be immutable module storage.
  - [x] Reject export of mutable module storage.
  - [x] Reject export of local storage.
  - [x] Reject export of shared state values directly.
  - [x] Require mutation to cross modules through exported operations.
- [x] Build a module contract tape.
  - [x] Extract exported operation inputs.
  - [x] Extract exported operation outputs.
  - [x] Extract exported operation effects.
  - [x] Extract exported operation capability requirements.
  - [x] Extract exported operation failure types.
  - [x] Extract exported operation async/timing metadata.
  - [x] Extract exported operation memory metadata.
  - [x] Extract exported type/record fields.
  - [x] Extract exported enum and error cases.
  - [x] Extract exported constants and literal trust metadata.
  - [x] Preserve source locations for every exported contract edge.
- [ ] Validate exports.
  - [x] Reject unknown exported symbols.
  - [x] Reject duplicate exports.
  - [ ] Reject export cycles if a public facade imports and re-exports itself.
  - [x] Warn when exported operation names are too generic.
  - [ ] Warn when exported symbols have no module ownership context.
  - [x] Warn when exported operations hide dependencies through wrapper names
        without purpose explaining the abstraction.
- [x] Add export tests.
  - [x] Exported operation happy path.
  - [x] Unknown exported operation.
  - [x] Exported private mutable state rejected.
  - [x] Exported immutable constant accepted.
  - [x] Exported error cases available to consumers.
  - [x] Exported capability available to consumers.
  - [x] Contract tape includes effects and failures.

### Module Imports And Qualified Calls

- [ ] Define canonical module import syntax.
  - [x] Keep current `importModule DOTTED.PATH [as ALIAS]` for 1.x
        compatibility.
  - [x] Prefer `importModule ALIAS MODULE_PATH` for new project modules if the
        grammar can migrate without ambiguity.
  - [x] Document aliases as local source names, not package identities.
  - [ ] Require aliases for external dependencies.
  - [x] Reject alias collisions with local declarations.
  - [x] Reject imports of modules not reachable from `build.sem`.
- [x] Define qualified name usage.
  - [x] Allow `moduleAlias.operationName` call targets.
  - [x] Allow `moduleAlias.TypeName` type references.
  - [x] Allow `moduleAlias.ErrorType` error references.
  - [x] Allow `moduleAlias.CapabilityName` capability references only where
        capability imports are legal.
  - [x] Reject qualified access to non-exported symbols.
  - [x] Reject qualified access to mutable storage.
  - [x] Preserve qualified names in diagnostics.
- [ ] Implement module import resolution.
  - [x] Resolve same-project registered modules.
  - [ ] Resolve dependency modules from `.semcache/`.
  - [x] Resolve standard-library modules.
  - [ ] Reject imports that bypass `build.sem` dependency declarations.
  - [ ] Reject ambiguous module paths.
  - [ ] Cache resolved contract tapes.
  - [x] Preserve source location of import rows for diagnostics.
- [ ] Add import diagnostics.
  - [x] Unknown module path.
  - [x] Unknown alias.
  - [x] Duplicate alias.
  - [x] Import cycle.
  - [ ] Imported module lacks module contract rows in `build.sem`.
  - [ ] Imported module has no exports.
  - [x] Imported symbol exists but is private.
  - [ ] Imported operation contract has undeclared effects.
- [ ] Add import tests.
  - [x] Qualified call to exported operation.
  - [x] Qualified type reference.
  - [x] Qualified error reference.
  - [x] Private symbol rejected.
  - [x] Alias collision rejected.
  - [x] Import cycle rejected.
  - [x] Standard-library import.
  - [ ] Dependency import from cache.

### Singular Imports

- [x] Define singular import rows.
  - [x] Add `importOperation LOCAL_NAME MODULE_ALIAS EXPORTED_OPERATION`.
  - [x] Add `importType LOCAL_NAME MODULE_ALIAS EXPORTED_TYPE`.
  - [x] Add `importError LOCAL_NAME MODULE_ALIAS EXPORTED_ERROR`.
  - [x] Add `importCapability LOCAL_NAME MODULE_ALIAS EXPORTED_CAPABILITY`.
  - [x] Add `importConstant LOCAL_NAME MODULE_ALIAS EXPORTED_CONSTANT`.
  - [x] Explicitly reject wildcard imports.
  - [x] Explicitly reject implicit singular imports by capitalization or naming.
- [x] Define singular import semantics.
  - [x] Singular imports create local aliases only.
  - [x] Singular imports do not change the provider module's contract.
  - [x] Singular operation imports bring the full operation contract.
  - [x] Singular type imports bring related record/enum layout metadata.
  - [x] Singular error imports bring exported error cases.
  - [x] Singular capability imports bring effect path and access metadata.
  - [x] Singular constant imports bring immutable value/type metadata.
  - [x] Singular imports must not shadow local declarations.
  - [x] Singular imports must not shadow other imports.
  - [x] Singular imports should be linted when they make the source less clear
        than qualified names.
- [ ] Add singular import lint guidance.
  - [x] Prefer qualified calls for most module usage.
  - [ ] Allow singular imports for central domain operations used repeatedly.
  - [ ] Allow singular imports for facade modules that intentionally re-export
        public API.
  - [x] Warn when a file imports many singular operations from the same module.
  - [x] Warn when singular local alias hides the provider domain.
  - [ ] Require rationale for aliasing two different modules into similar local
        names.
- [x] Add singular import tests.
  - [x] Singular operation import happy path.
  - [x] Singular type import happy path.
  - [x] Singular error import happy path.
  - [x] Singular capability import happy path.
  - [x] Singular constant import happy path.
  - [x] Unknown exported symbol rejected.
  - [x] Shadowing local symbol rejected.
  - [x] Wildcard import rejected.

### Cross-Module Effects And Capabilities

- [ ] Preserve effect contracts across module calls.
  - [ ] Caller diagnostics should cite imported operation effects.
  - [ ] Caller must declare matching effects when imported operation effects
        escape through the call boundary.
  - [ ] Caller must use a capability or authority covering its declared effect.
  - [ ] Callee capability requirements should not be silently satisfied by the
        provider module once called from another module unless the contract says
        so.
  - [ ] Decide whether imported operations require caller capability proof,
        callee capability proof, or both.
- [ ] Define capability exports.
  - [ ] Exported capabilities are authority names, not runtime tokens by
        default.
  - [x] Imported capability aliases must preserve effect path and access mode.
  - [ ] Hierarchical capability coverage works across modules.
  - [ ] Narrow imported capabilities should remain narrow.
  - [ ] Reject broad capability re-export without a rationale.
- [ ] Define dependency effect propagation.
  - [ ] External dependency effects in a provider module must appear in exported
        operation contracts if the exported operation can trigger them.
  - [ ] Wrapper/facade modules may narrow or rename effects only with explicit
        metadata explaining the boundary.
  - [x] Observability effects must cross module boundaries like other effects.
  - [x] Network/file/database effects must never disappear through import.
- [ ] Add cross-module effect tests.
  - [ ] Imported operation with console effect.
  - [ ] Imported operation with filesystem effect.
  - [ ] Imported operation with HTTP response effect.
  - [ ] Imported operation with broad provider capability and narrow caller
        effect.
  - [x] Missing caller effect diagnostic.
  - [ ] Missing caller capability diagnostic.
  - [ ] Re-exported broad capability warning.

### Dependency Fetching And Cache

- [ ] Define Go-style module fetching.
  - [ ] Add `sem get MODULE_PATH@VERSION_OR_REF`.
  - [ ] Keep `sem get` in the SemanticScript tool driver layer so real network
        IO does not couple directly to LLVM/codegen.
  - [ ] Define `sem build` dependency-prep order before invoking `semsc`.
  - [ ] Decide whether bare `semsc build.sem` is allowed to fetch or only
        validates dependency rows and compiles already-resolved sources.
  - [ ] Define agent-readable fetch logs with alias, module path, requested ref,
        resolved commit, cache path, lock path, and failure reason.
  - [x] Support GitHub module paths.
  - [ ] Resolve GitHub `OWNER/REPO REF` to a deterministic archive URL.
  - [ ] Resolve GitHub tags and branches through API metadata before download.
  - [ ] Support anonymous GitHub fetch first.
  - [ ] Add optional GitHub token support later without storing tokens in
        `build.sem` or `sem.lock`.
  - [ ] Support generic Git URLs later without making GitHub special in the
        language grammar.
  - [x] Support local path dependencies for development.
  - [x] Support pinned tags.
  - [x] Support pinned commits.
  - [ ] Classify refs as immutable commit pins, mutable tags, mutable branches,
        or local paths.
  - [ ] Reject floating branches in release builds unless explicitly allowed.
- [ ] Define build-time fetch API boundaries.
  - [ ] Treat `dependencyFetch` as the build-time dependency API.
  - [ ] Reserve runtime outbound HTTP calls for a separate future API such as
        `http.clientRequest`, `http.clientResponseText`, or `net.fetchText`.
  - [ ] Do not let runtime HTTP client naming collide with server-side
        `http.request*` and `http.response*` APIs.
  - [ ] Define capability paths for future runtime fetch calls, such as
        `network.http.client read/write`.
  - [ ] Require any future runtime fetch wrapper to export effects the same way
        dependency-imported operations do.
- [ ] Implement dependency resolution phase.
  - [ ] Add a resolver that reads `build.sem` dependency rows into structured
        dependency request records.
  - [ ] Validate alias uniqueness and source/fetch/integrity coverage before
        touching disk or network.
  - [ ] Resolve local path dependencies directly from disk.
  - [ ] Resolve GitHub dependencies through archive download as the first
        implementation strategy.
  - [ ] Decide whether to support `git clone` later for submodules and unusual
        refs.
  - [ ] Resolve HTTPS archive dependencies through direct download.
  - [ ] Verify downloaded bytes before extraction.
  - [ ] Extract into a temporary directory, verify extracted source, then
        atomically move into cache.
  - [ ] Return dependency roots to import resolution as read-only source roots.
- [ ] Define `.semcache/`.
  - [ ] Store cloned dependencies outside source roots.
  - [ ] Use `.semcache/` beside `build.sem` as the default project-local cache.
  - [ ] Define cache subfolders for source archives, extracted trees, temp
        downloads, and per-alias metadata.
  - [ ] Use content-addressed archive filenames to avoid ref-name collisions.
  - [ ] Use resolved commits in extracted tree paths for GitHub dependencies.
  - [ ] Keep local path dependencies as external references rather than cached
        copies during normal dev builds.
  - [x] Keep `.semcache/` ignored by git.
  - [ ] Support user-global cache later if useful.
  - [ ] Support project-local cache for reproducible experiments.
  - [ ] Do not modify cached dependency sources during normal builds.
  - [ ] Write cache entries atomically.
  - [ ] Add lock files or equivalent process coordination for concurrent builds.
  - [ ] Rehash cached archives before reuse.
  - [ ] Rehash extracted source trees before reuse.
  - [ ] Quarantine corrupt cache entries and emit a repair command suggestion.
- [ ] Define lockfile behavior without TOML.
  - [x] Decide whether lock data lives in `sem.lock`, `build.lock.sem`, or
        another SemanticScript tape file.
  - [ ] Define `sem.lock` as the canonical SemanticScript lock tape.
  - [ ] Define lock header rows: `lockProject`, `lockFormatVersion`,
        `lockGeneratedBy`, and optional non-semantic metadata.
  - [ ] Define locked dependency rows for alias, module path, requested ref,
        resolved commit, fetch kind, source URL, archive URL, archive checksum,
        extracted tree digest, and dependency root.
  - [ ] Record module path.
  - [ ] Record requested version/ref.
  - [ ] Record resolved commit.
  - [ ] Record checksum.
  - [ ] Record dependency module root.
  - [ ] Record transitive dependencies.
  - [ ] Make normal builds use locked versions without hitting the network.
  - [ ] Add locked mode that fails if `sem.lock` is missing or stale.
  - [ ] Add update mode that may rewrite `sem.lock`.
  - [ ] Fail if remote source bytes or resolved commits disagree with lock
        data.
  - [ ] Keep lock diffs stable and reviewable by sorting dependencies
        deterministically.
- [ ] Implement dependency update flows.
  - [ ] `sem get` adds or updates dependency rows in `build.sem`.
  - [ ] `sem get` fetches dependency source into `.semcache/`.
  - [ ] `sem get` writes or updates the matching `sem.lock` rows.
  - [ ] `sem get` validates the dependency's `build.sem` before accepting it.
  - [ ] `sem mod tidy` removes unused dependency rows.
  - [ ] `sem mod tidy` keeps lock rows only for reachable dependencies.
  - [ ] `sem update ALIAS` updates one dependency.
  - [ ] `sem update ALIAS` preserves version constraints when possible.
  - [ ] `sem update` updates all dependencies within allowed constraints.
  - [ ] `sem update` refuses floating release updates without an explicit flag.
  - [ ] `sem vendor` copies dependencies into a vendored tree if that workflow
        is later accepted.
- [ ] Integrate fetched dependencies with module imports.
  - [ ] Locate dependency `build.sem` under each cached dependency root.
  - [ ] Read dependency `registerModule` rows from cached `build.sem`.
  - [ ] Resolve dependency module source files from the cached root.
  - [ ] Build dependency export contract tapes from cached module sources.
  - [ ] Allow project modules to import dependency modules by registered module
        path and alias.
  - [ ] Prevent dependency private symbols from leaking into project imports.
  - [ ] Include dependency source paths in linter and compiler diagnostics.
- [ ] Add dependency fetch tests.
  - [ ] Local path dependency.
  - [ ] Local path dependency does not use network.
  - [x] GitHub tag dependency.
  - [x] GitHub commit dependency.
  - [ ] GitHub archive download happy path.
  - [ ] GitHub tag-to-commit resolution happy path.
  - [ ] GitHub branch rejected in prod/release locked mode.
  - [ ] HTTPS archive download happy path.
  - [ ] HTTPS archive rejects plain `http://`.
  - [ ] Missing repository diagnostic.
  - [ ] Missing `build.sem` diagnostic.
  - [ ] Missing module contract rows in `build.sem` diagnostic.
  - [ ] Lockfile prevents network access during build.
  - [ ] Missing lock fails in locked mode.
  - [ ] Stale lock fails in locked mode.
  - [ ] Checksum mismatch fails before extraction.
  - [ ] Cache corruption diagnostic.
  - [ ] Dependency import resolves from cache.
  - [ ] Dependency import diagnostics cite cached source file paths.

### Runtime HTTP Client And Fetch API

- [ ] Define the runtime fetcher scope separately from build-time dependency
      fetching.
  - [ ] Keep `dependencyFetch` as build-time source acquisition.
  - [ ] Define runtime fetch as compiled-program behavior that lowers to native
        runtime calls.
  - [ ] Require runtime fetch calls to work without Python tooling at program
        execution time.
  - [ ] Decide the public namespace: `http.client*`, `net.fetch*`, or another
        name that cannot be confused with server-side `http.request*` and
        `http.response*`.
  - [ ] Define MVP target as blocking HTTP/1.1 plus HTTPS, not HTTP/2.
  - [ ] Defer HTTP/2 client support until TLS/ALPN and backend-library choices
        are settled.
- [ ] Design runtime fetch call targets.
  - [ ] Add `http.clientRequest` or equivalent request-construction call.
  - [ ] Add `http.clientFetchText` for simple text responses.
  - [ ] Add `http.clientFetchBytes` for binary responses.
  - [ ] Add `http.clientSetHeader` or equivalent request-header API.
  - [ ] Add request method support for GET.
  - [ ] Add request method support for POST.
  - [ ] Add request method support for PUT/PATCH/DELETE later.
  - [ ] Add request body text support.
  - [ ] Add request body bytes support.
  - [ ] Add per-request timeout argument.
  - [ ] Add max response body size argument.
  - [ ] Add optional redirect policy argument.
  - [ ] Add response status reader.
  - [ ] Add response header reader.
  - [ ] Add response body text reader.
  - [ ] Add response body bytes reader.
  - [ ] Add response body length reader.
  - [ ] Add explicit response cleanup/free call if response memory is owned by
        the caller.
- [ ] Define source-level types for runtime fetch.
  - [ ] Add or document `HttpClientRequest`.
  - [ ] Add or document `HttpClientResponse`.
  - [ ] Add or document `HttpMethod`.
  - [ ] Add or document `HttpStatus`.
  - [ ] Add or document `HttpHeaderName`.
  - [ ] Add or document `HttpHeaderValue`.
  - [ ] Add or document `Url`.
  - [ ] Add or document `NetworkTimeout`.
  - [ ] Add or document `ResponseBodyLimit`.
  - [ ] Decide whether URLs are plain `CNullTerminatedByteString` in MVP or a
        trusted/sanitized domain type.
- [ ] Define runtime fetch effects and capabilities.
  - [ ] Add canonical capability path `network.http.client`.
  - [ ] Decide whether outbound request effects use `read`, `write`, or both.
  - [ ] Require operations that perform outbound fetch to declare
        `effect OP write network.http.client` or the chosen equivalent.
  - [ ] Require operations that read response data to declare the matching
        response read effect if fetch and response inspection are separated.
  - [ ] Add linter checks so runtime fetch wrappers cannot hide network
        effects.
  - [ ] Ensure exported runtime-fetch wrappers carry effect edges in their
        public contract tape.
  - [ ] Ensure imported runtime-fetch wrappers trigger `SS2542`-style caller
        effect propagation.
  - [ ] Add diagnostics that suggest reusable capabilities for
        `network.http.client`.
- [ ] Choose the native runtime backend.
  - [ ] Compare a small custom HTTP/1.1 client against libcurl.
  - [ ] Compare OS TLS APIs against OpenSSL/LibreSSL/BoringSSL.
  - [ ] Decide whether MVP uses libcurl for DNS, TLS, redirects, and HTTP
        parsing.
  - [ ] If libcurl is used, define minimum supported version.
  - [ ] If a custom client is used, define DNS, socket, TLS, parser, redirect,
        and proxy boundaries explicitly.
  - [ ] Keep the SemanticScript ABI small even if the backend library is large.
  - [ ] Avoid exposing backend-library structs in generated SemanticScript ABI.
- [ ] Implement native runtime client ABI.
  - [ ] Add `sem_http_client_*` declarations to the runtime header.
  - [ ] Add request allocation/init function.
  - [ ] Add request header setter.
  - [ ] Add request body setter for text.
  - [ ] Add request body setter for bytes.
  - [ ] Add blocking execute/fetch function.
  - [ ] Add response status getter.
  - [ ] Add response header getter.
  - [ ] Add response body text getter.
  - [ ] Add response body bytes getter.
  - [ ] Add response body length getter.
  - [ ] Add response cleanup/free function.
  - [ ] Return structured status codes from every runtime function.
  - [ ] Keep all runtime-owned pointers valid until explicit cleanup or until
        the documented operation lifetime ends.
- [ ] Add compiler lowering for runtime fetch calls.
  - [ ] Register runtime fetch call signatures in the compiler builtin surface.
  - [ ] Register runtime fetch call signatures in semlint builtin signature
        tables.
  - [ ] Lower request creation to the native runtime function.
  - [ ] Lower header setters to the native runtime function.
  - [ ] Lower body setters to the native runtime function.
  - [ ] Lower execute/fetch calls to the native runtime function.
  - [ ] Lower response readers to native runtime functions.
  - [ ] Lower response cleanup/free calls to native runtime functions.
  - [ ] Add agent-readable compiler diagnostics for unsupported runtime fetch
        call targets.
  - [ ] Keep runtime fetch target names synchronized across `semsc.py`,
        `semlint.py`, `SYNTAX.md`, and docs.
- [ ] Define TLS behavior.
  - [ ] Require HTTPS support for the runtime fetch MVP.
  - [ ] Decide platform TLS provider per OS.
  - [ ] Decide certificate trust-store behavior on Windows.
  - [ ] Decide certificate trust-store behavior on macOS.
  - [ ] Decide certificate trust-store behavior on Linux.
  - [ ] Add diagnostic for TLS backend not available at link/runtime.
  - [ ] Add option to reject insecure TLS by default.
  - [ ] Decide whether development builds can opt into insecure TLS for local
        test servers.
  - [ ] Ensure TLS errors map to typed SemanticScript errors.
- [ ] Define URL, redirect, and protocol rules.
  - [ ] Reject unsupported schemes before network access.
  - [ ] Support `https://` in MVP.
  - [ ] Decide whether `http://` is allowed for localhost/dev only or allowed
        generally with warning.
  - [ ] Define max redirect count.
  - [ ] Define whether POST redirects preserve method/body.
  - [ ] Reject redirects from HTTPS to HTTP by default.
  - [ ] Define header-size limit.
  - [ ] Define status-line parsing limit.
  - [ ] Define response body-size limit.
  - [ ] Define timeout behavior for DNS, connect, TLS handshake, write, and
        response read.
- [ ] Define runtime fetch error model.
  - [ ] Add `HttpClientError` error domain.
  - [ ] Add DNS failure case.
  - [ ] Add connect failure case.
  - [ ] Add timeout case.
  - [ ] Add TLS handshake failure case.
  - [ ] Add certificate validation failure case.
  - [ ] Add invalid URL case.
  - [ ] Add unsupported scheme case.
  - [ ] Add request body too large case.
  - [ ] Add response body too large case.
  - [ ] Add malformed response case.
  - [ ] Add redirect limit exceeded case.
  - [ ] Decide whether non-2xx HTTP status is a transport success or typed
        application-level failure.
- [ ] Define memory ownership for runtime fetch.
  - [ ] Decide whether simple `fetchText` copies body into runtime-owned memory
        or caller-owned heap memory.
  - [ ] Add explicit cleanup rule for response bodies.
  - [ ] Add linter diagnostic for missing cleanup if cleanup is explicit.
  - [ ] Ensure response header values have documented lifetime.
  - [ ] Ensure response body bytes have documented lifetime.
  - [ ] Prevent use-after-free of response-owned pointers where the linter can
        prove it.
  - [ ] Add max allocation guard before reading response body.
- [ ] Define blocking, async, and webserver interaction.
  - [ ] Allow blocking runtime fetch in console programs for MVP.
  - [ ] State explicitly that async plumbing is not required for the first
        runtime fetch MVP.
  - [ ] Define blocking fetch as a synchronous native runtime call that owns the
        socket/TLS operation until it returns a response or error.
  - [ ] Require every blocking fetch call to carry an explicit timeout value.
  - [ ] Reject or warn on blocking fetch calls that rely on an infinite/default
        timeout.
  - [ ] Define per-phase timeout defaults when the user supplies one aggregate
        timeout.
  - [ ] Define max response body size as mandatory for blocking fetch helpers.
  - [ ] Decide whether blocking fetch may be used in `main` and ordinary console
        operations with only an effect/capability proof.
  - [ ] Define warning when a native webserver handler performs blocking
        runtime fetch without timeout.
  - [ ] Require timeout/cancellation metadata for runtime fetch inside
        webserver handlers.
  - [ ] Add a linter rule that detects `http.client*` calls inside operations
        bound by `route` or `routeMiddleware`.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        must have a timeout row or a timeout argument on the fetch call.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        must declare the outbound network effect.
  - [ ] Add a linter rule that webserver-bound operations using blocking fetch
        should document backpressure/concurrency risk with `warning` or
        `invariant`.
  - [ ] Decide whether blocking fetch in webserver handlers is WARNING-only in
        dev and ERROR in prod/release build profiles.
  - [ ] Define runtime behavior when blocking fetch times out inside a handler:
        return typed error to handler, emit 500, or trap depending on the
        handler's error contract.
  - [ ] Define whether middleware is allowed to short-circuit after a failed
        outbound fetch.
  - [ ] Decide whether runtime fetch can be used inside middleware.
  - [ ] Add a gauntlet route that deliberately exercises blocking fetch through
        a local loopback server once runtime fetch exists.
  - [ ] Add a webserver test proving one blocking fetch pins the current
        single-threaded server loop until timeout/response.
  - [ ] Add docs warning that current native webserver adapter is blocking and
        single-threaded.
  - [ ] Defer async/event-loop integration until the native server adapter has
        an async story.
  - [ ] Define future async fetch shape with `start`, `await`, `timeout`, and
        `cancelOn`.
  - [ ] Define future async fetch as nonblocking runtime work, not just a
        blocking call hidden behind `start`.
  - [ ] Define whether async fetch uses a worker-thread pool, nonblocking
        sockets, or platform event loops.
  - [ ] Define the MVP async backend options: select/poll, epoll/kqueue, IOCP,
        or a portable library.
  - [ ] Define how DNS resolution works in async mode.
  - [ ] Define how TLS handshakes are driven in async mode.
  - [ ] Define how cancellation interrupts connect, TLS handshake, request
        write, and response read phases.
  - [ ] Define how response body streaming works without buffering the entire
        body.
  - [ ] Define async fetch result ownership after `await`.
  - [ ] Define event-loop ownership for console programs.
  - [ ] Define event-loop ownership for native webserver programs.
  - [ ] Define whether the native webserver must become event-loop based before
        async fetch is allowed inside handlers.
  - [ ] Define how async fetch interacts with existing `taskGroup`,
        `startInGroup`, `awaitGroup`, `timeout`, and `cancelOn` rows.
  - [ ] Add future tests for two concurrent async fetches completing out of
        order.
  - [ ] Add future tests for cancellation during DNS/connect/TLS/read.
- [ ] Define linker and distribution behavior.
  - [ ] Add platform-specific linker flags for the chosen HTTP/TLS backend.
  - [ ] Add Windows linker flags and DLL discovery rules.
  - [ ] Add macOS linker flags and framework/library rules.
  - [ ] Add Linux linker flags and package dependency notes.
  - [ ] Add `sem doctor` checks for runtime fetch prerequisites.
  - [ ] Add build-profile behavior for statically linked versus dynamically
        linked HTTP client runtime.
  - [ ] Document how generated executables discover runtime client libraries.
- [ ] Add runtime fetch documentation and examples.
  - [ ] Add `docs/language/native-http-client-api.md`.
  - [ ] Add `SYNTAX.md` rows for runtime fetch call targets.
  - [ ] Add `docs/toolchain/compiler.md` linker/runtime notes.
  - [ ] Add optimization-guide notes for agent-readable fetch errors.
  - [ ] Add a minimal console `GET https://example.com` sample.
  - [ ] Add a JSON API fetch sample.
  - [ ] Add a POST body sample.
  - [ ] Add a timeout failure sample.
  - [ ] Add a TLS failure documentation example.
- [ ] Add runtime fetch tests.
  - [ ] Unit-test compiler lowering for every fetch call target.
  - [ ] Unit-test semlint builtin signature coverage.
  - [ ] Unit-test missing network capability diagnostic.
  - [ ] Unit-test imported fetch-wrapper effect propagation.
  - [ ] Integration-test HTTP GET against a local test server.
  - [ ] Integration-test HTTPS GET against a controlled test server or fixture.
  - [ ] Integration-test request headers.
  - [ ] Integration-test response headers.
  - [ ] Integration-test POST text body.
  - [ ] Integration-test binary response body.
  - [ ] Integration-test timeout behavior.
  - [ ] Integration-test redirect policy.
  - [ ] Integration-test max body-size failure.
  - [ ] Integration-test response cleanup under sanitizer or leak-check mode
        when available.

### Tests And `*.test.sem`

- [ ] Define colocated test file behavior.
  - [x] `*.test.sem` belongs to the same folder module as sibling source.
  - [ ] Test files may access public exports by default.
  - [ ] Decide whether tests may access private symbols in their same folder
        module.
  - [ ] Reject test files that declare a different module path.
  - [x] Exclude `*.test.sem` from normal module-source selection.
  - [ ] Include `*.test.sem` in `sem test`.
- [ ] Define test import behavior.
  - [ ] Tests can import sibling folder modules through normal imports.
  - [ ] Tests can import dependency modules declared in `build.sem`.
  - [ ] Tests can define test-only helper operations.
  - [ ] Test-only helpers are not exported into production contract tape.
- [ ] Add test discovery diagnostics.
  - [ ] Test file without sibling module.
  - [ ] Test file outside `sourceRoot`.
  - [ ] Test file with wrong module declaration.
  - [ ] Test file accidentally included in production build.
- [ ] Add test layout tests.
  - [ ] Sibling `foo.test.sem` happy path.
  - [ ] Nested module test happy path.
  - [ ] Private symbol access decision enforced.
  - [ ] Test-only helper excluded from exports.

### Migration From Current Import/Module Behavior

- [ ] Audit existing `module` rows.
  - [ ] List files with source-level `module` rows that should move to
        `build.sem`.
  - [ ] Identify modules that can become build-owned folder modules unchanged.
  - [ ] Identify samples needing a root `build.sem`.
  - [ ] Identify stdlib modules needing relay entries in `std/module.sem`.
- [ ] Audit existing `importModule` usage.
  - [ ] List current import paths.
  - [ ] Decide compatibility period for `importModule DOTTED.PATH [as ALIAS]`.
  - [ ] Add migration diagnostics that suggest the new form.
  - [ ] Avoid breaking current `.sscript` / `.sem` tests before migration is
        staged.
- [ ] Add compatibility rules.
  - [x] Single-file scripts can keep old import behavior temporarily.
  - [x] Project builds through `build.sem` use registered module resolution.
  - [ ] Linter can warn on old form before compiler rejects it.
  - [x] Docs clearly mark filesystem/std-lib fallback as compatibility behavior.
- [ ] Add migration tests.
  - [x] Legacy single-file import still works during compatibility window.
  - [x] New project import works.
  - [ ] Mixed old/new imports produce clear diagnostics.
  - [ ] Migration suggestions include exact replacement rows.

## P1 - Developer Tooling Roadmap For A Real Language

This section tracks the toolchain needed for SemanticScript to feel like a
complete language instead of a set of implementation scripts. These are not all
required for the scoped 1.0 release, but they should guide the post-1.0 tooling
order.

### `semfmt` Formatter

- [x] Create a formatter entrypoint named `semfmt`.
  - [x] Decide whether `semfmt` lives under `SemanticScript/tools/`,
        `SemanticScript/formatter/`, or as a `sem fmt` subcommand wrapper.
  - [ ] Add command help with examples for `.sscript` and `.sem` files.
  - [x] Support formatting one file.
  - [x] Support formatting multiple explicit files.
  - [x] Support recursive project formatting with include/exclude globs.
  - [x] Add `--check` mode for CI that exits non-zero on formatting drift.
  - [x] Add `--diff` mode that prints a unified diff without writing files.
  - [x] Add `--stdin-file-name` support for editor integrations.
- [ ] Make formatting parser-aware instead of regex-only.
  - [ ] Reuse the compiler/linter tokenizer or extract a shared tokenizer.
  - [ ] Preserve comments exactly unless indentation is intentionally adjusted.
  - [x] Preserve blank lines where they separate logical sections.
  - [x] Preserve quoted strings and escape sequences byte-for-byte.
  - [x] Preserve unknown/proposed verbs instead of deleting or rewriting them.
- [ ] Define canonical row layout rules.
  - [x] Canonicalize one space between tokens.
  - [x] Trim trailing whitespace.
  - [x] Keep comments after code separated by at least two spaces if inline
        comments are allowed.
  - [x] Keep top-level declaration rows unindented.
  - [x] Decide whether operation body rows remain unindented or gain logical
        indentation in formatted output.
  - [ ] Define maximum line length and whether long strings are never wrapped.
  - [ ] Define how long metadata strings should be wrapped, if at all.
- [ ] Define canonical ordering rules where safe.
  - [x] Decide whether formatter may reorder metadata rows.
  - [ ] If reordering is allowed, order operation metadata as
        `purpose`, `input`, `output`, `effect`, `useCapability`, warnings, then
        invariants.
  - [x] Never reorder executable body rows unless a proof exists that behavior
        is unchanged.
  - [x] Never reorder route rows unless route precedence rules make ordering
        irrelevant.
- [ ] Add formatter configuration.
  - [x] Define formatter settings in `build.sem` or a future SemanticScript
        settings tape, not TOML.
  - [ ] Support line width.
  - [ ] Support newline mode.
  - [x] Support quote-preservation only, not quote-style rewrites.
  - [ ] Document defaults as the canonical project style.
- [ ] Add formatter tests.
  - [x] Golden-format tests for small syntax examples.
  - [ ] Golden-format tests for webserver apps.
  - [x] Golden-format tests for comments and blank lines.
  - [x] Golden-format tests for quoted strings with escaped characters.
  - [x] Idempotence tests: formatting twice produces byte-identical output.
  - [x] Safety tests: formatted source parses to the same high-level semantic
        tape as the original.
  - [ ] Fuzz tests for tokenizer/formatter round-tripping.
- [ ] Integrate formatter into editors and CI.
  - [ ] Add VS Code `DocumentFormattingEditProvider`.
  - [ ] Add format-on-save documentation.
  - [ ] Add CI `semfmt --check` once formatting is stable.
  - [ ] Add release checklist item requiring formatter clean output.

### `sem` Project Command Driver

- [x] Create a single daily-use command named `sem`.
  - [x] Decide implementation language for the first driver.
  - [x] Make the driver work from PowerShell on Windows.
  - [x] Make the driver work from POSIX shells.
  - [x] Add `sem --version`.
  - [x] Add `sem --help`.
  - [x] Add useful non-zero exit codes for scripting.
- [ ] Wrap compiler commands.
- [x] Add `sem build`.
  - [x] Add `sem run`.
  - [x] Add `sem check` for parse, lint, and type/codegen validation.
  - [ ] Add `sem emit-ir`.
  - [ ] Add `sem clean` for ignored local build artifacts.
  - [x] Pass through `--build-profile dev|prod`.
  - [x] Pass through `--runtime-checks off|traps|panic`.
  - [x] Pass through `--persist-llvm-ir auto|yes|no`.
  - [x] Pass through `--opt-level`.
- [ ] Wrap quality tools.
  - [ ] Add `sem lint`.
  - [ ] Add `sem lint --engine semlint`.
  - [ ] Add `sem lint --engine semlint`.
  - [ ] Add `sem fmt`.
  - [ ] Add `sem fmt --check`.
  - [ ] Add `sem test`.
  - [ ] Add `sem doc`.
  - [ ] Add `sem explain`.
  - [ ] Add `sem bench`.
  - [ ] Add `sem doctor`.
- [x] Add project discovery.
  - [x] Discover the nearest `build.sem`.
  - [x] Fall back to single-file mode when no build tape exists.
  - [x] Resolve source roots from `build.sem`.
  - [x] Resolve build output directories from `build.sem`.
  - [x] Resolve default entrypoints from `build.sem`.
  - [x] Resolve target runtime settings from `build.sem`.
- [ ] Add project templates.
  - [ ] Add `sem new console`.
  - [ ] Add `sem new web`.
  - [ ] Add `sem new library`.
  - [ ] Add `sem new package`.
  - [ ] Add template tests proving generated projects build.
- [ ] Add toolchain environment checks.
  - [ ] `sem doctor` checks Python version.
  - [ ] `sem doctor` checks `llvmlite`.
  - [ ] `sem doctor` checks clang or `SEMSC_CLANG`.
  - [ ] `sem doctor` checks Node.js when VS Code extension tooling is needed.
  - [ ] `sem doctor` checks native HTTP runtime build prerequisites.
  - [ ] `sem doctor` prints concrete fix commands where possible.
- [ ] Add driver tests.
  - [ ] Unit-test argument parsing.
  - [ ] Test single-file build.
  - [x] Test build-tape-based build.
  - [ ] Test `sem check` failure reporting.
  - [ ] Test PowerShell examples.
  - [ ] Test POSIX examples in CI if a POSIX runner is available.

### `build.sem` Project Build Tape

- [x] Define the project build tape schema.
  - [x] Project name.
  - [x] Project version.
  - [x] License field.
  - [x] Source roots.
  - [x] Default entry operation.
  - [x] Build profiles.
  - [x] Runtime target.
  - [x] Native HTTP settings.
  - [x] Test roots.
  - [x] Formatter settings.
  - [x] Linter settings.
  - [x] Documentation output settings.
  - [x] LLVM build flags.
  - [x] Compiler-managed build folder settings.
- [x] Implement build-tape parsing.
  - [x] Add strict diagnostics for malformed project build rows.
  - [x] Add strict diagnostics for unknown top-level keys.
  - [x] Add strict diagnostics for missing required fields.
  - [x] Add path normalization on Windows and POSIX.
  - [x] Add tests for relative and absolute paths.
- [x] Integrate project build tapes with existing tools.
  - [x] `semsc.py` can accept a `build.sem`-driven build through `sem build`.
  - [x] `semlint.py` can lint a `build.sem` project.
  - [x] VS Code extension can discover project settings from `build.sem`.
  - [x] Future language server can use `build.sem` as the workspace root.
- [x] Document the project build tape.
  - [x] Add a minimal console app `build.sem` example.
  - [x] Add a native webserver `build.sem` example.
  - [x] Add a library/package `build.sem` example.
  - [x] Add a schema reference table.

### `semls` Language Server

- [ ] Create a language server entrypoint named `semls`.
  - [ ] Decide whether to implement JSON-RPC directly or use an LSP library.
  - [ ] Define startup options.
  - [ ] Define workspace-root discovery through `build.sem`.
  - [ ] Support single-file mode.
  - [ ] Add structured logging for LSP failures.
- [ ] Move VS Code-only intelligence into reusable language services.
  - [ ] Extract tokenizer and symbol index into shared code.
  - [ ] Extract hover generation into shared code.
  - [ ] Extract completion data into shared code.
  - [ ] Extract diagnostics conversion into shared code.
  - [ ] Keep the VS Code extension as a thin client once `semls` is stable.
- [ ] Implement core LSP features.
  - [ ] `textDocument/didOpen`.
  - [ ] `textDocument/didChange`.
  - [ ] `textDocument/didSave`.
  - [ ] `textDocument/hover`.
  - [ ] `textDocument/definition`.
  - [ ] `textDocument/references`.
  - [ ] `textDocument/documentSymbol`.
  - [ ] `workspace/symbol`.
  - [ ] `textDocument/completion`.
  - [ ] `textDocument/semanticTokens/full`.
  - [ ] `textDocument/formatting` backed by `semfmt`.
  - [ ] `textDocument/codeAction`.
  - [ ] `textDocument/rename` after symbol resolution is reliable.
- [ ] Implement diagnostics.
  - [ ] Run parser diagnostics incrementally.
  - [ ] Run `semlint.py` or equivalent stable diagnostics.
  - [ ] Run `semlint.py` structured diagnostics.
  - [ ] Debounce diagnostics on type.
  - [ ] Cancel stale diagnostics for older document versions.
  - [ ] Map diagnostic codes to `sem explain` documentation.
  - [ ] Add quick fixes where the edit is obvious and low-risk.
- [ ] Implement project awareness.
  - [ ] Resolve imports.
  - [ ] Build a cross-file symbol index.
  - [ ] Detect duplicate exported names.
  - [ ] Detect ambiguous unqualified references.
  - [ ] Support go-to-definition across imported files.
  - [ ] Support find-references across imported files.
- [ ] Add language-server tests.
  - [ ] Protocol-level tests for initialize/shutdown.
  - [ ] Hover snapshot tests.
  - [ ] Completion snapshot tests.
  - [ ] Definition/reference tests.
  - [ ] Diagnostic debounce/cancellation tests.
  - [ ] Workspace import-resolution tests.

### `sem test` Test Runner

- [ ] Define first-class SemanticScript test conventions.
  - [ ] Decide test file naming rules.
  - [ ] Decide whether test operations use metadata or naming conventions.
  - [ ] Decide how fixtures are referenced.
  - [ ] Decide how expected failures are declared.
- [ ] Implement test discovery.
  - [ ] Discover tests from `build.sem` / `testPattern`.
  - [ ] Discover tests from default `tests/` roots.
  - [ ] Support explicit file selection.
  - [ ] Support explicit test name filtering.
  - [ ] Support tags.
- [ ] Support test kinds.
  - [ ] Parse-only tests.
  - [ ] Lint-clean tests.
  - [ ] Compile-success tests.
  - [ ] Compile-fail tests with expected diagnostic codes.
  - [ ] Runtime-success tests.
  - [ ] Runtime-fail tests with expected crash/error output.
  - [ ] Golden stdout tests.
  - [ ] Golden stderr tests.
  - [ ] HTTP route tests.
  - [ ] Multipart upload tests.
  - [ ] SSE response tests.
  - [ ] Timeout/metadata tests.
- [ ] Add test output formats.
  - [ ] Human-readable console output.
  - [ ] JSON output for agents and CI.
  - [ ] JUnit XML for CI systems.
  - [ ] Snapshot update mode for golden tests.
- [ ] Add test isolation.
  - [ ] Use temporary build directories.
  - [ ] Allocate non-conflicting local ports for web tests.
  - [ ] Kill child processes on timeout.
  - [ ] Clean generated executables and IR after each test unless debugging.
- [ ] Add test runner tests.
  - [ ] Test discovery.
  - [ ] Test success/failure exit codes.
  - [ ] Test compile-fail matching.
  - [ ] Test golden-output diff rendering.
  - [ ] Test webserver lifecycle cleanup.

### `semdoc` Documentation Generator

- [ ] Create a documentation generator entrypoint named `semdoc`.
  - [ ] Support `sem doc` as the primary user-facing wrapper.
  - [ ] Support Markdown output.
  - [ ] Support HTML output later if needed.
  - [ ] Support JSON output for agents.
- [ ] Extract source-level documentation.
  - [ ] Operations.
  - [ ] Inputs and outputs.
  - [ ] Effects.
  - [ ] Capabilities and authorities.
  - [ ] Records and fields.
  - [ ] Enums and error variants.
  - [ ] Web servers and route tables.
  - [ ] Route middleware and timeout metadata.
  - [ ] Warnings, invariants, security notes, and observability notes.
- [ ] Add cross-linking.
  - [ ] Link operation references to operation sections.
  - [ ] Link route handlers to operation sections.
  - [ ] Link capability uses to capability declarations.
  - [ ] Link diagnostic codes to `sem explain`.
- [ ] Add docs quality checks.
  - [ ] Warn when public operations lack `purpose`.
  - [ ] Warn when route handlers lack response behavior notes.
  - [ ] Warn when warnings/invariants reference missing operations or calls.
  - [ ] Warn when documented effects do not match declared effects.
- [ ] Add docs generator tests.
  - [ ] Snapshot generated docs for a console app.
  - [ ] Snapshot generated docs for a web app.
  - [ ] Snapshot generated docs for HTTP gauntlet.
  - [ ] Test broken references become diagnostics.

### `sem explain` Error Explainer

- [ ] Create an error explainer entrypoint.
  - [ ] Support `sem explain CODE`.
  - [ ] Support explaining compiler diagnostic codes.
  - [ ] Support explaining `semlint.py` rules.
  - [ ] Support explaining `semlint.py` diagnostic codes.
  - [ ] Support explaining runtime panic codes such as `SSRUN001`.
- [ ] Create a diagnostic knowledge base.
  - [ ] Store code title.
  - [ ] Store short explanation.
  - [ ] Store why agents usually trigger it.
  - [ ] Store common fixes.
  - [ ] Store bad/fixed source examples.
  - [ ] Store related spec/doc links.
  - [ ] Store severity and category.
- [ ] Integrate explain output into tools.
  - [ ] Compiler diagnostics include `Run: sem explain CODE`.
  - [ ] Linter diagnostics include explain links in JSON output.
  - [ ] VS Code hovers/code actions can open explain docs.
  - [ ] Language server diagnostics include `codeDescription` links.
- [ ] Add tests.
  - [ ] Every compiler diagnostic code has an explanation.
  - [ ] Every semlint diagnostic code has an explanation.
  - [ ] Examples in explanations parse or intentionally fail as documented.

### Trace, Crash, And Debug Tooling

- [ ] Define source-to-runtime trace metadata.
  - [ ] Map semantic tape rows to source file/line/column.
  - [ ] Map generated LLVM blocks back to operation and call names.
  - [ ] Map native runtime failures back to SemanticScript route/handler names.
- [ ] Add trace execution mode.
  - [ ] Add `sem run --trace`.
  - [ ] Add trace output for operation entry/exit.
  - [ ] Add trace output for call execution.
  - [ ] Add trace output for branch decisions.
  - [ ] Add trace output for returned values where safe.
  - [ ] Redact values from paths marked sensitive by future metadata.
- [ ] Add crash explanation mode.
  - [ ] Add `sem run --explain-crash`.
  - [ ] Capture runtime panic code.
  - [ ] Capture SemanticScript stack/operation context.
  - [ ] Capture direction message that hints at the likely fix.
  - [ ] Capture build profile and runtime-check mode.
  - [ ] Keep prod profile output minimal by default.
- [ ] Add IR inspection helpers.
  - [ ] Add `sem inspect-ir`.
  - [ ] Show the source operation that produced an IR function.
  - [ ] Show native ABI signatures for HTTP handlers.
  - [ ] Show linked runtime objects.
- [ ] Add minimal debugger plan.
  - [ ] Decide whether to integrate with LLDB/GDB or keep source-level traces
        only for the first release.
  - [ ] Define breakpoint syntax if source-level breakpoints are added.
  - [ ] Define watch/expression support only after value representation is
        stable.

### REPL And Scratch Runner

- [ ] Decide whether a REPL fits SemanticScript's file/operation model.
  - [ ] If yes, define how scratch operations are wrapped.
  - [ ] If no, document `sem scratch` as the supported interactive workflow.
- [ ] Add `sem scratch`.
  - [ ] Create a temporary source file.
  - [ ] Insert a minimal operation scaffold.
  - [ ] Compile/run the scratch file.
  - [ ] Preserve scratch files on failure for debugging.
- [ ] Add `sem run-snippet`.
  - [ ] Accept source from stdin.
  - [ ] Accept a named entry operation.
  - [ ] Print compiler/linter diagnostics with source snippets.
- [ ] Add tests for scratch/snippet workflows.

### `sem bench` Benchmark Tool

- [ ] Create a benchmark entrypoint.
  - [ ] Support `sem bench`.
  - [ ] Support `build.sem`-discovered benchmarks.
  - [ ] Support explicit benchmark files.
  - [ ] Support warmup iterations.
  - [ ] Support measured iterations.
  - [ ] Support JSON output.
- [ ] Track benchmark dimensions.
  - [ ] Compile time.
  - [ ] Native executable size.
  - [ ] Runtime duration.
  - [ ] Peak memory if practical.
  - [ ] HTTP requests per second for webserver benchmarks.
  - [ ] Startup latency for native webserver binaries.
- [ ] Add baseline benchmarks.
  - [ ] Console hello world.
  - [ ] Numeric loop.
  - [ ] String scanning.
  - [ ] JSON encode/decode once implemented.
  - [ ] Todo web hello route.
  - [ ] HTTP API gauntlet route matrix.
- [ ] Add benchmark guardrails.
  - [ ] Store baselines outside normal source unless intentionally committed.
  - [ ] Add tolerance thresholds.
  - [ ] Avoid flaky wall-clock assertions in normal CI.
  - [ ] Provide local comparison reports.

### Fuzzing And Property Testing

- [ ] Add parser fuzzing.
  - [ ] Fuzz token streams.
  - [ ] Fuzz quoted strings and escape sequences.
  - [ ] Fuzz comments and blank lines.
  - [ ] Assert parser never crashes.
  - [ ] Assert diagnostics stay source-located.
- [ ] Add formatter fuzzing.
  - [ ] Fuzz format round-trips.
  - [ ] Assert formatter is idempotent.
  - [ ] Assert formatted source still parses.
- [ ] Add linter fuzzing.
  - [ ] Fuzz operation/call graphs.
  - [ ] Fuzz route metadata.
  - [ ] Fuzz capability/effect paths.
  - [ ] Assert linter emits bounded diagnostics without exceptions.
- [ ] Add compiler fuzzing.
  - [ ] Generate small well-typed programs.
  - [ ] Generate expected-invalid programs.
  - [ ] Assert compiler never throws uncaught Python exceptions.
  - [ ] Assert invalid programs produce structured diagnostics.
- [ ] Add HTTP runtime fuzzing.
  - [ ] Fuzz request lines.
  - [ ] Fuzz headers.
  - [ ] Fuzz query strings.
  - [ ] Fuzz multipart boundaries.
  - [ ] Fuzz large bodies within configured limits.
  - [ ] Assert runtime returns controlled 4xx/5xx responses instead of
        crashing.
- [ ] Integrate fuzzing carefully.
  - [ ] Add short deterministic fuzz smoke tests to CI.
  - [ ] Add long fuzz jobs for manual/nightly runs.
  - [ ] Persist failure seeds.
  - [ ] Add minimization instructions.

### Package, Module, And Registry Tooling

- [ ] Define package layout conventions.
  - [ ] Source root.
  - [ ] Test root.
  - [ ] Generated output root.
  - [ ] Documentation output root.
  - [ ] Native runtime configuration root.
- [ ] Define dependency syntax in `build.sem` or a SemanticScript lock/build
      tape.
  - [ ] Local path dependencies.
  - [ ] Git dependencies.
  - [ ] Versioned registry dependencies later.
  - [ ] Dependency feature flags later if needed.
- [ ] Add dependency resolution.
  - [ ] Lockfile design.
  - [ ] Reproducible dependency graph.
  - [ ] Clear diagnostics for missing dependencies.
  - [ ] Clear diagnostics for conflicting versions.
- [ ] Add package validation.
  - [ ] License present.
  - [ ] README present.
  - [ ] Public operations documented.
  - [ ] Tests pass.
  - [ ] No generated artifacts included.
- [ ] Defer registry implementation until local/package workflow is stable.
  - [ ] Document registry requirements.
  - [ ] Define package signing or checksum expectations.
  - [ ] Define ownership/namespace rules.

### Installer And Version Manager

- [ ] Decide install strategy.
  - [ ] Single archive download.
  - [ ] Python package wrapper.
  - [ ] Native launcher.
  - [ ] Platform package managers later.
- [ ] Create `semup` or equivalent version manager plan.
  - [ ] Install a named SemanticScript version.
  - [ ] Update to latest stable.
  - [ ] Select active version per user.
  - [ ] Select active version per project.
  - [ ] Print installed versions.
- [ ] Add Windows support.
  - [ ] PowerShell installer script.
  - [ ] PATH setup instructions.
  - [ ] Toolchain detection.
  - [ ] Uninstall instructions.
- [ ] Add POSIX support.
  - [ ] Shell installer script.
  - [ ] PATH setup instructions.
  - [ ] Toolchain detection.
  - [ ] Uninstall instructions.
- [ ] Add release artifact checks.
  - [ ] Checksums.
  - [ ] Signature plan if needed.
  - [ ] Smoke test installed `sem`.
  - [ ] Smoke test installed VS Code extension package separately.

### Agent-Focused Tooling

- [ ] Add machine-readable project context output.
  - [ ] `sem context --json` summarizes project roots, entrypoints, tools, and
        supported syntax.
  - [ ] Include compiler version.
  - [ ] Include linter version.
  - [ ] Include runtime feature flags.
  - [ ] Include known xfail/deferred features.
- [ ] Add machine-readable symbol graph output.
  - [ ] `sem symbols --json`.
  - [ ] Include operations, calls, inputs, outputs, effects, and routes.
  - [ ] Include source locations.
  - [ ] Include unresolved references.
- [ ] Add agent-safe fix suggestions.
  - [ ] Diagnostics should include minimal fix direction.
  - [ ] Diagnostics should distinguish safe automatic edits from human review
        edits.
  - [ ] Avoid suggestions that require broad refactors unless explicitly marked.
- [ ] Add docs for agent workflows.
  - [ ] How to run the fast validation set.
  - [ ] How to inspect route/effect/capability graphs.
  - [ ] How to safely update generated docs.
  - [ ] How to avoid touching ignored build artifacts.

### Release, Packaging, And Repository Policy

- [x] Add MIT root `LICENSE`.
- [x] Align `vscode-semanticscript/package.json` license with root `LICENSE`.
- [ ] Decide VS Code publisher identity before marketplace publishing.
- [x] Align VS Code extension version with the release plan.
- [ ] Get to a release-clean worktree before tagging.
  - [ ] Commit or intentionally discard modified source/docs.
  - [ ] Commit or intentionally remove untracked README/doc files.
  - [ ] Confirm generated `.exe`, `.ll`, `__pycache__`, `todos.json`, and
        `.vsix` artifacts are ignored and absent from source control.
- [x] Decide whether duplicate top-level `python/` and `samples/python/`
      folders should both remain.
- [x] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked alias fixtures or generated artifacts.
- [x] Run and record aggressive validation before any 1.0 tag.
  - [x] Compiler unit tests.
  - [x] Standalone linter tests.
  - [x] Structured linter tests.
  - [x] Feature coverage tests.
  - [x] Bootstrap parity tests.
  - [x] Native HTTP webserver tests.
  - [x] Runtime CMake build.
  - [x] VS Code extension syntax/package checks.

### Initial Release Hardening Gaps

These items were identified after comparing the current release checklist,
`TODO.md`, release docs, and repository state. They are release-polish and
release-trust tasks that were either absent from this file or too implicit to
assign cleanly.

- [ ] Define a single release version policy.
  - [ ] Decide whether all first-party tools should share the same release
        version for the initial public release.
  - [ ] Decide whether `semsc`, `semlint`, `semfmt`, `sem`, and the VS Code
        extension are independently versioned components or one product
        version.
  - [ ] Record the decision in `RELEASE.md`.
  - [ ] Record the decision in `docs/reference/release-hygiene.md`.
  - [ ] Add a release version matrix listing each public command/package and
        its version.
  - [ ] Include `SemanticScript/compiler/semsc.py`.
  - [ ] Include `SemanticScript/linter/semlint.py`.
  - [ ] Include `SemanticScript/formatter/semfmt.py`.
  - [ ] Include `SemanticScript/tools/sem.py`.
  - [ ] Include `vscode-semanticscript/package.json`.
  - [ ] Align stale docs that still mention old VSIX versions.
  - [ ] Update `README.md` if it references an older
        `semanticscript-vscode-*.vsix` artifact.
  - [ ] Update `docs/reference/release-hygiene.md` if it references an older
        extension version.
  - [ ] Add a simple release check that prints all tool versions.
  - [ ] Decide whether mismatched tool versions fail a release check or are
        allowed when documented in the matrix.

- [ ] Add a real security contact before public release.
  - [ ] Replace the `TODO` contact placeholder in `SECURITY.md`.
  - [ ] Decide the reporting channel: email address, GitHub security advisory,
        private issue tracker, or another maintained channel.
  - [ ] Document expected acknowledgement timing.
  - [ ] Document expected fix/disclosure timing.
  - [ ] Document which versions are supported for security fixes.
  - [ ] Confirm the contact can receive reports before tagging a public
        release.
  - [ ] Add a release checklist item that fails if `SECURITY.md` still contains
        a public-release contact placeholder.

- [ ] Add a third-party license and SBOM review.
  - [ ] Inventory every directory under `third_party/`.
  - [ ] Record upstream project name for each vendored dependency.
  - [ ] Record upstream URL for each vendored dependency.
  - [ ] Record pinned revision, release tag, or source acquisition date.
  - [ ] Record license for `third_party/h2o`.
  - [ ] Record license for `third_party/sqlite`.
  - [ ] Preserve upstream license files in packaged source archives.
  - [ ] Decide whether to add a root `NOTICE` file.
  - [ ] Decide whether to add a machine-readable SBOM file.
  - [ ] If adding an SBOM, choose a format such as SPDX or CycloneDX.
  - [ ] Document which release artifacts include third-party code.
  - [ ] Document whether source-only releases and binary releases have
        different notice requirements.
  - [ ] Run a basic vulnerability review for vendored dependencies.
  - [ ] Record known CVE exceptions or "none known at release time" in release
        notes.
  - [ ] Add a release checklist item that requires third-party license/SBOM
        review before tagging.

- [ ] Verify generated artifacts are removed from Git history.
  - [ ] Define which historical artifacts are disallowed in repository history.
  - [ ] Include generated `.exe` files.
  - [ ] Include generated `.ll` files.
  - [ ] Include generated `.bc`, `.obj`, `.o`, `.pdb`, `.res`, `.rc`, and
        native build folders.
  - [ ] Include packaged `.vsix` files if the release policy keeps VSIX
        artifacts outside Git.
  - [ ] Include local app data such as `todos.json`.
  - [ ] Add a non-destructive history scan command to `RELEASE.md`.
  - [ ] Run the history scan against all branches intended for release.
  - [ ] Decide whether history rewriting is required before the first public
        push/tag.
  - [ ] If rewriting history, document the exact tool and command used.
  - [ ] Prefer `git filter-repo` or another repeatable non-interactive tool for
        any required history rewrite.
  - [ ] Verify rewritten history still contains required source, docs, and test
        fixtures.
  - [ ] Verify current `.gitignore` catches the same artifact classes after the
        history scrub.
  - [ ] Record the final history-scan result in release notes.

- [ ] Make CI enforce the full release checklist.
  - [ ] Compare `.github/workflows/ci.yml` against `RELEASE.md`.
  - [ ] Add CI coverage for `SemanticScript/formatter/test_semfmt.py` if not
        already enforced.
  - [ ] Add CI coverage for `SemanticScript/tests/test_compiler.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/test_stdlib.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/compare.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/sem_alias_parity.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/sem_compiler_parity.py`.
  - [ ] Add CI coverage for `SemanticScript/tests/feature_coverage.py`.
  - [ ] Add CI coverage for `SemanticScript/bootstrap/run_bootstrap_chain.py`.
  - [ ] Add CI coverage for `app/todo-web/test_todo_web.py`.
  - [ ] Add CI coverage for `app/todo-web-advanced/test_advanced_todo_web.py`.
  - [ ] Add CI coverage for `app/http-api-gauntlet/scripts/test_http_api_gauntlet.py`.
  - [ ] Add CI coverage for the native HTTP runtime CMake build where the
        runner toolchain supports it.
  - [ ] Add CI coverage for the native JSON runtime CMake build if it remains
        in the release scope.
  - [ ] Add CI coverage for the native SQLite runtime CMake build if it remains
        in the release scope.
  - [ ] Add CI coverage for `npm --prefix vscode-semanticscript run check`.
  - [ ] Add optional CI coverage for `npm --prefix vscode-semanticscript run
        package:vsix` without uploading the artifact by default.
  - [ ] Run native executable tests on Windows CI, not only Linux.
  - [ ] Run at least parse/lint/tooling checks on Linux CI.
  - [ ] Document any release validation commands that intentionally remain
        manual.
  - [ ] Add a release checklist item requiring CI green on the exact release
        commit.

- [ ] Define the public 1.0 compatibility contract.
  - [ ] Write down what `languageVersion PROJECT "1.0"` guarantees.
  - [ ] Define which syntax rows are stable for 1.0.
  - [ ] Define which syntax rows are preview, partial, metadata-only, or
        subject to change.
  - [ ] Define whether `.sscript` and `.sem` have equal long-term support.
  - [ ] Define whether `.sscript` remains canonical and `.sem` remains an alias.
  - [ ] Define compatibility guarantees for `build.sem`.
  - [ ] Define compatibility guarantees for module/import/export rows.
  - [ ] Define compatibility guarantees for native HTTP APIs.
  - [ ] Define compatibility guarantees for JSON runtime APIs currently in
        scope.
  - [ ] Define compatibility guarantees for VS Code syntax highlighting and
        extension configuration keys.
  - [ ] Define the deprecation process for syntax that changes after 1.0.
  - [ ] Define whether future compiler versions warn before rejecting old 1.0
        syntax.
  - [ ] Add the compatibility contract to `README.md` or a dedicated docs page.
  - [ ] Link the compatibility contract from `RELEASE.md`.
  - [ ] Link the compatibility contract from `SYNTAX.md`.

- [ ] Add a release artifact manifest.
  - [ ] Define a manifest filename and location for each release.
  - [ ] Record release tag.
  - [ ] Record release commit SHA.
  - [ ] Record release date.
  - [ ] Record tool versions.
  - [ ] Record Python version used for release validation.
  - [ ] Record Node.js version used for VS Code extension validation.
  - [ ] Record clang/LLVM version used for native executable validation.
  - [ ] Record operating systems used for validation.
  - [ ] Record exact validation commands run.
  - [ ] Record skipped validation commands and the reason.
  - [ ] Record generated release artifacts such as source archive and VSIX.
  - [ ] Record artifact checksums.
  - [ ] Record whether signatures were generated.
  - [ ] Record known deferred features from `TODO.md`.
  - [ ] Record known xfail/bootstrap limitations.
  - [ ] Add a release checklist item requiring the manifest before tagging.
  - [ ] Decide whether manifests are committed, attached to GitHub releases, or
        both.

## P1 - Packaging, Install, And CI

- [x] Add dependency metadata for Python tooling.
  - [x] Document Python version requirements.
  - [x] Document `llvmlite` requirement.
  - [x] Document `clang` / `SEMSC_CLANG` requirement.
- [x] Add a repeatable release validation entrypoint.
  - [x] CI workflow or script for compiler unit tests.
  - [x] CI workflow or script for stdlib tests.
  - [x] CI workflow or script for semlint tests.
  - [x] CI workflow or script for extension syntax check.
  - [x] CI workflow or script for parity/feature coverage once green.
- [x] Add release process documentation.
  - [x] Required local commands.
  - [x] Artifact cleanup rules.
  - [x] Version bump rules.
  - [x] VSIX packaging rule.
- [x] Decide license before publishing.
  - [x] Use MIT for first-party source, docs, samples, and tooling.
  - [x] Add root `LICENSE`.
  - [x] Align `vscode-semanticscript/package.json` license.
- [ ] Decide VS Code publisher/marketplace identity.
  - [ ] Replace `publisher: semanticscript-local` if publishing externally.
  - [x] Align extension version with release plan.

## P2 - Documentation Cleanup

- [x] Remove stale `experiments/` references from current docs.
  - [x] `README.md`.
  - [x] `SYNTAX.md`.
  - [x] `SemanticScript/AST.md`.
  - [x] `docs/toolchain/vscode-extension.md`.
  - [x] `SemanticScript/compiler/semsc.py` comments if they refer to deleted
        paths rather than current refined examples.
- [x] Fix stale documentation map entries.
  - [x] Replace `SemanticScript/CHANGELOG.md` with root `CHANGELOG.md`.
  - [x] Remove references to retired `experiments/whatsneeded.md`.
  - [x] Remove references to retired `experiments/refined_syntax_graph.md`.
- [x] Fix bad linter command examples.
  - [x] Replace `SemanticScript/as` with a real path such as
        `SemanticScript/sem`.
- [x] Fix grammar issues found during review.
  - [x] `An SemanticScript file` -> `A SemanticScript file`.
- [x] Update docs for recently added compiler flags.
  - [x] `--build-profile dev|prod`.
  - [x] `--runtime-checks off|traps|panic`.
  - [x] `--persist-llvm-ir auto|yes|no`.
  - [x] `SSRUN001` runtime panic output.
  - [x] `SSOK000` / `SSOK001` success output.

## P2 - Repository Hygiene

- [ ] Get to a release-clean worktree before tagging.
  - [ ] Commit or intentionally discard modified source/docs.
  - [ ] Commit or intentionally remove untracked README/doc files.
  - [x] Keep generated `.exe`, `.ll`, `__pycache__`, `todos.json`, and `.vsix`
        artifacts ignored and out of source control.
- [x] Run legacy-name scans before release.
  - [x] Confirm no `AgentScript` branding remains except the repository folder
        name or intentionally documented local paths.
  - [x] Confirm no stale `experiments/` paths remain after docs cleanup.

## P3 - Nice-To-Have Before 1.0

- [x] Add `SECURITY.md`.
- [x] Add `CONTRIBUTING.md`.
- [x] Add a top-level release checklist command block in `README.md`.
- [x] Decide whether the duplicate top-level `python/` and `samples/python/`
      folders should both remain.
- [x] Decide whether `.sem` mirror files under `SemanticScript/sem/` should be
      tracked as alias fixtures or generated artifacts.
