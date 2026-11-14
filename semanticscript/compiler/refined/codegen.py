"""LLVM backend for the refined front end.

Generates LLVM IR straight from the checked refined model (no legacy compiler,
no lowering bridge). It compiles only what is reachable from the roots it is
given (the project entry, or one test), so a module that uses features the
backend does not support yet only blocks programs that actually reach it.

Value representation:
- integers, `Byte`, `ExitCode`: fixed-width integers; `Bool`: i1; floats: f32/f64
- `String`: {i8* bytes, i64 length} (not NUL-terminated, LR-27)
- records: a literal struct of their fields, by value
- enums (including error enums): {i32 tag, i64 payload}; payloads are integer-like
- operation references: function pointers

Calling convention: an operation that raises returns {i1 failed, output, error};
one that does not returns its output (or void).

Run-time rules enforced here (LR-12, LR-22, LR-38): overflow, division by zero,
narrowing conversions, out-of-range shifts, `maxIterations` (counted as returns
to the loop header from inside the loop), and `maxRecursion`. Each traps through
`refined_trap` with a message naming the source.

Not supported yet (reported as R901): tasks and task groups, regions and every
region-owned value other than string literals, cleanups, generic operations and
instances, and library targets without an implementation below.
"""
from __future__ import annotations

from typing import Optional

from llvmlite import ir

from . import shapes as S
from .diagnostics import Diagnostic
from .check import TEST_OFFSET
from .runtime import default_triple
from .semantics import CallInfo, Module, OpInfo, World, resolve_variant

I1, I8, I16, I32, I64 = ir.IntType(1), ir.IntType(8), ir.IntType(16), ir.IntType(32), ir.IntType(64)
F32, F64 = ir.FloatType(), ir.DoubleType()
PTR = I8.as_pointer()
STR = ir.LiteralStructType([PTR, I64])
ENUM = ir.LiteralStructType([I32, I64])
INT_TYPES = {"Int8": I8, "Int16": I16, "Int32": I32, "Int64": I64, "UInt8": I8, "UInt16": I16, "UInt32": I32,
             "UInt64": I64, "Byte": I8, "ExitCode": I32}
UNSIGNED = {"UInt8", "UInt16", "UInt32", "UInt64", "Byte"}

# callbacks provided by the runtime (runtime.py)
CALLBACKS = {
    "refined_trap": ir.FunctionType(ir.VoidType(), [PTR, I64]),
    "refined_write": ir.FunctionType(I32, [I32, PTR, I64, I32]),
    "refined_write_int": ir.FunctionType(I32, [I32, I64, I32]),
    "refined_bytes_equal": ir.FunctionType(I32, [PTR, I64, PTR, I64]),
    "refined_assert_int": ir.FunctionType(ir.VoidType(), [I64, I64, PTR, I64]),
    "refined_assert_true": ir.FunctionType(ir.VoidType(), [I32, PTR, I64]),
    "refined_assert_str": ir.FunctionType(ir.VoidType(), [PTR, I64, PTR, I64, PTR, I64]),
    "refined_fail": ir.FunctionType(ir.VoidType(), [PTR, I64, PTR, I64]),
    "refined_region_new": ir.FunctionType(PTR, [I64, PTR, I64]),
    "refined_region_alloc": ir.FunctionType(PTR, [PTR, I64]),
    "refined_region_free": ir.FunctionType(ir.VoidType(), [PTR]),
    "refined_write_float": ir.FunctionType(I32, [I32, F64, I32]),
    "refined_format_int": ir.FunctionType(PTR, [I64, PTR, I64.as_pointer()]),
    "refined_find": ir.FunctionType(I64, [PTR, I64, PTR, I64]),
    "refined_parse_int": ir.FunctionType(I32, [PTR, I64, I64.as_pointer()]),
}
# list.List value: pointer to {length, capacity, data, region}
LIST_HEADER = ir.LiteralStructType([I64, I64, PTR, PTR])
LIST = LIST_HEADER.as_pointer()


class Unsupported(Exception):
    def __init__(self, file: str, line: int, message: str):
        super().__init__(message)
        self.file, self.line, self.message = file, line, message


def function_name(module: str, op: str) -> str:
    return f"{module}.{op}"


class Backend:
    def __init__(self, world: World):
        self.world = world
        self.module = ir.Module(name="refined")
        self.module.triple = default_triple()
        self.functions: dict[tuple[str, str], ir.Function] = {}
        self.pending: list[tuple[Module, OpInfo, ir.Function]] = []
        self.strings: dict[bytes, ir.GlobalVariable] = {}
        self.callbacks = {n: ir.Function(self.module, t, name=n) for n, t in CALLBACKS.items()}
        self.tables: dict[tuple[str, str], ir.GlobalVariable] = {}
        self.depth: dict[str, ir.GlobalVariable] = {}
        self._types: dict[str, ir.Type] = {}
        self._stack_guard()

    def _stack_guard(self) -> None:
        """A stack floor for recursive operations (LR-12): the runtime calls `refined_set_stack_budget`
        on the thread that runs the program, and a recursive operation traps when its frame lies below
        the floor, instead of overflowing the native stack."""
        self.stack_floor = ir.GlobalVariable(self.module, I64, name="refined.stackFloor")
        self.stack_floor.initializer = I64(0)
        fn = ir.Function(self.module, ir.FunctionType(ir.VoidType(), [I64]), name="refined_set_stack_budget")
        b = ir.IRBuilder(fn.append_basic_block("entry"))
        here = b.ptrtoint(b.alloca(I8, name="probe"), I64)
        b.store(b.sub(here, fn.args[0]), self.stack_floor)
        b.ret_void()

    # ------------------------------------------------------------ driver

    def build(self, roots: list[tuple[str, str]]) -> ir.Module:
        for mod, op in roots:
            self.function_for(mod, op, None, 1)
        while self.pending:
            m, info, fn = self.pending.pop()
            OpGen(self, m, info, fn).emit()
        return self.module

    # ------------------------------------------------------------ types

    def ltype(self, canon: Optional[str], file: str = "", line: int = 0) -> ir.Type:
        if canon is None:
            raise Unsupported(file, line, "a value of unknown type")
        if canon in INT_TYPES:
            return INT_TYPES[canon]
        if canon == "Bool":
            return I1
        if canon == "Float64":
            return F64
        if canon == "Float32":
            return F32
        if canon == "String":
            return STR
        if canon == "Region":
            return PTR
        if canon in self._types:
            return self._types[canon]
        info = self.world.type_info(canon)
        if info is None:
            raise Unsupported(file, line, f"type `{canon}`")
        if info.kind == "record" and not info.type_params:
            t = ir.LiteralStructType([self.ltype(ft, file, line) for _n, ft in info.fields])
        elif info.kind in ("enum",) and not info.type_params or (info.kind == "instance" and info.variants
                                                                  and info.generic == "option.Option"):
            for _n, p in info.variants:
                if p is not None and p not in INT_TYPES and p != "Bool" and not self.tag_only(p):
                    raise Unsupported(file, line, f"an enum payload of type `{p}` in `{canon}` (payloads are "
                                      "integers, `Byte`, `Bool`, or enums without payloads)")
            t = ENUM
        elif info.kind == "instance" and info.generic == "list.List":
            self.ltype(info.args[0], file, line)  # the element type must be supported too
            t = LIST
        elif info.kind == "alias":
            t = self.ltype(info.base, file, line)
        elif info.kind == "operationType" and info.sig is not None:
            t = self.fn_type(info.sig, file, line).as_pointer()
        else:
            raise Unsupported(file, line, f"values of type `{canon}`")
        self._types[canon] = t
        return t

    def tag_only(self, canon: Optional[str]) -> bool:
        """An enum none of whose variants carries a payload: stored by its tag alone."""
        info = self.world.type_info(canon)
        return info is not None and info.kind == "enum" and all(p is None for _n, p in info.variants)

    def fn_type(self, sig, file: str, line: int) -> ir.FunctionType:
        params = [self.ltype(p.type, file, line) for p in sig.inputs]
        out = self.ltype(sig.output, file, line) if sig.output else None
        if sig.raises:
            ret = ir.LiteralStructType([I1, out or I8, self.ltype(sig.raises, file, line)])
        else:
            ret = out or ir.VoidType()
        return ir.FunctionType(ret, params)

    # ------------------------------------------------------------ functions, strings, tables

    def function_for(self, mod: str, op: str, file: Optional[str], line: int) -> ir.Function:
        key = (mod, op)
        if key in self.functions:
            return self.functions[key]
        m = self.world.modules[mod]
        info = m.op_infos.get(op)
        if info is None:
            raise Unsupported(file or m.file, line, f"`{mod}.{op}`")
        ent = info.entity
        if info.tparams:
            raise Unsupported(m.file, ent.line, f"generic operation `{op}`")
        if ent.value("async") == "true":
            raise Unsupported(m.file, ent.line, f"async operations such as `{op}`")
        fn = ir.Function(self.module, self.fn_type(info.sig, m.file, ent.line), name=function_name(mod, op))
        self.functions[key] = fn
        self.pending.append((m, info, fn))
        return fn

    def string(self, text: str) -> ir.Constant:
        data = text.encode("utf-8", "surrogateescape")
        g = self.strings.get(data)
        if g is None:
            arr = ir.ArrayType(I8, max(len(data), 1))
            g = ir.GlobalVariable(self.module, arr, name=f"str.{len(self.strings)}")
            g.global_constant = True
            g.linkage = "private"
            g.initializer = ir.Constant(arr, bytearray(data or b"\0"))
            self.strings[data] = g
        return ir.Constant(STR, [g.gep([I32(0), I32(0)]), I64(len(data))])

    def enum_const(self, canon: str, variant: str, payload: int = 0) -> ir.Constant:
        info = self.world.type_info(canon)
        tag = [n for n, _p in info.variants].index(variant)
        return ir.Constant(ENUM, [I32(tag), I64(payload)])

    def table(self, m: Module, name: str) -> tuple[ir.GlobalVariable, int, str]:
        key = (m.short, name)
        ent = m.tables[name]
        from .semantics import resolve_type
        rec = resolve_type(self.world, m, ent.value("of"), ent.line, quiet=True)
        info = self.world.type_info(rec)
        rtype = self.ltype(rec, m.file, ent.line)
        rows = sorted(ent.facts("row"), key=lambda r: int(r.text(1)))
        if key not in self.tables:
            consts = []
            for r in rows:
                cells = {c.text(1): c.args[2] for c in ent.facts("cell") if c.text(0) == r.text(0)}
                vals = [self.literal(m, cells[fname], ftype, ent.line) for fname, ftype in info.fields]
                consts.append(ir.Constant(rtype, vals))
            arr = ir.ArrayType(rtype, len(consts))
            g = ir.GlobalVariable(self.module, arr, name=f"table.{m.short}.{name}")
            g.global_constant = True
            g.initializer = ir.Constant(arr, consts)
            self.tables[key] = g
        return self.tables[key], len(rows), rec

    def literal(self, m: Module, tok, canon: str, line: int) -> ir.Constant:
        t = self.ltype(canon, m.file, line)
        info = self.world.type_info(canon)
        base = info.base if info is not None and info.kind == "alias" else canon
        if tok.kind == "string":
            return self.string(tok.value)
        raw = tok.raw
        if raw in ("true", "false"):
            return ir.Constant(I1, 1 if raw == "true" else 0)
        if S.is_variant(raw):
            v = resolve_variant(self.world, m, raw, line, quiet=True)
            return self.enum_const(v[0], v[1])
        if S.INT.match(raw):
            return ir.Constant(t, int(raw))
        if S.FLOAT.match(raw):
            return ir.Constant(t, float(raw))
        if S.is_name(raw) and raw in m.ops:
            return self.function_for(m.short, raw, m.file, line)
        raise Unsupported(m.file, line, f"literal `{raw}` of type `{base}`")

    def depth_counter(self, name: str) -> ir.GlobalVariable:
        if name not in self.depth:
            g = ir.GlobalVariable(self.module, I64, name=f"depth.{name}")
            g.initializer = I64(0)
            self.depth[name] = g
        return self.depth[name]


class OpGen:
    """Emits the body of one operation or test."""

    def __init__(self, backend: Backend, m: Module, info: OpInfo, fn: ir.Function):
        self.be, self.m, self.info, self.fn = backend, m, info, fn
        self.ent = info.entity
        self.world = backend.world
        self.allocas: dict[str, ir.AllocaInstr] = {}
        self.failed: dict[str, ir.AllocaInstr] = {}
        self.blocks: dict[str, ir.Block] = {}
        self.steps: dict[str, list] = {}
        self.order: list[str] = []
        self.kinds: dict[str, str] = {}
        self.within: dict[str, str] = {}
        self.bounds: dict[str, str] = {}
        self.counters: dict[str, ir.AllocaInstr] = {}
        self.indexes: dict[str, ir.AllocaInstr] = {}
        self.edge_cache: dict[tuple[str, str], ir.Block] = {}
        self.depth: Optional[ir.GlobalVariable] = None
        self.max_depth: Optional[int] = None

    def fn_alloca(self, t: ir.Type, name: str):
        """An alloca in the entry block, so loops do not grow the stack."""
        b = ir.IRBuilder(self.fn.entry_basic_block)
        b.position_at_start(self.fn.entry_basic_block)
        return b.alloca(t, name=name)

    def where(self, line: int) -> tuple[str, int]:
        """Rows from a module's `.test.sem` file carry an offset line number (check.TEST_OFFSET)."""
        if line >= TEST_OFFSET:
            return self.m.file[:-4] + ".test.sem", line - TEST_OFFSET
        return self.m.file, line

    def unsupported(self, line: int, what: str):
        raise Unsupported(*self.where(line), what)

    # ------------------------------------------------------------ setup

    def emit(self) -> None:
        ent = self.ent
        for o in self.info.owned.values():
            if o.kind not in ("call", "region"):
                self.unsupported(o.line, f"`{o.kind}` entities")
        self.regions = [o for o in self.info.owned.values() if o.kind == "region"]
        for r in ent.facts("at"):
            lab = r.text(0)
            if lab not in self.steps:
                self.steps[lab] = []
                self.order.append(lab)
            self.steps[lab].append((r.line, r.text(1), [t.raw for t in r.args[2:]]))
        for r in ent.facts("label"):
            lab, fact, val = r.text(0), r.text(1), r.text(2)
            if fact == "loopKind":
                self.kinds[lab] = val
            elif fact == "within":
                self.within[lab] = val
            elif fact == "maxIterations":
                self.bounds[lab] = val
        entry = self.fn.append_basic_block("entry")
        b = ir.IRBuilder(entry)
        for name, bind in self.info.bindings.items():
            self.allocas[name] = b.alloca(self.be.ltype(bind.type, *self.where(bind.line)), name=name)
        for name, ci in self.info.calls.items():
            if ci.catch is not None:
                self.failed[name] = b.alloca(I1, name=f"{name}.failed")
        for lab, kind in self.kinds.items():
            if kind != "none" and self.bounds.get(lab) not in (None, "unbounded"):
                self.counters[lab] = b.alloca(I64, name=f"{lab}.passes")
            if kind == "forEach":
                self.indexes[lab] = b.alloca(I64, name=f"{lab}.index")
        params = [p.name for p in self.info.sig.inputs]
        for arg, pname in zip(self.fn.args, params):
            b.store(arg, self.allocas[pname])
        for reg in self.regions:
            label = self.be.string(f"region `{reg.name}` of `{self.ent.name}`")
            handle = b.call(self.be.callbacks["refined_region_new"],
                            [I64(int(reg.value("capacity"))), b.extract_value(label, 0), b.extract_value(label, 1)])
            b.store(handle, self.allocas[reg.name])
        for r in ent.facts("let"):
            tok = r.args[3]
            if tok.raw == "unset":
                continue
            bind = self.info.bindings[r.text(0)]
            if tok.kind == "word" and S.is_name(tok.raw) and tok.raw in self.info.bindings:
                b.store(b.load(self.allocas[tok.raw]), self.allocas[bind.name])
            else:
                b.store(self.be.literal(self.m, tok, bind.type, r.line), self.allocas[bind.name])
        mr = ent.value("maxRecursion")
        if mr not in (None, "none"):
            self.depth = self.be.depth_counter(function_name(self.m.short, ent.name))
            self.max_depth = int(mr)
            d = b.add(b.load(self.depth), I64(1))
            b.store(d, self.depth)
            over = b.icmp_signed(">", d, I64(self.max_depth))
            with b.if_then(over, likely=False):
                self.trap(b, ent.line, f"`{ent.name}` called itself deeper than maxRecursion {self.max_depth}")
            here = b.ptrtoint(b.alloca(I8, name="stack.probe"), I64)
            floor = b.load(self.be.stack_floor)
            low = b.and_(b.icmp_unsigned("!=", floor, I64(0)), b.icmp_unsigned("<", here, floor))
            with b.if_then(low, likely=False):
                self.trap(b, ent.line, f"`{ent.name}` ran out of stack before reaching maxRecursion "
                          f"{self.max_depth}; lower the bound or recurse less deeply")
        for lab in self.order:
            self.blocks[lab] = self.fn.append_basic_block(lab)
        b.branch(self.edge(None, "begin"))
        for lab in self.order:
            self.emit_block(lab)

    def ancestors(self, lab: str) -> set:
        out, cur = set(), self.within.get(lab, "none")
        while cur != "none" and cur not in out:
            out.add(cur)
            cur = self.within.get(cur, "none")
        return out

    def trap(self, b: ir.IRBuilder, line: int, message: str) -> None:
        file, ln = self.where(line)
        text = self.be.string(f"{file}:{ln}: {message}")
        b.call(self.be.callbacks["refined_trap"], [b.extract_value(text, 0), b.extract_value(text, 1)])
        b.unreachable()

    def edge(self, frm: Optional[str], to: str) -> ir.Block:
        """The block that performs any loop bookkeeping for the jump frm -> to, then enters `to`."""
        kind = self.kinds.get(to, "none")
        if kind == "none":
            return self.blocks[to]
        key = (frm or "", to)
        if key in self.edge_cache:
            return self.edge_cache[key]
        blk = self.fn.append_basic_block(f"edge.{frm or 'entry'}.{to}")
        self.edge_cache[key] = blk
        b = ir.IRBuilder(blk)
        back = frm is not None and (frm == to or to in self.ancestors(frm))
        if back:
            if to in self.counters:
                n = b.add(b.load(self.counters[to]), I64(1))
                b.store(n, self.counters[to])
                bound = self.bounds[to]
                limit = I64(int(bound)) if S.INT.match(bound) else b.load(self.allocas[bound])
                over = b.icmp_signed(">", n, limit)
                with b.if_then(over, likely=False):
                    self.trap(b, self.steps[to][0][0], f"loop `{to}` in `{self.ent.name}` returned to its header more "
                              f"than maxIterations {bound} times")
        else:
            if to in self.counters:
                b.store(I64(0), self.counters[to])
            if to in self.indexes:
                b.store(I64(0), self.indexes[to])
        b.branch(self.blocks[to])
        return blk

    # ------------------------------------------------------------ steps

    def emit_block(self, lab: str) -> None:
        b = ir.IRBuilder(self.blocks[lab])
        steps = self.steps[lab]
        i = 0
        while i < len(steps):
            line, verb, a = steps[i]
            if verb == "do":
                self.call(b, self.info.calls[a[0]], line)
            elif verb == "set":
                b.store(b.load(self.allocas[a[1]]), self.allocas[a[0]])
            elif verb == "goto":
                b.branch(self.edge(lab, a[0]))
            elif verb == "branch" and a[0] == "if":
                b.cbranch(b.load(self.allocas[a[1]]), self.edge(lab, a[-4]), self.edge(lab, a[-1]))
            elif verb == "branch" and a[0] == "ifError":
                b.cbranch(b.load(self.failed[a[1]]), self.edge(lab, a[-4]), self.edge(lab, a[-1]))
            elif verb == "branch" and a[0] == "ifNext":
                self.if_next(b, lab, a, line)
            elif verb == "match":
                self.match(b, lab, a, steps[i + 1:], line)
                return
            elif verb == "return":
                self.ret(b, a, line)
            else:
                self.unsupported(line, f"the `{verb}` step")
            i += 1

    def if_next(self, b: ir.IRBuilder, lab: str, a: list, line: int) -> None:
        coll, item, yes, no = a[1], a[3], a[-4], a[-1]
        idx_ptr = self.indexes[lab]
        idx = b.load(idx_ptr)
        if coll in self.m.tables:
            g, n, _rec = self.be.table(self.m, coll)
            more = b.icmp_signed("<", idx, I64(n))
        elif coll in self.allocas:
            hdr = b.load(self.allocas[coll])
            more = b.icmp_signed("<", idx, b.load(b.gep(hdr, [I32(0), I32(0)])))
        else:
            self.unsupported(line, f"`forEach` over `{coll}`")
        take = self.fn.append_basic_block(f"{lab}.take")
        b.cbranch(more, take, self.edge(lab, no))
        tb = ir.IRBuilder(take)
        if coll in self.m.tables:
            elem = tb.load(tb.gep(g, [I32(0), idx]))
        else:
            et = self.be.ltype(self.info.bindings[item].type, *self.where(line))
            data = tb.bitcast(tb.load(tb.gep(hdr, [I32(0), I32(2)])), et.as_pointer())
            elem = tb.load(tb.gep(data, [idx]))
        tb.store(elem, self.allocas[item])
        tb.store(tb.add(idx, I64(1)), idx_ptr)
        tb.branch(self.edge(lab, yes))

    def match(self, b: ir.IRBuilder, lab: str, a: list, cases: list, line: int) -> None:
        value = b.load(self.allocas[a[0]])
        tag = b.extract_value(value, 0)
        payload = b.extract_value(value, 1)
        unreachable = self.fn.append_basic_block(f"{lab}.nomatch")
        ir.IRBuilder(unreachable).unreachable()
        sw = b.switch(tag, unreachable)
        for cline, _verb, ca in cases:
            v = resolve_variant(self.world, self.m, ca[0], cline, quiet=True)
            info = self.world.type_info(v[0])
            tagn = [n for n, _p in info.variants].index(v[1])
            blk = self.fn.append_basic_block(f"{lab}.case.{v[1]}")
            cb = ir.IRBuilder(blk)
            if ca[2] != "none":
                cb.store(self.narrow(cb, payload, self.info.bindings[ca[2]].type), self.allocas[ca[2]])
            cb.branch(self.edge(lab, ca[-1]))
            sw.add_case(I32(tagn), blk)

    def ret(self, b: ir.IRBuilder, a: list, line: int) -> None:
        for reg in self.regions:
            if reg.value("released") == "atReturn":
                b.call(self.be.callbacks["refined_region_free"], [b.load(self.allocas[reg.name])])
        if self.depth is not None:
            b.store(b.sub(b.load(self.depth), I64(1)), self.depth)
        sig = self.info.sig
        rtype = self.fn.function_type.return_type
        if sig.raises:
            out_t = rtype.elements[1]
            if a[0] == "ok":
                out = b.load(self.allocas[a[1]]) if a[1] != "none" else ir.Constant(out_t, 0)
                agg = b.insert_value(ir.Constant(rtype, ir.Undefined), I1(0), 0)
                agg = b.insert_value(agg, out, 1)
                agg = b.insert_value(agg, ir.Constant(ENUM, [I32(0), I64(0)]), 2)
            else:
                agg = b.insert_value(ir.Constant(rtype, ir.Undefined), I1(1), 0)
                agg = b.insert_value(agg, ir.Constant(out_t, None), 1)
                agg = b.insert_value(agg, b.load(self.allocas[a[1]]), 2)
            b.ret(agg)
        elif a[1] == "none":
            b.ret_void()
        else:
            b.ret(b.load(self.allocas[a[1]]))

    # ------------------------------------------------------------ values

    def widen(self, b: ir.IRBuilder, v, canon: str):
        if self.be.tag_only(canon):
            return b.zext(b.extract_value(v, 0), I64)
        if canon == "Bool" or canon in UNSIGNED:
            return b.zext(v, I64) if v.type != I64 else v
        return b.sext(v, I64) if v.type != I64 else v

    def narrow(self, b: ir.IRBuilder, v, canon: str):
        if self.be.tag_only(canon):
            return b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.trunc(v, I32), 0)
        t = self.be.ltype(canon, self.m.file, 0)
        return b.trunc(v, t) if t != I64 else v

    def arg_value(self, b: ir.IRBuilder, value: str, line: int):
        if value in self.allocas:
            return b.load(self.allocas[value])
        if value in self.m.ops:
            return self.be.function_for(self.m.short, value, self.m.file, line)
        self.unsupported(line, f"value `{value}`")

    # ------------------------------------------------------------ calls

    def call(self, b: ir.IRBuilder, ci: CallInfo, line: int) -> None:
        ent = ci.entity
        args = {slot: self.arg_value(b, value, ent.line) for slot, _t, value, _m, _l in ci.args}
        inv = ent.value("invokes")
        out = failed = err = None
        if ci.reference is not None:
            fptr = b.load(self.allocas[ci.reference])
            res = b.call(fptr, [args[p.name] for p in self._ref_sig(ci).inputs])
            out, failed, err = self._split(b, res, self._ref_sig(ci))
        elif ci.callee_op is not None or (inv and inv.split(".")[0] in self.world.modules and len(inv.split(".")) == 2):
            mod, op = (self.m.short, ci.callee_op) if ci.callee_op is not None and "." not in inv else inv.split(".")
            if mod not in self.world.modules or op not in self.world.modules[mod].op_infos:
                self.unsupported(ent.line, f"calling `{inv}` (generic operations are not supported yet)")
            fn = self.be.function_for(mod, op, self.m.file, ent.line)
            sig = self.world.modules[mod].op_infos[op].sig
            res = b.call(fn, [args[p.name] for p in sig.inputs])
            out, failed, err = self._split(b, res, sig)
        else:
            out, failed, err = self.intrinsic(b, inv, ci, args, ent.line)
        if ci.out is not None:
            b.store(out, self.allocas[ci.out[0]])
        if ci.catch is not None:
            b.store(failed if failed is not None else I1(0), self.failed[ent.name])
            if err is not None:
                b.store(err, self.allocas[ci.catch[0]])

    def _ref_sig(self, ci: CallInfo):
        t = self.info.bindings[ci.reference].type
        return self.world.type_info(t).sig

    def _split(self, b: ir.IRBuilder, res, sig):
        if sig.raises:
            return (b.extract_value(res, 1) if sig.output else None, b.extract_value(res, 0), b.extract_value(res, 2))
        return (res if sig.output else None), None, None

    def ctx(self, ci: CallInfo):
        file, ln = self.where(ci.entity.line)
        s = self.be.string(f"{file}:{ln}: `{ci.entity.name}` in `{self.ent.name}`")
        return s

    def intrinsic(self, b: ir.IRBuilder, inv: str, ci: CallInfo, args: dict, line: int):
        """Library targets and derived targets implemented in the backend."""
        parts = inv.split(".")
        cb = self.be.callbacks
        # derived targets of local or imported types
        if (len(parts) == 2 and S.UPPER.match(parts[0])) or len(parts) == 3:
            return self.derived(b, inv, ci, args, line)
        mod, name = parts
        a = [args[s] for s, *_ in ci.args]

        def trap_if(cond, message: str) -> None:
            with b.if_then(cond, likely=False):
                self.trap(b, line, message)

        def arith(op: str, x, y, t: str):
            if op in ("add", "subtract", "multiply"):
                fn = {"add": b.sadd_with_overflow, "subtract": b.ssub_with_overflow, "multiply": b.smul_with_overflow}[op]
                r = fn(x, y)
                trap_if(b.extract_value(r, 1), f"`{inv}` overflowed `{t}` in `{ci.entity.name}`")
                return b.extract_value(r, 0)
            width = x.type.width
            trap_if(b.icmp_signed("==", y, ir.Constant(x.type, 0)), f"`{inv}` divided by zero in `{ci.entity.name}`")
            trap_if(b.and_(b.icmp_signed("==", x, ir.Constant(x.type, -(1 << (width - 1)))),
                           b.icmp_signed("==", y, ir.Constant(x.type, -1))),
                    f"`{inv}` overflowed `{t}` in `{ci.entity.name}`")
            return b.sdiv(x, y) if op == "divide" else b.srem(x, y)

        if mod == "math":
            for t in ("Int64", "Int32"):
                for op in ("add", "subtract", "multiply", "divide", "remainder"):
                    if name == f"{op}{t}":
                        return arith(op, a[0], a[1], t), None, None
            for op, fn in (("Add", b.add), ("Subtract", b.sub), ("Multiply", b.mul)):
                if name == f"wrapping{op}Int64":
                    return fn(a[0], a[1]), None, None
            for op, fn in (("Add", b.sadd_with_overflow), ("Subtract", b.ssub_with_overflow),
                           ("Multiply", b.smul_with_overflow)):
                if name == f"saturating{op}Int64":
                    # on overflow the result clamps to the end of the range the exact result lies past
                    r = fn(a[0], a[1])
                    overflowed = b.extract_value(r, 1)
                    # an add or subtract overflows past the end its left operand's sign points to;
                    # a multiply past the end the product's sign points to
                    sign_of = b.xor(a[0], a[1]) if op == "Multiply" else a[0]
                    negative = b.icmp_signed("<", sign_of, I64(0))
                    clamp = b.select(negative, I64(-(1 << 63)), I64((1 << 63) - 1))
                    return b.select(overflowed, clamp, b.extract_value(r, 0)), None, None
            for op, ff in (("add", b.fadd), ("subtract", b.fsub), ("multiply", b.fmul), ("divide", b.fdiv)):
                if name == f"{op}Float64":
                    return ff(a[0], a[1]), None, None
        if mod == "compare":
            ops = {"equal": "==", "notEqual": "!=", "lessThan": "<", "lessOrEqual": "<=", "greaterThan": ">",
                   "greaterOrEqual": ">="}
            for op, sym in ops.items():
                for t in ("Int64", "Int32", "Byte", "Float64"):
                    if name == f"{op}{t}":
                        if t == "Float64":
                            return b.fcmp_ordered(sym, a[0], a[1]), None, None
                        if t == "Byte":
                            return b.icmp_unsigned(sym, a[0], a[1]), None, None
                        return b.icmp_signed(sym, a[0], a[1]), None, None
        if mod == "logic":
            if name == "and":
                return b.and_(a[0], a[1]), None, None
            if name == "or":
                return b.or_(a[0], a[1]), None, None
            if name == "xor":
                return b.xor(a[0], a[1]), None, None
            if name == "not":
                return b.not_(a[0]), None, None
        if mod == "math" and name in ("negateInt64", "absoluteInt64"):
            r = b.ssub_with_overflow(I64(0), a[0])
            trap_if(b.extract_value(r, 1), f"`{inv}` overflowed `Int64` in `{ci.entity.name}`")
            neg = b.extract_value(r, 0)
            if name == "negateInt64":
                return neg, None, None
            return b.select(b.icmp_signed("<", a[0], I64(0)), neg, a[0]), None, None
        if mod == "math" and name == "powerInt64":
            base, exp = a
            trap_if(b.icmp_signed("<", exp, I64(0)), f"`{inv}` with a negative exponent in `{ci.entity.name}`")
            # square-and-multiply: at most 63 rounds whatever the exponent. Squaring happens only while
            # exponent bits remain, so an overflowing square means the exact result overflows too.
            res_ptr = self.fn_alloca(I64, f"{ci.entity.name}.result")
            base_ptr = self.fn_alloca(I64, f"{ci.entity.name}.base")
            exp_ptr = self.fn_alloca(I64, f"{ci.entity.name}.exponent")
            b.store(I64(1), res_ptr)
            b.store(base, base_ptr)
            b.store(exp, exp_ptr)
            head = self.fn.append_basic_block(f"{ci.entity.name}.power")
            body = self.fn.append_basic_block(f"{ci.entity.name}.step")
            done = self.fn.append_basic_block(f"{ci.entity.name}.powered")
            b.branch(head)
            hb = ir.IRBuilder(head)
            hb.cbranch(hb.icmp_signed(">", hb.load(exp_ptr), I64(0)), body, done)
            bb = ir.IRBuilder(body)
            e = bb.load(exp_ptr)
            cur = bb.load(base_ptr)
            odd = bb.icmp_signed("!=", bb.and_(e, I64(1)), I64(0))
            with bb.if_then(odd):
                r = bb.smul_with_overflow(bb.load(res_ptr), cur)
                with bb.if_then(bb.extract_value(r, 1), likely=False):
                    self.trap(bb, line, f"`{inv}` overflowed `Int64` in `{ci.entity.name}`")
                bb.store(bb.extract_value(r, 0), res_ptr)
            rest = bb.ashr(e, I64(1))
            bb.store(rest, exp_ptr)
            with bb.if_then(bb.icmp_signed(">", rest, I64(0))):
                sq = bb.smul_with_overflow(cur, cur)
                with bb.if_then(bb.extract_value(sq, 1), likely=False):
                    self.trap(bb, line, f"`{inv}` overflowed `Int64` in `{ci.entity.name}`")
                bb.store(bb.extract_value(sq, 0), base_ptr)
            bb.branch(head)
            b.position_at_end(done)
            return b.load(res_ptr), None, None
        if mod == "bits":
            simple = {"andInt64": b.and_, "orInt64": b.or_, "xorInt64": b.xor}
            if name in simple:
                return simple[name](a[0], a[1]), None, None
            if name == "notInt64":
                return b.not_(a[0]), None, None
            if name in ("shiftLeftInt64", "shiftRightInt64"):
                bad = b.or_(b.icmp_signed("<", a[1], I64(0)), b.icmp_signed(">=", a[1], I64(64)))
                trap_if(bad, f"`{inv}` shift amount outside 0..63 in `{ci.entity.name}`")
                return (b.shl(a[0], a[1]) if name == "shiftLeftInt64" else b.ashr(a[0], a[1])), None, None
        if mod == "convert":
            def ranged(v, lo: int, hi: int, to, what: str):
                trap_if(b.or_(b.icmp_signed("<", v, ir.Constant(v.type, lo)), b.icmp_signed(">", v, ir.Constant(v.type, hi))),
                        f"`{inv}`: value out of range for `{what}` in `{ci.entity.name}`")
                return b.trunc(v, to)
            if name == "int32ToInt64" or name == "exitCodeToInt64":
                return b.sext(a[0], I64), None, None
            if name == "byteToInt64":
                return b.zext(a[0], I64), None, None
            if name in ("int64ToInt32", "int64ToExitCode"):
                return ranged(a[0], -(1 << 31), (1 << 31) - 1, I32, "Int32"), None, None
            if name == "int64ToByte":
                return ranged(a[0], 0, 255, I8, "Byte"), None, None
            if name == "int64ToFloat64":
                return b.sitofp(a[0], F64), None, None
            if name == "float64ToInt64":
                ok = b.and_(b.fcmp_ordered(">=", a[0], F64(-9.223372036854775808e18)),
                            b.fcmp_ordered("<", a[0], F64(9.223372036854775808e18)))
                trap_if(b.not_(ok), f"`{inv}`: value out of range for `Int64` in `{ci.entity.name}`")
                return b.fptosi(a[0], I64), None, None
        if mod == "console" and name in ("writeLine", "write", "writeError", "writeIntegerLine", "writeFloatLine"):
            fd = I32(2 if name == "writeError" else 1)
            newline = I32(0 if name in ("write",) else 1)
            if name == "writeIntegerLine":
                status = b.call(cb["refined_write_int"], [fd, a[0], newline])
            elif name == "writeFloatLine":
                status = b.call(cb["refined_write_float"], [fd, a[0], newline])
            else:
                status = b.call(cb["refined_write"], [fd, b.extract_value(a[0], 0), b.extract_value(a[0], 1), newline])
            failed = b.icmp_signed("!=", status, I32(0))
            err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.sext(status, I64), 1)
            return None, failed, err
        if mod == "string":
            if name == "byteLength":
                return b.extract_value(a[0], 1), None, None
            if name == "concat":
                l1, l2 = b.extract_value(a[0], 1), b.extract_value(a[1], 1)
                total = b.add(l1, l2)
                dst = b.call(self.be.callbacks["refined_region_alloc"], [a[2], total])
                memcpy = self.be.module.declare_intrinsic("llvm.memcpy", [PTR, PTR, I64])
                b.call(memcpy, [dst, b.extract_value(a[0], 0), l1, I1(0)])
                b.call(memcpy, [b.gep(dst, [l1]), b.extract_value(a[1], 0), l2, I1(0)])
                s = b.insert_value(ir.Constant(STR, ir.Undefined), dst, 0)
                return b.insert_value(s, total, 1), None, None
            if name == "fromInt64":
                len_ptr = self.fn_alloca(I64, f"{ci.entity.name}.len")
                p = b.call(cb["refined_format_int"], [a[0], a[1], len_ptr])
                s = b.insert_value(ir.Constant(STR, ir.Undefined), p, 0)
                return b.insert_value(s, b.load(len_ptr), 1), None, None
            if name == "slice":
                text, start, length = a
                ok = b.and_(b.icmp_signed(">=", start, I64(0)), b.icmp_signed(">=", length, I64(0)))
                # compare without forming start + length, which can overflow and wrap past the check:
                # start <= size and length <= size - start (both sides non-negative when ok)
                size = b.extract_value(text, 1)
                ok = b.and_(ok, b.icmp_signed("<=", start, size))
                ok = b.and_(ok, b.icmp_signed("<=", length, b.sub(size, start)))
                safe_start = b.select(ok, start, I64(0))
                s = b.insert_value(ir.Constant(STR, ir.Undefined), b.gep(b.extract_value(text, 0), [safe_start]), 0)
                s = b.insert_value(s, b.select(ok, length, I64(0)), 1)
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), start, 1)
                return s, b.not_(ok), err
            if name == "find":
                at = b.call(cb["refined_find"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                 b.extract_value(a[1], 0), b.extract_value(a[1], 1)])
                return at, b.icmp_signed("<", at, I64(0)), ir.Constant(ENUM, [I32(0), I64(0)])
            if name == "toInt64":
                out_ptr = self.fn_alloca(I64, f"{ci.entity.name}.parsed")
                status = b.call(cb["refined_parse_int"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1), out_ptr])
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), b.sub(status, I32(1)), 0)
                return b.load(out_ptr), b.icmp_signed("!=", status, I32(0)), err
            if name == "equals":
                eq = b.call(cb["refined_bytes_equal"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                        b.extract_value(a[1], 0), b.extract_value(a[1], 1)])
                return b.icmp_signed("!=", eq, I32(0)), None, None
            if name == "startsWith":
                plen = b.extract_value(a[1], 1)
                long_enough = b.icmp_signed(">=", b.extract_value(a[0], 1), plen)
                eq = b.call(cb["refined_bytes_equal"], [b.extract_value(a[0], 0), b.select(long_enough, plen, I64(0)),
                                                        b.extract_value(a[1], 0), plen])
                return b.and_(long_enough, b.icmp_signed("!=", eq, I32(0))), None, None
            if name == "byteAt":
                text, idx = a
                inside = b.and_(b.icmp_signed(">=", idx, I64(0)), b.icmp_signed("<", idx, b.extract_value(text, 1)))
                start = b.block
                read = self.fn.append_basic_block(f"{ci.entity.name}.read")
                done = self.fn.append_basic_block(f"{ci.entity.name}.done")
                b.cbranch(inside, read, done)
                rb = ir.IRBuilder(read)
                byte = rb.load(rb.gep(rb.extract_value(text, 0), [idx]))
                rb.branch(done)
                b.position_at_end(done)
                phi = b.phi(I8)
                phi.add_incoming(byte, read)
                phi.add_incoming(I8(0), start)
                err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), idx, 1)
                return phi, b.not_(inside), err
        if mod == "byte":
            v = a[0]

            def between(lo: int, hi: int):
                return b.and_(b.icmp_unsigned(">=", v, I8(lo)), b.icmp_unsigned("<=", v, I8(hi)))
            letter = b.or_(between(ord("a"), ord("z")), between(ord("A"), ord("Z")))
            digit = between(ord("0"), ord("9"))
            if name == "isLetter":
                return letter, None, None
            if name == "isDigit":
                return digit, None, None
            if name == "isLetterOrDigit":
                return b.or_(letter, digit), None, None
            if name == "isSpace":
                sp = b.or_(b.icmp_unsigned("==", v, I8(32)), b.icmp_unsigned("==", v, I8(9)))
                sp = b.or_(sp, b.or_(b.icmp_unsigned("==", v, I8(10)), b.icmp_unsigned("==", v, I8(13))))
                return sp, None, None
            if name == "equals":
                return b.icmp_unsigned("==", a[0], a[1]), None, None
        if mod == "test":
            c = self.ctx(ci)
            cp, cl = b.extract_value(c, 0), b.extract_value(c, 1)
            if name == "assertEqualInt64":
                b.call(cb["refined_assert_int"], [a[0], a[1], cp, cl])
                return None, None, None
            if name == "assertEqualExitCode":
                b.call(cb["refined_assert_int"], [b.sext(a[0], I64), b.sext(a[1], I64), cp, cl])
                return None, None, None
            if name == "assertTrue":
                b.call(cb["refined_assert_true"], [b.zext(a[0], I32), cp, cl])
                return None, None, None
            if name == "assertEqualString":
                b.call(cb["refined_assert_str"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1),
                                                  b.extract_value(a[1], 0), b.extract_value(a[1], 1), cp, cl])
                return None, None, None
            if name == "fail":
                b.call(cb["refined_fail"], [b.extract_value(a[0], 0), b.extract_value(a[0], 1), cp, cl])
                return None, None, None
        self.unsupported(line, f"the library target `{inv}`")

    def derived(self, b: ir.IRBuilder, inv: str, ci: CallInfo, args: dict, line: int):
        parts = inv.split(".")
        type_text, member = ".".join(parts[:-1]), parts[-1]
        from .semantics import resolve_type
        canon = resolve_type(self.world, self.m, type_text, line, quiet=True)
        info = self.world.type_info(canon)
        if info is None:
            self.unsupported(line, f"`{inv}`")
        if info.kind == "instance" and info.generic == "list.List":
            return self.list_member(b, member, info.args[0], args, ci, line)
        if info.kind == "record":
            t = self.be.ltype(canon, self.m.file, line)
            names = [n for n, _t in info.fields]
            if member == "new":
                agg = ir.Constant(t, ir.Undefined)
                for i, n in enumerate(names):
                    agg = b.insert_value(agg, args[n], i)
                return agg, None, None
            if member == "with":
                field = [s for s in args if s != "record"][0]
                return b.insert_value(args["record"], args[field], names.index(field)), None, None
            if member in names:
                return b.extract_value(args["record"], names.index(member)), None, None
            if member == "equals":
                return self.equals(b, args["left"], args["right"], canon, line), None, None
        if info.variants:
            names = [n for n, _p in info.variants]
            if member in names:
                payload = info.variants[names.index(member)][1]
                agg = ir.Constant(ENUM, [I32(names.index(member)), I64(0)])
                if payload is not None:
                    agg = b.insert_value(agg, self.widen(b, args["payload"], payload), 1)
                return agg, None, None
            if member == "equals":
                return self.equals(b, args["left"], args["right"], canon, line), None, None
        self.unsupported(line, f"`{inv}`")

    def sizeof(self, b: ir.IRBuilder, t: ir.Type):
        return b.ptrtoint(b.gep(ir.Constant(t.as_pointer(), None), [I32(1)]), I64)

    def list_member(self, b: ir.IRBuilder, member: str, item: str, args: dict, ci: CallInfo, line: int):
        """list.List in a region: a header {length, capacity, data, region} and a data block that doubles."""
        et = self.be.ltype(item, *self.where(line))
        alloc = self.be.callbacks["refined_region_alloc"]
        if member == "new":
            raw = b.call(alloc, [args["region"], self.sizeof(b, LIST_HEADER)])
            hdr = b.bitcast(raw, LIST)
            b.store(ir.Constant(LIST_HEADER, [I64(0), I64(0), ir.Constant(PTR, None), ir.Constant(PTR, None)]), hdr)
            b.store(args["region"], b.gep(hdr, [I32(0), I32(3)]))
            return hdr, None, None
        hdr = args["list"]
        len_ptr, cap_ptr, data_ptr = (b.gep(hdr, [I32(0), I32(i)]) for i in (0, 1, 2))
        length = b.load(len_ptr)
        if member == "length":
            return length, None, None
        if member == "clear":
            b.store(I64(0), len_ptr)
            return None, None, None
        if member == "append":
            cap = b.load(cap_ptr)
            with b.if_then(b.icmp_signed("==", length, cap)):
                newcap = b.select(b.icmp_signed("==", cap, I64(0)), I64(4), b.mul(cap, I64(2)))
                size = self.sizeof(b, et)
                fresh = b.call(alloc, [b.load(b.gep(hdr, [I32(0), I32(3)])), b.mul(newcap, size)])
                memcpy = self.be.module.declare_intrinsic("llvm.memcpy", [PTR, PTR, I64])
                b.call(memcpy, [fresh, b.load(data_ptr), b.mul(length, size), I1(0)])
                b.store(fresh, data_ptr)
                b.store(newcap, cap_ptr)
            slot = b.gep(b.bitcast(b.load(data_ptr), et.as_pointer()), [length])
            b.store(args["item"], slot)
            b.store(b.add(length, I64(1)), len_ptr)
            return None, None, None
        if member in ("get", "set"):
            idx = args["index"]
            inside = b.and_(b.icmp_signed(">=", idx, I64(0)), b.icmp_signed("<", idx, length))
            err = b.insert_value(ir.Constant(ENUM, [I32(0), I64(0)]), idx, 1)
            start = b.block
            body = self.fn.append_basic_block(f"{ci.entity.name}.inside")
            done = self.fn.append_basic_block(f"{ci.entity.name}.done")
            b.cbranch(inside, body, done)
            ib = ir.IRBuilder(body)
            slot = ib.gep(ib.bitcast(ib.load(data_ptr), et.as_pointer()), [idx])
            if member == "set":
                ib.store(args["item"], slot)
                ib.branch(done)
                b.position_at_end(done)
                return None, b.not_(inside), err
            value = ib.load(slot)
            ib.branch(done)
            b.position_at_end(done)
            phi = b.phi(et)
            phi.add_incoming(value, body)
            phi.add_incoming(ir.Constant(et, None), start)
            return phi, b.not_(inside), err
        self.unsupported(line, f"`list.List.{member}`")

    def equals(self, b: ir.IRBuilder, x, y, canon: str, line: int):
        if canon in INT_TYPES or canon == "Bool":
            return b.icmp_unsigned("==", x, y)
        if canon == "Float64":
            return b.fcmp_ordered("==", x, y)
        if canon == "String":
            eq = b.call(self.be.callbacks["refined_bytes_equal"], [b.extract_value(x, 0), b.extract_value(x, 1),
                                                                   b.extract_value(y, 0), b.extract_value(y, 1)])
            return b.icmp_signed("!=", eq, I32(0))
        info = self.world.type_info(canon)
        if info.kind == "record":
            acc = I1(1)
            for i, (_n, ft) in enumerate(info.fields):
                acc = b.and_(acc, self.equals(b, b.extract_value(x, i), b.extract_value(y, i), ft, line))
            return acc
        if info.variants:
            return b.and_(b.icmp_signed("==", b.extract_value(x, 0), b.extract_value(y, 0)),
                          b.icmp_signed("==", b.extract_value(x, 1), b.extract_value(y, 1)))
        self.unsupported(line, f"comparing values of `{canon}`")


def compile_roots(world: World, roots: list[tuple[str, str]]) -> tuple[Optional[ir.Module], list[Diagnostic]]:
    be = Backend(world)
    try:
        return be.build(roots), []
    except Unsupported as exc:
        return None, [Diagnostic("R901", f"the backend does not support {exc.message} yet", exc.file, exc.line)]
