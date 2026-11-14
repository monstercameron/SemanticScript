"""Standard library signatures (LR-40) for the refined checker.

Each target states its parameters with modes, its output and who owns it, its
error enum, its effects, whether it waits, which parameter its result is a view
of, and which parameter is checked against a capability scope. The checker reads
only this table, so a call can be checked without the library's source.

The table covers the modules LR-40 rule 3 lists. Each module moves to
SemanticScript source and publishes its own signatures as the library is
rewritten (plan step 14).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    mode: str  # value | borrowed | borrowedMutable | owned


@dataclass(frozen=True)
class Sig:
    inputs: tuple[Param, ...]
    output: Optional[str] = None
    output_owner: Optional[str] = None  # None, "caller", or the name of a Region parameter
    raises: Optional[str] = None
    effects: frozenset = frozenset()  # {(verb, resource)}
    waits: bool = False
    borrows: Optional[str] = None  # parameter whose value the result is a view of
    scoped: Optional[str] = None  # parameter whose literal value must fall inside the capability's scope


@dataclass
class TypeInfo:
    name: str  # canonical: builtin name or "module.Type"
    kind: str  # builtin | record | enum | opaque | resource | generic | instance | alias | operationType | typeParam
    plain: Optional[bool] = None  # None: computed from contents
    fields: list[tuple[str, str]] = field(default_factory=list)
    variants: list[tuple[str, Optional[str]]] = field(default_factory=list)
    targets: dict[str, Sig] = field(default_factory=dict)
    type_params: list[str] = field(default_factory=list)
    generic: Optional[str] = None  # for instances: canonical generic name
    args: list[str] = field(default_factory=list)  # for instances: type arguments
    sig: Optional[Sig] = None  # for operationType
    base: Optional[str] = None  # for alias


def P(name: str, type_: str, mode: str) -> Param:
    return Param(name, type_, mode)


def E(*pairs: str) -> frozenset:
    return frozenset(tuple(p.split(" ")) for p in pairs)


BUILTINS = {
    **{t: TypeInfo(t, "builtin", True) for t in
       ("Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64",
        "Float32", "Float64", "Bool", "Byte", "ExitCode", "Region")},
    "String": TypeInfo("String", "builtin", False),
    "Bytes": TypeInfo("Bytes", "builtin", False),
}
INTEGER_RANGES = {
    "Int8": (-2**7, 2**7 - 1), "Int16": (-2**15, 2**15 - 1), "Int32": (-2**31, 2**31 - 1),
    "Int64": (-2**63, 2**63 - 1), "UInt8": (0, 2**8 - 1), "UInt16": (0, 2**16 - 1),
    "UInt32": (0, 2**32 - 1), "UInt64": (0, 2**64 - 1), "Byte": (0, 255),
    "ExitCode": (0, 255),  # what every platform delivers to the parent process
}
FLOAT_TYPES = {"Float32", "Float64"}

# LR-34 rule 5: resources whose capability must state a scope, and how a literal
# argument is compared with it. Every other resource takes `scope none`.
SCOPED_RESOURCES = {
    "net.tcp": "port",  # scope "<address>:<port>"; the literal is the port
    "net.outbound": "prefix",  # scope "<host>:<port>" prefix; the literal is the address
    "fs.files": "prefix",  # scope is a directory prefix; the literal path starts with it
    "process.programs": "exact",  # scope is the program name; the literal equals it
    "ffi.libraries": "exact",  # scope is the shared library's name; the literal equals it
    "ffi.symbols": "exact",  # scope is one C symbol's name: each foreign function is granted by name (D-41)
}


def path_within(path: str, scope: str, resolve: bool) -> bool:
    """D-41: an `fs.files` scope is a directory (`"data/"`: anything inside it) or a name pattern
    (`"suite-*"`: entries of that directory whose name starts with `suite-`). `resolve` follows `..` and
    links (at run time); without it the path is normalized as written (at check time)."""
    import os
    if not scope.endswith(("/", "*")):
        return False
    norm = (lambda p: os.path.normcase(os.path.realpath(p))) if resolve else \
        (lambda p: os.path.normcase(os.path.abspath(os.path.normpath(p))))
    real = norm(path)
    if scope.endswith("/"):
        base = norm(scope[:-1] or ".")
        return real == base or real.startswith(base.rstrip(os.sep) + os.sep)
    head, tail = os.path.split(scope[:-1])
    base = norm(head or ".")
    if not real.startswith(base.rstrip(os.sep) + os.sep):
        return False
    first = real[len(base.rstrip(os.sep)) + 1:].split(os.sep)[0]
    return first.startswith(os.path.normcase(tail))


def scope_within(resource: str, inner: str, outer: str) -> bool:
    """Whether a capability's scope `inner` is covered by the project's allowed scope `outer`."""
    kind = SCOPED_RESOURCES.get(resource)
    if kind is None:
        return True
    if inner == outer:
        return True
    if resource == "fs.files":
        if outer.endswith("/"):
            return path_within(inner.rstrip("/*") or ".", outer, resolve=False)
        return inner.endswith("*") and inner[:-1].startswith(outer[:-1]) and "/" not in inner[len(outer) - 1:]
    if resource == "net.outbound":
        return inner.startswith(outer) and (outer.endswith((":", "/")) or inner[len(outer)] in ":/")
    return False

# Types that may cross the foreign function interface: numbers and `Bool`, passed by the C ABI as is.
FOREIGN_TYPES = {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64", "Byte", "Float64", "Bool"}


def _bin(t: str, out: str) -> Sig:
    return Sig((P("left", t, "value"), P("right", t, "value")), out)


def _un(t: str, out: str) -> Sig:
    return Sig((P("value", t, "value"),), out)


def _compare(t: str) -> dict:
    names = ("equal", "notEqual", "lessThan", "lessOrEqual", "greaterThan", "greaterOrEqual")
    return {f"{n}{t}": _bin(t, "Bool") for n in names}


def _generic(name: str, params: list[str], plain: Optional[bool] = False, variants=None) -> TypeInfo:
    return TypeInfo(name, "generic", plain, type_params=params, variants=variants or [])


def _err(name: str, *variants: tuple) -> TypeInfo:
    return TypeInfo(name, "enum", True, variants=list(variants))


_W = E("write console.stdout")
_RG = P("region", "Region", "borrowed")
_DL = P("deadline", "time.Deadline", "value")

LIBRARY: dict[str, dict] = {
    "console": {
        "types": {
            "WriteError": _err("console.WriteError", ("failed", "Int32")),
            "ReadError": _err("console.ReadError", ("endOfInput", None), ("tooLong", None), ("timedOut", None),
                              ("cancelled", None), ("failed", "Int32")),
        },
        "targets": {
            "writeLine": Sig((P("text", "String", "borrowed"),), raises="console.WriteError", effects=_W),
            "write": Sig((P("text", "String", "borrowed"),), raises="console.WriteError", effects=_W),
            "writeIntegerLine": Sig((P("value", "Int64", "value"),), raises="console.WriteError", effects=_W),
            "writeFloatLine": Sig((P("value", "Float64", "value"),), raises="console.WriteError", effects=_W),
            "writeError": Sig((P("text", "String", "borrowed"),), raises="console.WriteError",
                              effects=E("write console.stderr")),
            "readLine": Sig((_RG, P("maxBytes", "Int64", "value"), _DL), "String", "region", "console.ReadError",
                            E("read console.stdin"), waits=True),
        },
    },
    "math": {
        "types": {},
        "targets": {
            **{f"{op}Int64": _bin("Int64", "Int64") for op in ("add", "subtract", "multiply", "divide", "remainder")},
            **{f"{op}Int32": _bin("Int32", "Int32") for op in ("add", "subtract", "multiply", "divide", "remainder")},
            **{f"{kind}{op}Int64": _bin("Int64", "Int64") for kind in ("wrapping", "saturating")
               for op in ("Add", "Subtract", "Multiply")},
            **{f"{op}Float64": _bin("Float64", "Float64") for op in ("add", "subtract", "multiply", "divide")},
            "negateInt64": _un("Int64", "Int64"),
            "absoluteInt64": _un("Int64", "Int64"),
            "powerInt64": Sig((P("base", "Int64", "value"), P("exponent", "Int64", "value")), "Int64"),
        },
    },
    "compare": {
        "types": {},
        "targets": {**_compare("Int64"), **_compare("Int32"), **_compare("Byte"), **_compare("Float64")},
    },
    "logic": {
        "types": {},
        "targets": {
            "and": _bin("Bool", "Bool"),
            "or": _bin("Bool", "Bool"),
            "xor": _bin("Bool", "Bool"),
            "not": _un("Bool", "Bool"),
        },
    },
    "bits": {
        "types": {},
        "targets": {
            **{f"{op}Int64": _bin("Int64", "Int64") for op in ("and", "or", "xor")},
            "notInt64": _un("Int64", "Int64"),
            "shiftLeftInt64": Sig((P("value", "Int64", "value"), P("amount", "Int64", "value")), "Int64"),
            "shiftRightInt64": Sig((P("value", "Int64", "value"), P("amount", "Int64", "value")), "Int64"),
        },
    },
    "convert": {
        "types": {},
        "targets": {
            "int32ToInt64": _un("Int32", "Int64"),
            "int64ToInt32": _un("Int64", "Int32"),
            "byteToInt64": _un("Byte", "Int64"),
            "int64ToByte": _un("Int64", "Byte"),
            "int64ToFloat64": _un("Int64", "Float64"),
            "float64ToInt64": _un("Float64", "Int64"),
            "exitCodeToInt64": _un("ExitCode", "Int64"),
            "int64ToExitCode": _un("Int64", "ExitCode"),
        },
    },
    "string": {
        "types": {
            "StringIndexError": _err("string.StringIndexError", ("outOfRange", "Int64")),
            "ParseError": _err("string.ParseError", ("notANumber", None), ("outOfRange", None)),
            "NotFound": _err("string.NotFound", ("absent", None)),
            "Utf8Error": _err("string.Utf8Error", ("invalidAt", "Int64")),
        },
        "targets": {
            "byteLength": Sig((P("text", "String", "borrowed"),), "Int64"),
            "byteAt": Sig((P("text", "String", "borrowed"), P("index", "Int64", "value")), "Byte",
                          raises="string.StringIndexError"),
            "equals": Sig((P("left", "String", "borrowed"), P("right", "String", "borrowed")), "Bool"),
            "startsWith": Sig((P("text", "String", "borrowed"), P("prefix", "String", "borrowed")), "Bool"),
            "find": Sig((P("text", "String", "borrowed"), P("needle", "String", "borrowed")), "Int64",
                        raises="string.NotFound"),
            "slice": Sig((P("text", "String", "borrowed"), P("start", "Int64", "value"), P("length", "Int64", "value")),
                         "String", raises="string.StringIndexError", borrows="text"),
            "concat": Sig((P("left", "String", "borrowed"), P("right", "String", "borrowed"), _RG), "String",
                          output_owner="region"),
            "fromInt64": Sig((P("value", "Int64", "value"), _RG), "String", output_owner="region"),
            "toInt64": Sig((P("text", "String", "borrowed"),), "Int64", raises="string.ParseError"),
            "fromBytes": Sig((P("bytes", "Bytes", "borrowed"), _RG), "String", "region", "string.Utf8Error"),
            "toBytes": Sig((P("text", "String", "borrowed"),), "Bytes", borrows="text"),
        },
    },
    "byte": {
        "types": {},
        "targets": {**{n: _un("Byte", "Bool") for n in ("isLetter", "isDigit", "isLetterOrDigit", "isSpace")},
                    "equals": _bin("Byte", "Bool")},
    },
    "buffer": {
        "types": {
            "ByteBuffer": TypeInfo("buffer.ByteBuffer", "opaque", False),
        },
        "targets": {
            "new": Sig((_RG,), "buffer.ByteBuffer", "region"),
            "appendString": Sig((P("buffer", "buffer.ByteBuffer", "borrowedMutable"), P("text", "String", "borrowed"))),
            "appendByte": Sig((P("buffer", "buffer.ByteBuffer", "borrowedMutable"), P("value", "Byte", "value"))),
            "appendInt64": Sig((P("buffer", "buffer.ByteBuffer", "borrowedMutable"), P("value", "Int64", "value"))),
            "length": Sig((P("buffer", "buffer.ByteBuffer", "borrowed"),), "Int64"),
            "toString": Sig((P("buffer", "buffer.ByteBuffer", "borrowed"), _RG), "String", "region", "string.Utf8Error"),
            "toBytes": Sig((P("buffer", "buffer.ByteBuffer", "borrowed"),), "Bytes", borrows="buffer"),
        },
    },
    "time": {
        "types": {
            "Deadline": TypeInfo("time.Deadline", "opaque", True, targets={
                "never": Sig((), "time.Deadline"),
                "after": Sig((P("milliseconds", "Int64", "value"),), "time.Deadline"),
            }),
        },
        "targets": {
            "sleep": Sig((P("milliseconds", "Int64", "value"),), waits=True),
        },
    },
    "clock": {
        "types": {},
        "targets": {
            "now": Sig((), "Int64", effects=E("read clock.wall")),
            "monotonic": Sig((), "Int64", effects=E("read clock.monotonic")),
        },
    },
    "environment": {
        "types": {"MissingError": _err("environment.MissingError", ("missing", None))},
        "targets": {
            "get": Sig((P("name", "String", "borrowed"), _RG), "String", "region", "environment.MissingError",
                       E("read environment.variables")),
        },
    },
    "process": {
        "types": {
            "ArgumentError": _err("process.ArgumentError", ("outOfRange", "Int64")),
            "RunError": _err("process.RunError", ("notFound", None), ("timedOut", None), ("cancelled", None),
                             ("tooLarge", None), ("failed", "Int32")),
            "Arguments": TypeInfo("process.Arguments", "opaque", False),
            "Output": TypeInfo("process.Output", "record", False,
                               fields=[("status", "ExitCode"), ("stdout", "Bytes"), ("stderr", "Bytes")]),
        },
        "targets": {
            "argumentCount": Sig((), "Int64", effects=E("read process.arguments")),
            "argument": Sig((P("index", "Int64", "value"), _RG), "String", "region", "process.ArgumentError",
                            E("read process.arguments")),
            "newArguments": Sig((_RG,), "process.Arguments", "region"),
            "addArgument": Sig((P("arguments", "process.Arguments", "borrowedMutable"), P("text", "String", "borrowed"))),
            "run": Sig((P("program", "String", "borrowed"), P("arguments", "process.Arguments", "borrowed"), _DL),
                       "ExitCode", raises="process.RunError", effects=E("spawn process.programs"), waits=True,
                       scoped="program"),
            # run a program with `input` on its standard input, collecting what it writes (a pipe each way)
            "runCaptured": Sig((P("program", "String", "borrowed"), P("arguments", "process.Arguments", "borrowed"),
                                P("input", "Bytes", "borrowed"), _RG, P("maxBytes", "Int64", "value"), _DL),
                               "process.Output", "region", "process.RunError", E("spawn process.programs"),
                               waits=True, scoped="program"),
        },
    },
    "fs": {
        "types": {
            "FileHandle": TypeInfo("fs.FileHandle", "resource", False),
            "FileError": _err("fs.FileError", ("notFound", None), ("denied", None), ("exists", None),
                              ("tooLarge", None), ("timedOut", None), ("cancelled", None), ("failed", "Int32")),
            "DirectoryListing": TypeInfo("fs.DirectoryListing", "opaque", False),
            "EntryIndexError": _err("fs.EntryIndexError", ("outOfRange", "Int64")),
        },
        "targets": {
            "openRead": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                            E("read fs.files"), scoped="path"),
            "openWrite": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                             E("write fs.files"), scoped="path"),
            "create": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                          E("write fs.files"), scoped="path"),
            "openAppend": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                              E("write fs.files"), scoped="path"),
            "createDirectory": Sig((P("path", "String", "borrowed"),), raises="fs.FileError",
                                   effects=E("write fs.files"), scoped="path"),
            "removeDirectory": Sig((P("path", "String", "borrowed"),), raises="fs.FileError",
                                   effects=E("write fs.files"), scoped="path"),
            "listDirectory": Sig((P("path", "String", "borrowed"), _RG), "fs.DirectoryListing", "region",
                                 "fs.FileError", E("read fs.files"), scoped="path"),
            "entryCount": Sig((P("listing", "fs.DirectoryListing", "borrowed"),), "Int64"),
            # an exclusive advisory lock on an open file, released by `unlock` or by closing the file
            # D-43: a target that changes the state of the handle it is given (its position, its lock, the
            # stream behind it) takes an exclusive loan, so two tasks can never use one handle at once
            "lock": Sig((P("file", "fs.FileHandle", "borrowedMutable"), _DL), raises="fs.FileError",
                        effects=E("write fs.files"), waits=True),
            "unlock": Sig((P("file", "fs.FileHandle", "borrowedMutable"),), raises="fs.FileError",
                          effects=E("write fs.files")),
            "entryName": Sig((P("listing", "fs.DirectoryListing", "borrowed"), P("index", "Int64", "value"), _RG),
                             "String", "region", "fs.EntryIndexError"),
            "read": Sig((P("file", "fs.FileHandle", "borrowedMutable"), _RG, P("maxBytes", "Int64", "value"), _DL),
                        "Bytes", "region", "fs.FileError", E("read fs.files"), waits=True),
            "write": Sig((P("file", "fs.FileHandle", "borrowedMutable"), P("bytes", "Bytes", "borrowed"), _DL),
                         raises="fs.FileError", effects=E("write fs.files"), waits=True),
            # closing a handle you own needs no authority beyond holding it
            "close": Sig((P("file", "fs.FileHandle", "owned"),), raises="fs.FileError"),
            "exists": Sig((P("path", "String", "borrowed"),), "Bool", effects=E("read fs.files"), scoped="path"),
            "remove": Sig((P("path", "String", "borrowed"),), raises="fs.FileError", effects=E("write fs.files"),
                          scoped="path"),
            "readAll": Sig((P("path", "String", "borrowed"), _RG, P("maxBytes", "Int64", "value"), _DL),
                           "Bytes", "region", "fs.FileError", E("read fs.files"), waits=True, scoped="path"),
            "writeAll": Sig((P("path", "String", "borrowed"), P("bytes", "Bytes", "borrowed"), _DL),
                            raises="fs.FileError", effects=E("write fs.files"), waits=True, scoped="path"),
        },
    },
    "net": {
        "types": {
            "TcpListener": TypeInfo("net.TcpListener", "resource", False),
            "TcpConnection": TypeInfo("net.TcpConnection", "resource", False),
            "NetError": _err("net.NetError", ("closed", None), ("timedOut", None), ("refused", None),
                             ("cancelled", None), ("failed", "Int32")),
        },
        "targets": {
            "listen": Sig((P("port", "Int32", "value"),), "net.TcpListener", "caller", "net.NetError",
                          E("listen net.tcp"), scoped="port"),
            "closeListener": Sig((P("listener", "net.TcpListener", "owned"),), raises="net.NetError",
                                 effects=E("listen net.tcp")),
            "accept": Sig((P("listener", "net.TcpListener", "borrowedMutable"), _DL),
                          "net.TcpConnection", "caller", "net.NetError", E("listen net.tcp"), waits=True),
            "connect": Sig((P("address", "String", "borrowed"), _DL), "net.TcpConnection", "caller", "net.NetError",
                           E("connect net.outbound"), waits=True, scoped="address"),
            "read": Sig((P("connection", "net.TcpConnection", "borrowedMutable"), _RG, P("maxBytes", "Int64", "value"), _DL),
                        "Bytes", "region", "net.NetError", E("readWrite net.connection"), waits=True),
            "write": Sig((P("connection", "net.TcpConnection", "borrowedMutable"), P("bytes", "Bytes", "borrowed"), _DL),
                         raises="net.NetError", effects=E("readWrite net.connection"), waits=True),
            "close": Sig((P("connection", "net.TcpConnection", "owned"),), raises="net.NetError",
                         effects=E("readWrite net.connection")),
        },
    },
    "http": {
        "types": {
            "HttpMethod": TypeInfo("http.HttpMethod", "enum", True, variants=[
                ("get", None), ("head", None), ("post", None), ("put", None), ("delete", None),
                ("options", None), ("patch", None)]),
            "HttpRequest": TypeInfo("http.HttpRequest", "record", False,
                                    fields=[("method", "http.HttpMethod"), ("path", "String")]),
            "HttpResponse": TypeInfo("http.HttpResponse", "opaque", False),
            "HttpParseError": _err("http.HttpParseError", ("malformed", None), ("tooLarge", None)),
        },
        "targets": {
            "parseRequest": Sig((P("bytes", "Bytes", "borrowed"), _RG), "http.HttpRequest", "region",
                                "http.HttpParseError"),
            "response": Sig((P("status", "Int32", "value"), P("body", "String", "borrowed"), _RG),
                            "http.HttpResponse", "region"),
            "serializeResponse": Sig((P("response", "http.HttpResponse", "borrowed"), _RG), "Bytes", "region"),
            "header": Sig((P("request", "http.HttpRequest", "borrowed"), P("name", "String", "borrowed")), "String",
                          raises="string.NotFound", borrows="request"),
        },
    },
    "list": {
        "types": {"List": _generic("list.List", ["T@any"]),
                  "IndexOutOfRange": _err("list.IndexOutOfRange", ("outOfRange", "Int64"))},
        "targets": {},
    },
    "map": {
        "types": {"Map": _generic("map.Map", ["K@plain", "V@any"]),
                  "KeyMissing": _err("map.KeyMissing", ("missing", None))},
        "targets": {},
    },
    "set": {
        "types": {"Set": _generic("set.Set", ["T@plain"])},
        "targets": {},
    },
    "option": {
        "types": {"Option": _generic("option.Option", ["T@any"], None,
                                     variants=[("present", "T@any"), ("absent", None)])},
        "targets": {},
    },
    "channel": {
        "types": {"Channel": _generic("channel.Channel", ["T@any"]),
                  "ChannelError": _err("channel.ChannelError", ("closed", None), ("timedOut", None),
                                       ("cancelled", None))},
        "targets": {},
    },
    "ffi": {
        "types": {
            "Library": TypeInfo("ffi.Library", "resource", False),
            "Function": _generic("ffi.Function", ["F@any"]),
            "LoadError": _err("ffi.LoadError", ("notFound", None), ("symbolMissing", None)),
        },
        "targets": {
            # load a shared library by name ("c" is the platform's C runtime); release it with `close`
            "open": Sig((P("name", "String", "borrowed"),), "ffi.Library", "caller", "ffi.LoadError",
                        E("load ffi.libraries"), scoped="name"),
            "close": Sig((P("library", "ffi.Library", "owned"),), effects=E("load ffi.libraries")),
        },
    },
    "random": {
        "types": {
            "Generator": TypeInfo("random.Generator", "opaque", False),
            "RangeError": _err("random.RangeError", ("emptyRange", None)),
        },
        "targets": {
            # a fresh number from the operating system's entropy source, in [low, high]
            "int64Between": Sig((P("low", "Int64", "value"), P("high", "Int64", "value")), "Int64",
                                raises="random.RangeError", effects=E("read random.entropy")),
            # a deterministic generator: the same seed gives the same numbers
            "newGenerator": Sig((P("seed", "Int64", "value"), _RG), "random.Generator", "region"),
            "nextInt64": Sig((P("generator", "random.Generator", "borrowedMutable"), P("low", "Int64", "value"),
                              P("high", "Int64", "value")), "Int64", raises="random.RangeError"),
        },
    },
    "crypto": {
        "types": {},
        "targets": {
            "sha256": Sig((P("bytes", "Bytes", "borrowed"), _RG), "Bytes", "region"),
            "hmacSha256": Sig((P("key", "Bytes", "borrowed"), P("message", "Bytes", "borrowed"), _RG), "Bytes",
                              "region"),
            "toHex": Sig((P("bytes", "Bytes", "borrowed"), _RG), "String", "region"),
            "constantTimeEquals": Sig((P("left", "Bytes", "borrowed"), P("right", "Bytes", "borrowed")), "Bool"),
        },
    },
    "log": {
        "types": {"LogError": _err("log.LogError", ("failed", "Int32"))},
        "targets": {
            level: Sig((P("text", "String", "borrowed"),), raises="log.LogError", effects=E("write console.stderr"))
            for level in ("debug", "info", "warn", "error")
        },
    },
    "json": {
        "types": {
            "Value": TypeInfo("json.Value", "opaque", False),
            "Kind": TypeInfo("json.Kind", "enum", True, variants=[
                ("null", None), ("boolean", None), ("number", None), ("text", None), ("array", None),
                ("object", None)]),
            "ParseError": _err("json.ParseError", ("invalidAt", "Int64"), ("tooDeep", None)),
            "AccessError": _err("json.AccessError", ("wrongKind", None), ("missing", None),
                                ("outOfRange", "Int64"), ("notWhole", None)),
        },
        "targets": {
            "parse": Sig((P("text", "String", "borrowed"), _RG), "json.Value", "region", "json.ParseError"),
            "kind": Sig((P("value", "json.Value", "borrowed"),), "json.Kind"),
            "asInt64": Sig((P("value", "json.Value", "borrowed"),), "Int64", raises="json.AccessError"),
            "asBool": Sig((P("value", "json.Value", "borrowed"),), "Bool", raises="json.AccessError"),
            "asText": Sig((P("value", "json.Value", "borrowed"), _RG), "String", "region", "json.AccessError"),
            "length": Sig((P("value", "json.Value", "borrowed"),), "Int64", raises="json.AccessError"),
            "item": Sig((P("value", "json.Value", "borrowed"), P("index", "Int64", "value"), _RG), "json.Value",
                        "region", "json.AccessError"),
            "field": Sig((P("value", "json.Value", "borrowed"), P("name", "String", "borrowed"), _RG), "json.Value",
                         "region", "json.AccessError"),
            "newObject": Sig((_RG,), "json.Value", "region"),
            "newArray": Sig((_RG,), "json.Value", "region"),
            "setInt64": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                             P("number", "Int64", "value")), raises="json.AccessError"),
            "setText": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                            P("text", "String", "borrowed")), raises="json.AccessError"),
            "setBool": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                            P("flag", "Bool", "value")), raises="json.AccessError"),
            "setValue": Sig((P("object", "json.Value", "borrowedMutable"), P("name", "String", "borrowed"),
                             P("value", "json.Value", "borrowed")), raises="json.AccessError"),
            "appendInt64": Sig((P("array", "json.Value", "borrowedMutable"), P("number", "Int64", "value")),
                               raises="json.AccessError"),
            "appendText": Sig((P("array", "json.Value", "borrowedMutable"), P("text", "String", "borrowed")),
                              raises="json.AccessError"),
            "stringify": Sig((P("value", "json.Value", "borrowed"), _RG), "String", "region"),
        },
    },
    "secret": {
        "types": {"Secret": TypeInfo("secret.Secret", "opaque", False)},
        "targets": {
            # a Secret has no conversion to text except `reveal`, which needs `read secret.values`
            "fromText": Sig((P("text", "String", "borrowed"), _RG), "secret.Secret", "region"),
            "fromEnvironment": Sig((P("name", "String", "borrowed"), _RG), "secret.Secret", "region",
                                   "environment.MissingError", E("read environment.variables")),
            "reveal": Sig((P("secret", "secret.Secret", "borrowed"), _RG), "String", "region",
                          effects=E("read secret.values")),
            # comparing or measuring a secret reveals something about it, so it needs the same authority
            "matches": Sig((P("secret", "secret.Secret", "borrowed"), P("candidate", "String", "borrowed")), "Bool",
                           effects=E("read secret.values")),
            "length": Sig((P("secret", "secret.Secret", "borrowed"),), "Int64", effects=E("read secret.values")),
        },
    },
    "signal": {
        "types": {"SignalError": _err("signal.SignalError", ("timedOut", None), ("cancelled", None))},
        "targets": {
            "interrupted": Sig((), "Bool", effects=E("read signal.interrupts")),
            "waitForInterrupt": Sig((_DL,), raises="signal.SignalError", effects=E("read signal.interrupts"),
                                    waits=True),
        },
    },
    "test": {
        "types": {},
        "targets": {
            "assertEqualInt64": Sig((P("expected", "Int64", "value"), P("actual", "Int64", "value"))),
            "assertEqualExitCode": Sig((P("expected", "ExitCode", "value"), P("actual", "ExitCode", "value"))),
            "assertEqualString": Sig((P("expected", "String", "borrowed"), P("actual", "String", "borrowed"))),
            "assertTrue": Sig((P("value", "Bool", "value"),)),
            "fail": Sig((P("message", "String", "borrowed"),)),
        },
    },
}


def generic_members(generic: str, inst: str, args: list[str], plain) -> dict[str, Sig]:
    """Call targets of an instantiated library generic (LR-24, LR-25, LR-33)."""
    def own_mode(t: str) -> str:
        return "value" if plain(t) else "owned"

    def read_mode(t: str) -> str:
        return "value" if plain(t) else "borrowed"

    if generic == "list.List":
        item = args[0]
        return {
            "new": Sig((_RG,), inst, "region"),
            "append": Sig((P("list", inst, "borrowedMutable"), P("item", item, own_mode(item)))),
            "get": Sig((P("list", inst, "borrowed"), P("index", "Int64", "value")), item,
                       raises="list.IndexOutOfRange", borrows=None if plain(item) else "list"),
            "set": Sig((P("list", inst, "borrowedMutable"), P("index", "Int64", "value"), P("item", item, own_mode(item))),
                       raises="list.IndexOutOfRange"),
            "length": Sig((P("list", inst, "borrowed"),), "Int64"),
            "clear": Sig((P("list", inst, "borrowedMutable"),)),
        }
    if generic == "map.Map":
        key, value = args
        return {
            "new": Sig((_RG,), inst, "region"),
            "put": Sig((P("map", inst, "borrowedMutable"), P("key", key, "value"), P("value", value, own_mode(value)))),
            "get": Sig((P("map", inst, "borrowed"), P("key", key, "value")), value, raises="map.KeyMissing",
                       borrows=None if plain(value) else "map"),
            "contains": Sig((P("map", inst, "borrowed"), P("key", key, "value")), "Bool"),
            "remove": Sig((P("map", inst, "borrowedMutable"), P("key", key, "value")), raises="map.KeyMissing"),
            "length": Sig((P("map", inst, "borrowed"),), "Int64"),
        }
    if generic == "set.Set":
        item = args[0]
        return {
            "new": Sig((_RG,), inst, "region"),
            "add": Sig((P("set", inst, "borrowedMutable"), P("item", item, "value"))),
            "contains": Sig((P("set", inst, "borrowed"), P("item", item, "value")), "Bool"),
            "remove": Sig((P("set", inst, "borrowedMutable"), P("item", item, "value"))),
            "length": Sig((P("set", inst, "borrowed"),), "Int64"),
        }
    if generic == "option.Option":
        item = args[0]
        return {"present": Sig((P("payload", item, own_mode(item)),), inst), "absent": Sig((), inst)}
    if generic == "ffi.Function":
        # `bind` looks a symbol up in a loaded library and gives it the declared operation type
        return {"bind": Sig((P("library", "ffi.Library", "borrowed"), P("symbol", "String", "borrowed")), args[0],
                            raises="ffi.LoadError", effects=E("load ffi.symbols"), scoped="symbol")}
    if generic == "channel.Channel":
        item = args[0]
        return {
            "new": Sig((P("capacity", "Int64", "value"), _RG), inst, "region"),
            "send": Sig((P("channel", inst, "borrowed"), P("item", item, own_mode(item)), _DL),
                        raises="channel.ChannelError", waits=True),
            "receive": Sig((P("channel", inst, "borrowed"), _DL), item, "caller" if not plain(item) else None,
                           "channel.ChannelError", waits=True),
            "close": Sig((P("channel", inst, "borrowed"),)),
        }
    return {}


def type_param_name(canon: str) -> str:
    """`T@plain` -> `T`."""
    return canon.split("@", 1)[0]
