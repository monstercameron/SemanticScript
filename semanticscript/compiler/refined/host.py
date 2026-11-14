"""Host library targets: the standard-library calls the backend hands to the runtime.

Compiled code reaches every target here through one callback, `refined_host`
(see `runtime._host` and `codegen.OpGen.host_call`). Arguments arrive as one
tuple of 64-bit slots per parameter, flattened from the parameter's machine
type: an integer or `Bool` is one slot, a `String` or `Bytes` is (pointer,
length), an enum is (tag, payload), a record is its fields in order, a region
or handle is one slot. A handler returns `ok(*slots)` with the result flattened
the same way, or `fail(<error enum>, <variant>, payload)`.

Tasks run in parallel on their own threads (tasks.py). A channel send or
receive, and a sleep, wait through the scheduler: they end early with
`cancelled` when the task is cancelled, and a wait that nothing can ever end
traps as a deadlock. Accepting and reading sockets wake every tenth of a second
to notice cancellation.

Handles (files, sockets, maps, sets, channels, buffers, argument lists,
responses) are small integers into one table. A handle created in a region is
dropped when the region is released; using a dropped handle traps.
"""
from __future__ import annotations

import ctypes
import os
import socket
import subprocess
import time
from collections import deque
from typing import Callable

from . import runtime as rt
from . import tasks
from .library import LIBRARY

HANDLERS: dict[str, Callable] = {}
NEVER = -1


def target(*names: str):
    def register(fn):
        for n in names:
            HANDLERS[n] = fn
        return fn
    return register


class Fail(Exception):
    def __init__(self, enum: str, variant: str, payload: int = 0):
        mod, name = enum.split(".")
        variants = [v for v, _p in LIBRARY[mod]["types"][name].variants]
        self.status, self.payload = variants.index(variant) + 1, payload


def ok(*slots: int) -> tuple[int, tuple, int]:
    return 0, slots, 0


def fail(enum: str, variant: str, payload: int = 0):
    raise Fail(enum, variant, payload)


# ---------------------------------------------------------------- slots and handles

def data(p: tuple) -> bytes:
    return rt._bytes(p[0], p[1])


def text(p: tuple) -> str:
    return data(p).decode("utf-8", "replace")


def put(region: int, payload: bytes) -> tuple[int, int]:
    """Copy bytes into a region; the (pointer, length) of the copy."""
    return rt._region_copy(region, payload), len(payload)


_objects: dict[int, object] = {}
_next = [1]


def new_handle(obj: object, region: int | None = None) -> int:
    h = _next[0]
    _next[0] += 1
    _objects[h] = obj
    if region is not None:
        rt.region_owns(region, h)
    return h


def get(h: int, kind: type):
    obj = _objects.get(h)
    if not isinstance(obj, kind):
        rt._trap_now(f"a {kind.__name__} handle was used after it was closed or its region was released")
    return obj


def drop(h: int) -> None:
    _objects.pop(h, None)


def now_ms() -> int:
    return time.monotonic_ns() // 1_000_000


def seconds_left(deadline: int) -> float | None:
    """None for no deadline; otherwise the seconds left, never negative."""
    if deadline == NEVER:
        return None
    return max(0.0, (deadline - now_ms()) / 1000.0)


# ---------------------------------------------------------------- time and clock

@target("time.Deadline.never")
def _never(_p):
    return ok(NEVER)


@target("time.Deadline.after")
def _after(p):
    return ok(now_ms() + max(0, p[0][0]))


@target("time.sleep")
def _sleep(p):
    tasks.sleep(max(0, p[0][0]) / 1000.0)
    return ok()


@target("clock.now")
def _now(_p):
    return ok(time.time_ns() // 1_000_000)


@target("clock.monotonic")
def _monotonic(_p):
    return ok(now_ms())


# ---------------------------------------------------------------- console, environment, process

@target("console.readLine")
def _read_line(p):
    region, limit, _deadline = p[0][0], p[1][0], p[2][0]
    line = rt.read_stdin_line(limit + 2)
    if line is None:
        fail("console.ReadError", "endOfInput")
    if line.endswith(b"\n"):
        line = line[:-1]
    if line.endswith(b"\r"):
        line = line[:-1]
    if len(line) > limit:
        fail("console.ReadError", "tooLong")
    return ok(*put(region, line))


@target("environment.get")
def _env_get(p):
    value = os.environ.get(text(p[0]))
    if value is None:
        fail("environment.MissingError", "missing")
    return ok(*put(p[1][0], value.encode("utf-8", "surrogateescape")))


@target("process.argumentCount")
def _arg_count(_p):
    return ok(len(rt.PROGRAM_ARGUMENTS))


@target("process.argument")
def _argument(p):
    index = p[0][0]
    if not 0 <= index < len(rt.PROGRAM_ARGUMENTS):
        fail("process.ArgumentError", "outOfRange", index)
    return ok(*put(p[1][0], rt.PROGRAM_ARGUMENTS[index].encode("utf-8", "surrogateescape")))


class Arguments(list):
    pass


@target("process.newArguments")
def _new_arguments(p):
    return ok(new_handle(Arguments(), p[0][0]))


@target("process.addArgument")
def _add_argument(p):
    get(p[0][0], Arguments).append(text(p[1]))
    return ok()


@target("process.run")
def _run(p):
    program, arguments, deadline = text(p[0]), get(p[1][0], Arguments), p[2][0]
    rt.flush_output()
    try:
        proc = subprocess.run([program, *arguments], timeout=seconds_left(deadline))
    except FileNotFoundError:
        fail("process.RunError", "notFound")
    except subprocess.TimeoutExpired:
        fail("process.RunError", "timedOut")
    except OSError as exc:
        fail("process.RunError", "failed", exc.errno or 1)
    return ok(proc.returncode)


# ---------------------------------------------------------------- files

class File:
    def __init__(self, fh):
        self.fh = fh


def _file_error(exc: OSError):
    if isinstance(exc, FileNotFoundError):
        fail("fs.FileError", "notFound")
    if isinstance(exc, PermissionError):
        fail("fs.FileError", "denied")
    if isinstance(exc, FileExistsError):
        fail("fs.FileError", "exists")
    fail("fs.FileError", "failed", exc.errno or 1)


def _open(path: str, mode: str) -> tuple:
    try:
        if mode == "r+b" and not os.path.isfile(path):
            raise FileNotFoundError(path)
        fh = open(path, mode)
        if mode == "r+b":
            fh.truncate(0)
    except OSError as exc:
        _file_error(exc)
    return ok(new_handle(File(fh)))


@target("fs.openRead")
def _open_read(p):
    return _open(text(p[0]), "rb")


@target("fs.openWrite")
def _open_write(p):
    return _open(text(p[0]), "r+b")


@target("fs.create")
def _create(p):
    return _open(text(p[0]), "xb")


@target("fs.openAppend")
def _open_append(p):
    """Open for writing at the end, creating the file if it is missing."""
    return _open(text(p[0]), "ab")


@target("fs.createDirectory")
def _make_directory(p):
    try:
        os.mkdir(text(p[0]))
    except OSError as exc:
        _file_error(exc)
    return ok()


@target("fs.removeDirectory")
def _remove_directory(p):
    try:
        os.rmdir(text(p[0]))
    except OSError as exc:
        _file_error(exc)
    return ok()


class Listing(list):
    pass


@target("fs.listDirectory")
def _list_directory(p):
    try:
        names = sorted(os.listdir(text(p[0])))
    except OSError as exc:
        _file_error(exc)
    return ok(new_handle(Listing(n.encode("utf-8", "surrogateescape") for n in names), p[1][0]))


@target("fs.entryCount")
def _entry_count(p):
    return ok(len(get(p[0][0], Listing)))


@target("fs.entryName")
def _entry_name(p):
    listing, index, region = get(p[0][0], Listing), p[1][0], p[2][0]
    if not 0 <= index < len(listing):
        fail("fs.EntryIndexError", "outOfRange", index)
    return ok(*put(region, listing[index]))


@target("fs.read")
def _fs_read(p):
    f = get(p[0][0], File)
    try:
        chunk = f.fh.read(max(0, p[2][0]))
    except OSError as exc:
        _file_error(exc)
    return ok(*put(p[1][0], chunk))


@target("fs.write")
def _fs_write(p):
    f = get(p[0][0], File)
    try:
        f.fh.write(data(p[1]))
        f.fh.flush()
    except OSError as exc:
        _file_error(exc)
    return ok()


@target("fs.close")
def _fs_close(p):
    f = get(p[0][0], File)
    drop(p[0][0])
    try:
        f.fh.close()
    except OSError as exc:
        _file_error(exc)
    return ok()


@target("fs.exists")
def _exists(p):
    return ok(1 if os.path.exists(text(p[0])) else 0)


@target("fs.remove")
def _remove(p):
    try:
        os.remove(text(p[0]))
    except OSError as exc:
        _file_error(exc)
    return ok()


@target("fs.readAll")
def _read_all(p):
    path, region, limit = text(p[0]), p[1][0], p[2][0]
    try:
        with open(path, "rb") as fh:
            content = fh.read(limit + 1)
    except OSError as exc:
        _file_error(exc)
    if len(content) > limit:
        fail("fs.FileError", "tooLarge")
    return ok(*put(region, content))


@target("fs.writeAll")
def _write_all(p):
    try:
        with open(text(p[0]), "wb") as fh:
            fh.write(data(p[1]))
    except OSError as exc:
        _file_error(exc)
    return ok()


# ---------------------------------------------------------------- network

class Listener:
    def __init__(self, sock):
        self.sock = sock


class Connection:
    def __init__(self, sock):
        self.sock = sock


def _net_error(exc: OSError):
    if isinstance(exc, socket.timeout):
        fail("net.NetError", "timedOut")
    if isinstance(exc, ConnectionRefusedError):
        fail("net.NetError", "refused")
    if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
        fail("net.NetError", "closed")
    fail("net.NetError", "failed", exc.errno or 1)


@target("net.listen")
def _listen(p):
    port, host = p[0][0], text(p[1]) or "127.0.0.1"
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(128)
    except OSError as exc:
        _net_error(exc)
    return ok(new_handle(Listener(sock)))


@target("net.closeListener")
def _close_listener(p):
    lst = get(p[0][0], Listener)
    drop(p[0][0])
    lst.sock.close()
    return ok()


def _until_ready(sock, deadline: int, call):
    """Run a blocking socket call in short slices, so a cancelled task stops and a deadline holds."""
    while True:
        if tasks.cancelled():
            fail("net.NetError", "cancelled")
        left = seconds_left(deadline)
        if left is not None and left <= 0:
            fail("net.NetError", "timedOut")
        sock.settimeout(0.1 if left is None else min(0.1, left))
        try:
            return call()
        except socket.timeout:
            continue
        except OSError as exc:
            _net_error(exc)


@target("net.accept")
def _accept(p):
    lst, deadline = get(p[0][0], Listener), p[1][0]
    conn, _addr = _until_ready(lst.sock, deadline, lst.sock.accept)
    conn.settimeout(None)
    return ok(new_handle(Connection(conn)))


@target("net.connect")
def _connect(p):
    address, deadline = text(p[0]), p[1][0]
    host, _, port = address.rpartition(":")
    try:
        sock = socket.create_connection((host, int(port)), timeout=seconds_left(deadline))
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError):
            fail("net.NetError", "failed", 22)
        _net_error(exc)
    sock.settimeout(None)
    return ok(new_handle(Connection(sock)))


@target("net.read")
def _net_read(p):
    conn, region, limit, deadline = get(p[0][0], Connection), p[1][0], p[2][0], p[3][0]
    chunk = _until_ready(conn.sock, deadline, lambda: conn.sock.recv(max(1, limit)))
    if not chunk:
        fail("net.NetError", "closed")
    return ok(*put(region, chunk))


@target("net.write")
def _net_write(p):
    conn, payload, deadline = get(p[0][0], Connection), data(p[1]), p[2][0]
    conn.sock.settimeout(seconds_left(deadline))
    try:
        conn.sock.sendall(payload)
    except OSError as exc:
        _net_error(exc)
    return ok()


@target("net.close")
def _net_close(p):
    conn = get(p[0][0], Connection)
    drop(p[0][0])
    try:
        conn.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    conn.sock.close()
    return ok()


# ---------------------------------------------------------------- http

_METHODS = [m for m, _p in LIBRARY["http"]["types"]["HttpMethod"].variants]
_headers: dict[int, dict[str, tuple[int, int]]] = {}  # path pointer of a parsed request -> its headers


class Response:
    def __init__(self, status: int, body: bytes):
        self.status, self.body = status, body


_REASONS = {200: "OK", 201: "Created", 204: "No Content", 400: "Bad Request", 404: "Not Found",
            405: "Method Not Allowed", 500: "Internal Server Error"}


@target("http.parseRequest")
def _parse_request(p):
    raw, region = data(p[0]), p[1][0]
    head, sep, _body = raw.partition(b"\r\n\r\n")
    if not sep:
        head, sep, _body = raw.partition(b"\n\n")
    lines = head.replace(b"\r\n", b"\n").split(b"\n")
    parts = lines[0].split(b" ") if lines and lines[0] else []
    if len(parts) != 3 or not parts[2].startswith(b"HTTP/") or not parts[1].startswith(b"/"):
        fail("http.HttpParseError", "malformed")
    method = parts[0].decode("ascii", "replace").lower()
    if method not in _METHODS:
        fail("http.HttpParseError", "malformed")
    path_ptr, path_len = put(region, parts[1])
    headers = {}
    for line in lines[1:]:
        name, colon, value = line.partition(b":")
        if not colon:
            fail("http.HttpParseError", "malformed")
        headers[name.strip().lower().decode("ascii", "replace")] = put(region, value.strip())
    _headers[path_ptr] = headers
    return ok(_METHODS.index(method), 0, path_ptr, path_len)


@target("http.header")
def _header(p):
    request, name = p[0], text(p[1]).lower()
    found = _headers.get(request[2], {}).get(name)
    if found is None:
        fail("string.NotFound", "absent")
    return ok(*found)


@target("http.response")
def _response(p):
    return ok(new_handle(Response(p[0][0], data(p[1])), p[2][0]))


@target("http.serializeResponse")
def _serialize(p):
    r = get(p[0][0], Response)
    head = (f"HTTP/1.1 {r.status} {_REASONS.get(r.status, 'Status')}\r\nContent-Type: text/plain; charset=utf-8\r\n"
            f"Content-Length: {len(r.body)}\r\nConnection: close\r\n\r\n").encode("ascii")
    return ok(*put(p[1][0], head + r.body))


# ---------------------------------------------------------------- byte buffers and text

class Buffer:
    def __init__(self):
        self.data = bytearray()
        self.kept: list = []  # copies handed out by toBytes stay alive with the buffer


@target("buffer.new")
def _buffer_new(p):
    return ok(new_handle(Buffer(), p[0][0]))


@target("buffer.appendString")
def _append_string(p):
    get(p[0][0], Buffer).data += data(p[1])
    return ok()


@target("buffer.appendByte")
def _append_byte(p):
    get(p[0][0], Buffer).data.append(p[1][0] & 0xFF)
    return ok()


@target("buffer.appendInt64")
def _append_int(p):
    get(p[0][0], Buffer).data += str(p[1][0]).encode()
    return ok()


@target("buffer.length")
def _buffer_length(p):
    return ok(len(get(p[0][0], Buffer).data))


def _utf8(raw: bytes) -> None:
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        fail("string.Utf8Error", "invalidAt", exc.start)


@target("buffer.toString")
def _buffer_string(p):
    raw = bytes(get(p[0][0], Buffer).data)
    _utf8(raw)
    return ok(*put(p[1][0], raw))


@target("buffer.toBytes")
def _buffer_bytes(p):
    buf = get(p[0][0], Buffer)
    copy = ctypes.create_string_buffer(bytes(buf.data), max(len(buf.data), 1))
    buf.kept.append(copy)
    return ok(ctypes.addressof(copy), len(buf.data))


@target("string.fromBytes")
def _from_bytes(p):
    raw = data(p[0])
    _utf8(raw)
    return ok(*put(p[1][0], raw))


# ---------------------------------------------------------------- maps, sets, channels

class Map(dict):
    pass


class Set(set):
    pass


class Channel:
    def __init__(self, capacity: int):
        self.capacity, self.items, self.closed = capacity, deque(), False


@target("map.Map.new")
def _map_new(p):
    return ok(new_handle(Map(), p[0][0]))


@target("map.Map.put")
def _map_put(p):
    get(p[0][0], Map)[p[1]] = p[2]
    return ok()


@target("map.Map.get")
def _map_get(p):
    m = get(p[0][0], Map)
    if p[1] not in m:
        fail("map.KeyMissing", "missing")
    return ok(*m[p[1]])


@target("map.Map.contains")
def _map_contains(p):
    return ok(1 if p[1] in get(p[0][0], Map) else 0)


@target("map.Map.remove")
def _map_remove(p):
    m = get(p[0][0], Map)
    if p[1] not in m:
        fail("map.KeyMissing", "missing")
    del m[p[1]]
    return ok()


@target("map.Map.length")
def _map_length(p):
    return ok(len(get(p[0][0], Map)))


@target("set.Set.new")
def _set_new(p):
    return ok(new_handle(Set(), p[0][0]))


@target("set.Set.add")
def _set_add(p):
    get(p[0][0], Set).add(p[1])
    return ok()


@target("set.Set.contains")
def _set_contains(p):
    return ok(1 if p[1] in get(p[0][0], Set) else 0)


@target("set.Set.remove")
def _set_remove(p):
    get(p[0][0], Set).discard(p[1])
    return ok()


@target("set.Set.length")
def _set_length(p):
    return ok(len(get(p[0][0], Set)))


@target("channel.Channel.new")
def _channel_new(p):
    if p[0][0] < 1:
        rt._trap_now(f"a channel needs a capacity of at least 1, not {p[0][0]}")
    return ok(new_handle(Channel(p[0][0]), p[1][0]))


def _channel_wait(ready, deadline: int, what: str) -> None:
    left = seconds_left(deadline)
    outcome = tasks.wait_until(ready, None if left is None else time.monotonic() + left, what)
    if outcome == "cancelled":
        fail("channel.ChannelError", "cancelled")
    if outcome == "timedOut":
        fail("channel.ChannelError", "timedOut")


@target("channel.Channel.send")
def _channel_send(p):
    ch = get(p[0][0], Channel)
    _channel_wait(lambda: ch.closed or len(ch.items) < ch.capacity, p[2][0], "a send waits on a full channel")
    if ch.closed:
        fail("channel.ChannelError", "closed")
    ch.items.append(p[1])
    tasks.notify()
    return ok()


@target("channel.Channel.receive")
def _channel_receive(p):
    ch = get(p[0][0], Channel)
    _channel_wait(lambda: ch.closed or bool(ch.items), p[1][0], "a receive waits on an empty channel")
    if ch.items:
        item = ch.items.popleft()
        tasks.notify()
        return ok(*item)
    fail("channel.ChannelError", "closed")


@target("channel.Channel.close")
def _channel_close(p):
    get(p[0][0], Channel).closed = True
    tasks.notify()
    return ok()


def dispatch(name: str, params: list[tuple]) -> tuple[int, tuple, int]:
    handler = HANDLERS.get(name)
    if handler is None:
        rt._trap_now(f"the runtime has no implementation of `{name}`")
    try:
        return handler(params)
    except Fail as f:
        return f.status, (), f.payload

