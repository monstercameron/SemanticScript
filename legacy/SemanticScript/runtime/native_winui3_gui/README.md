# SemanticScript Native WinUI 3 GUI Backend

This directory is the scaffold for the future WinUI 3 backend for the existing
`standard.gui` `gui.*` API. It is not the active executable backend yet. The
current executable backend remains `SemanticScript/runtime/native_win32_gui`.

## Decision

Use the existing SemanticScript-owned C ABI from
`SemanticScript/runtime/native_win32_gui/sem_win32_gui_runtime.h`. The compiler
should keep lowering `gui.*` calls exactly once, then select either a classic
Win32 implementation or a WinUI 3 implementation at native-link time.

The WinUI 3 backend should be implemented as a C++/WinRT adapter that exports
the same `ss_gui_*` symbols. SemanticScript-generated code should not know about
XAML, COM apartments, Windows App SDK bootstrapper calls, or WinUI control
classes.

Do not add C# / XAML application sidecars under `apps/` as the WinUI path. App
UI must remain authored in SemanticScript (`standard.gui` `gui.*` calls), with
WinUI hidden behind the selected native backend.

## Researched Requirements

Primary Microsoft docs establish these constraints:

- WinUI 3 is the Windows App SDK modern native UI framework for desktop apps.
- WinUI 3 targets Windows 10 version 1809, build 17763, and later, including
  Windows 11.
- Supported app languages are C# and C++; a native SemanticScript backend should
  use C++/WinRT so it can export the C ABI used by generated LLVM/native code.
- Development requires Visual Studio with the WinUI / Windows App SDK workloads.
- C++ development requires the C++ WinUI app development tools.
- Developer Mode must be enabled for normal local build/deploy/test workflows.
- Unpackaged apps using Windows App SDK must initialize the Windows App SDK
  runtime before using WinUI. The explicit C/C++ path is the bootstrapper API:
  `MddBootstrapInitialize`, `MddBootstrapInitialize2`, and
  `MddBootstrapShutdown` from `mddbootstrap.h`.
- Unpackaged apps are responsible for Windows App SDK runtime deployment. The
  runtime can be installed by `WindowsAppRuntimeInstall.exe --quiet` or by
  deploying the required MSIX packages directly.
- Unpackaged apps also require the Visual C++ Redistributable on target
  machines.
- Microsoft recommends deploying `.winmd` metadata files with apps that use the
  Windows App SDK runtime.

## Backend Shape

The adapter should own these platform details:

- Start the UI thread and initialize the COM apartment.
- Initialize and shut down the Windows App SDK bootstrapper for unpackaged mode,
  unless the selected packaging mode provides auto-initialization.
- Create a WinUI `Application` and `Window`.
- Map `SSGuiApplicationConfig`, `SSGuiWindowConfig`, and `SSGuiControlConfig` to
  WinUI objects.
- Store `SSGuiSession` and `SSGuiEvent` state behind opaque pointers.
- Dispatch WinUI events to `SSGuiHandler` function pointers.
- Convert all C ABI strings between UTF-8 and WinRT `hstring`.
- Keep SemanticScript handlers on the UI thread unless a future cross-thread
  dispatch ABI is added.

Initial control mapping:

| SemanticScript kind | WinUI 3 control |
| --- | --- |
| `SS_GUI_CONTROL_TEXT_LABEL` | `Microsoft.UI.Xaml.Controls.TextBlock` |
| `SS_GUI_CONTROL_TEXT_BOX` | `Microsoft.UI.Xaml.Controls.TextBox` |
| `SS_GUI_CONTROL_BUTTON` | `Microsoft.UI.Xaml.Controls.Button` |
| `SS_GUI_CONTROL_CHECK_BOX` | `Microsoft.UI.Xaml.Controls.CheckBox` |
| `SS_GUI_CONTROL_LIST_BOX` | `Microsoft.UI.Xaml.Controls.ListView` or `ListBox` |

Initial layout mapping:

| SemanticScript layout | WinUI 3 layout |
| --- | --- |
| `verticalStack` | `StackPanel` with vertical orientation |
| `horizontalStack` | `StackPanel` with horizontal orientation |
| `grid` | Explicitly reject until the grid row/column API is designed |
| `absolute` | Explicitly reject until coordinate semantics are designed |

## Compiler Integration Needed

The current `--emit-exe` path invokes `clang` directly with generated LLVM IR
and C runtime sources. That is enough for raw Win32 C, but not enough for an
honest WinUI 3 backend.

Needed compiler/build work:

- `guiBackend PROJECT win32|winui3` exists and defaults to `win32`; `winui3`
  currently fails with a compiler diagnostic until this backend is buildable.
- Add an MSBuild/C++ path, or a CMake+NuGet path, that can consume Windows App
  SDK packages and compile C++/WinRT sources.
- Preserve the generated SemanticScript code as normal native code, but link it
  with the C++/WinRT adapter instead of the C Win32 adapter.
- Decide deployment mode: packaged MSIX, packaged with external location, or
  unpackaged plus bootstrapper.
- Emit or generate the required app manifest and package metadata for the chosen
  deployment mode.
- Once the adapter exists, refine diagnostics so `guiBackend winui3` reports
  exactly which Windows App SDK tooling or runtime deployment prerequisite is
  missing.

## First Implementation Slice

The first useful implementation should run the current hello GUI sample with
real WinUI controls while leaving `apps/desktop-window-smoke/main.sem` as the
only app UI source:

- one `Window` titled from `gui.windowCreate`;
- a vertical `StackPanel` content root;
- `TextBlock`, `TextBox`, `Button`, `ListView`, and status `TextBlock`;
- button click and text-box enter dispatch to `SSGuiHandler`;
- `ss_gui_text_box_text`, `ss_gui_text_box_set_text`,
  `ss_gui_list_box_append_item`, `ss_gui_list_box_clear`, and
  `ss_gui_text_label_set_text_by_handle` implemented against WinUI controls.

Do not introduce a second public GUI API for WinUI. The backend exists to make
the current `standard.gui` surface look and behave like native Windows 11 UI,
not to move app code into a C# or XAML project.
