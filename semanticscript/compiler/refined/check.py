"""Load a module file or a project (build.sem) and run every check."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from . import parser
from . import shapes as S
from .diagnostics import CODES, Diagnostic, Sink
from .flow import check_flow
from .lexer import lex
from .library import LIBRARY
from .model import Entity, SourceFile
from .semantics import Module, World, check_module, finish_module, index_module

# Rows from a module's `.test.sem` file are merged into the module. Their line
# numbers are offset so every diagnostic can be routed back to the right file.
TEST_OFFSET = 1_000_000


class RoutedSink(Sink):
    def __init__(self, file: str, test_file: Optional[str] = None):
        super().__init__(file)
        self.test_file = test_file

    def error(self, code: str, line: int, message: str) -> None:
        assert code in CODES, code
        if self.test_file is not None and line >= TEST_OFFSET:
            self.items.append(Diagnostic(code, message, self.test_file, line - TEST_OFFSET))
        else:
            self.items.append(Diagnostic(code, message, self.file, line))


@dataclass
class Result:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    world: Optional[World] = None
    project: Optional[Entity] = None
    root: Optional[str] = None

    @property
    def ok(self) -> bool:
        return not self.diagnostics


# Unsaved editor text by file (the language server sets it): checked in place of what is on disk.
OVERLAY: dict[str, str] = {}


def _read(path: str, sink: Sink) -> Optional[SourceFile]:
    try:
        key = os.path.normcase(os.path.abspath(path))
        if key in OVERLAY:
            text = OVERLAY[key]
        else:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
    except UnicodeDecodeError:
        sink.error("R102", 1, "source is not valid UTF-8")
        return None
    except OSError as exc:
        sink.error("R602", 1, f"cannot read file: {exc.strerror}")
        return None
    return parser.parse(lex(text, sink), path, sink)


def _load_module(dotted: Optional[str], path: str, sinks: list[Sink]) -> Optional[Module]:
    test_path = path[:-4] + ".test.sem"
    has_tests = os.path.exists(test_path)
    sink = RoutedSink(path, test_path if has_tests else None)
    sinks.append(sink)
    src = _read(path, sink)
    if src is None:
        return None
    entities = list(src.entities)
    test_ids: set[int] = set()
    if has_tests:
        tsink = Sink(test_path)
        sinks.append(tsink)
        tsrc = _read(test_path, tsink)
        if tsrc is not None:
            for e in tsrc.entities:
                e.line += TEST_OFFSET
                for r in e.rows:
                    r.line += TEST_OFFSET
                test_ids.add(id(e))
            entities += tsrc.entities
    for e in entities:
        if e.kind is None:
            continue
        if e.kind in S.PROJECT_KINDS:
            sink.error("R601", e.line, "the project entity lives in build.sem, not in a module file")
            continue
        parser.check_entity(e, sink)
    me = next((e for e in src.entities if e.kind == "module"), None)
    short = me.name if me is not None else os.path.basename(path)[:-4]
    module_path = (me.value("path") if me is not None else None) or dotted or short
    if dotted is not None and me is not None and me.value("path") != dotted:
        sink.error("R602", me.line, f"build.sem lists this file as `{dotted}`, but its module path is `{me.value('path')}`")
    m = Module(short, module_path, path,
               [e for e in entities if e.kind is not None and e.kind not in S.PROJECT_KINDS], sink)
    m.test_ids = test_ids  # type: ignore[attr-defined]
    return m


def check_path(path: str) -> Result:
    """`path` is a module file, a build.sem file, or a directory that holds build.sem."""
    if os.path.isdir(path):
        path = os.path.join(path, "build.sem")
    if os.path.basename(path) == "build.sem":
        return check_project(path)
    return check_modules([path])


def check_modules(paths: list[str]) -> Result:
    """Check module files outside a project. Imports of non-standard modules
    resolve only among the files given."""
    sinks: list[Sink] = []
    modules = []
    for p in paths:
        if p.endswith(".test.sem"):
            s = Sink(p)
            sinks.append(s)
            s.error("R602", 1, "a test file is checked with the module beside it; check that module instead")
            continue
        m = _load_module(None, p, sinks)
        if m is not None:
            modules.append(m)
    return _run(World(), modules, sinks)


def _load_project(build_path: str, package: str, sinks: list[Sink], stack: list[str]):
    """(project entity, its sink, its modules and those of every project it requires), or (None, sink, [])."""
    bsink = Sink(build_path)
    sinks.append(bsink)
    src = _read(build_path, bsink)
    if src is None:
        return None, bsink, []
    for e in src.entities:
        if e.kind is not None and e.kind != "project":
            bsink.error("R601", e.line, "build.sem holds only the project entity")
        elif e.kind == "project":
            parser.check_entity(e, bsink)
    projects = [e for e in src.entities if e.kind == "project"]
    if len(projects) != 1:
        bsink.error("R601", 1, "build.sem declares exactly one `<name> is project` entity")
        return None, bsink, []
    proj = projects[0]
    _check_versions(proj, bsink)
    root = os.path.dirname(os.path.abspath(build_path))
    modules = []
    for r in proj.facts("module"):
        dotted = r.text(0)
        file = os.path.join(root, *dotted.split(".")) + ".sem"
        if not os.path.exists(file):
            bsink.error("R602", r.line, f"module `{dotted}` belongs in `{os.path.relpath(file, root)}`, which does not exist")
            continue
        m = _load_module(dotted, file, sinks)
        if m is not None:
            m.package, m.local_path = package, m.path  # type: ignore[attr-defined]
            if package:
                m.path = f"{package}.{m.path}"
            modules.append(m)
    for r in proj.facts("requires"):
        if r.text(0) == "none":
            continue
        name, rel, constraint = r.text(0), r.args[1].value, r.args[2].value
        if not valid_constraint(constraint):
            bsink.error("R601", r.line, f"`{constraint}` is not a version constraint; write comparators such as "
                        "`>=1.2.0 <2.0.0`, `^1.2.0`, `=1.2.3`, or `*`")
            continue
        dep_build = os.path.normpath(os.path.join(root, rel, "build.sem"))
        if not os.path.exists(dep_build):
            bsink.error("R601", r.line, f"`{name}` is required from `{rel}`, which holds no build.sem")
            continue
        if dep_build in stack:
            bsink.error("R603", r.line, f"projects require each other in a cycle through `{name}`")
            continue
        dep, _dep_sink, dep_modules = _load_project(dep_build, f"{package}.{name}" if package else name, sinks,
                                                    stack + [dep_build])
        if dep is None:
            continue
        if dep.name != name:
            bsink.error("R601", r.line, f"`{rel}` holds project `{dep.name}`, not `{name}`")
        if dep.value("target") != "library":
            bsink.error("R601", r.line, f"a required project is a library; `{name}` is `{dep.value('target')}`")
        version = dep.fact("version").args[0].value if dep.fact("version") is not None else "?"
        if not satisfies(version, constraint):
            bsink.error("R601", r.line, f"`{name}` is version {version}, which does not satisfy `{constraint}`")
        modules += dep_modules
    return proj, bsink, modules


def check_project(build_path: str) -> Result:
    sinks: list[Sink] = []
    proj, bsink, modules = _load_project(build_path, "", sinks, [os.path.normpath(os.path.abspath(build_path))])
    if proj is None:
        return Result(diagnostics=_collect(sinks))
    root = os.path.dirname(os.path.abspath(build_path))
    world = World()
    entry = proj.value("entry")
    if entry not in (None, "none") and "." in entry:
        world.entry = tuple(entry.split(".", 1))  # type: ignore[assignment]
    res = _run(world, modules, sinks)
    _check_project_entity(world, proj, bsink)
    _check_import_cycles(world, bsink)
    res.diagnostics = _collect(sinks)
    res.project, res.root = proj, root
    return res


def _run(world: World, modules: list[Module], sinks: list[Sink]) -> Result:
    for m in modules:
        line = next((e.line for e in m.entities if e.kind == "module"), 1)
        if m.short in world.modules:
            m.sink.error("R602", line, f"two modules are named `{m.short}`")
            continue
        if m.short in LIBRARY:
            m.sink.error("R602", line, f"module `{m.short}` has the name of standard module `standard.{m.short}`; a "
                         f"reference such as `{m.short}.<name>` would be ambiguous, so rename the module")
            continue
        world.modules[m.short] = m
    for m in world.modules.values():
        index_module(world, m, getattr(m, "test_ids", set()))
    for m in world.modules.values():
        check_module(world, m)
        for info in m.op_infos.values():
            check_flow(world, m, info)
        finish_module(m)
    return Result(diagnostics=_collect(sinks), world=world)


def _collect(sinks: list[Sink]) -> list[Diagnostic]:
    seen = set()
    out = []
    for s in sinks:
        for d in s.items:
            key = (d.code, d.file, d.line, d.message)
            if key not in seen:
                seen.add(key)
                out.append(d)
    return sorted(out, key=lambda d: (d.file, d.line, d.code))


def _check_project_entity(world: World, proj: Entity, sink: Sink) -> None:
    target = proj.value("target")
    entry = proj.value("entry")
    erow = proj.fact("entry")
    if erow is None:
        return
    if target == "library":
        if entry != "none":
            sink.error("R601", erow.line, "a `library` project has `entry none`")
        return
    if entry in (None, "none") or "." not in entry:
        sink.error("R601", erow.line, "a `console` project names its entry operation as `<module>.<operation>`")
        return
    mod, op = entry.split(".", 1)
    m = world.modules.get(mod)
    if m is None or op not in m.ops:
        sink.error("R601", erow.line, f"entry `{entry}` is not an operation of a module in this project")
        return
    ent = m.ops[op]
    if ent.value("input") != "none" or ent.value("output") != "ExitCode":
        sink.error("R601", erow.line, f"a console entry has `input none` and `output ExitCode`; `{entry}` does not")
    if op not in m.exports:
        sink.error("R601", erow.line, f"entry `{entry}` must be exported by module `{mod}`")


def _check_import_cycles(world: World, sink: Sink) -> None:
    graph = {n: {s for s in m.imports if s in world.modules} for n, m in world.modules.items()}
    color: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        color[n] = 1
        for nxt in sorted(graph.get(n, ())):
            if color.get(nxt) == 1:
                sink.error("R603", 1, "modules import each other in a cycle: " + " -> ".join(path + [nxt]))
            elif nxt not in color:
                visit(nxt, path + [nxt])
        color[n] = 2

    for n in sorted(graph):
        if n not in color:
            visit(n, [n])


# ---------------------------------------------------------------- versions and packages (D-34)

LANGUAGE = "refined-1"
STANDARD_LIBRARY_VERSION = 1


def _semver(text: str):
    parts = text.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def satisfies(version: str, constraint: str) -> bool:
    """`constraint` is `*`, or comparators separated by spaces: `>=1.2.0 <2.0.0`, `=1.4.1`, `^1.2.0` (same major)."""
    v = _semver(version)
    if v is None:
        return False
    for part in constraint.split():
        if part == "*":
            continue
        op = next((o for o in (">=", "<=", ">", "<", "=", "^") if part.startswith(o)), None)
        want = _semver(part[len(op):]) if op else None
        if op is None or want is None:
            return False
        ok = {">=": v >= want, "<=": v <= want, ">": v > want, "<": v < want, "=": v == want,
              "^": v >= want and v[0] == want[0]}[op]
        if not ok:
            return False
    return True


def valid_constraint(constraint: str) -> bool:
    return all(p == "*" or (any(p.startswith(o) for o in (">=", "<=", ">", "<", "=", "^")) and
                            _semver(p.lstrip("<>=^")) is not None) for p in constraint.split()) and bool(constraint)


def _check_versions(proj: Entity, sink: Sink) -> None:
    row = proj.fact("version")
    if row is not None and _semver(row.args[0].value) is None:
        sink.error("R601", row.line, f"a project version is `MAJOR.MINOR.PATCH`, not `{row.args[0].value}`")
    row = proj.fact("language")
    if row is not None and row.text(0) != LANGUAGE:
        sink.error("R601", row.line, f"this compiler reads `{LANGUAGE}`")
    row = proj.fact("standardLibrary")
    if row is not None and row.text(0) != str(STANDARD_LIBRARY_VERSION):
        sink.error("R601", row.line, f"this compiler provides standard library version {STANDARD_LIBRARY_VERSION}, "
                   f"not {row.text(0)}")
