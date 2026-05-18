# SemanticScript Runtime

Runtime-owned native code lives here. This tree is for SemanticScript adapter
layers, not vendored third-party source.

- `native_http/` contains the first HTTP runtime bridge. It presents a stable
  C ABI for generated SemanticScript route handlers and hides the selected HTTP
  engine behind that ABI.
