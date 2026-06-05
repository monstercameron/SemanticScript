import importlib

semanticscript = importlib.import_module("semanticscript")


def _ir(src: str) -> str:
    return str(semanticscript.lower_to_llvm(semanticscript.parse(src)))


_HEAD = (
    "P is project\nP module m\nP target console\nP entry main\n"
    "m is module\nm path a.b\nm exports main\n"
    "ExitCode is alias\nExitCode for Int32\n"
    "ByteCount is alias\nByteCount for Int64\n"
    "EventStreamHandle is alias\nEventStreamHandle for OpaquePointer\n"
    "EventQueueCapacity is alias\nEventQueueCapacity for Int64\n"
    "EventError is error\n"
    "GuiWindow is alias\nGuiWindow for OpaquePointer\n"
    "GuiControl is alias\nGuiControl for OpaquePointer\n"
    "GuiError is error\n"
    "AllocError is error\n"
)


def test_event_open_catch_wires_zero_handle_error():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let name immutable String \"events\"\n"
        "main let cap immutable EventQueueCapacity 4\n"
        "main let ok immutable ExitCode 0\nmain let failed immutable ExitCode 7\n"
        "main do openIt\nmain branch ifError openIt goto bad\nmain return ok\n"
        "main at bad return failed\n"
        "openIt is call\nopenIt in main\nopenIt invokes event.openProcessStream\n"
        "openIt arg streamName String name\n"
        "openIt arg queueCapacity EventQueueCapacity cap\n"
        "openIt out stream EventStreamHandle\n"
        "openIt catch eventErr EventError\n"
    )
    ir = _ir(src)
    assert "ss_event_open_stream" in ir
    assert "icmp eq i64" in ir
    assert "br i1 false" not in ir


def test_gui_status_catch_wires_nonzero_status_error():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let window immutable GuiWindow 1\n"
        "main let control immutable GuiControl 2\n"
        "main let ok immutable ExitCode 0\nmain let failed immutable ExitCode 7\n"
        "main do attach\nmain branch ifError attach goto bad\nmain return ok\n"
        "main at bad return failed\n"
        "attach is call\nattach in main\nattach invokes gui.windowAddControl\n"
        "attach arg window GuiWindow window\n"
        "attach arg control GuiControl control\n"
        "attach out status Int32\n"
        "attach catch guiErr GuiError\n"
    )
    ir = _ir(src)
    assert "ss_widget_window_add_control" in ir
    assert "icmp ne i32" in ir
    assert "br i1 false" not in ir


def test_libc_null_return_catch_wires_zero_error():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let size immutable ByteCount 16\n"
        "main let ok immutable ExitCode 0\nmain let failed immutable ExitCode 7\n"
        "main do alloc\nmain branch ifError alloc goto bad\nmain return ok\n"
        "main at bad return failed\n"
        "alloc is call\nalloc in main\nalloc invokes c.malloc\n"
        "alloc arg size ByteCount size\n"
        "alloc out ptr OpaquePointer\n"
        "alloc catch allocErr AllocError\n"
    )
    ir = _ir(src)
    assert "ss_c_malloc" in ir
    assert "icmp eq i64" in ir
    assert "br i1 false" not in ir


def test_libc_negative_status_catch_wires_less_than_zero_error():
    src = _HEAD + (
        "main is operation\nmain out ExitCode\nmain async no\n"
        "main let text immutable String \"hello\"\n"
        "main let ok immutable ExitCode 0\nmain let failed immutable ExitCode 7\n"
        "main do writeIt\nmain branch ifError writeIt goto bad\nmain return ok\n"
        "main at bad return failed\n"
        "writeIt is call\nwriteIt in main\nwriteIt invokes c.puts\n"
        "writeIt arg text String text\n"
        "writeIt out status Int32\n"
        "writeIt catch writeErr AllocError\n"
    )
    ir = _ir(src)
    assert "ss_c_puts" in ir
    assert "icmp slt i32" in ir
    assert "br i1 false" not in ir
