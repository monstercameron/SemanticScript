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
    "UInt32": (0, 2**32 - 1), "UInt64": (0, 2**64 - 1), "Byte": (0, 255), "ExitCode": (-2**31, 2**31 - 1),
}
FLOAT_TYPES = {"Float32", "Float64"}

# LR-34 rule 5: resources whose capability must state a scope, and how a literal
# argument is compared with it. Every other resource takes `scope none`.
SCOPED_RESOURCES = {
    "net.tcp": "port",  # scope "<address>:<port>"; the literal is the port
    "net.outbound": "prefix",  # scope "<host>:<port>" prefix; the literal is the address
    "fs.files": "prefix",  # scope is a directory prefix; the literal path starts with it
    "process.programs": "exact",  # scope is the program name; the literal equals it
}


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
                              ("failed", "Int32")),
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
            "RunError": _err("process.RunError", ("notFound", None), ("timedOut", None), ("failed", "Int32")),
            "Arguments": TypeInfo("process.Arguments", "opaque", False),
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
        },
    },
    "fs": {
        "types": {
            "FileHandle": TypeInfo("fs.FileHandle", "resource", False),
            "FileError": _err("fs.FileError", ("notFound", None), ("denied", None), ("exists", None),
                              ("tooLarge", None), ("timedOut", None), ("failed", "Int32")),
        },
        "targets": {
            "openRead": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                            E("read fs.files"), scoped="path"),
            "openWrite": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                             E("write fs.files"), scoped="path"),
            "create": Sig((P("path", "String", "borrowed"),), "fs.FileHandle", "caller", "fs.FileError",
                          E("write fs.files"), scoped="path"),
            "read": Sig((P("file", "fs.FileHandle", "borrowed"), _RG, P("maxBytes", "Int64", "value"), _DL),
                        "Bytes", "region", "fs.FileError", E("read fs.files"), waits=True),
            "write": Sig((P("file", "fs.FileHandle", "borrowed"), P("bytes", "Bytes", "borrowed"), _DL),
                         raises="fs.FileError", effects=E("write fs.files"), waits=True),
            "close": Sig((P("file", "fs.FileHandle", "owned"),), raises="fs.FileError", effects=E("read fs.files")),
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
            "accept": Sig((P("listener", "net.TcpListener", "borrowed"), _DL),
                          "net.TcpConnection", "caller", "net.NetError", E("listen net.tcp"), waits=True),
            "connect": Sig((P("address", "String", "borrowed"), _DL), "net.TcpConnection", "caller", "net.NetError",
                           E("connect net.outbound"), waits=True, scoped="address"),
            "read": Sig((P("connection", "net.TcpConnection", "borrowed"), _RG, P("maxBytes", "Int64", "value"), _DL),
                        "Bytes", "region", "net.NetError", E("readWrite net.connection"), waits=True),
            "write": Sig((P("connection", "net.TcpConnection", "borrowed"), P("bytes", "Bytes", "borrowed"), _DL),
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
