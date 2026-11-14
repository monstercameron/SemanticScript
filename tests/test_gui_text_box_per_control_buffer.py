#!/usr/bin/env python3
"""R-265: ss_gui_text_box_text returns a per-control buffer (no use-after-free).

The function returned session->text_buffer — a single SHARED buffer that
replace_session_text_buffer grew via realloc. So reading any text box could move
that buffer, dangling the pointer a prior read of a DIFFERENT box had returned
(use-after-free). Each control now owns its text buffer (freed with the control
array), so a returned pointer stays valid until that same box is read again.

Asserted at the source level (matching the other sem_win32_gui_runtime.c review);
the fix is also behaviorally verified out-of-band: a harness reads box A, then
reads box B with a longer value (which reallocs B's buffer), and confirms box A's
pointer and content are unchanged and the two buffers are independent.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SRC = (ROOT / "semanticscript" / "runtime" / "native_win32_gui"
        / "sem_win32_gui_runtime.c").read_text(encoding="utf-8")


def test_control_struct_owns_text_buffer():
    m = re.search(r"struct SSGuiControlState \{.*?\};", _SRC, re.S)
    assert m and "char *text_buffer;" in m.group(0)
    assert "size_t text_buffer_capacity;" in m.group(0)


def test_session_no_longer_holds_shared_text_buffer():
    m = re.search(r"struct SSGuiSession \{.*?\};", _SRC, re.S)
    assert m and "text_buffer" not in m.group(0), "session must not keep a shared buffer"


def test_text_box_text_returns_control_buffer():
    body = re.search(r"const char \*ss_gui_text_box_text\(.*?\n\}", _SRC, re.S).group(0)
    assert "replace_control_text_buffer(control" in body
    assert "return control->text_buffer;" in body
    assert "session->text_buffer" not in body


def test_control_buffers_freed_on_cleanup():
    # each control's buffer is freed before the control array block
    assert re.search(r"free\(session\.controls\[\w+\]\.text_buffer\)", _SRC)
