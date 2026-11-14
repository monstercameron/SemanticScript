"""Names, types, signatures, ownership rows, and exact declared facts.

Covers enforcement-plan steps 3, 4, 6, and the static half of 8:
- every name resolves, and resolves to the right kind of thing (LR-02, LR-32);
- every stated type matches what it describes (LR-05);
- every call's arguments match the target's parameters, in order, with the
  paired passing mode (LR-20, LR-31);
- `result`, `catch`, `ownedBy`, `cleanedBy`, and `borrows` agree with the target;
- `effect`, `uses`, `async`, `memoryHeap`, and `maxRecursion` state exactly
  what the operation does (LR-07, LR-10, LR-20, LR-22, LR-33).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from . import shapes as S
from .diagnostics import Sink
from .library import (BUILTINS, FLOAT_TYPES, INTEGER_RANGES, LIBRARY, SCOPED_RESOURCES, Param, Sig, TypeInfo,
                      path_within,
                      fits_constraint, generic_members, type_param_name)
from .model import Entity, Row

# ---------------------------------------------------------------- program model


@dataclass
class Binding:
    name: str
    type: Optional[str]
    kind: str  # input | let | out | catch | bind | region | group
    line: int
    mutable: bool = False
    unset: bool = False
    mode: Optional[str] = None
    literal: Optional[object] = None  # the literal an immutable let starts from (decoded), if any
    view_of: Optional[str] = None  # for results that borrow another value


@dataclass
class CallInfo:
    entity: Entity
    sig: Optional[Sig]
    args: list[tuple[str, str, str, str, int]]  # (slot, type, value, mode, line)
    out: Optional[tuple[str, str]]  # (name, type)
    catch: Optional[tuple[str, str]]
    reference: Optional[str]  # invokesReference binding
    callee_op: Optional[str]  # local operation invoked directly


@dataclass
class OpInfo:
    entity: Entity
    module: "Module"
    bindings: dict[str, Binding] = field(default_factory=dict)
    calls: dict[str, CallInfo] = field(default_factory=dict)  # calls and tasks
    owned: dict[str, Entity] = field(default_factory=dict)  # every owned entity
    labels: list[str] = field(default_factory=list)
    output: Optional[str] = None
    raises: Optional[str] = None
    sig: Optional[Sig] = None
    tparams: dict[str, str] = field(default_factory=dict)


class Module:
    def __init__(self, short: str, path: str, file: str, entities: list[Entity], sink: Sink):
        self.short = short
        self.path = path
        self.file = file
        self.entities = entities
        self.sink = sink
        self.module_entity: Optional[Entity] = None
        self.imports: dict[str, tuple[str, int]] = {}  # short -> (path, line)
        self.used_imports: set[str] = set()
        self.exports: set[str] = set()
        self.types: dict[str, Entity] = {}
        self.ops: dict[str, Entity] = {}
        self.tests: dict[str, Entity] = {}
        self.test_helpers: set[str] = set()  # D-112: operations declared in the module's test file
        self.tables: dict[str, Entity] = {}
        self.constants: dict[str, Entity] = {}  # D-103
        self.capabilities: dict[str, Entity] = {}
        self.op_instances: dict[str, Entity] = {}
        self.owned: list[Entity] = []
        self.op_infos: dict[str, OpInfo] = {}
        self._type_cache: dict[str, Optional[TypeInfo]] = {}


class World:
    """All project modules plus the standard library."""

    def __init__(self) -> None:
        self.modules: dict[str, Module] = {}
        self.entry: Optional[tuple[str, str]] = None  # (module, operation) named by build.sem
        # every operation used as a value, by the operationType it was used as: an operation that invokes a
        # reference of that type may be calling any of them (the recursion check follows these edges)
        self.taken: dict[str, set[tuple[str, str]]] = {}
        # D-92: instances at type arguments the backend put in (`concrete`), by their made-up names
        self.synthetic: dict[str, Optional[TypeInfo]] = {}

    # ------------------------------------------------------------ types

    def type_info(self, canon: Optional[str]) -> Optional[TypeInfo]:
        if canon is None:
            return None
        if canon in self.synthetic:
            return self.synthetic[canon]
        if canon in BUILTINS:
            return BUILTINS[canon]
        if "@" in canon:  # a type parameter, `T@plain` or `T@any`
            return TypeInfo(canon, "typeParam", canon.endswith("@plain"))
        if "." not in canon:
            return None
        mod, name = canon.split(".", 1)
        if mod in self.modules:
            m = self.modules[mod]
            if canon not in m._type_cache:
                m._type_cache[canon] = None  # cycle guard
                m._type_cache[canon] = self._local_type_info(m, name)
            return m._type_cache[canon]
        lib = LIBRARY.get(mod)
        return lib["types"].get(name) if lib else None

    def holds(self, canon: Optional[str], test, _seen: Optional[set] = None) -> bool:
        """Whether a value of `canon` holds, at any depth through records, enum payloads, and aliases, a part
        for which `test(canon)` is true (D-107)."""
        if canon is None:
            return False
        seen = _seen or set()
        if canon in seen:
            return False
        seen.add(canon)
        if test(canon):
            return True
        info = self.type_info(canon)
        if info is None:
            return False
        if info.kind == "alias":
            return self.holds(info.base, test, seen)
        parts = [t for _n, t in info.fields] + [p for _n, p in info.variants if p is not None]
        return any(self.holds(t, test, seen) for t in parts)

    def holds_container(self, canon: Optional[str]) -> bool:
        """A list, map, set, or channel somewhere inside: values that live in a region as a whole. A type
        parameter that is not `plain` may stand for one (D-108)."""
        def container(c):
            if c.endswith("@any"):
                return True
            info = self.type_info(c)
            return info is not None and info.kind == "instance" and info.generic in (
                "list.List", "map.Map", "set.Set", "channel.Channel")
        return self.holds(canon, container)

    def plain(self, canon: Optional[str], _seen: Optional[set] = None) -> bool:
        info = self.type_info(canon)
        if info is None:
            return True
        if info.plain is not None:
            return info.plain
        seen = _seen or set()
        if canon in seen:
            return True
        seen.add(canon)
        if info.kind == "record":
            return all(self.plain(t, seen) for _n, t in info.fields)
        if info.kind == "enum":
            return all(p is None or self.plain(p, seen) for _n, p in info.variants)
        if info.kind == "alias":
            return self.plain(info.base, seen)
        if info.kind == "instance" and info.generic == "option.Option":
            return self.plain(info.args[0], seen)
        if info.kind == "operationType":
            return True
        return False

    def mode_for(self, canon: Optional[str]) -> str:
        """LR-31: the passing mode a type takes when it is only read."""
        if canon == "Region":
            return "borrowed"
        return "copied" if self.plain(canon) else "borrowed"

    def _local_type_info(self, m: Module, name: str) -> Optional[TypeInfo]:
        ent = m.types.get(name)
        if ent is None:
            return None
        canon = f"{m.short}.{name}"
        tparams = type_params_of(ent)
        if ent.kind == "record":
            fields = [(r.text(0), resolve_type(self, m, r.text(1), r.line, tparams, quiet=True)) for r in ent.facts("field")]
            return TypeInfo(canon, "record", None, fields=fields, type_params=list(tparams.values()))
        if ent.kind == "enum":
            variants = [(r.text(0), None if r.text(1) == "none" else resolve_type(self, m, r.text(1), r.line, tparams, quiet=True))
                        for r in ent.facts("variant")]
            return TypeInfo(canon, "enum", None, variants=variants, type_params=list(tparams.values()))
        if ent.kind == "alias":
            idx = ent.value("indexes")
            return TypeInfo(canon, "alias", None, base=resolve_type(self, m, ent.value("aliasOf"), ent.line, quiet=True),
                            index=None if idx in (None, "none") else resolve_type(self, m, idx, ent.line, quiet=True))
        if ent.kind == "operationType":
            return TypeInfo(canon, "operationType", True, sig=header_sig(self, m, ent, quiet=True),
                            type_params=list(tparams.values()))
        if ent.kind == "typeInstance":
            row = ent.fact("instantiates")
            if row is None:
                return None
            scope = instance_scope(m, ent)
            gen = resolve_type(self, m, row.text(0), row.line, quiet=True, generic=True)
            args = [resolve_type(self, m, t.raw, row.line, scope, quiet=True) for t in row.args[1:]]
            info = self.instance_info(m, canon, gen, args)
            info.owner = instance_owner(ent)
            return info
        return None

    def instance_info(self, m: Module, canon: str, gen: Optional[str], args: list) -> TypeInfo:
        """The type a `typeInstance` names: generic `gen` at type arguments `args`."""
        ginfo = self.type_info(gen)
        info = TypeInfo(canon, "instance", None, generic=gen, args=args)
        if ginfo is not None and ginfo.kind in ("record", "enum") and ginfo.type_params:
            sub = dict(zip(ginfo.type_params, args))
            info.kind = ginfo.kind
            info.fields = [(n, sub.get(t, t)) for n, t in ginfo.fields]
            info.variants = [(n, sub.get(p, p) if p else None) for n, p in ginfo.variants]
        elif ginfo is not None and ginfo.kind == "operationType" and ginfo.type_params and ginfo.sig is not None:
            # D-94: an instance of a generic operation type is an operation type
            info.kind, info.plain = "operationType", True
            info.sig = self.substitute(ginfo.sig, dict(zip(ginfo.type_params, args)))
        elif ginfo is not None and ginfo.kind == "generic":
            sub = dict(zip(ginfo.type_params, args))
            info.variants = [(n, sub.get(p, p) if p else None) for n, p in ginfo.variants]
            if gen == "list.List" and "<" not in canon:
                info.index = self.index_alias(m, canon)
            info.targets = generic_members(gen, canon, args, self.plain, info.index)
            if gen != "option.Option":
                info.plain = False
        return info

    # ------------------------------------------------------------ D-92: instances at a type parameter

    def is_open(self, canon: Optional[str]) -> bool:
        """Whether a type still names a type parameter: the parameter itself, or an instance stated
        `in <operation>` whose arguments name one."""
        if canon is None:
            return False
        if "@" in canon:
            return True
        info = self.type_info(canon)
        return info is not None and info.owner is not None and any(self.is_open(a) for a in info.args)

    def concrete(self, canon: Optional[str], sub: dict) -> Optional[str]:
        """A type with the type arguments `sub` put in. An open instance becomes the instance of the same generic
        at the arguments put in, named `<instance><arg,...>` (made once, kept in `synthetic`); the backend
        compiles one copy of a generic operation per set of arguments, and uses these for its values."""
        if canon is None or not sub:
            return canon
        if canon in sub:
            return sub[canon]
        if not self.is_open(canon):
            return canon
        info = self.type_info(canon)
        args = [self.concrete(a, sub) for a in info.args]
        name = f"{canon.split('<', 1)[0]}<{','.join(str(a) for a in args)}>"
        if name not in self.synthetic:
            mod = canon.split(".", 1)[0]
            self.synthetic[name] = None  # cycle guard
            made = self.instance_info(self.modules[mod], name, info.generic, args)
            self.synthetic[name] = made
        return name

    def concrete_sig(self, sig: Sig, sub: dict) -> Sig:
        t = lambda x: self.concrete(x, sub) if x else x  # noqa: E731
        return Sig(tuple(Param(p.name, t(p.type), p.mode) for p in sig.inputs), t(sig.output), sig.output_owner,
                   t(sig.raises), sig.effects, sig.waits, sig.borrows, sig.scoped)

    def rescope(self, m: Module, canon: Optional[str], sub: dict, owner: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """D-92: a type of a generic operation's signature, seen from an instance of it. Type parameters become
        the instance's arguments; an open instance of the generic operation becomes the instance of this module
        that the caller declared for the same generic at the same arguments, in the caller's scope (`in none`, or
        `in <owner>`). Returns (type, None), or (None, what is missing) when the caller declared none."""
        if canon is None:
            return None, None
        if canon in sub:
            return sub[canon], None
        if not self.is_open(canon):
            return canon, None
        info = self.type_info(canon)
        args = []
        for a in info.args:
            got, missing = self.rescope(m, a, sub, owner)
            if missing is not None:
                return None, missing
            args.append(got)
        for ent in m.types.values():
            if ent.kind != "typeInstance" or instance_owner(ent) not in (None, owner):
                continue
            other = self.type_info(f"{m.short}.{ent.name}")
            if other is not None and other.generic == info.generic and other.args == args:
                return f"{m.short}.{ent.name}", None
        return None, f"{type_param_name(info.generic or '?')} {' '.join(type_param_name(a or '?') for a in args)}"

    def index_aliases(self, m: Module, canon: str) -> list[Entity]:
        """D-60: the aliases of module `m` that state `indexes` naming the list type `canon`."""
        out = []
        for ent in m.types.values():
            idx = ent.value("indexes") if ent.kind == "alias" else None
            if idx not in (None, "none") and (idx == canon.split(".", 1)[1] or idx == canon):
                out.append(ent)
        return sorted(out, key=lambda e: e.line)

    def index_alias(self, m: Module, canon: str) -> Optional[str]:
        found = self.index_aliases(m, canon)
        return f"{m.short}.{found[0].name}" if found else None

    def substitute(self, sig: Sig, sub: dict[str, str]) -> Sig:
        """Replace type parameters in a signature (generic operations, LR-24)."""
        t = lambda x: sub.get(x, x) if x else x  # noqa: E731
        return Sig(tuple(Param(p.name, t(p.type), p.mode) for p in sig.inputs), t(sig.output), sig.output_owner,
                   t(sig.raises), sig.effects, sig.waits, sig.borrows, sig.scoped)

    def members(self, canon: str) -> dict[str, Sig]:
        """Derived call targets of a type (LR-28, LR-42 A10)."""
        info = self.type_info(canon)
        if info is None:
            return {}
        out = dict(info.targets)
        mode = self.mode_for
        if info.kind == "record" and not info.type_params:
            params = tuple(Param(n, t, mode(t)) for n, t in info.fields)
            owned = any(not self.plain(t) for _n, t in info.fields)
            if owned:
                params += (Param("region", "Region", "borrowed"),)
            out["new"] = Sig(params, canon, "region" if owned else None)
            for n, t in info.fields:
                out[n] = Sig((Param("record", canon, mode(canon)),), t, borrows=None if self.plain(t) else "record")
            out["equals"] = Sig((Param("left", canon, mode(canon)), Param("right", canon, mode(canon))), "Bool")
        if info.kind == "alias" and info.index is not None:
            # D-100: a position's number, for printing and as a key; there is no way back
            out["toInt64"] = Sig((Param("position", canon, "copied"),), "Int64")
        if info.kind in ("enum", "instance") and info.variants and not info.type_params:
            for n, p in info.variants:
                out[n] = Sig(() if p is None else (Param("payload", p, "copied" if self.plain(p) else "owned"),), canon)
            out["equals"] = Sig((Param("left", canon, mode(canon)), Param("right", canon, mode(canon))), "Bool")
        return out


# ---------------------------------------------------------------- resolution helpers

class TypeScope(dict):
    """The type parameters names resolve against, and the operation they belong to (D-92): an instance stated
    `in <operation>` is visible only where the scope's owner is that operation."""

    def __init__(self, params: dict, owner: Optional[str] = None):
        super().__init__(params)
        self.owner = owner


def type_params_of(ent: Entity) -> TypeScope:
    """`T typeParam plain` -> {"T": "T@plain"}."""
    return TypeScope({r.text(0): f"{r.text(0)}@{r.text(1)}" for r in ent.facts("typeParameter") if r.text(0) != "none"},
                     ent.name if ent.kind in ("operation", "test") else None)


def instance_owner(ent: Entity) -> Optional[str]:
    """D-92: the generic operation an instance belongs to (`in <operation>`), or None for `in none`."""
    if ent.kind not in ("typeInstance", "operationInstance"):
        return None
    v = ent.value("in")
    return None if v in (None, "none") else v


def instance_scope(m: "Module", ent: Entity) -> TypeScope:
    """The type parameters an instance's type arguments may name: its operation's, for `in <operation>`."""
    owner = instance_owner(ent)
    if owner is not None and owner in m.ops:
        return type_params_of(m.ops[owner])
    return TypeScope({}, owner)


def resolve_type(world: World, m: Module, text: Optional[str], line: int, tparams=None, quiet: bool = False,
                 generic: bool = False) -> Optional[str]:
    """`generic`: the name is the generic an `instantiates` row names; anywhere else a generic type is R402."""
    if tparams is None:
        tparams = {}
    if text is None:
        return None
    sink = m.sink

    def err(code, msg):
        if not quiet:
            sink.error(code, line, msg)

    def unapplied(ent_or_info) -> None:
        """D-94: a generic record, enum, or operation type, or a library generic, is used through a typeInstance
        that names its type arguments."""
        if generic:
            return
        params = (type_params_of(ent_or_info) if isinstance(ent_or_info, Entity) else
                  ent_or_info.type_params if ent_or_info.kind == "generic" else [])
        if params:
            err("R402", f"`{text}` is generic; use it through a typeInstance that names its type arguments "
                f"(`<Name> instantiates {text} <Type>...`)")

    if text in S.BUILTIN_TYPES:
        return text
    if "." in text:
        mod, name = text.split(".", 1)
        if mod not in m.imports:
            err("R404", f"`{text}` uses module `{mod}`, which `{m.short}` does not import")
            return None
        m.used_imports.add(mod)
        if mod in world.modules:
            other = world.modules[mod]
            if name not in other.types:
                err("R401", f"module `{mod}` declares no type `{name}`")
                return None
            if name not in other.exports:
                err("R404", f"type `{name}` is not exported by module `{mod}`")
                return None
            unapplied(other.types[name])
            return text
        lib = LIBRARY.get(mod)
        if lib is None:
            err("R401", f"module `{mod}` is not part of this project, so it has no type `{name}`")
            return None
        if name not in lib["types"]:
            err("R401", f"the standard module `{mod}` has no type `{name}`")
            return None
        unapplied(lib["types"][name])
        return text
    if text in tparams:
        return tparams[text]
    if text in m.types:
        owner = instance_owner(m.types[text])
        if owner is not None and getattr(tparams, "owner", None) != owner:
            err("R402", f"`{text}` belongs to the generic operation `{owner}` (`{text} in {owner}`): it names that "
                "operation's type parameters, so only `" + owner + "` uses it (D-92)")
        unapplied(m.types[text])
        return f"{m.short}.{text}"
    err("R401", f"unknown type `{text}`; built-in types are not prefixed, local types are declared in "
        f"this module, and imported types are written `module.Type`")
    return None


def header_sig(world: World, m: Module, ent: Entity, quiet: bool = False) -> Sig:
    tp = type_params_of(ent)
    inputs = []
    for r in ent.facts("input"):
        if r.text(0) != "none":
            inputs.append(Param(r.text(0), resolve_type(world, m, r.text(1), r.line, tp, quiet=quiet), r.text(2)))
    out = ent.value("output")
    raises = ent.value("raises")
    owner = ent.value("outputOwnedBy")
    effects = frozenset((r.text(0), r.text(1)) for r in ent.facts("effect") if r.text(0) != "none")
    return Sig(tuple(inputs),
               None if out in (None, "none") else resolve_type(world, m, out, ent.line, tp, quiet=True),
               None if owner in (None, "none") else owner,
               None if raises in (None, "none") else resolve_type(world, m, raises, ent.line, tp, quiet=True),
               effects, ent.value("async") == "true")


def literal_value(tok):
    """The value a literal token denotes, for scope checks and the backend."""
    if tok.kind == "string":
        return tok.value
    raw = tok.raw
    if raw in ("true", "false"):
        return raw == "true"
    if S.INT.match(raw):
        return int(raw)
    if S.FLOAT.match(raw):
        return float(raw)
    return raw  # a variant


def literal_fits(world: World, tok, canon: Optional[str]) -> bool:
    if canon is None:
        return True
    raw = tok.raw
    if tok.kind == "string":
        return canon == "String"
    if raw in ("true", "false"):
        return canon == "Bool"
    if S.INT.match(raw):
        base = canon
        info = world.type_info(canon)
        if info is not None and info.kind == "alias":
            base = info.base
        if base in INTEGER_RANGES:
            lo, hi = INTEGER_RANGES[base]
            return lo <= int(raw) <= hi
        return False
    if S.FLOAT.match(raw):
        return canon in FLOAT_TYPES
    return False


def resolve_variant(world: World, m: Module, text: str, line: int, quiet: bool = False, tparams=None):
    """`Enum.variant` or `module.Enum.variant` -> (enum canon, variant, payload) or None."""
    parts = text.split(".")
    type_text = ".".join(parts[:-1])
    canon = resolve_type(world, m, type_text, line, tparams, quiet=quiet)
    info = world.type_info(canon)
    if info is None:
        return None
    for n, p in info.variants:
        if n == parts[-1]:
            return canon, n, p
    if not quiet:
        m.sink.error("R401", line, f"`{type_text}` has no variant `{parts[-1]}`")
    return None


# ---------------------------------------------------------------- module checks

def index_module(world: World, m: Module, test_file_entities: set[int]) -> None:
    """Collect module-level names (no diagnostics about bodies yet)."""
    sink = m.sink
    seen: dict[str, Entity] = {}
    for ent in m.entities:
        if ent.kind == "module":
            if id(ent) in test_file_entities:
                sink.error("R602", ent.line, "a test file belongs to the module beside it and declares no module")
            elif m.module_entity is not None:
                sink.error("R602", ent.line, "a file declares exactly one module")
            else:
                m.module_entity = ent
            continue
        if ent.kind in S.OWNED_KINDS:
            m.owned.append(ent)
            continue
        if id(ent) in test_file_entities and ent.kind == "operation":
            # D-112: a helper the module's tests share; only tests and other helpers call it
            m.test_helpers.add(ent.name)
            inv = ent.facts("invariant")
            if not inv or inv[0].text(0) != "none":
                sink.error("R604", ent.line, f"`{ent.name}` is a test helper (it is declared in the test file); it "
                           "states `invariant none`, since the tests that call it are what it is checked by")
        elif id(ent) in test_file_entities and ent.kind != "test":
            sink.error("R602", ent.line, f"a test file holds only tests, the operations they share, and the "
                       f"entities those own; move `{ent.name}` to the module file")
        if ent.kind == "test" and id(ent) not in test_file_entities:
            sink.error("R602", ent.line, f"test `{ent.name}` belongs in the `.test.sem` file beside this module")
        if ent.name in seen:
            sink.error("R203", ent.line, f"`{ent.name}` is already declared on line {seen[ent.name].line}")
            continue
        seen[ent.name] = ent
        if ent.kind in S.TYPE_KINDS:
            m.types[ent.name] = ent
        elif ent.kind == "operation":
            m.ops[ent.name] = ent
        elif ent.kind == "test":
            m.tests[ent.name] = ent
        elif ent.kind == "table":
            m.tables[ent.name] = ent
        elif ent.kind == "constant":
            m.constants[ent.name] = ent
        elif ent.kind == "capability":
            m.capabilities[ent.name] = ent
        elif ent.kind == "operationInstance":
            m.op_instances[ent.name] = ent
    me = m.module_entity
    if me is not None:
        for r in me.facts("imports"):
            p = r.text(0)
            if p == "none":
                continue
            short = p.split(".")[-1]
            if short in m.imports:
                sink.error("R404", r.line, f"two imports end in `{short}`; imported names are written with the last "
                           "path segment, so it must be unique")
            m.imports[short] = (p, r.line)
        for r in me.facts("exports"):
            if r.text(0) != "none":
                m.exports.add(r.text(0))


def check_module(world: World, m: Module) -> None:
    sink = m.sink
    me = m.module_entity
    if me is None:
        sink.error("R602", 1, "a module file declares one `<name> is module` entity")
    else:
        path = me.value("path") or ""
        if path.split(".")[-1] != me.name:
            sink.error("R602", me.line, f"module `{me.name}` must be named after the last segment of its path "
                       f"`{path}` (`{path.split('.')[-1]}`)")
        for r in me.facts("imports"):
            p = r.text(0)
            if p == "none":
                continue
            short = p.split(".")[-1]
            if p.startswith("standard."):
                if short not in LIBRARY or p != f"standard.{short}":
                    sink.error("R404", r.line, f"there is no standard module `{p}`")
            elif short not in world.modules or p not in _import_paths(world.modules[short], m):
                sink.error("R404", r.line, f"module `{p}` is not part of this project")
        for r in me.facts("exports"):
            n = r.text(0)
            if n == "none":
                continue
            if n in m.capabilities:
                sink.error("R402", r.line, f"`{n}` is a capability; capabilities are never exported. Each module "
                           "declares the authority its own operations use, and build.sem bounds them all, so authority "
                           "cannot be handed from one module to another")
            elif n in m.test_helpers:
                sink.error("R402", r.line, f"`{n}` is a test helper (declared in the test file); it is never "
                           "exported (D-112)")
            elif n not in m.ops and n not in m.types and n not in m.tables and n not in m.op_instances:
                sink.error("R401", r.line, f"`{n}` is exported but not declared in this module")
            elif n in m.ops and world.entry != (m.short, n):
                inv = m.ops[n].facts("invariant")
                if inv and inv[0].text(0) == "none":
                    sink.error("R304", inv[0].line, f"exported operation `{n}` cannot state `invariant none`; "
                               "an exported operation makes a tested claim")

    for ent in m.types.values():
        _check_type_entity(world, m, ent)
    for ent in m.tables.values():
        _check_table(world, m, ent)
    for ent in m.capabilities.values():
        _check_capability(m, ent)
    for c in m.constants.values():
        # D-103: a constant's value is a literal of its type
        canon = resolve_type(world, m, c.value("type"), c.line) if c.fact("type") is not None else None
        row = c.fact("value")
        if canon is not None and row is not None:
            _check_value_token(world, m, row.args[0], canon, row.line, f"constant `{c.name}`")
    for ent in m.op_instances.values():
        _check_op_instance(world, m, ent)
    for ent in m.owned:
        owner = ent.owner
        holder = m.ops.get(owner) or m.tests.get(owner)
        if holder is None:
            sink.error("R401", ent.fact("in").line if ent.fact("in") else ent.line,
                       f"`{ent.name}` belongs to `{owner}`, which is not an operation or test in this module")
    for ent in list(m.ops.values()) + list(m.tests.values()):
        m.op_infos[ent.name] = _build_op(world, m, ent)
    for info in m.op_infos.values():
        _check_op(world, m, info)
    used_caps = {r.text(0) for e in list(m.ops.values()) + list(m.tests.values()) for r in e.facts("uses")}
    for name, cap in m.capabilities.items():
        if name not in used_caps:
            sink.error("R408", cap.line, f"capability `{name}` is not used by any operation")
    _check_invariant_coverage(m)


def _check_invariant_coverage(m: Module) -> None:
    """LR-06 rule 3: every invariant is named by at least one test's `verifies` row."""
    verified = {(r.text(0), r.text(1)) for t in m.tests.values() for r in t.facts("verifies")}
    for op in m.ops.values():
        for r in op.facts("invariant"):
            if r.text(0) != "none" and (op.name, r.text(0)) not in verified:
                m.sink.error("R604", r.line, f"invariant `{r.text(0)}` of `{op.name}` is not verified by any test; "
                             f"add a test in `{m.short}.test.sem` with `verifies {op.name} {r.text(0)}`")


def grant_scope(row) -> Optional[str]:
    """The scope a `grants <verb> <resource> <scope|none>` row states, or None for `none` (D-47)."""
    return row.args[2].value if len(row.args) > 2 and row.args[2].kind == "string" else None


def _check_capability(m: Module, cap: Entity) -> None:
    """LR-34 rule 5: a grant of a scoped resource states its scope; any other grant states `none`."""
    for g in cap.facts("grants"):
        res, scope = g.text(1), grant_scope(g)
        if res in SCOPED_RESOURCES and scope is None:
            m.sink.error("R408", g.line, f"`{res}` is a scoped resource, so the grant states which part of it "
                         f"`{cap.name}` covers")
        elif res not in SCOPED_RESOURCES and scope is not None:
            m.sink.error("R408", g.line, f"`{res}` takes no scope; this grant ends in `none`")
        elif res == "fs.files" and scope is not None and not scope.endswith(("/", "*")):
            m.sink.error("R408", g.line, f"an `fs.files` scope is a directory ending in `/` (`\"data/\"`) or a name "
                         f"pattern ending in `*` (`\"suite-*\"`); `{scope}` is neither")


def _check_op_instance(world: World, m: Module, ent: Entity) -> None:
    row = ent.fact("instantiates")
    if row is None:
        return
    gen = m.ops.get(row.text(0))
    if gen is None:
        m.sink.error("R401", row.line, f"`{row.text(0)}` is not an operation of this module")
        return
    params = list(type_params_of(gen).values())
    if not params:
        m.sink.error("R402", row.line, f"`{row.text(0)}` has no type parameters, so it is called directly")
        return
    if not _check_instance_owner(m, ent):
        return
    args = [resolve_type(world, m, t.raw, row.line, instance_scope(m, ent)) for t in row.args[1:]]
    if len(args) != len(params):
        m.sink.error("R403", row.line, f"`{row.text(0)}` takes {len(params)} type argument(s), not {len(args)}")
        return
    for p, a in zip(params, args):
        if a is not None and p.endswith("@plain") and not world.plain(a):
            m.sink.error("R403", row.line, f"type parameter `{type_param_name(p)}` of `{row.text(0)}` is `plain`; "
                         f"`{_show(a)}` is not a plain type")
    if any(a is None for a in args):
        return
    # D-92: each instance of the generic operation's own types that its signature uses must be one the caller
    # declared too, so a value passed in has a type the caller names
    sig = header_sig(world, m, gen, quiet=True)
    sub = dict(zip(params, args))
    for t in [p.type for p in sig.inputs] + [sig.output, sig.raises]:
        _got, missing = world.rescope(m, t, sub, instance_owner(ent))
        if missing is not None:
            where = f"in {instance_owner(ent)}" if instance_owner(ent) else "in none"
            m.sink.error("R403", row.line, f"`{ent.name}` gives `{row.text(0)}` a signature that uses `{missing}`, "
                         f"which this module does not name here; declare a typeInstance stated `{where}` that "
                         f"instantiates `{missing}` (D-92)")
            return


def _check_instance_owner(m: Module, ent: Entity) -> bool:
    """D-92: `<instance> in <operation>` names a generic operation of this module, and the instance is not exported."""
    owner = instance_owner(ent)
    if owner is None:
        return True
    row = ent.fact("in")
    if owner not in m.ops:
        m.sink.error("R401", row.line, f"`{ent.name} in {owner}`: `{owner}` is not an operation of this module")
        return False
    if not type_params_of(m.ops[owner]):
        m.sink.error("R402", row.line, f"`{owner}` has no type parameters, so `{ent.name}` names concrete types "
                     f"only and belongs to the module: `{ent.name} in none`")
        return False
    if ent.name in m.exports:
        m.sink.error("R402", row.line, f"`{ent.name}` belongs to the generic operation `{owner}`, so it is not exported")
    return True


def instance_sig(world: World, m: Module, ent: Entity) -> Optional[Sig]:
    """The signature an `operationInstance` gives its callers (D-92: in the caller's own types)."""
    row = ent.fact("instantiates")
    gen = m.ops.get(row.text(0)) if row is not None else None
    if gen is None:
        return None
    params = list(type_params_of(gen).values())
    args = [resolve_type(world, m, t.raw, row.line, instance_scope(m, ent), quiet=True) for t in row.args[1:]]
    if any(a is None for a in args) or len(args) != len(params):
        return None  # the instance's own row is reported; its callers are not checked against a guess
    sub, owner = dict(zip(params, args)), instance_owner(ent)
    sig = header_sig(world, m, gen, quiet=True)
    t = lambda x: world.rescope(m, x, sub, owner)[0] if x else x  # noqa: E731
    return Sig(tuple(Param(p.name, t(p.type), p.mode) for p in sig.inputs), t(sig.output), sig.output_owner,
               t(sig.raises), sig.effects, sig.waits, sig.borrows, sig.scoped)


def finish_module(m: Module) -> None:
    for short, (_p, line) in m.imports.items():
        if short not in m.used_imports:
            m.sink.error("R404", line, f"module `{short}` is imported but nothing in `{m.short}` uses it")


def _contains_by_value(world: World, canon: Optional[str], target: str, seen: set, through: bool = False) -> bool:
    """True if a value of `canon` holds a `target` by value (through record fields or enum payloads), or, with
    `through`, also inside a collection it holds (the type arguments of a list, map, set, or channel)."""
    info = world.type_info(canon)
    if info is None or canon in seen:
        return False
    seen.add(canon)
    inner = [t for _n, t in info.fields] + [p for _n, p in info.variants if p is not None]
    if info.kind == "alias":
        inner.append(info.base)
    if through and info.generic is not None:
        inner += info.args
    return any(t == target or _contains_by_value(world, t, target, seen, through) for t in inner if t is not None)


def _no_resource_inside(world: World, m: Module, canon: Optional[str], line: int, what: str) -> None:
    """D-108: a resource (a file, a connection, a library) is owned by one operation and released by it; held in a
    record or an enum it could be copied, stored in a collection, or outlive its release."""
    info = world.type_info(canon)
    if info is not None and info.kind == "resource":
        m.sink.error("R403", line, f"{what} is `{_show(canon)}`, a resource; a resource is owned by one operation and "
                     "is never part of a record or an enum")


def _check_type_entity(world: World, m: Module, ent: Entity) -> None:
    tparams = type_params_of(ent)
    canon = f"{m.short}.{ent.name}"
    if ent.kind in ("record", "enum", "alias") and _contains_by_value(world, canon, canon, set()):
        m.sink.error("R403", ent.line, f"`{ent.name}` contains itself by value, so it would have no finite size; "
                     "refer to other values through a list and a typed index (LR-25 rule 5)")
    elif ent.kind in ("record", "enum") and _contains_by_value(world, canon, canon, set(), through=True):
        # D-60: one way to build trees and graphs: nodes in a list, referring to each other by a typed index
        m.sink.error("R403", ent.line, f"`{ent.name}` holds itself inside a collection; build a tree from a list "
                     "of nodes and an index alias (`<Alias> indexes <List>`), so nodes refer to each other by "
                     "position (D-60)")
    for r in ent.facts("field"):
        _no_resource_inside(world, m, resolve_type(world, m, r.text(1), r.line, tparams), r.line, f"field `{r.text(0)}`")
    for r in ent.facts("variant"):
        if r.text(1) != "none":
            _no_resource_inside(world, m, resolve_type(world, m, r.text(1), r.line, tparams), r.line,
                                f"variant `{r.text(0)}`")
    if ent.kind == "alias":
        base = resolve_type(world, m, ent.value("aliasOf"), ent.line)
        idx = ent.value("indexes")
        if idx not in (None, "none"):
            _check_index_alias(world, m, ent, base, resolve_type(world, m, idx, ent.line))
    if ent.kind == "operationType":
        _check_header(world, m, ent)
    if ent.kind == "typeInstance":
        row = ent.fact("instantiates")
        if row is None or not _check_instance_owner(m, ent):
            return
        gen = resolve_type(world, m, row.text(0), row.line, generic=True)
        args = [resolve_type(world, m, t.raw, row.line, instance_scope(m, ent)) for t in row.args[1:]]
        ginfo = world.type_info(gen)
        if gen is not None and (ginfo is None or not ginfo.type_params):
            m.sink.error("R402", row.line, f"`{row.text(0)}` is not generic, so it cannot be instantiated")
        elif ginfo is not None and len(args) != len(ginfo.type_params):
            m.sink.error("R403", row.line, f"`{row.text(0)}` takes {len(ginfo.type_params)} type argument(s), "
                         f"not {len(args)}")
        elif ginfo is not None:
            for p, a in zip(ginfo.type_params, args):
                if a is not None and p.endswith("@plain") and not world.plain(a):
                    m.sink.error("R403", row.line, f"type parameter `{type_param_name(p)}` of `{row.text(0)}` is "
                                 f"`plain`; `{a}` is not a plain type")
                elif a is not None and not fits_constraint(p, a, world.plain):
                    what = "an item" if gen == "set.Set" else "a key"
                    m.sink.error("R403", row.line, f"{what} of `{row.text(0)}` is a plain value or a `String`; `{a}` "
                                 "is neither (D-61, D-93)")
            if gen == "ffi.Function" and args and args[0] is not None:
                _check_foreign(world, m, row, args[0])
            for a in args:
                ai = world.type_info(a) if a is not None else None
                if ai is not None and ai.kind == "resource" and gen != "ffi.Function":
                    m.sink.error("R403", row.line, f"`{a}` is a resource, owned by one operation and released by it; it "
                                 f"cannot be stored in `{row.text(0)}`, which a region releases without closing it")


def _check_index_alias(world: World, m: Module, ent: Entity, base: Optional[str], listed: Optional[str]) -> None:
    """D-60: `<Alias> indexes <List>` makes the alias the position type of one list type of the same module."""
    row = ent.fact("indexes")
    line = row.line if row is not None else ent.line
    if listed is None:
        return
    info = world.type_info(listed)
    if info is None or info.kind != "instance" or info.generic != "list.List" or not listed.startswith(f"{m.short}."):
        m.sink.error("R403", line, f"`indexes` names a `list.List` type declared in this module; "
                     f"`{ent.value('indexes')}` is not one")
        return
    if base is not None and base != "Int64":
        m.sink.error("R403", line, f"an index alias is `aliasOf Int64`; `{ent.name}` is `aliasOf {ent.value('aliasOf')}`")
    first = world.index_aliases(m, listed)
    if first and first[0] is not ent:
        m.sink.error("R403", line, f"`{ent.value('indexes')}` is already indexed by `{first[0].name}` on line "
                     f"{first[0].line}; a list type has one index alias")


def _import_paths(target: Module, importer: Module) -> set:
    """How `importer` may name `target`: by its full path, or by its path inside the package they share (D-34)."""
    paths = {target.path}
    if getattr(target, "package", "") == getattr(importer, "package", ""):
        paths.add(getattr(target, "local_path", target.path))
    return paths


def _check_foreign(world: World, m: Module, row, canon: str) -> None:
    """A foreign function's type is an operation type over numbers and `Bool` that raises nothing, waits for
    nothing, and has no effects: only values the C ABI passes as they are cross the boundary."""
    from .library import FOREIGN_TYPES
    info = world.type_info(canon)
    if info is None or info.kind != "operationType" or info.sig is None:
        m.sink.error("R403", row.line, f"`ffi.Function` takes an operation type; `{canon}` is not one")
        return
    sig = info.sig
    bad = [p.type for p in sig.inputs if p.type not in FOREIGN_TYPES or p.mode != "copied"]
    if sig.output is not None and sig.output not in FOREIGN_TYPES:
        bad.append(sig.output)
    if bad:
        m.sink.error("R403", row.line, f"a foreign function takes and returns numbers or `Bool` by value; "
                     f"`{canon}` uses {', '.join(f'`{b}`' for b in bad)}")
    if sig.raises or sig.effects or sig.waits or sig.output_owner:
        m.sink.error("R403", row.line, f"a foreign function's type raises nothing, has no effects, and waits for "
                     f"nothing; `{canon}` does not say so")


def _check_table(world: World, m: Module, ent: Entity) -> None:
    sink = m.sink
    rec = resolve_type(world, m, ent.value("rowType"), ent.line)
    info = world.type_info(rec)
    if rec is not None and (info is None or info.kind != "record"):
        sink.error("R306", ent.line, f"a table holds records; `{ent.value('of')}` is not a record")
        return
    fields = dict(info.fields) if info else {}
    rows: dict[str, int] = {}
    positions: dict[str, int] = {}
    for r in ent.facts("row"):
        rid, pos = r.text(0), r.text(1)
        if rid in rows:
            sink.error("R306", r.line, f"row `{rid}` is already declared on line {rows[rid]}")
        if pos in positions:
            sink.error("R306", r.line, f"position {pos} is already used by line {positions[pos]}")
        rows[rid], positions[pos] = r.line, r.line
    if sorted(int(p) for p in positions) != list(range(1, len(positions) + 1)):
        sink.error("R306", ent.line, "row positions must be 1, 2, 3, ... with no gaps")
    seen: dict[tuple[str, str], int] = {}
    for r in ent.facts("cell"):
        rid, fld, val = r.text(0), r.text(1), r.args[2]
        if rid not in rows:
            sink.error("R306", r.line, f"cell names row `{rid}`, which no `row` row declares")
        if fld not in fields:
            sink.error("R306", r.line, f"`{ent.value('of')}` has no field `{fld}`")
            continue
        if (rid, fld) in seen:
            sink.error("R306", r.line, f"cell `{rid} {fld}` is already set on line {seen[(rid, fld)]}")
        seen[(rid, fld)] = r.line
        _check_value_token(world, m, val, fields[fld], r.line, f"field `{fld}`")
    for rid in rows:
        for fld in fields:
            if (rid, fld) not in seen:
                sink.error("R306", ent.line, f"row `{rid}` has no cell for field `{fld}`")


def _check_value_token(world: World, m: Module, tok, canon: Optional[str], line: int, what: str,
                       tparams=None) -> None:
    """A literal, a variant, or the name of a module operation (as an operation reference)."""
    if canon is None:
        return
    if tok.kind == "word" and S.is_variant(tok.raw):
        v = resolve_variant(world, m, tok.raw, line, tparams=tparams)
        if v is not None and v[0] != canon:
            m.sink.error("R403", line, f"{what} is `{_show(canon)}`, but `{tok.raw}` is a `{_show(v[0])}`")
        if v is not None and v[2] is not None:
            m.sink.error("R403", line, f"variant `{tok.raw}` carries a payload, so it cannot be written as a value")
        return
    if tok.kind == "word" and S.is_name(tok.raw):
        if tok.raw in m.ops:
            _check_op_reference(world, m, tok.raw, canon, line, what)
        else:
            m.sink.error("R401", line, f"`{tok.raw}` is not a literal or an operation of this module")
        return
    info = world.type_info(canon)
    if info is not None and info.kind == "alias" and info.index is not None:
        m.sink.error("R403", line, f"{what} is `{_show(canon)}`, a position in `{_show(info.index)}`; a position has "
                     f"no literal, it comes from `{_show(info.index).rsplit('.', 1)[-1]}.appendIndexed` (D-60)")
        return
    if not literal_fits(world, tok, canon):
        m.sink.error("R403", line, f"{what} is `{_show(canon)}`; `{tok.raw}` is not a valid `{_show(canon)}` literal")


def _check_op_reference(world: World, m: Module, op_name: str, canon: Optional[str], line: int, what: str) -> None:
    info = world.type_info(canon)
    if info is None or info.kind != "operationType":
        m.sink.error("R403", line, f"{what} is `{_show(canon)}`, but `{op_name}` is an operation")
        return
    world.taken.setdefault(canon, set()).add((m.short, op_name))
    want = info.sig
    got = header_sig(world, m, m.ops[op_name], quiet=True)
    if want is None:
        return
    problems = []
    if [(p.name, p.type, p.mode) for p in got.inputs] != [(p.name, p.type, p.mode) for p in want.inputs]:
        problems.append("its inputs differ")
    for attr, label in (("output", "output"), ("output_owner", "outputOwnedBy"), ("raises", "raises"), ("waits", "async")):
        if getattr(got, attr) != getattr(want, attr):
            problems.append(f"its `{label}` differs")
    if not got.effects <= want.effects:
        problems.append("it has effects the type does not allow")
    if problems:
        m.sink.error("R403", line, f"operation `{op_name}` does not match `{_show(canon)}`: " + "; ".join(problems))


def _show(canon: Optional[str]) -> str:
    return type_param_name(canon) if canon else "?"


# ---------------------------------------------------------------- operations

def _check_header(world: World, m: Module, ent: Entity) -> None:
    sink = m.sink
    tp = type_params_of(ent)
    inputs = {}
    for r in ent.facts("input"):
        if r.text(0) == "none":
            continue
        t = resolve_type(world, m, r.text(1), r.line, tp)
        inputs[r.text(0)] = t
        _check_mode(world, m, t, r.text(2), r.line, f"input `{r.text(0)}`")
    out = ent.value("output")
    out_t = None if out in (None, "none") else resolve_type(world, m, out, ent.fact("output").line, tp)
    owner = ent.value("outputOwnedBy")
    oline = ent.fact("outputOwnedBy").line if ent.fact("outputOwnedBy") else ent.line
    if out_t is None or world.plain(out_t):
        if owner not in (None, "none"):
            sink.error("R409", oline, "`outputOwnedBy` is `none` when there is no output or the output is a plain value")
    else:
        info = world.type_info(out_t)
        if info is not None and info.kind == "resource":
            if owner != "caller":
                sink.error("R409", oline, f"`{out}` is a resource, so `outputOwnedBy caller` hands it to the caller")
        elif owner == "caller" or owner == "none" or owner not in inputs or inputs[owner] != "Region":
            sink.error("R409", oline, f"`{out}` is region-owned, so `outputOwnedBy` names the `Region` input it is "
                       "allocated in")
    raises = ent.value("raises")
    if raises not in (None, "none"):
        rt = resolve_type(world, m, raises, ent.fact("raises").line, tp)
        info = world.type_info(rt)
        if rt is not None and (info is None or info.kind not in ("enum",)):
            sink.error("R403", ent.fact("raises").line, f"`raises` names an error enum; `{raises}` is not an enum")
        elif rt is not None and not world.plain(rt):
            # D-108: an error leaves its operation through `return error`, and no region is named for it, so it
            # carries only plain values (numbers, positions, flags); text in it would outlive its region
            sink.error("R403", ent.fact("raises").line, f"an error carries only plain values; `{raises}` holds text "
                       "or a collection, which would outlive the region it was made in. Carry a position or a code, "
                       "and report the text where it is known")


def _check_mode(world: World, m: Module, t: Optional[str], mode: str, line: int, what: str) -> None:
    if t is None:
        return
    if t == "Region":
        if mode != "borrowed":
            m.sink.error("R406", line, f"{what} is a `Region`, which is always `borrowed`")
        return
    if world.plain(t) and mode != "copied":
        m.sink.error("R406", line, f"{what} has the plain type `{_show(t)}`, so it is passed as `value`")
    if not world.plain(t) and mode == "copied":
        m.sink.error("R406", line, f"{what} has the non-plain type `{_show(t)}`, so it cannot be copied; use "
                     "`borrowed`, `borrowedMutable`, or `owned`")


def _owned_by(m: Module) -> dict[str, list[Entity]]:
    """Owned entities grouped by the operation their `in` row names, built once per module (D-106)."""
    index = getattr(m, "_owned_index", None)
    if index is None or index[0] != len(m.owned):
        groups: dict[str, list[Entity]] = {}
        for o in m.owned:
            groups.setdefault(o.owner, []).append(o)
        index = (len(m.owned), groups)
        m._owned_index = index  # type: ignore[attr-defined]
    return index[1]


def _build_op(world: World, m: Module, ent: Entity) -> OpInfo:
    sink = m.sink
    info = OpInfo(ent, m)
    info.tparams = type_params_of(ent)
    tp = info.tparams
    info.sig = header_sig(world, m, ent, quiet=True)
    info.output = info.sig.output
    info.raises = info.sig.raises
    names: dict[str, int] = {}
    module_names = getattr(m, "_module_names", None)
    if module_names is None:  # the module's own names do not change once it is indexed (D-106)
        module_names = set(m.ops) | set(m.types) | set(m.tables) | set(m.capabilities) | set(m.tests) \
            | set(m.op_instances) | set(m.constants)
        m._module_names = module_names  # type: ignore[attr-defined]

    def claim(name: str, line: int, what: str) -> None:
        if name in names:
            sink.error("R411", line, f"`{name}` ({what}) is already used in `{ent.name}` on line {names[name]}; names "
                       "in one operation's scope are unique across labels, values, and owned entities")
        elif name in module_names:
            sink.error("R411", line, f"`{name}` ({what}) is already a module-level name")
        names.setdefault(name, line)

    if ent.kind == "test" and tp:
        sink.error("R604", ent.fact("typeParameter").line, "a test is not generic; it states `typeParameter none`")
    for r in ent.facts("input"):
        if r.text(0) != "none":
            t = resolve_type(world, m, r.text(1), r.line, tp, quiet=True)
            info.bindings[r.text(0)] = Binding(r.text(0), t, "input", r.line, mode=r.text(2))
            claim(r.text(0), r.line, "input")
    for c in m.constants.values():
        # D-103: every operation of the module sees the module's constants as immutable values set on entry
        row = c.fact("value")
        if row is None or c.fact("type") is None:
            continue
        t = resolve_type(world, m, c.value("type"), c.line, quiet=True)
        info.bindings[c.name] = Binding(c.name, t, "let", c.line, mutable=False, literal=literal_value(row.args[0]))
    for r in ent.facts("let"):
        if r.text(0) == "none":
            continue
        t = resolve_type(world, m, r.text(1), r.line, tp)
        tok = r.args[2]
        lit = None
        if r.text(3) == "immutable" and (tok.kind == "string" or not S.is_name(tok.raw)):
            lit = literal_value(tok)
        info.bindings[r.text(0)] = Binding(r.text(0), t, "let", r.line, mutable=r.text(3) == "mutable",
                                           unset=tok.raw == "unset", literal=lit)
        claim(r.text(0), r.line, "let")
    for r in ent.facts("at"):
        lab = r.text(0)
        if lab not in info.labels:
            info.labels.append(lab)
    for lab in info.labels:
        claim(lab, ent.line, "label")
    for o in _owned_by(m).get(ent.name, ()):
        claim(o.name, o.line, o.kind)
        info.owned[o.name] = o
        if o.kind == "region":
            info.bindings[o.name] = Binding(o.name, "Region", "region", o.line)
        elif o.kind == "taskGroup":
            info.bindings[o.name] = Binding(o.name, None, "group", o.line)
            crow = o.fact("catch")
            if crow is not None and crow.text(0) != "none":
                t = resolve_type(world, m, crow.text(1), crow.line)
                info.bindings[crow.text(0)] = Binding(crow.text(0), t, "catch", crow.line)
                claim(crow.text(0), crow.line, f"error of task group `{o.name}`")
    for o in info.owned.values():
        if o.kind in ("call", "task"):
            ci = _build_call(world, m, info, o)
            info.calls[o.name] = ci
            if ci.out:
                b = o.value("borrows")
                info.bindings[ci.out[0]] = Binding(ci.out[0], ci.out[1], "out", o.fact("result").line,
                                                   view_of=None if b in (None, "none") else b)
                claim(ci.out[0], o.fact("result").line, f"result of `{o.name}`")
            if ci.catch:
                info.bindings[ci.catch[0]] = Binding(ci.catch[0], ci.catch[1], "catch", o.fact("catch").line)
                claim(ci.catch[0], o.fact("catch").line, f"error of `{o.name}`")
    for r in ent.facts("at"):
        verb = r.text(1)
        # at-row payload: <label> case <variant> bind <name> <Type> goto <label>
        if verb == "case" and r.text(4) != "none":
            t = resolve_type(world, m, r.text(5), r.line, tp)
            info.bindings[r.text(4)] = Binding(r.text(4), t, "bind", r.line)
            claim(r.text(4), r.line, "case binding")
        # at-row payload: <label> branch ifNext <collection> bind <name> <Type> goto ...
        if verb == "branch" and r.text(2) == "ifNext":
            t = resolve_type(world, m, r.text(6), r.line, tp)
            view = None if world.plain(t) else r.text(3)
            info.bindings[r.text(5)] = Binding(r.text(5), t, "bind", r.line, view_of=view)
            claim(r.text(5), r.line, "loop item")
    return info


def _build_call(world: World, m: Module, op: OpInfo, ent: Entity) -> CallInfo:
    tp = op.tparams
    args = []
    for r in ent.facts("argument"):
        if r.text(0) != "none":
            args.append((r.text(0), resolve_type(world, m, r.text(1), r.line, tp), r.text(2), r.text(3), r.line))
    outr, catchr = ent.fact("result"), ent.fact("catch")
    out = None
    if outr is not None and outr.text(0) != "none":
        out = (outr.text(0), resolve_type(world, m, outr.text(1), outr.line, tp))
    catch = None
    if catchr is not None and catchr.text(0) != "none":
        catch = (catchr.text(0), resolve_type(world, m, catchr.text(1), catchr.line, tp))
    ref = ent.value("invokesReference")
    sig, callee = None, None
    inv = ent.fact("invokes")
    if inv is not None:
        sig, callee = resolve_target(world, m, inv.text(0), inv.line, args=args, scope=tp)
    return CallInfo(ent, sig, args, out, catch, ref, callee)


def resolve_target(world: World, m: Module, text: str, line: int, quiet: bool = False, args=None, scope=None):
    """`scope`: the type parameters of the operation the call belongs to (D-92: what its instances may name)."""
    sink = m.sink

    def err(code, msg):
        if not quiet:
            sink.error(code, line, msg)
        return None, None

    def member(canon: str, name: str, shown: str):
        if name == "with":
            return _with_sig(world, m, canon, shown, args or [], line, quiet)
        sig = world.members(canon).get(name)
        if sig is None:
            return err("R401", f"type `{shown}` has no target `{name}`")
        return sig, None

    parts = text.split(".")
    if len(parts) == 1:
        if text in m.test_helpers:
            owner = getattr(scope, "owner", None)
            if owner not in m.tests and owner not in m.test_helpers:
                return err("R402", f"`{text}` is a test helper (declared in the test file); only tests and other "
                           "test helpers invoke it (D-112)")
        if text in m.ops:
            if type_params_of(m.ops[text]):
                return err("R402", f"`{text}` is generic; call it through an `operationInstance` that names its "
                           "type arguments")
            return header_sig(world, m, m.ops[text], quiet=True), text
        if text in m.op_instances:
            inst = m.op_instances[text]
            owner = instance_owner(inst)
            if owner is not None and getattr(scope, "owner", None) != owner:
                return err("R402", f"`{text}` belongs to the generic operation `{owner}` (`{text} in {owner}`), so "
                           f"only calls in `{owner}` invoke it (D-92)")
            gen = inst.value("instantiates")
            return instance_sig(world, m, inst), gen
        if text in m.tests:
            return err("R402", f"`{text}` is a test; tests are run by the test runner, not invoked")
        return err("R401", f"`{text}` is not an operation of this module")
    if len(parts) == 2 and parts[0] in m.tables:
        # D-104: a table is a fixed array of rows: read one by its row number (1 to n, as its `row` rows number
        # them), or ask how many there are
        table = m.tables[parts[0]]
        rec = resolve_type(world, m, table.value("rowType"), table.line, quiet=True)
        if parts[1] == "rowAt":
            return Sig((Param("position", "Int64", "copied"),), rec, raises="list.IndexOutOfRange"), None
        if parts[1] == "length":
            return Sig((), "Int64"), None
        if parts[1] == "find":
            # D-111: the first row whose first field equals the key; the first field is the table's key
            info = world.type_info(rec) if rec else None
            key = info.fields[0][1] if info is not None and info.fields else None
            if key not in ("Int64", "String", "Byte", "Bool"):
                return err("R401", f"table `{parts[0]}` has no `find`: its first field is `{key}`, and `find` "
                           "compares a key of `Int64`, `String`, `Byte`, or `Bool`")
            return Sig((Param("key", key, "borrowed" if key == "String" else "copied"),), rec,
                       raises="list.NotFound"), None
        return err("R401", f"table `{parts[0]}` has the targets `rowAt`, `length`, and `find`, not `{parts[1]}`")
    if len(parts) == 2 and S.UPPER.match(parts[0]):
        canon = resolve_type(world, m, parts[0], line, scope, quiet=quiet)
        if canon is None:
            return None, None
        return member(canon, parts[1], parts[0])
    mod = parts[0]
    if mod not in m.imports:
        return err("R404", f"`{text}` uses module `{mod}`, which `{m.short}` does not import")
    m.used_imports.add(mod)
    if len(parts) == 3:
        canon = resolve_type(world, m, f"{mod}.{parts[1]}", line, quiet=quiet)
        if canon is None:
            return None, None
        return member(canon, parts[2], f"{mod}.{parts[1]}")
    name = parts[1]
    if mod in world.modules:
        other = world.modules[mod]
        if name in other.op_instances and name in other.exports:
            return instance_sig(world, other, other.op_instances[name]), None
        if name not in other.ops:
            return err("R401", f"module `{mod}` has no operation `{name}`")
        if name not in other.exports:
            return err("R404", f"operation `{name}` is not exported by module `{mod}`")
        if type_params_of(other.ops[name]):
            return err("R402", f"`{text}` is generic; call it through an `operationInstance`")
        return header_sig(world, other, other.ops[name], quiet=True), None
    if mod not in LIBRARY:
        return err("R401", f"module `{mod}` is not part of this project, so it has no target `{name}`")
    sig = LIBRARY[mod].get("targets", {}).get(name)
    if sig is None:
        return err("R401", f"the standard module `{mod}` has no target `{name}`")
    return sig, None


def _with_sig(world: World, m: Module, canon: str, shown: str, args, line: int, quiet: bool):
    """LR-28 / A10: `<Record>.with` takes the record and one slot named by the field it changes."""
    info = world.type_info(canon)
    if info is None or info.kind != "record":
        if not quiet:
            m.sink.error("R401", line, f"`with` changes one field of a record; `{shown}` is not a record")
        return None, None
    fields = dict(info.fields)
    slots = [a[0] for a in args]
    if len(slots) != 2 or slots[0] != "record" or slots[1] not in fields:
        if not quiet:
            m.sink.error("R405", line, f"`{shown}.with` takes `record`, then one slot named by the field to change "
                         f"({', '.join(fields)})")
        return None, None
    f = slots[1]
    return Sig((Param("record", canon, world.mode_for(canon)), Param(f, fields[f], world.mode_for(fields[f]))), canon), None


def value_type(world: World, m: Module, op: OpInfo, name: str) -> tuple[str, Optional[str]]:
    """('binding', type) | ('op', None) | ('table', record type) | ('unknown', None)."""
    if name in op.bindings:
        return "binding", op.bindings[name].type
    if name in m.ops:
        return "op", None
    if name in m.tables:
        return "table", resolve_type(world, m, m.tables[name].value("rowType"), m.tables[name].line, quiet=True)
    return "unknown", None


def _check_op(world: World, m: Module, op: OpInfo) -> None:
    sink = m.sink
    ent = op.entity
    _check_header(world, m, ent)
    if ent.kind == "test":
        for pred in ("input", "output", "outputOwnedBy", "raises"):
            v = ent.value(pred)
            if v not in (None, "none"):
                sink.error("R604", ent.fact(pred).line, f"a test states `{pred} none`")
        for r in ent.facts("verifies"):
            target, inv_id = r.text(0), r.text(1)
            tgt = m.ops.get(target)
            if tgt is None:
                sink.error("R604", r.line, f"`verifies` names `{target}`, which is not an operation of module `{m.short}`")
            elif inv_id not in [x.text(0) for x in tgt.facts("invariant")]:
                sink.error("R604", r.line, f"operation `{target}` has no invariant `{inv_id}`")
            elif not any(ci.entity.value("invokes") == target for ci in op.calls.values()):
                sink.error("R604", r.line, f"test `{ent.name}` verifies `{target}` but never calls it; a test proves "
                           "an invariant by running the operation")
        if not any((ci.entity.value("invokes") or "").startswith("test.") for ci in op.calls.values()):
            sink.error("R604", ent.line, f"test `{ent.name}` asserts nothing; it calls at least one `test.` target")
    for r in ent.facts("let"):
        _check_let(world, m, op, r)
    effective: set = set()
    for ci in op.calls.values():
        _check_call(world, m, op, ci)
        sig = ci.sig
        if ci.reference is not None:
            sig = _reference_sig(world, m, op, ci)
        if sig is not None:
            effective |= set(sig.effects)
    _check_cleanups(world, m, op)
    declared = {(r.text(0), r.text(1)) for r in ent.facts("effect") if r.text(0) != "none"}
    eline = ent.fact("effect").line if ent.fact("effect") else ent.line
    for verb, res in sorted(effective - declared):
        sink.error("R407", eline, f"`{ent.name}` performs `{verb} {res}` through what it activates but does not "
                   f"declare `{ent.name} effect {verb} {res}`")
    for verb, res in sorted(declared - effective):
        sink.error("R407", eline, f"`{ent.name}` declares `effect {verb} {res}`, but nothing it activates performs it")
    _check_uses(m, op, declared)
    _check_exact_facts(world, m, op)
    _check_abi(m, op)


# D-123: what crosses the C boundary as it is: integers, `Byte`, `Bool`, `Float64`, and addresses
ABI_TYPES = ("Int64", "Int32", "Byte", "Bool", "Float64", "machine.Address")
C_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def abi_symbol(ent) -> Optional[str]:
    """The C symbol an operation is exported under (`abi c "<symbol>"`, D-123), or None."""
    row = ent.fact("abi")
    return row.args[1].value if row is not None and len(row.args) > 1 else None


def _check_abi(m: Module, op: OpInfo) -> None:
    """D-123: an operation exported to C takes and gives only values the C ABI passes as they are, raises nothing,
    and is neither generic nor async."""
    ent = op.entity
    row = ent.fact("abi")
    if row is None:
        return
    sink = m.sink
    symbol = abi_symbol(ent)
    if not C_SYMBOL.match(symbol or ""):
        sink.error("R402", row.line, f"`{symbol}` is not a C symbol: a letter or `_`, then letters, digits, and `_`")
    if op.tparams:
        sink.error("R402", row.line, f"`{ent.name}` is generic; an operation exported to C has one signature")
    if ent.value("raises") not in (None, "none"):
        sink.error("R402", row.line, f"`{ent.name}` raises an error; an operation exported to C raises nothing, since "
                   "C has no error values (return a status instead)")
    if ent.value("async") == "true":
        sink.error("R402", row.line, f"`{ent.name}` waits; an operation exported to C does not")
    if op.sig is None:
        return
    shown = ", ".join(f"`{t}`" for t in ABI_TYPES)
    for p in op.sig.inputs:
        if p.type not in ABI_TYPES:
            sink.error("R403", row.line, f"input `{p.name}` is `{_show(p.type)}`; an operation exported to C takes "
                       f"only {shown}")
    if op.sig.output is not None and op.sig.output not in ABI_TYPES:
        sink.error("R403", row.line, f"`{ent.name}` gives `{_show(op.sig.output)}`; an operation exported to C gives "
                   f"only {shown}, or nothing")


def check_abi_symbols(world: World) -> None:
    """D-123: one operation per C symbol in a program."""
    seen: dict[str, str] = {}
    for m in world.modules.values():
        for name, ent in m.ops.items():
            symbol = abi_symbol(ent)
            if symbol is None:
                continue
            if symbol in seen:
                m.sink.error("R402", ent.fact("abi").line, f"`{symbol}` is already the C symbol of `{seen[symbol]}`")
            else:
                seen[symbol] = f"{m.short}.{name}"


def _check_let(world: World, m: Module, op: OpInfo, r: Row) -> None:
    if r.text(0) == "none":
        return
    b = op.bindings.get(r.text(0))
    tok = r.args[2]
    if b is None or b.type is None:
        return
    if tok.raw == "unset":
        if not b.mutable:
            m.sink.error("R205", r.line, "`unset` is only for a `mutable` let; an immutable value needs its value")
        return
    if tok.kind == "word" and S.is_name(tok.raw):
        kind, t = value_type(world, m, op, tok.raw)
        if kind == "op":
            _check_op_reference(world, m, tok.raw, b.type, r.line, f"`{b.name}`")
        elif kind == "binding":
            src = op.bindings[tok.raw]
            if src.kind not in ("input", "let") or (src.kind == "let" and src.line > r.line):
                m.sink.error("R507", r.line, f"a let starts from a literal, an input, or an earlier let; `{tok.raw}` "
                             "is not set when the operation starts")
            elif t != b.type:
                m.sink.error("R403", r.line, f"`{b.name}` is `{_show(b.type)}`, but `{tok.raw}` is `{_show(t)}`")
            elif not world.plain(b.type):
                m.sink.error("R514", r.line, f"a let copies only plain values; `{b.name}` would be a second name for "
                             f"`{tok.raw}` (a `{_show(b.type)}`) and could outlive its loan; use `{tok.raw}` directly")
        else:
            m.sink.error("R401", r.line, f"`{tok.raw}` is not a value in `{op.entity.name}`")
        return
    _check_value_token(world, m, tok, b.type, r.line, f"`{b.name}`", op.tparams)


def _reference_sig(world: World, m: Module, op: OpInfo, ci: CallInfo) -> Optional[Sig]:
    b = op.bindings.get(ci.reference)
    line = ci.entity.fact("invokesReference").line
    if b is None:
        m.sink.error("R401", line, f"`{ci.reference}` is not a value in `{op.entity.name}`")
        return None
    info = world.type_info(b.type)
    if info is None or info.kind != "operationType":
        m.sink.error("R402", line, f"`invokesReference` needs a value whose type is an operationType; "
                     f"`{ci.reference}` is `{_show(b.type)}`")
        return None
    return info.sig


def _check_call(world: World, m: Module, op: OpInfo, ci: CallInfo) -> None:
    sink = m.sink
    ent = ci.entity
    sig = ci.sig if ci.reference is None else _reference_sig(world, m, op, ci)
    if sig is None:
        return
    if ent.kind == "call" and sig.waits:
        sink.error("R410", ent.line, f"`{ent.name}` can wait, so it is a task (started with `start`, finished with "
                   "`join`), not a call")
    # arguments, in signature order
    want = [p.name for p in sig.inputs]
    got = [a[0] for a in ci.args]
    if want != got:
        if not want:
            sink.error("R405", ent.line, f"`{ent.name}`'s target takes no arguments; write `{ent.name} argument none`")
        else:
            sink.error("R405", ent.line, f"`{ent.name}` passes ({', '.join(got) or 'none'}); its target takes "
                       f"({', '.join(want)}), in that order")
    params = {p.name: p for p in sig.inputs}
    passed: dict[str, str] = {}
    for slot, t, value, mode, line in ci.args:
        p = params.get(slot)
        if p is None:
            continue
        passed[slot] = value
        if t is not None and p.type is not None and t != p.type:
            sink.error("R403", line, f"argument `{slot}` is `{_show(p.type)}`, not `{_show(t)}`")
        expect_mode = S.MODE_PAIRS.get(p.mode)
        if mode != expect_mode:
            sink.error("R406", line, f"argument `{slot}` is passed as `{expect_mode}` (the target takes it "
                       f"`{p.mode}`), not `{mode}`")
        kind, vt = value_type(world, m, op, value)
        if kind == "op":
            _check_op_reference(world, m, value, p.type, line, f"argument `{slot}`")
        elif kind == "binding":
            if vt is not None and t is not None and vt != t:
                sink.error("R403", line, f"argument `{slot}` states `{_show(t)}`, but `{value}` is `{_show(vt)}`")
        elif kind == "table":
            sink.error("R402", line, f"`{value}` is a table; tables are read with `forEach`, not passed")
        else:
            sink.error("R401", line, f"`{value}` is not a value in `{op.entity.name}`")
    if sig is not None:
        _check_stored_regions(world, m, op, ci, sig)
    _check_loans(m, op, ci)
    if sig.scoped and sig.scoped in passed:
        _check_scope(m, op, ci, sig, passed[sig.scoped])
    # out and catch
    outr, catchr = ent.fact("result"), ent.fact("catch")
    if outr is not None:
        if sig.output is None and ci.out is not None:
            sink.error("R403", outr.line, f"`{ent.name}`'s target returns nothing; write `{ent.name} result none`")
        elif sig.output is not None and ci.out is None:
            sink.error("R403", outr.line, f"`{ent.name}`'s target returns `{_show(sig.output)}`; name it with "
                       f"`{ent.name} result <name> {_show(sig.output)}`")
        elif ci.out is not None and ci.out[1] is not None and ci.out[1] != sig.output:
            sink.error("R403", outr.line, f"`{ent.name}`'s target returns `{_show(sig.output)}`, not `{_show(ci.out[1])}`")
    if catchr is not None:
        if sig.raises is None and ci.catch is not None:
            sink.error("R403", catchr.line, f"`{ent.name}`'s target cannot fail; write `{ent.name} catch none`")
        elif sig.raises is not None and ci.catch is None:
            sink.error("R403", catchr.line, f"`{ent.name}`'s target raises `{_show(sig.raises)}`; catch it with "
                       f"`{ent.name} catch <name> {_show(sig.raises)}`")
        elif ci.catch is not None and ci.catch[1] is not None and ci.catch[1] != sig.raises:
            sink.error("R403", catchr.line, f"`{ent.name}`'s target raises `{_show(sig.raises)}`, not `{_show(ci.catch[1])}`")
    # ownership rows
    owner = op.entity.name
    if sig.output is None or world.plain(sig.output):
        exp_owned = "none"
    elif sig.output_owner == "caller":
        exp_owned = owner
    elif sig.output_owner:
        exp_owned = passed.get(sig.output_owner, "?")
    else:
        exp_owned = "none"
    _expect_row(m, ent, "ownedBy", exp_owned, "who owns the result")
    exp_borrows = passed.get(sig.borrows, "?") if sig.borrows else "none"
    _expect_row(m, ent, "borrows", exp_borrows, "which value the result is a view of")
    cleaned = ent.value("cleanedBy")
    crow = ent.fact("cleanedBy")
    if crow is not None:
        if exp_owned != owner and cleaned != "none":
            sink.error("R409", crow.line, f"only a result owned by `{owner}` has a cleanup; write "
                       f"`{ent.name} cleanedBy none`")
        if exp_owned == owner and cleaned != "none":
            c = op.owned.get(cleaned)
            if c is None or c.kind != "cleanup":
                sink.error("R409", crow.line, f"`cleanedBy {cleaned}` does not name a cleanup of `{owner}`")
            elif ci.out is not None and c.value("cleans") != ci.out[0]:
                sink.error("R409", crow.line, f"cleanup `{cleaned}` cleans `{c.value('cleans')}`, not `{ci.out[0]}`")
        if exp_owned == owner and cleaned == "none" and ci.out is not None:
            if not _value_leaves(op, ci.out[0]):
                sink.error("R409", crow.line, f"`{ci.out[0]}` is owned by `{owner}` and is neither cleaned up, given "
                           "away, nor returned")


COLLECTION_SLOTS = ("list", "map", "set", "channel")


def _region_of(op: OpInfo, name: str) -> Optional[str]:
    """The region a value lives in, when this operation can tell: the `ownedBy` region of the call or task that
    produced it, or the region itself when the value is a `Region` input lent in."""
    for c in op.calls.values():
        if c.out and c.out[0] == name:
            owner = c.entity.value("ownedBy")
            return owner if owner not in (None, "none", "caller") else None
    return None


def _check_stored_regions(world: World, m: Module, op: OpInfo, ci: CallInfo, sig: Sig) -> None:
    """D-107: a collection outlives what is stored in it only if what is stored lives in its region. Text, and text
    inside records and enum payloads, is copied into the collection's region when it is stored. A value that holds
    a list, map, set, or channel cannot be copied that way, so it must come from a call whose `ownedBy` names the
    same region as the collection's, in this operation."""
    params = {p.name: p for p in sig.inputs}

    def is_collection(t):
        info = world.type_info(t)
        return info is not None and info.kind == "instance" and info.generic in (
            "list.List", "map.Map", "set.Set", "channel.Channel")
    # D-108: the collection is found by its type (a list, map, set, or channel lent exclusively), not by its slot
    coll = next(((slot, value) for slot, _t, value, mode, _l in ci.args
                 if slot in params and is_collection(params[slot].type) and mode == "lendMutable"), None)
    if coll is None:
        return
    for slot, t, value, mode, line in ci.args:
        p = params.get(slot)
        if mode != "give" or p is None or p.mode != "owned" or slot == coll[0]:
            continue
        typ = world.type_info(p.type)
        if world.plain(p.type) or (typ is not None and typ.kind == "resource") or not world.holds_container(p.type):
            continue  # plain values are copied; text inside a value is copied into the collection's region
        where, home = _region_of(op, value), _region_of(op, coll[1])
        if where is None or home is None or where != home:
            m.sink.error("R514", line, f"`{value}` is stored in `{coll[1]}`, so it must live in the same region; "
                         f"{'its region is `' + where + '`' if where else 'its region is not known here'}, and "
                         f"`{coll[1]}`'s is {'`' + home + '`' if home else 'not known here'}. Make it in the "
                         "collection's region in this operation (or return it to the operation that owns the "
                         "collection, allocated in a region that operation passes in)")


def _check_loans(m: Module, op: OpInfo, ci: CallInfo) -> None:
    """LR-31 rule 1: an exclusive loan is the only use of its value in the call, and only a value
    the operation may change can be lent exclusively."""
    for slot, _t, value, mode, line in ci.args:
        if mode != "lendMutable":
            continue
        others = [s for s, _t2, v, _m, _l in ci.args if v == value and s != slot]
        if others:
            m.sink.error("R515", line, f"`{value}` is lent exclusively to `{slot}` and also passed to "
                         f"{', '.join(f'`{o}`' for o in others)} in the same call")
        b = op.bindings.get(value)
        if b is None:
            continue
        if b.kind == "input" and b.mode != "borrowedMutable" and b.mode != "owned":
            m.sink.error("R515", line, f"`{value}` is a `{b.mode}` input, so it cannot be lent exclusively; take it "
                         "`borrowedMutable` to change it")
        if b.view_of is not None:
            m.sink.error("R515", line, f"`{value}` is a view of `{b.view_of}`, so it cannot be lent exclusively")


def address_within(address: str, scope: str) -> bool:
    """A `net.outbound` scope names a host (any port) or a host and port; it never matches a longer name or
    port that merely starts the same way (`127.0.0.1:80` does not allow `127.0.0.1:8080`)."""
    if address == scope:
        return True
    if not address.startswith(scope):
        return False
    return scope.endswith((":", "/")) or address[len(scope)] in ":/"


def _check_scope(m: Module, op: OpInfo, ci: CallInfo, sig: Sig, value: str) -> None:
    """LR-34 rule 5: a literal argument outside every granting capability's scope is a check error."""
    b = op.bindings.get(value)
    if b is None or b.literal is None:
        return  # a computed value is checked at run time, before the call happens (D-38)
    lit = b.literal
    if any(r in ("fs.files",) for _v, r in sig.effects) and ".." in str(lit).replace("\\", "/").split("/"):
        m.sink.error("R408", ci.entity.line, f"`{ci.entity.name}` passes `{lit}`, whose `..` would step out of "
                     "the capability's scope; name the file directly")
        return
    resources = [(v, r) for v, r in sig.effects if r in SCOPED_RESOURCES]
    for verb, res in resources:
        kind = SCOPED_RESOURCES[res]
        scopes = []
        for r in op.entity.facts("uses"):
            cap = m.capabilities.get(r.text(0))
            if cap is None:
                continue
            scopes += [grant_scope(g) for g in cap.facts("grants")
                       if (g.text(0), g.text(1)) == (verb, res) and grant_scope(g) is not None]
        ok = False
        for s in scopes:
            if kind == "port":
                ok = ok or s.rsplit(":", 1)[-1] == str(lit)
            elif res == "fs.files":
                ok = ok or path_within(str(lit), s, resolve=False)
            elif kind == "prefix" and res == "net.outbound":
                ok = ok or address_within(str(lit), s)
            elif kind == "prefix":
                ok = ok or str(lit).startswith(s)
            else:
                ok = ok or str(lit) == s
        if scopes and not ok:
            m.sink.error("R408", ci.entity.line, f"`{ci.entity.name}` passes `{lit}`, which is outside the scope "
                         f"{', '.join(repr(s) for s in scopes)} of every capability granting `{verb} {res}`")


def _expect_row(m: Module, ent: Entity, pred: str, expected: str, what: str) -> None:
    row = ent.fact(pred)
    if row is None or expected == "?":
        return
    if row.text(0) != expected:
        m.sink.error("R409", row.line, f"`{ent.name} {pred}` states {what}; it is `{expected}`, not `{row.text(0)}`")


def _value_leaves(op: OpInfo, name: str) -> bool:
    """Weak form of the LR-20 rule 6 linear check: the value is given away or returned somewhere.
    The per-path version is not implemented yet (see Part 4 of the notes)."""
    for ci in op.calls.values():
        if any(a[2] == name and a[3] == "give" for a in ci.args):
            return True
    return any(r.text(1) == "return" and r.text(3) == name for r in op.entity.facts("at"))


def _check_cleanups(world: World, m: Module, op: OpInfo) -> None:
    sink = m.sink
    for c in op.owned.values():
        if c.kind != "cleanup":
            continue
        worker, cleans = c.value("runs"), c.value("cleans")
        b = op.bindings.get(cleans)
        owned_input = b is not None and b.kind == "input" and b.mode == "owned"
        owned_out = any(ci.out and ci.out[0] == cleans and ci.entity.value("ownedBy") == op.entity.name
                        for ci in op.calls.values())
        if not (owned_input or owned_out):
            sink.error("R409", (c.fact("cleans") or c).line, f"cleanup `{c.name}` cleans `{cleans}`, which `{op.entity.name}` "
                       "does not own (an `owned` input or a result with `ownedBy " + op.entity.name + "`)")
        w = op.calls.get(worker)
        if w is None or w.entity.kind != "call":
            sink.error("R402", (c.fact("runs") or c).line, f"cleanup `{c.name}` runs `{worker}`, which is not a call of "
                       f"`{op.entity.name}`")
        elif not any(a[2] == cleans and a[3] == "give" for a in w.args):
            sink.error("R409", (c.fact("runs") or c).line, f"the cleanup's call `{worker}` must take `{cleans}` with `give`")
        for ci in op.calls.values():
            if ci.out and ci.out[0] == cleans and ci.entity.value("cleanedBy") != c.name:
                row = ci.entity.fact("cleanedBy")
                sink.error("R409", row.line if row is not None else ci.entity.line,
                           f"cleanup `{c.name}` cleans `{cleans}`, so `{ci.entity.name} cleanedBy` names it, "
                           f"not `{ci.entity.value('cleanedBy')}`")


def _check_uses(m: Module, op: OpInfo, declared: set) -> None:
    sink = m.sink
    ent = op.entity
    granted: set = set()
    caps = []
    for r in ent.facts("uses"):
        n = r.text(0)
        if n == "none":
            if declared:
                sink.error("R408", r.line, f"`{ent.name}` has effects, so `uses` names the capabilities that grant them")
            continue
        cap = m.capabilities.get(n)
        if cap is None:
            sink.error("R401", r.line, f"`{n}` is not a capability of this module")
            continue
        g = {(x.text(0), x.text(1)) for x in cap.facts("grants")}
        caps.append((n, r.line, g))
        granted |= g
    for verb, res in sorted(declared - granted):
        sink.error("R408", ent.fact("effect").line, f"effect `{verb} {res}` is not granted by any capability "
                   f"in `{ent.name}`'s `uses` rows")
    for n, line, g in caps:
        if not g & declared:
            sink.error("R408", line, f"capability `{n}` grants nothing `{ent.name}` does")


def _check_exact_facts(world: World, m: Module, op: OpInfo) -> None:
    sink = m.sink
    ent = op.entity
    steps = [r.text(1) for r in ent.facts("at")]
    waits = any(v in ("join", "awaitSlot") for v in steps)
    arow = ent.fact("async")
    if arow is not None and (arow.text(0) == "true") != waits:
        sink.error("R410", arow.line, f"`async` is `true` exactly when the operation has a `join` or `awaitSlot` "
                   f"step; `{ent.name}` should state `async {'true' if waits else 'false'}`")
    heap = any(o.kind == "region" for o in op.owned.values()) or \
        any(b.kind == "input" and b.type == "Region" for b in op.bindings.values())
    mrow = ent.fact("memoryHeap")
    if mrow is not None and (mrow.text(0) == "true") != heap:
        sink.error("R410", mrow.line, f"`memoryHeap` is `true` exactly when the operation owns a region or takes "
                   f"one as input; `{ent.name}` should state `memoryHeap {'true' if heap else 'false'}`")


def check_recursion(world: World) -> None:
    """LR-12: an operation that can reach itself states `maxRecursion <depth>`, and one that cannot states
    `maxRecursion none`. Reaching follows direct calls (within a module and across modules) and calls through
    operation references: invoking a reference of an operationType may call any operation used as a value of
    that type anywhere in the program, so a cycle through a reference counts."""
    graph: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for m in world.modules.values():
        for name, info in m.op_infos.items():
            out = graph.setdefault((m.short, name), set())
            for ci in info.calls.values():
                if ci.callee_op:
                    out.add((m.short, ci.callee_op))
                inv = ci.entity.fact("invokes")
                if inv is not None and inv.text(0).count(".") == 1:
                    mod, op = inv.text(0).split(".")
                    other = world.modules.get(mod)
                    if other is not None and op in other.op_instances:
                        op = other.op_instances[op].value("instantiates")
                    if other is not None:
                        out.add((mod, op))
                if ci.reference is not None:
                    b = info.bindings.get(ci.reference)
                    if b is not None:
                        out |= world.taken.get(b.type, set())
    for m in world.modules.values():
        _check_recursion(world, m, graph)


def _check_recursion(world: World, m: Module, graph: dict) -> None:
    for name, info in m.op_infos.items():
        start = (m.short, name)
        seen, stack, recursive = set(), list(graph.get(start, ())), False
        while stack:
            cur = stack.pop()
            if cur == start:
                recursive = True
                break
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(graph.get(cur, ()))
        row = info.entity.fact("maxRecursion")
        if row is None:
            continue
        if recursive and row.text(0) == "none":
            m.sink.error("R410", row.line, f"`{name}` can call itself, so it states `maxRecursion <depth>`")
        if not recursive and row.text(0) != "none":
            m.sink.error("R410", row.line, f"`{name}` cannot call itself, so it states `maxRecursion none`")
