"""Names, types, signatures, ownership rows, and exact declared facts.

Covers enforcement-plan steps 3, 4, 6, and the static half of 8:
- every name resolves, and resolves to the right kind of thing (LR-02, LR-32);
- every stated type matches what it describes (LR-05);
- every call's arguments match the target's parameters, in order, with the
  paired passing mode (LR-20, LR-31);
- `out`, `catch`, `ownedBy`, `cleanedBy`, and `borrows` agree with the target;
- `effect`, `uses`, `async`, `memory heap`, and `maxRecursion` state exactly
  what the operation does (LR-07, LR-10, LR-20, LR-22, LR-33).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import shapes as S
from .diagnostics import Sink
from .library import (BUILTINS, FLOAT_TYPES, INTEGER_RANGES, LIBRARY, SCOPED_RESOURCES, Param, Sig, TypeInfo,
                      generic_members, type_param_name)
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
        self.tables: dict[str, Entity] = {}
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

    # ------------------------------------------------------------ types

    def type_info(self, canon: Optional[str]) -> Optional[TypeInfo]:
        if canon is None:
            return None
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
        return "value" if self.plain(canon) else "borrowed"

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
            return TypeInfo(canon, "alias", None, base=resolve_type(self, m, ent.value("for"), ent.line, quiet=True))
        if ent.kind == "operationType":
            return TypeInfo(canon, "operationType", True, sig=header_sig(self, m, ent, quiet=True))
        if ent.kind == "instance":
            row = ent.fact("instantiates")
            if row is None:
                return None
            gen = resolve_type(self, m, row.text(0), row.line, quiet=True)
            args = [resolve_type(self, m, t.raw, row.line, quiet=True) for t in row.args[1:]]
            ginfo = self.type_info(gen)
            info = TypeInfo(canon, "instance", None, generic=gen, args=args)
            if ginfo is not None and ginfo.kind in ("record", "enum") and ginfo.type_params:
                sub = dict(zip(ginfo.type_params, args))
                info.kind = ginfo.kind
                info.fields = [(n, sub.get(t, t)) for n, t in ginfo.fields]
                info.variants = [(n, sub.get(p, p) if p else None) for n, p in ginfo.variants]
            elif ginfo is not None and ginfo.kind == "generic":
                sub = dict(zip(ginfo.type_params, args))
                info.variants = [(n, sub.get(p, p) if p else None) for n, p in ginfo.variants]
                info.targets = generic_members(gen, canon, args, self.plain)
                if gen != "option.Option":
                    info.plain = False
            return info
        return None

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
        if info.kind in ("enum", "instance") and info.variants and not info.type_params:
            for n, p in info.variants:
                out[n] = Sig(() if p is None else (Param("payload", p, "value" if self.plain(p) else "owned"),), canon)
            out["equals"] = Sig((Param("left", canon, mode(canon)), Param("right", canon, mode(canon))), "Bool")
        return out


# ---------------------------------------------------------------- resolution helpers

def type_params_of(ent: Entity) -> dict[str, str]:
    """`T typeParam plain` -> {"T": "T@plain"}."""
    return {r.text(0): f"{r.text(0)}@{r.text(1)}" for r in ent.facts("typeParam") if r.text(0) != "none"}


def resolve_type(world: World, m: Module, text: Optional[str], line: int, tparams=None, quiet: bool = False) -> Optional[str]:
    tparams = tparams or {}
    if text is None:
        return None
    sink = m.sink

    def err(code, msg):
        if not quiet:
            sink.error(code, line, msg)

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
            return text
        lib = LIBRARY.get(mod)
        if lib is None:
            err("R401", f"module `{mod}` is not part of this project, so it has no type `{name}`")
            return None
        if name not in lib["types"]:
            err("R401", f"the standard module `{mod}` has no type `{name}`")
            return None
        return text
    if text in tparams:
        return tparams[text]
    if text in m.types:
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
    owner = ent.value("outputOwner")
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


def resolve_variant(world: World, m: Module, text: str, line: int, quiet: bool = False):
    """`Enum.variant` or `module.Enum.variant` -> (enum canon, variant, payload) or None."""
    parts = text.split(".")
    type_text = ".".join(parts[:-1])
    canon = resolve_type(world, m, type_text, line, quiet=quiet)
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
        if id(ent) in test_file_entities and ent.kind != "test":
            sink.error("R602", ent.line, f"a test file holds only tests and the entities they own; move `{ent.name}` "
                       "to the module file")
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
            if n not in m.ops and n not in m.types and n not in m.tables and n not in m.op_instances:
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
    _check_recursion(m)
    _check_invariant_coverage(m)


def _check_invariant_coverage(m: Module) -> None:
    """LR-06 rule 3: every invariant is named by at least one test's `verifies` row."""
    verified = {(r.text(0), r.text(1)) for t in m.tests.values() for r in t.facts("verifies")}
    for op in m.ops.values():
        for r in op.facts("invariant"):
            if r.text(0) != "none" and (op.name, r.text(0)) not in verified:
                m.sink.error("R604", r.line, f"invariant `{r.text(0)}` of `{op.name}` is not verified by any test; "
                             f"add a test in `{m.short}.test.sem` with `verifies {op.name} {r.text(0)}`")


def _check_capability(m: Module, cap: Entity) -> None:
    """LR-34 rule 5: a capability over a scoped resource states its scope; others state `scope none`."""
    kinds = {SCOPED_RESOURCES.get(r.text(1)) for r in cap.facts("grants")}
    scope_row = cap.fact("scope")
    if scope_row is None:
        return
    scoped = {k for k in kinds if k is not None}
    if len(scoped) > 1 or (scoped and None in kinds):
        m.sink.error("R408", scope_row.line, f"capability `{cap.name}` grants resources that are scoped differently; "
                     "split it into one capability per kind of scope")
    elif scoped and scope_row.text(0) == "none":
        res = next(r.text(1) for r in cap.facts("grants") if r.text(1) in SCOPED_RESOURCES)
        m.sink.error("R408", scope_row.line, f"`{res}` is a scoped resource, so `{cap.name} scope` states which part "
                     "of it the capability covers")
    elif not scoped and scope_row.text(0) != "none":
        m.sink.error("R408", scope_row.line, f"nothing `{cap.name}` grants takes a scope; write `{cap.name} scope none`")


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
    args = [resolve_type(world, m, t.raw, row.line) for t in row.args[1:]]
    if len(args) != len(params):
        m.sink.error("R403", row.line, f"`{row.text(0)}` takes {len(params)} type argument(s), not {len(args)}")
        return
    for p, a in zip(params, args):
        if a is not None and p.endswith("@plain") and not world.plain(a):
            m.sink.error("R403", row.line, f"type parameter `{type_param_name(p)}` of `{row.text(0)}` is `plain`; "
                         f"`{a}` is not a plain type")


def instance_sig(world: World, m: Module, ent: Entity) -> Optional[Sig]:
    row = ent.fact("instantiates")
    gen = m.ops.get(row.text(0)) if row is not None else None
    if gen is None:
        return None
    params = list(type_params_of(gen).values())
    args = [resolve_type(world, m, t.raw, row.line, quiet=True) for t in row.args[1:]]
    return world.substitute(header_sig(world, m, gen, quiet=True), dict(zip(params, args)))


def finish_module(m: Module) -> None:
    for short, (_p, line) in m.imports.items():
        if short not in m.used_imports:
            m.sink.error("R404", line, f"module `{short}` is imported but nothing in `{m.short}` uses it")


def _contains_by_value(world: World, canon: Optional[str], target: str, seen: set) -> bool:
    """True if a value of `canon` holds a `target` by value (through record fields or enum payloads)."""
    info = world.type_info(canon)
    if info is None or canon in seen:
        return False
    seen.add(canon)
    inner = [t for _n, t in info.fields] + [p for _n, p in info.variants if p is not None]
    if info.kind == "alias":
        inner.append(info.base)
    return any(t == target or _contains_by_value(world, t, target, seen) for t in inner if t is not None)


def _check_type_entity(world: World, m: Module, ent: Entity) -> None:
    tparams = type_params_of(ent)
    canon = f"{m.short}.{ent.name}"
    if ent.kind in ("record", "enum", "alias") and _contains_by_value(world, canon, canon, set()):
        m.sink.error("R403", ent.line, f"`{ent.name}` contains itself by value, so it would have no finite size; "
                     "refer to other values through a list and a typed index (LR-25 rule 5)")
    for r in ent.facts("field"):
        resolve_type(world, m, r.text(1), r.line, tparams)
    for r in ent.facts("variant"):
        if r.text(1) != "none":
            resolve_type(world, m, r.text(1), r.line, tparams)
    if ent.kind == "alias":
        resolve_type(world, m, ent.value("for"), ent.line)
        idx = ent.value("indexes")
        if idx not in (None, "none"):
            resolve_type(world, m, idx, ent.line)
    if ent.kind == "operationType":
        _check_header(world, m, ent)
    if ent.kind == "instance":
        row = ent.fact("instantiates")
        if row is None:
            return
        gen = resolve_type(world, m, row.text(0), row.line)
        args = [resolve_type(world, m, t.raw, row.line) for t in row.args[1:]]
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
            if gen == "ffi.Function" and args and args[0] is not None:
                _check_foreign(world, m, row, args[0])


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
    bad = [p.type for p in sig.inputs if p.type not in FOREIGN_TYPES or p.mode != "value"]
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
    rec = resolve_type(world, m, ent.value("of"), ent.line)
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


def _check_value_token(world: World, m: Module, tok, canon: Optional[str], line: int, what: str) -> None:
    """A literal, a variant, or the name of a module operation (as an operation reference)."""
    if canon is None:
        return
    if tok.kind == "word" and S.is_variant(tok.raw):
        v = resolve_variant(world, m, tok.raw, line)
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
    if not literal_fits(world, tok, canon):
        m.sink.error("R403", line, f"{what} is `{_show(canon)}`; `{tok.raw}` is not a valid `{_show(canon)}` literal")


def _check_op_reference(world: World, m: Module, op_name: str, canon: Optional[str], line: int, what: str) -> None:
    info = world.type_info(canon)
    if info is None or info.kind != "operationType":
        m.sink.error("R403", line, f"{what} is `{_show(canon)}`, but `{op_name}` is an operation")
        return
    want = info.sig
    got = header_sig(world, m, m.ops[op_name], quiet=True)
    if want is None:
        return
    problems = []
    if [(p.name, p.type, p.mode) for p in got.inputs] != [(p.name, p.type, p.mode) for p in want.inputs]:
        problems.append("its inputs differ")
    for attr, label in (("output", "output"), ("output_owner", "outputOwner"), ("raises", "raises"), ("waits", "async")):
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
    owner = ent.value("outputOwner")
    oline = ent.fact("outputOwner").line if ent.fact("outputOwner") else ent.line
    if out_t is None or world.plain(out_t):
        if owner not in (None, "none"):
            sink.error("R409", oline, "`outputOwner` is `none` when there is no output or the output is a plain value")
    else:
        info = world.type_info(out_t)
        if info is not None and info.kind == "resource":
            if owner != "caller":
                sink.error("R409", oline, f"`{out}` is a resource, so `outputOwner caller` hands it to the caller")
        elif owner == "caller" or owner == "none" or owner not in inputs or inputs[owner] != "Region":
            sink.error("R409", oline, f"`{out}` is region-owned, so `outputOwner` names the `Region` input it is "
                       "allocated in")
    raises = ent.value("raises")
    if raises not in (None, "none"):
        rt = resolve_type(world, m, raises, ent.fact("raises").line, tp)
        info = world.type_info(rt)
        if rt is not None and (info is None or info.kind not in ("enum",)):
            sink.error("R403", ent.fact("raises").line, f"`raises` names an error enum; `{raises}` is not an enum")


def _check_mode(world: World, m: Module, t: Optional[str], mode: str, line: int, what: str) -> None:
    if t is None:
        return
    if t == "Region":
        if mode != "borrowed":
            m.sink.error("R406", line, f"{what} is a `Region`, which is always `borrowed`")
        return
    if world.plain(t) and mode != "value":
        m.sink.error("R406", line, f"{what} has the plain type `{_show(t)}`, so it is passed as `value`")
    if not world.plain(t) and mode == "value":
        m.sink.error("R406", line, f"{what} has the non-plain type `{_show(t)}`, so it cannot be copied; use "
                     "`borrowed`, `borrowedMutable`, or `owned`")


def _build_op(world: World, m: Module, ent: Entity) -> OpInfo:
    sink = m.sink
    info = OpInfo(ent, m)
    info.tparams = type_params_of(ent)
    tp = info.tparams
    info.sig = header_sig(world, m, ent, quiet=True)
    info.output = info.sig.output
    info.raises = info.sig.raises
    names: dict[str, int] = {}
    module_names = set(m.ops) | set(m.types) | set(m.tables) | set(m.capabilities) | set(m.tests) | set(m.op_instances)

    def claim(name: str, line: int, what: str) -> None:
        if name in names:
            sink.error("R411", line, f"`{name}` ({what}) is already used in `{ent.name}` on line {names[name]}; names "
                       "in one operation's scope are unique across labels, values, and owned entities")
        elif name in module_names:
            sink.error("R411", line, f"`{name}` ({what}) is already a module-level name")
        names.setdefault(name, line)

    if ent.kind == "test" and tp:
        sink.error("R604", ent.fact("typeParam").line, "a test is not generic; it states `typeParam none`")
    for r in ent.facts("input"):
        if r.text(0) != "none":
            t = resolve_type(world, m, r.text(1), r.line, tp, quiet=True)
            info.bindings[r.text(0)] = Binding(r.text(0), t, "input", r.line, mode=r.text(2))
            claim(r.text(0), r.line, "input")
    for r in ent.facts("let"):
        t = resolve_type(world, m, r.text(2), r.line, tp)
        tok = r.args[3]
        lit = None
        if r.text(1) == "immutable" and (tok.kind == "string" or not S.is_name(tok.raw)):
            lit = literal_value(tok)
        info.bindings[r.text(0)] = Binding(r.text(0), t, "let", r.line, mutable=r.text(1) == "mutable",
                                           unset=r.text(3) == "unset", literal=lit)
        claim(r.text(0), r.line, "let")
    for r in ent.facts("at"):
        lab = r.text(0)
        if lab not in info.labels:
            info.labels.append(lab)
    for lab in info.labels:
        claim(lab, ent.line, "label")
    for o in m.owned:
        if o.owner != ent.name:
            continue
        claim(o.name, o.line, o.kind)
        info.owned[o.name] = o
        if o.kind == "region":
            info.bindings[o.name] = Binding(o.name, "Region", "region", o.line)
        elif o.kind == "taskGroup":
            info.bindings[o.name] = Binding(o.name, None, "group", o.line)
    for o in info.owned.values():
        if o.kind in ("call", "task"):
            ci = _build_call(world, m, info, o)
            info.calls[o.name] = ci
            if ci.out:
                b = o.value("borrows")
                info.bindings[ci.out[0]] = Binding(ci.out[0], ci.out[1], "out", o.fact("out").line,
                                                   view_of=None if b in (None, "none") else b)
                claim(ci.out[0], o.fact("out").line, f"result of `{o.name}`")
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
    for r in ent.facts("arg"):
        if r.text(0) != "none":
            args.append((r.text(0), resolve_type(world, m, r.text(1), r.line, tp), r.text(2), r.text(3), r.line))
    outr, catchr = ent.fact("out"), ent.fact("catch")
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
        sig, callee = resolve_target(world, m, inv.text(0), inv.line, args=args)
    return CallInfo(ent, sig, args, out, catch, ref, callee)


def resolve_target(world: World, m: Module, text: str, line: int, quiet: bool = False, args=None):
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
        if text in m.ops:
            if type_params_of(m.ops[text]):
                return err("R402", f"`{text}` is generic; call it through an `operationInstance` that names its "
                           "type arguments")
            return header_sig(world, m, m.ops[text], quiet=True), text
        if text in m.op_instances:
            gen = m.op_instances[text].value("instantiates")
            return instance_sig(world, m, m.op_instances[text]), gen
        if text in m.tests:
            return err("R402", f"`{text}` is a test; tests are run by the test runner, not invoked")
        return err("R401", f"`{text}` is not an operation of this module")
    if len(parts) == 2 and S.UPPER.match(parts[0]):
        canon = resolve_type(world, m, parts[0], line, quiet=quiet)
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
        return "table", resolve_type(world, m, m.tables[name].value("of"), m.tables[name].line, quiet=True)
    return "unknown", None


def _check_op(world: World, m: Module, op: OpInfo) -> None:
    sink = m.sink
    ent = op.entity
    _check_header(world, m, ent)
    if ent.kind == "test":
        for pred in ("input", "output", "outputOwner", "raises"):
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


def _check_let(world: World, m: Module, op: OpInfo, r: Row) -> None:
    b = op.bindings.get(r.text(0))
    tok = r.args[3]
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
        else:
            m.sink.error("R401", r.line, f"`{tok.raw}` is not a value in `{op.entity.name}`")
        return
    _check_value_token(world, m, tok, b.type, r.line, f"`{b.name}`")


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
            sink.error("R405", ent.line, f"`{ent.name}`'s target takes no arguments; write `{ent.name} arg none`")
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
    _check_loans(m, op, ci)
    if sig.scoped and sig.scoped in passed:
        _check_scope(m, op, ci, sig, passed[sig.scoped])
    # out and catch
    outr, catchr = ent.fact("out"), ent.fact("catch")
    if outr is not None:
        if sig.output is None and ci.out is not None:
            sink.error("R403", outr.line, f"`{ent.name}`'s target returns nothing; write `{ent.name} out none`")
        elif sig.output is not None and ci.out is None:
            sink.error("R403", outr.line, f"`{ent.name}`'s target returns `{_show(sig.output)}`; name it with "
                       f"`{ent.name} out <name> {_show(sig.output)}`")
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


def _check_scope(m: Module, op: OpInfo, ci: CallInfo, sig: Sig, value: str) -> None:
    """LR-34 rule 5: a literal argument outside every granting capability's scope is a check error."""
    b = op.bindings.get(value)
    if b is None or b.literal is None:
        return
    lit = b.literal
    resources = [(v, r) for v, r in sig.effects if r in SCOPED_RESOURCES]
    for verb, res in resources:
        kind = SCOPED_RESOURCES[res]
        scopes = []
        for r in op.entity.facts("uses"):
            cap = m.capabilities.get(r.text(0))
            if cap is None or (verb, res) not in {(g.text(0), g.text(1)) for g in cap.facts("grants")}:
                continue
            srow = cap.fact("scope")
            if srow is not None and srow.args[0].kind == "string":
                scopes.append(srow.args[0].value)
        ok = False
        for s in scopes:
            if kind == "port":
                ok = ok or s.rsplit(":", 1)[-1] == str(lit)
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
        worker, cleans = c.value("call"), c.value("cleans")
        b = op.bindings.get(cleans)
        owned_input = b is not None and b.kind == "input" and b.mode == "owned"
        owned_out = any(ci.out and ci.out[0] == cleans and ci.entity.value("ownedBy") == op.entity.name
                        for ci in op.calls.values())
        if not (owned_input or owned_out):
            sink.error("R409", c.fact("cleans").line, f"cleanup `{c.name}` cleans `{cleans}`, which `{op.entity.name}` "
                       "does not own (an `owned` input or a result with `ownedBy " + op.entity.name + "`)")
        w = op.calls.get(worker)
        if w is None or w.entity.kind != "call":
            sink.error("R402", c.fact("call").line, f"cleanup `{c.name}` runs `{worker}`, which is not a call of "
                       f"`{op.entity.name}`")
        elif not any(a[2] == cleans and a[3] == "give" for a in w.args):
            sink.error("R409", c.fact("call").line, f"the cleanup's call `{worker}` must take `{cleans}` with `give`")


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
    mrow = ent.fact("memory")
    if mrow is not None and (mrow.text(1) == "true") != heap:
        sink.error("R410", mrow.line, f"`memory heap` is `true` exactly when the operation owns a region or takes "
                   f"one as input; `{ent.name}` should state `memory heap {'true' if heap else 'false'}`")


def _check_recursion(m: Module) -> None:
    graph = {n: {ci.callee_op for ci in info.calls.values() if ci.callee_op} for n, info in m.op_infos.items()}
    for name, info in m.op_infos.items():
        seen, stack, recursive = set(), list(graph.get(name, ())), False
        while stack:
            cur = stack.pop()
            if cur == name:
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
