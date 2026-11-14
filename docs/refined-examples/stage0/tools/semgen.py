"""semgen: a small DSL that expands to explicit SemanticScript rows.

A .dsl file holds module-level entities (record, enum, instance, table, constant)
and operations/tests written as blocks of statements. Calls are written
`[name:] [result =] target(args) [mark]`; the generator looks the target's
signature up (standard library through refined.library, other stage0 modules by
reading their .sem files, this module from its own declarations) and writes the
call entity with every slot, type, mode, ownedBy, borrows, catch, and suppresses
row spelled out.
"""
from __future__ import annotations

import os
import re
import sys
from collections import OrderedDict

# the repository: this file lives in docs/refined-examples/stage0/tools, or SEMGEN_WT names the checkout
_HERE = os.path.dirname(os.path.abspath(__file__))
WT = os.environ.get("SEMGEN_WT") or os.path.normpath(os.path.join(_HERE, "..", "..", "..", ".."))
sys.path.insert(0, os.path.join(WT, "semanticscript", "compiler"))

from refined.library import LIBRARY, BUILTINS, generic_members  # noqa: E402
from refined.fmt import format_text  # noqa: E402

STD = set(LIBRARY.keys())
MODES = {"copied": "copy", "borrowed": "lend", "borrowedMutable": "lendMutable", "owned": "give"}
SMALL = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
         9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 16: "sixteen", 32: "thirtyTwo", 64: "sixtyFour"}


class GenError(Exception):
    pass


class P:
    def __init__(self, name, type_, mode):
        self.name, self.type, self.mode = name, type_, mode


class S:
    """A signature: params (P), output canon, owner param name, raises canon, borrows param name."""

    def __init__(self, params, output=None, owner=None, raises=None, borrows=None):
        self.params, self.output, self.owner, self.raises, self.borrows = list(params), output, owner, raises, borrows


class TypeDecl:
    def __init__(self, kind, canon):
        self.kind = kind  # record | enum | instance | table
        self.canon = canon
        self.fields = []
        self.variants = []
        self.generic = None
        self.args = []
        self.row_type = None


class Module:
    def __init__(self, name):
        self.name = name
        self.types: dict[str, TypeDecl] = {}
        self.tables: dict[str, TypeDecl] = {}
        self.ops: dict[str, S] = {}
        self.constants: dict[str, str] = {}
        self.imports = []


class Program:
    def __init__(self):
        self.modules: dict[str, Module] = {}

    # ------------------------------------------------------------ reading existing .sem files
    def load_sem(self, name, path):
        m = Module(name)
        self.modules[name] = m
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        ents = OrderedDict()
        for ln in lines:
            t = ln.split()
            if len(t) < 3 or t[0].startswith("#"):
                continue
            if t[1] == "is":
                ents[t[0]] = (t[2], [])
                continue
            if t[0] in ents:
                ents[t[0]][1].append(t[1:])
        for ename, (kind, rows) in ents.items():
            self._declare_rows(m, ename, kind, rows)
        return m

    def _declare_rows(self, m, ename, kind, rows):
        if kind == "operationType":
            d = TypeDecl("optype", f"{m.name}.{ename}")
            ins, out, raises = [], None, None
            for r in rows:
                if r[0] == "input" and r[1] != "none":
                    ins.append((r[1], r[2], r[3]))
                elif r[0] == "output":
                    out = None if r[1] == "none" else r[1]
                elif r[0] == "raises":
                    raises = None if r[1] == "none" else r[1]
            d.sig = ("raw", ins, out, None, raises)
            m.types[ename] = d
            return
        if kind in ("record", "enum", "typeInstance", "table"):
            k = {"typeInstance": "instance"}.get(kind, kind)
            d = TypeDecl(k, f"{m.name}.{ename}")
            for r in rows:
                if r[0] == "field":
                    d.fields.append((r[1], r[2]))
                elif r[0] == "variant":
                    d.variants.append((r[1], None if r[2] == "none" else r[2]))
                elif r[0] == "instantiates":
                    d.generic, d.args = r[1], r[2:]
                elif r[0] == "rowType":
                    d.row_type = r[1]
            if k == "table":
                m.tables[ename] = d
            else:
                m.types[ename] = d
        elif kind in ("operation",):
            ins, out, owner, raises = [], None, None, None
            for r in rows:
                if r[0] == "input" and r[1] != "none":
                    ins.append((r[1], r[2], r[3]))
                elif r[0] == "output":
                    out = None if r[1] == "none" else r[1]
                elif r[0] == "outputOwnedBy":
                    owner = None if r[1] in ("none", "caller") else r[1]
                elif r[0] == "raises":
                    raises = None if r[1] == "none" else r[1]
            m.ops[ename] = ("raw", ins, out, owner, raises)
        elif kind == "constant":
            for r in rows:
                if r[0] == "type":
                    m.constants[ename] = r[1]

    # ------------------------------------------------------------ types
    def canon(self, m: Module, t: str) -> str:
        if t is None:
            return None
        if t in BUILTINS:
            return t
        if "." in t:
            return t
        if t in m.types:
            return f"{m.name}.{t}"
        raise GenError(f"unknown type {t} in {m.name}")

    def spell(self, m: Module, c: str) -> str:
        if c is None:
            return "none"
        if c.startswith(m.name + "."):
            return c[len(m.name) + 1:]
        return c

    def decl(self, c: str):
        if c is None or c in BUILTINS:
            return None
        mod, name = c.split(".", 1)
        if mod in self.modules:
            d = self.modules[mod].types.get(name)
            if d is None:
                raise GenError(f"unknown type {c}")
            return d
        if mod in STD:
            ti = LIBRARY[mod]["types"].get(name)
            if ti is None:
                raise GenError(f"unknown library type {c}")
            return ti
        raise GenError(f"unknown type {c}")

    def fields(self, c):
        d = self.decl(c)
        if isinstance(d, TypeDecl):
            mm = self.modules[d.canon.split(".", 1)[0]]
            return [(n, self.canon(mm, t)) for n, t in d.fields]
        return list(d.fields)

    def variants(self, c):
        d = self.decl(c)
        if isinstance(d, TypeDecl):
            mm = self.modules[d.canon.split(".", 1)[0]]
            return [(n, None if p is None else self.canon(mm, p)) for n, p in d.variants]
        return list(d.variants)

    def inst_args(self, c):
        d = self.decl(c)
        mm = self.modules[d.canon.split(".", 1)[0]]
        return [self.canon(mm, a) for a in d.args]

    def kind(self, c):
        if c in BUILTINS:
            return "builtin"
        d = self.decl(c)
        return d.kind

    def plain(self, c) -> bool:
        if c in BUILTINS:
            return bool(BUILTINS[c].plain)
        d = self.decl(c)
        if isinstance(d, TypeDecl):
            if d.kind == "record":
                return all(self.plain(fc) for _n, fc in self.fields(c))
            if d.kind == "enum":
                return all(p is None or self.plain(p) for _n, p in self.variants(c))
            if d.kind == "instance":
                return d.generic not in ("list.List", "map.Map", "set.Set")
            return True
        if d.plain is not None:
            return bool(d.plain)
        if d.kind == "record":
            return all(self.plain(t) for _n, t in d.fields)
        if d.kind == "enum":
            return all(p is None or self.plain(p) for _n, p in d.variants)
        return False

    def read_mode(self, c):
        if c == "Region":
            return "borrowed"
        return "copied" if self.plain(c) else "borrowed"

    # ------------------------------------------------------------ signatures
    def optype_sig(self, c: str) -> S:
        """The signature an operationType declares, for a call through a reference of that type."""
        d = self.decl(c)
        if not isinstance(d, TypeDecl) or d.kind != "optype":
            raise GenError(f"{c} is not an operationType")
        mm = self.modules[d.canon.split(".", 1)[0]]
        if not isinstance(d.sig, S):
            _raw, ins, out, owner, raises = d.sig
            d.sig = S([P(n, self.canon(mm, t), md) for n, t, md in ins], self.canon(mm, out), owner,
                      self.canon(mm, raises))
        return d.sig

    def op_sig(self, mod: Module, name: str) -> S:
        v = mod.ops[name]
        if isinstance(v, S):
            return v
        _raw, ins, out, owner, raises = v
        s = S([P(n, self.canon(mod, t), md) for n, t, md in ins], self.canon(mod, out), owner, self.canon(mod, raises))
        mod.ops[name] = s
        return s

    def member(self, c: str, member: str) -> S:
        d = self.decl(c)
        kind = d.kind
        if kind == "record":
            fl = self.fields(c)
            if member == "new":
                # derived new: mode_for(t) = copied if plain else borrowed
                ps = [P(n, t, "copied" if self.plain(t) else "borrowed") for n, t in fl]
                owned = any(not self.plain(t) for _n, t in fl)
                if owned:
                    ps.append(P("region", "Region", "borrowed"))
                return S(ps, c, "region" if owned else None)
            for n, t in fl:
                if n == member:
                    return S([P("record", c, self.read_mode(c))], t, None, None, None if self.plain(t) else "record")
            if member == "equals":
                return S([P("left", c, self.read_mode(c)), P("right", c, self.read_mode(c))], "Bool")
            if member == "with":
                raise GenError("with is not supported by semgen")
        if kind == "enum":
            for n, p in self.variants(c):
                if n == member:
                    return S([] if p is None else [P("payload", p, "copied" if self.plain(p) else "owned")], c)
            if member == "equals":
                return S([P("left", c, self.read_mode(c)), P("right", c, self.read_mode(c))], "Bool")
        if kind == "instance":
            args = self.inst_args(c) if isinstance(d, TypeDecl) else d.args
            gm = generic_members(d.generic, c, list(args), self.plain)
            if member in gm:
                return self._from_sig(gm[member])
        if kind == "opaque" or hasattr(d, "targets"):
            tg = getattr(d, "targets", {}) or {}
            if member in tg:
                return self._from_sig(tg[member])
        raise GenError(f"no member {member} of {c}")

    def _from_sig(self, sig) -> S:
        return S([P(p.name, p.type, p.mode) for p in sig.inputs], sig.output, sig.output_owner, sig.raises, sig.borrows)

    def target_sig(self, m: Module, target: str) -> S:
        parts = target.split(".")
        if len(parts) == 1:
            if target in m.ops:
                return self.op_sig(m, target)
            raise GenError(f"unknown operation {target} in {m.name}")
        if parts[0] in m.tables and len(parts) == 2:
            t = m.tables[parts[0]]
            rec = self.canon(m, t.row_type)
            if parts[1] == "rowAt":
                return S([P("position", "Int64", "copied")], rec, None, "list.IndexOutOfRange")
            if parts[1] == "length":
                return S([], "Int64")
        if parts[0] in self.modules and parts[0] != m.name:
            mm = self.modules[parts[0]]
            if len(parts) == 2:
                if parts[1] in mm.ops:
                    return self.op_sig(mm, parts[1])
                raise GenError(f"unknown {target}")
            return self.member(f"{parts[0]}.{parts[1]}", parts[2])
        if parts[0] in STD and len(parts) == 2:
            tg = LIBRARY[parts[0]]["targets"]
            if parts[1] in tg:
                return self._from_sig(tg[parts[1]])
            raise GenError(f"unknown library target {target}")
        if parts[0] in STD and len(parts) == 3:
            return self.member(f"{parts[0]}.{parts[1]}", parts[2])
        if parts[0][:1].isupper() and len(parts) == 2:
            return self.member(self.canon(m, parts[0]), parts[1])
        raise GenError(f"cannot resolve target {target}")


# ---------------------------------------------------------------- text helpers

def q(text: str) -> str:
    """A SemanticScript string literal for a Python string."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t") + '"'


def split_args(s: str):
    out, cur, inq, esc = [], "", False, False
    for ch in s:
        if inq:
            cur += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                inq = False
            continue
        if ch == '"':
            inq = True
            cur += ch
        elif ch == ",":
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def tokens(s: str):
    """Split a line on spaces, keeping quoted text together."""
    out, cur, inq, esc = [], "", False, False
    for ch in s:
        if inq:
            cur += ch
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                inq = False
            continue
        if ch == '"':
            inq = True
            cur += ch
        elif ch in " \t":
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def cap(s):
    return s[:1].upper() + s[1:]


CALL_RE = re.compile(r"^(?:([a-z][A-Za-z0-9]*):\s*)?(?:([a-z][A-Za-z0-9]*)\s*=\s*)?(\*?[A-Za-z][A-Za-z0-9.]*)\((.*)\)\s*(.*)$")
INT_RE = re.compile(r"^-?[0-9]+$")


class Block:
    def __init__(self, name, loop="none", within="none", bound=None, over=None, note=None):
        self.name, self.loop, self.within, self.bound, self.over, self.note = name, loop, within, bound, over, note
        self.steps = []
        self.closed = False


TERMINATORS = ("goto", "branch", "return", "case")


class OpBuilder:
    def __init__(self, gen, m: Module, name, purpose, test=False):
        self.gen, self.prog, self.m = gen, gen.prog, m
        self.name, self.purpose, self.test = name, purpose, test
        self.invariants = []
        self.verifies = []
        self.inputs = []
        self.output = None
        self.owner = None
        self.raises = None
        self.effects = []
        self.uses = []
        self.recursion = None
        self.async_ = False
        self.regions = []
        self.lets = OrderedDict()
        self.locals: dict[str, str] = {}
        self.blocks: list[Block] = []
        self.fail_blocks: list[Block] = []
        self.calls = []
        self.names = set()
        self.cur: Block = None
        self.match_type = None
        self.match_cases = None
        self.counter = 0

    # ---------------------------------------------------------------- names
    def claim(self, name):
        if name in self.names:
            raise GenError(f"{self.name}: name {name} used twice")
        if name in self.m.constants or name in self.m.ops or name in self.m.tables:
            raise GenError(f"{self.name}: name {name} clashes with a module-level name")
        self.names.add(name)

    def local(self, name, canon):
        self.claim(name)
        self.locals[name] = canon

    def type_of(self, name):
        if name in self.locals:
            return self.locals[name]
        if name in self.m.constants:
            return self.prog.canon(self.m, self.m.constants[name])
        raise GenError(f"{self.name}: unknown value {name}")

    # ---------------------------------------------------------------- header
    def header(self, t):
        k = t[0]
        if k == "invariant":
            self.invariants.append((t[1], t[2]))
        elif k == "verifies":
            self.verifies.append((t[1], t[2]))
        elif k == "input":
            self.inputs.append((t[1], t[2], t[3]))
            self.local(t[1], self.prog.canon(self.m, t[2]))
        elif k == "output":
            self.output = t[1]
        elif k == "owner":
            self.owner = t[1]
        elif k == "raises":
            self.raises = t[1]
        elif k == "effect":
            self.effects.append(" ".join(t[1:]))
        elif k == "uses":
            self.uses.append(t[1])
        elif k == "recursion":
            self.recursion = t[1]
        elif k == "async":
            self.async_ = True
        elif k == "region":
            self.regions.append((t[1], t[2], "atProcessExit" if len(t) > 3 and t[3] == "exit" else "atReturn"))
            self.local(t[1], "Region")
        elif k == "let":
            self.add_let(t[1], t[2], t[3], len(t) > 4 and t[4] == "mut")
        else:
            return False
        return True

    def add_let(self, name, type_, value, mutable):
        c = self.prog.canon(self.m, type_)
        if name in self.lets:
            old = self.lets[name]
            if (old[0], old[1], old[2]) != (c, value, mutable):
                raise GenError(f"{self.name}: let {name} declared twice differently")
            return
        self.local(name, c)
        self.lets[name] = (c, value, mutable)

    # ---------------------------------------------------------------- blocks
    def open_block(self, name, **attrs):
        if self.cur is not None and not self.cur.closed:
            raise GenError(f"{self.name}: block {self.cur.name} does not end with a jump before {name}")
        if name != "begin":
            self.claim(name)
        b = Block(name, **attrs)
        self.blocks.append(b)
        self.cur = b
        self.match_type = None
        return b

    def step(self, text):
        if self.cur is None:
            self.open_block("begin")
        if self.cur.closed and not text.startswith("case "):
            raise GenError(f"{self.name}: step after the end of block {self.cur.name}: {text}")
        self.cur.steps.append(text)
        verb = text.split()[0]
        if verb in ("goto", "branch", "return"):
            self.cur.closed = True

    def within_for_next(self):
        b = self.cur
        return b.name if b.loop != "none" else b.within

    # ---------------------------------------------------------------- literals as lets
    def literal_let(self, value, canon, name=None):
        if name is None:
            if INT_RE.match(value):
                n = int(value)
                if canon == "Int64":
                    name = SMALL.get(n, ("minus" + str(-n)) if n < 0 else "n" + str(n))
                elif canon == "Byte":
                    name = "byte" + str(n)
                elif canon == "ExitCode":
                    name = "code" + str(n)
                else:
                    name = canon[:1].lower() + canon[1:].replace(".", "") + str(n)
            elif value in ("true", "false"):
                name = "yes" if value == "true" else "no"
            else:
                self.counter += 1
                name = f"text{self.counter}"
        self.add_let(name, self.prog.spell(self.m, canon), value, False)
        return name

    # ---------------------------------------------------------------- statements
    def stmt(self, line):
        t = tokens(line)
        k = t[0]
        if k == "goto":
            self.step(f"goto {t[1]}")
        elif k == "if":
            self.need(t[1], "Bool")
            self.step(f"branch if {t[1]} goto {t[2]} else goto {t[3]}")
        elif k == "iferr":
            self.step(f"branch ifError {t[1]} goto {t[2]} else goto {t[3]}")
        elif k == "next":
            coll, item, yes, no = t[1], t[2], t[3], t[4]
            ctype = self.coll_item(coll)
            self.local(item, ctype)
            self.step(f"branch ifNext {coll} bind {item} {self.prog.spell(self.m, ctype)} goto {yes} else goto {no}")
        elif k == "match":
            c = self.type_of(t[1])
            self.match_type = c
            self.match_cases = [n for n, _p in self.prog.variants(c)]
            self.step(f"match {t[1]} {self.prog.spell(self.m, c)}")
        elif k == "case":
            if self.match_type is None:
                raise GenError(f"{self.name}: case without match")
            vname = t[1]
            payload = dict(self.prog.variants(self.match_type)).get(vname, "missing")
            if payload == "missing":
                raise GenError(f"{self.name}: no variant {vname} of {self.match_type}")
            sp = self.prog.spell(self.m, self.match_type)
            if len(t) == 3 and payload is not None:
                bname, k2 = "ignored" + cap(vname), 2
                while bname in self.names:
                    bname = f"ignored{cap(vname)}{k2}"
                    k2 += 1
                t = [t[0], t[1], bname, t[2]]
            if len(t) == 3:
                self.step(f"case {sp}.{vname} bind none none goto {t[2]}")
            else:
                if payload is None:
                    raise GenError(f"{self.name}: variant {vname} has no payload")
                self.local(t[2], payload)
                self.step(f"case {sp}.{vname} bind {t[2]} {self.prog.spell(self.m, payload)} goto {t[3]}")
            self.match_cases.remove(vname)
            if not self.match_cases:
                self.cur.closed = True
        elif k == "others":
            if self.match_type is None or not self.match_cases:
                raise GenError(f"{self.name}: others without open cases")
            for vname in list(self.match_cases):
                self.stmt(f"case {vname} {t[1]}")
        elif k == "set":
            self.type_of(t[1]), self.type_of(t[2])
            self.step(f"set {t[1]} {t[2]}")
        elif k == "return":
            if len(t) == 1:
                self.step("return ok none")
            else:
                self.type_of(t[1])
                self.step(f"return ok {t[1]}")
        elif k == "raise":
            self.type_of(t[1])
            self.step(f"return error {t[1]}")
        elif k == "let":
            self.add_let(t[1], t[2], t[3], len(t) > 4 and t[4] == "mut")
        elif k == "task":
            self.call_stmt(line.strip()[5:].strip(), task=True)
        else:
            self.call_stmt(line)

    def need(self, name, canon):
        c = self.type_of(name)
        if c != canon:
            raise GenError(f"{self.name}: {name} is {c}, not {canon}")

    def coll_item(self, coll):
        if coll in self.m.tables:
            return self.prog.canon(self.m, self.m.tables[coll].row_type)
        c = self.type_of(coll)
        d = self.prog.decl(c)
        if getattr(d, "generic", None) in ("list.List", "map.Map", "set.Set"):
            return self.prog.inst_args(c)[0]
        raise GenError(f"{self.name}: cannot iterate {coll}")

    def call_name(self, target, result):
        last = target.split(".")[-1]
        if result:
            base = ("read" if last not in ("new",) else "make") + cap(result)
        else:
            base = "do" + cap(last)
        name, i = base, 2
        while name in self.names:
            name = f"{base}{i}"
            i += 1
        return name

    def call_stmt(self, line, task=False):
        mt = CALL_RE.match(line.strip())
        if not mt:
            raise GenError(f"{self.name}: cannot read statement: {line}")
        cname, result, target, argtext, mark = mt.groups()
        reference = None
        if target.endswith(".with"):
            # `<Record>.with`: the record, then one slot named by the field it changes (`field:value`)
            canon = self.prog.canon(self.m, target[:-len(".with")]) if not target.count(".") > 1 else \
                target[:-len(".with")]
            field, _sep, _v = split_args(argtext)[1].partition(":")
            ftype = dict(self.prog.fields(canon))[field]
            sig = S([P("record", canon, self.prog.read_mode(canon)), P(field, ftype, self.prog.read_mode(ftype))],
                    canon)
            argtext = ", ".join([split_args(argtext)[0], _v])
        elif target.startswith("*"):
            # a call through a value of an operationType: `invokesReference <value>`
            reference = target[1:]
            sig = self.prog.optype_sig(self.type_of(reference))
        else:
            sig = self.prog.target_sig(self.m, target)
        args = split_args(argtext)
        if len(args) != len(sig.params):
            raise GenError(f"{self.name}: {target} takes {len(sig.params)} arguments, given {len(args)}: {line}")
        rows_args = []
        values = {}
        for a, p in zip(args, sig.params):
            nm = None
            if "=" in a and not a.startswith('"'):
                nm, a = a.split("=", 1)
            if INT_RE.match(a) or a.startswith('"') or a in ("true", "false"):
                v = self.literal_let(a, p.type, nm)
            else:
                v = a
                if nm is not None:
                    raise GenError(f"{self.name}: named argument with a non-literal: {a}")
                self.type_of(v)
            values[p.name] = v
            rows_args.append((p.name, self.prog.spell(self.m, p.type), v, MODES[p.mode]))
        if cname is None:
            cname = self.call_name(target, result)
        self.claim(cname)
        ent = [f"{cname} is {'task' if task else 'call'}", f"{cname} in {self.name}",
               f"{cname} invokesReference {reference}" if reference else f"{cname} invokes {target}"]
        if rows_args:
            ent += [f"{cname} argument {s} {t} {v} {md}" for s, t, v, md in rows_args]
        else:
            ent.append(f"{cname} argument none")
        if result:
            if sig.output is None:
                raise GenError(f"{self.name}: {target} gives no result")
            self.local(result, sig.output)
            ent.append(f"{cname} result {result} {self.prog.spell(self.m, sig.output)}")
        else:
            ent.append(f"{cname} result none")
        owner = values.get(sig.owner, "none") if sig.owner else "none"
        ent.append(f"{cname} ownedBy {owner if result else 'none'}")
        ent.append(f"{cname} cleanedBy none")
        borrows = values.get(sig.borrows, "none") if sig.borrows and result else "none"
        ent.append(f"{cname} borrows {borrows}")
        mark = mark.strip()
        after = None
        if sig.raises:
            et = self.prog.spell(self.m, sig.raises)
            if mark.startswith("~"):
                # D-54: a discarded failure is caught, both ifError arms go to one block, and it names every variant
                why = mark[1:].strip() or '"The failure has nowhere to be reported, so it is discarded"'
                ent.insert(1, f"{cname} rationale {why}")
                mark = "~"
                ename = cname + "Error"
                self.local(ename, sig.raises)
                ent.append(f"{cname} catch {ename} {et}")
                ent += [f"{cname} suppresses {et}.{n}" for n, _p in self.prog.variants(sig.raises)]
                after = (cname + "Done", None)
            else:
                if mark.startswith("!"):
                    ename = mark[1:].strip()
                else:
                    ename = cname + "Error"
                self.local(ename, sig.raises)
                ent.append(f"{cname} catch {ename} {et}")
                ent.append(f"{cname} suppresses none")
                if mark == "?^":
                    if self.raises is None or self.prog.canon(self.m, self.raises) != sig.raises:
                        raise GenError(f"{self.name}: cannot propagate {sig.raises} from {target}")
                    fail = cname + "Failed"
                    after = (fail, None)
                elif mark.startswith("?"):
                    after = (mark[1:].strip(), None)
                elif mark.startswith("!"):
                    after = None
                else:
                    raise GenError(f"{self.name}: {target} can fail; mark it ?^, ? label, ! name, or ~: {line}")
        else:
            if mark:
                raise GenError(f"{self.name}: {target} cannot fail, but is marked {mark}")
            ent.append(f"{cname} catch none")
            ent.append(f"{cname} suppresses none")
        self.calls.append(ent)
        if task:
            self.step(f"start {cname} into none")
            self.step(f"join {cname}")
        else:
            self.step(f"do {cname}")
        if after is not None:
            target_label = after[0]
            done = cname + "Done"
            within = self.within_for_next()
            self.step(f"branch ifError {cname} goto {target_label} else goto {done}")
            if mark == "?^":
                self.claim(target_label)
                fb = Block(target_label)
                fb.steps.append(f"return error {cname}Error")
                fb.closed = True
                self.fail_blocks.append(fb)
            self.open_block(done, within=within)

    # ---------------------------------------------------------------- rendering
    def render(self):
        if self.cur is not None and not self.cur.closed:
            raise GenError(f"{self.name}: block {self.cur.name} does not end with a jump")
        n = self.name
        rows = [f"{n} is {'test' if self.test else 'operation'}", f"{n} purpose {q(self.purpose)}"]
        if self.test:
            rows += [f"{n} verifies {a} {b}" for a, b in self.verifies]
        else:
            rows += [f"{n} invariant {a} {q(b)}" for a, b in self.invariants] or [f"{n} invariant none"]
        rows.append(f"{n} typeParameter none")
        rows += [f"{n} input {a} {b} {c}" for a, b, c in self.inputs] or [f"{n} input none"]
        rows.append(f"{n} output {self.output or 'none'}")
        rows.append(f"{n} outputOwnedBy {self.owner or 'none'}")
        rows.append(f"{n} raises {self.raises or 'none'}")
        rows += [f"{n} effect {e}" for e in self.effects] or [f"{n} effect none"]
        rows += [f"{n} uses {u}" for u in self.uses] or [f"{n} uses none"]
        heap = bool(self.regions) or any(t == "Region" for _a, t, _c in self.inputs)
        rows.append(f"{n} memoryHeap {'true' if heap else 'false'}")
        rows.append(f"{n} async {'true' if self.async_ else 'false'}")
        rows.append(f"{n} maxRecursion {self.recursion or 'none'}")
        blocks = self.blocks + self.fail_blocks
        for b in blocks:
            if b.note:
                rows.append(f"{n} label {b.name} note {b.note}")
            rows.append(f"{n} label {b.name} loopKind {b.loop}")
            rows.append(f"{n} label {b.name} within {b.within}")
            if b.bound is not None:
                rows.append(f"{n} label {b.name} maxIterations {b.bound}")
            if b.over is not None:
                rows.append(f"{n} label {b.name} over {b.over}")
        if self.lets:
            for name, (c, v, mut) in self.lets.items():
                rows.append(f"{n} let {name} {self.prog.spell(self.m, c)} {v} {'mutable' if mut else 'immutable'}")
        else:
            rows.append(f"{n} let none")
        for b in blocks:
            rows += [f"{n} at {b.name} {s}" for s in b.steps]
        out = ["\n".join(rows)]
        for r, size, rel in self.regions:
            out.append("\n".join([f"{r} is region", f"{r} in {n}", f"{r} strategy arena", f"{r} maxBytes {size}",
                                  f"{r} released {rel}"]))
        out += ["\n".join(c) for c in self.calls]
        return out


class Generator:
    def __init__(self, prog: Program, m: Module):
        self.prog, self.m = prog, m
        self.out = []  # (text) chunks, comments included
        self.test_out = []
        self.header_comment = []

    def parse(self, text):
        lines = text.split("\n")
        i = 0
        pending_comment = []
        target = self.out
        while i < len(lines):
            raw = lines[i]
            if raw.strip() == "" :
                i += 1
                continue
            if raw.startswith("##"):
                pending_comment.append("#" + raw[2:])
                i += 1
                continue
            if raw.startswith("#"):
                i += 1
                continue
            if raw.startswith("@tests"):
                target = self.test_out
                i += 1
                continue
            if raw[0] in " \t":
                raise GenError(f"{self.m.name}: unexpected indented line {i + 1}: {raw}")
            body = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith((" ", "\t", ":")) or lines[j].strip() == "" or
                                      (lines[j].startswith("@") and not lines[j].startswith("@tests"))):
                if lines[j].strip() and not lines[j].strip().startswith("#"):
                    body.append(lines[j].strip())
                j += 1
            try:
                chunks = self.entity(raw, body)
            except GenError as e:
                raise GenError(f"{self.m.name} line {i + 1}: {e}")
            if pending_comment and chunks:
                chunks[0] = "\n".join(pending_comment) + "\n" + chunks[0]
            pending_comment = []
            target.extend(chunks)
            i = j

    def entity(self, head, body):
        t = tokens(head)
        k = t[0]
        m = self.m
        if k == "comment":
            return []
        if k == "module":
            name, purpose = t[1], t[2]
            rows = [f"{name} is module", f"{name} purpose {purpose}"]
            for b in body:
                bt = tokens(b)
                rows += [f"{name} {bt[0]} {x}" for x in bt[1:]]
            return ["\n".join(rows)]
        if k == "capability":
            name, purpose = t[1], t[2]
            rows = [f"{name} is capability", f"{name} purpose {purpose}"]
            if len(t) > 3:
                rows.append(f"{name} grants {' '.join(t[3:])}")
            rows += [f"{name} {b}" for b in body if tokens(b)[0] == "grants"]
            return ["\n".join(rows)]
        if k == "record":
            name, purpose = t[1], t[2]
            rows = [f"{name} is record", f"{name} purpose {purpose}", f"{name} typeParameter none"]
            for b in body:
                bt = tokens(b)
                rows.append(f"{name} field {bt[1]} {bt[2]}")
            return ["\n".join(rows)]
        if k == "enum":
            name, purpose = t[1], t[2]
            rows = [f"{name} is enum", f"{name} purpose {purpose}", f"{name} typeParameter none"]
            for b in body:
                bt = tokens(b)
                rows.append(f"{name} variant {bt[1]} {bt[2] if len(bt) > 2 else 'none'}")
            return ["\n".join(rows)]
        if k == "optype":
            name, purpose = t[1], t[2]
            ins = [tokens(b)[1:] for b in body if tokens(b)[0] == "input"]
            out = [tokens(b)[1] for b in body if tokens(b)[0] == "output"]
            raises = [tokens(b)[1] for b in body if tokens(b)[0] == "raises"]
            rows = [f"{name} is operationType", f"{name} purpose {purpose}", f"{name} typeParameter none"]
            rows += [f"{name} input {' '.join(i)}" for i in ins] or [f"{name} input none"]
            rows += [f"{name} output {out[0] if out else 'none'}", f"{name} outputOwnedBy none",
                     f"{name} raises {raises[0] if raises else 'none'}", f"{name} effect none", f"{name} async false"]
            return ["\n".join(rows)]
        if k == "instance":
            name, purpose = t[1], t[2]
            return ["\n".join([f"{name} is typeInstance", f"{name} purpose {purpose}", f"{name} in none",
                               f"{name} instantiates {' '.join(t[3:])}"])]
        if k == "constant":
            name, purpose, type_, value = t[1], t[2], t[3], " ".join(t[4:])
            return ["\n".join([f"{name} is constant", f"{name} purpose {purpose}", f"{name} type {type_}",
                               f"{name} value {value}"])]
        if k == "table":
            name, purpose, rtype = t[1], t[2], t[3]
            rows = [f"{name} is table", f"{name} purpose {purpose}", f"{name} rowType {rtype}"]
            cells = []
            for idx, b in enumerate(body, 1):
                bt = tokens(b)
                rname = bt[1]
                rows.append(f"{name} row {rname} {idx}")
                for kv in bt[2:]:
                    key, val = kv.split("=", 1)
                    cells.append(f"{name} cell {rname} {key} {val}")
            return ["\n".join(rows + cells)]
        if k in ("op", "test"):
            ob = OpBuilder(self, m, t[1], unq(t[2]), test=(k == "test"))
            header_done = False
            body = self.expand(body)
            early = [b for b in body if b.startswith(("let ", "region "))]
            body = [b for b in body if not b.startswith(("let ", "region "))]
            heads = [b for b in body if tokens(b)[0] in ("invariant", "verifies", "input", "output", "owner", "raises",
                                                         "effect", "uses", "recursion", "async")]
            for b in heads:
                ob.header(tokens(b))
            body = [b for b in body if b not in heads]
            for b in early:
                ob.header(tokens(b))
            for b in body:
                bt = tokens(b)
                if not header_done and ob.header(bt):
                    continue
                header_done = True
                if b.startswith(":"):
                    self.block_line(ob, b)
                else:
                    ob.stmt(b)
            return ob.render()
        raise GenError(f"unknown entity line: {head}")

    macros = {}

    def expand(self, body):
        out = []
        for b in body:
            if b.startswith("@"):
                t = tokens(b[1:])
                fn = self.macros.get(t[0])
                if fn is None:
                    raise GenError(f"unknown macro {t[0]}")
                out += self.expand([x.strip() for x in fn(*t[1:]) if x.strip()])
            else:
                out.append(b)
        return out

    def block_line(self, ob, b):
        bt = tokens(b)
        name = bt[0][1:]
        attrs = {}
        for kv in bt[1:]:
            key, val = kv.split("=", 1)
            attrs[key] = val
        loop = attrs.get("loop", "none")
        ob.open_block(name, loop=loop, within=attrs.get("in", "none"), bound=attrs.get("max"),
                      over=attrs.get("over"), note=attrs.get("note"))

    def declare(self, text):
        """First pass over a DSL text: declare types, ops, constants, tables so signatures resolve."""
        m = self.m
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            raw = lines[i]
            if not raw.strip() or raw.startswith("#") or raw[0] in " \t" or raw.startswith("@"):
                i += 1
                continue
            t = tokens(raw)
            body = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith((" ", "\t", ":")) or lines[j].strip() == ""):
                if lines[j].strip() and not lines[j].strip().startswith("#"):
                    body.append(tokens(lines[j].strip()))
                j += 1
            k = t[0]
            if k == "record":
                d = TypeDecl("record", f"{m.name}.{t[1]}")
                d.fields = [(b[1], b[2]) for b in body]
                m.types[t[1]] = d
            elif k == "enum":
                d = TypeDecl("enum", f"{m.name}.{t[1]}")
                d.variants = [(b[1], b[2] if len(b) > 2 else None) for b in body]
                m.types[t[1]] = d
            elif k == "optype":
                d = TypeDecl("optype", f"{m.name}.{t[1]}")
                d.sig = ("raw", [(b[1], b[2], b[3]) for b in body if b[0] == "input"],
                         ([b[1] for b in body if b[0] == "output"] or [None])[0], None,
                         ([b[1] for b in body if b[0] == "raises"] or [None])[0])
                m.types[t[1]] = d
            elif k == "instance":
                d = TypeDecl("instance", f"{m.name}.{t[1]}")
                d.generic, d.args = t[3], t[4:]
                m.types[t[1]] = d
            elif k == "table":
                d = TypeDecl("table", f"{m.name}.{t[1]}")
                d.row_type = t[3]
                m.tables[t[1]] = d
            elif k == "constant":
                m.constants[t[1]] = t[3]
            elif k == "op":
                ins, out, owner, raises = [], None, None, None
                for b in body:
                    if b[0] == "input":
                        ins.append((b[1], b[2], b[3]))
                    elif b[0] == "output":
                        out = b[1]
                    elif b[0] == "owner":
                        owner = b[1]
                    elif b[0] == "raises":
                        raises = b[1]
                m.ops[t[1]] = ("raw", ins, out, owner, raises)
            i = j

    def render(self, header_comment, tests_header=None):
        text = "\n".join(header_comment) + "\n\n" + "\n\n".join(self.out) + "\n"
        f = format_text(text)
        if f is None:
            raise GenError(f"{self.m.name}: generated text has lexical errors")
        tf = None
        if self.test_out:
            ttext = "\n".join(tests_header or []) + "\n\n" + "\n\n".join(self.test_out) + "\n"
            tf = format_text(ttext)
            if tf is None:
                raise GenError(f"{self.m.name}: generated tests have lexical errors")
        return f, tf


def unq(s):
    if s.startswith('"') and s.endswith('"'):
        return s[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return s
