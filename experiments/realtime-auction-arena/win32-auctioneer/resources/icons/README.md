Icon placeholder
================

The Win32 auctioneer console will eventually carry a dedicated icon group for:

- executable icon;
- taskbar/window icon;
- small title-bar icon.

No binary icon is committed yet because the current SemanticScript GUI/runtime
path does not expose per-project resource embedding. When that lands, add the
`.ico` here and wire it through the build/resource plan.
