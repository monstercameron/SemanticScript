# SemanticScript Runtime

Runtime-owned native code lives here. This tree is for SemanticScript adapter
layers, not vendored third-party source.

- `native_http/` contains the first HTTP runtime bridge. It presents a stable
  C ABI for generated SemanticScript route handlers and hides the selected HTTP
  engine behind that ABI.
- `native_sqlite/` contains the embedded SQLite runtime ABI surface. It keeps
  generated SemanticScript callers isolated from the vendored SQLite header and
  implementation details.
- `native_win32_gui/` contains the initial desktop GUI runtime adapter. It
  exposes a small backend-neutral `ss_gui_*` C ABI over lowered application,
  window, control, and event-edge config tables, with HWND details kept inside
  the Win32 implementation.
