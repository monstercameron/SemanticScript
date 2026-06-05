#!/usr/bin/env python3
"""R-266: GUI control handles are tombstoned when their window is destroyed.

ss_gui_window_close DestroyWindow'd the parent (Win32 auto-destroys children) but
never cleared the cached child SSGuiControlState.hwnd values, and
ensure_control_kind only checked `hwnd != NULL` — so a post-close control op
(e.g. ss_gui_list_box_append_item) SendMessageW'd a destroyed/recycled HWND.

The fix: (1) on window close/destroy, tombstone every child control (clear its
hwnd) so ensure_control_kind rejects it; (2) ensure_control_kind also calls
IsWindow, catching a window the user closed directly (WM_DESTROY) where the
tombstone did not run.

Asserted at the source level; the tombstone is also behaviorally verified
out-of-band: a harness with two controls in two windows tombstones one window and
confirms only that window's control hwnd is cleared.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = (ROOT / "semanticscript" / "runtime" / "native_win32_gui"
        / "sem_win32_gui_runtime.c").read_text(encoding="utf-8")


def test_ensure_control_kind_checks_iswindow():
    body = re.search(r"static int32_t ensure_control_kind\(.*?\n\}", _SRC, re.S).group(0)
    assert "IsWindow(control->hwnd)" in body


def test_tombstone_helper_exists_and_clears_matching_controls():
    body = re.search(r"static void tombstone_window_controls\(.*?\n\}", _SRC, re.S).group(0)
    assert ".window == window" in body
    assert ".hwnd = NULL" in body


def test_close_paths_tombstone_controls():
    # window close clears children + the window handle
    close = re.search(r"int32_t ss_gui_window_close\(SSGuiSession.*?\n\}", _SRC, re.S).group(0)
    assert "tombstone_window_controls(session, window)" in close
    assert "window->hwnd = NULL;" in close
    # the session-teardown sweep tombstones too
    destroy = re.search(r"static void destroy_remaining_windows\(.*?\n\}", _SRC, re.S).group(0)
    assert "tombstone_window_controls(session" in destroy
