"""The builder for tools/cmathlong.dsl: a small Python layer that writes the runtime's DSL (blocks, labels, loops)
so the long double mathematics (cmathlonggen.py) can be written as the algorithms they are.

An `Op` collects the lines of one DSL operation. Control is structured here and written out as the DSL's labelled
blocks: `if_`, `while_`, `for_`, with `exit_loop` to leave the innermost loop early. Each block of a loop is written
with `in=<loop head>`, as the language's checker wants (a block of a loop may jump to a block of its loop, to the loop
itself, or out of it).
"""
from __future__ import annotations

import re

ADDR = "machine.Address"


class Op:
    def __init__(self, name, doc, inputs, output=None, abi=None, invariant=None, effects=True):
        self.name, self.doc, self.inputs, self.output = name, doc, inputs, output
        self.abi, self.invariant, self.effects = abi, invariant, effects
        self.wsname = "ws"
        self.eff = (1, 1) if effects else (0, 0)
        self.lets, self.lines, self.closed = [], [":begin"], False
        self.ctx, self.exits, self.count = [], [], 0
        self.consts = {}
        self.labels = 0
        self.declared = {n for n, _t in inputs}

    # ------------------------------------------------------------ plumbing
    def fresh(self, base="t"):
        self.count += 1
        return f"{base}{self.count}"

    def emit(self, line):
        if self.closed:
            raise RuntimeError(f"{self.name}: statement after a jump: {line}")
        if self.wsname != "ws":
            line = re.sub(r"\bws\b", self.wsname, line)
        self.lines.append("  " + line)

    def newlabel(self, base):
        self.labels += 1
        return f"{base}{self.labels}"

    def label(self, name, head=False):
        text = f":{name}"
        if head:
            text += " loop=while max=forever"
        if self.ctx:
            text += f" in={self.ctx[-1]}"
        self.lines.append(text)
        self.closed = False

    # ------------------------------------------------------------ values
    def var(self, typ, init, base="v"):
        name = self.fresh(base)
        self.lets.append(f"  let {name} {typ} {init} mut")
        return name

    def const(self, typ, value, base=None):
        key = (typ, value)
        if key not in self.consts:
            name = base or self.fresh("k")
            if base and any(base == n for n in self.consts.values()):
                name = self.fresh(base)
            self.consts[key] = name
            self.lets.append(f"  let {name} {typ} {value}")
        return self.consts[key]

    def calc(self, expr, base="t"):
        name = self.fresh(base)
        self.emit(f"calc {name} = {expr}")
        return name

    def set(self, var, expr):
        self.emit(f"calc {var} := {expr}")

    def call(self, text):
        self.emit(text)

    # ------------------------------------------------------------ control
    def ret(self, name=None):
        self.emit("return" + (f" {name}" if name else ""))
        self.closed = True

    def goto(self, label):
        self.emit(f"goto {label}")
        self.closed = True

    def if_(self, cond, then, otherwise=None):
        yes, no, join = self.newlabel("yes"), self.newlabel("no"), self.newlabel("join")
        self.emit(f"when {cond} {yes} {no if otherwise else join}")
        self.closed = True
        self.label(yes)
        then()
        then_closed = self.closed
        if not then_closed:
            self.goto(join)
        else_closed = False
        if otherwise:
            self.label(no)
            otherwise()
            else_closed = self.closed
            if not else_closed:
                self.goto(join)
        if then_closed and otherwise and else_closed:
            self.closed = True
            return
        self.label(join)

    def while_(self, cond, body):
        head, inside, done = self.newlabel("head"), self.newlabel("body"), self.newlabel("done")
        if not self.closed:
            self.goto(head)
        self.label(head, head=True)
        self.emit(f"when {cond} {inside} {done}")
        self.closed = True
        self.ctx.append(head)
        self.exits.append(done)
        self.label(inside)
        body()
        if not self.closed:
            self.goto(head)
        self.ctx.pop()
        self.exits.pop()
        self.label(done)

    def exit_loop(self):
        self.goto(self.exits[-1])

    def for_(self, start, stop, body, var=None):
        i = var or self.var("Int64", "0", "i")
        self.set(i, str(start))

        def step():
            body(i)
            if not self.closed:
                self.set(i, f"{i} + 1")

        self.while_(f"{i} < {stop}", step)
        return i

    # ------------------------------------------------------------ rendering
    def render_test(self, verifies):
        out = [f'test {self.name} "{self.doc}"']
        out += [f"  verifies {a} {b}" for a, b in verifies]
        out += self.effect_lines()
        out += self.lets
        out += self.lines
        return "\n".join(out)

    def effect_lines(self):
        mem, sys_ = self.eff
        out = []
        if mem:
            out.append("  effect use machine.memory")
        if sys_:
            out.append("  effect use system.calls")
        if mem:
            out.append("  uses memoryAccess")
        if sys_:
            out.append("  uses systemCalls")
        return out

    def render(self):
        out = [f'op {self.name} "{self.doc}"']
        if self.invariant:
            out.append(f'  invariant {self.invariant[0]} "{self.invariant[1]}"')
        for nm, ty in self.inputs:
            out.append(f"  input {nm} {ty} copied")
        if self.output:
            out.append(f"  output {self.output}")
        out += self.effect_lines()
        if self.abi:
            out.append(f'  abi library "{self.abi}"')
        out += self.lets
        out += self.lines
        return "\n".join(out)


# ---------------------------------------------------------------- the workspace (shared by the generator's files)

N = 10                # limbs of a register's significand
REG = 128             # bytes of a register
BUF_P, BUF_Q, BUF_T, BUF_U = 16384, 16640, 16896, 17280      # raw buffers (cells of 8 bytes): 24, 24, 40, 40
WS_BYTES = 17664
MASK = "4294967295"
ALL = []              # every op, in order


def ld(e):
    return f"machine.loadUInt64(ws + ({e}))"


def ldi(e):
    return f"machine.loadInt64(ws + ({e}))"


def st(e, v):
    return f"machine.storeUInt64(ws + ({e}), {v})"


def sti(e, v):
    return f"machine.storeInt64(ws + ({e}), {v})"


def LIM(r, i):
    return f"({r}) * 128 + 24 + ({i}) * 8"


def HEAD(r, k):
    return f"({r}) * 128 + {8 * k}"


def new(name, doc, inputs, output=None, abi=None, invariant=None, effects=True, ws=True):
    ins = ([("ws", ADDR)] if ws else []) + inputs
    o = Op(name, doc, ins, output, abi, invariant, effects)
    ALL.append(o)
    return o


# ---------------------------------------------------------------- the effects each operation needs

EXTERNAL = {
    "clong.getPart": (1, 0), "clong.setPart": (1, 0), "clong.highOf": (1, 0), "clong.lowOf": (1, 0),
    "clong.setSignificand": (1, 0), "clong.unpack": (1, 1), "clong.pack": (1, 1), "clong.partsNew": (1, 1),
    "clong.settleAs": (1, 1), "clong.format": (0, 1), "clong.bitLength": (0, 0), "clong.lowBitsSet": (0, 0),
    "clibrary.setErrno": (1, 0), "heap.take": (1, 1), "heap.give": (1, 1), "system.aarch64": (0, 1),
}


def assign_effects(ops):
    """Give every op the effects it and what it calls perform (the checker rejects a declared effect nothing performs)."""
    by_name = {o.name: o for o in ops}
    calls = {}
    direct = {}
    for o in ops:
        text = chr(10).join(o.lets + o.lines)
        names = set(re.findall(r"([A-Za-z_][A-Za-z0-9_.]*)[(]", text))
        mem = sys_ = 0
        local = set()
        for n in names:
            if n in by_name:
                local.add(n)
            elif n in EXTERNAL:
                mem |= EXTERNAL[n][0]
                sys_ |= EXTERNAL[n][1]
            elif n.startswith("machine."):
                mem = 1
        calls[o.name] = local
        direct[o.name] = [mem, sys_]
    changed = True
    while changed:
        changed = False
        for name, local in calls.items():
            for callee in local:
                for i in (0, 1):
                    if direct[callee][i] and not direct[name][i]:
                        direct[name][i] = 1
                        changed = True
    for o in ops:
        o.eff = tuple(direct[o.name])
