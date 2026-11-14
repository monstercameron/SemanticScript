"""Control flow for one operation or test (plan step 5; LR-04, LR-16, LR-22, LR-23, LR-30, LR-33, LR-42).

The steps of an operation are an explicit graph: blocks named by labels, each
ending in a terminator. This module checks:
- block structure (contiguous, `begin` first, one terminator, match/case),
- label declarations (`loopKind`, `within`, and the loop-only facts),
- jumps, reachability, single entry into loops, cycles through headers,
- counted loops set their counter exactly once per pass,
- a fallible `do`/`join` is followed at once by its `branch ifError`,
- each call, task, and cleanup is activated the right number of times,
- every value is set on every path that reads it (definite assignment),
  with types checked at each use,
- returns, match coverage, and that tasks and groups are settled at returns.
"""
from __future__ import annotations

from typing import Optional

from . import shapes as S
from .semantics import CallInfo, Module, OpInfo, World, resolve_type, resolve_variant


class Step:
    __slots__ = ("line", "label", "verb", "args")

    def __init__(self, line: int, label: str, verb: str, args: list[str]):
        self.line, self.label, self.verb, self.args = line, label, verb, args


def check_flow(world: World, m: Module, op: OpInfo) -> None:
    Flow(world, m, op).run()


class Flow:
    def __init__(self, world: World, m: Module, op: OpInfo):
        self.world, self.m, self.op, self.sink = world, m, op, m.sink
        self.ent = op.entity
        self.blocks: dict[str, list[Step]] = {}
        self.order: list[str] = []
        self.decl: dict[str, dict[str, tuple[int, list[str]]]] = {}
        self.kinds: dict[str, str] = {}
        self.within: dict[str, str] = {}
        self.edges: list[tuple[int, str, str]] = []

    def err(self, code: str, line: int, msg: str) -> None:
        self.sink.error(code, line, msg)

    # ------------------------------------------------------------ driver

    def run(self) -> None:
        if not self._blocks():
            return
        self._labels()
        self._structure()
        self._loops()
        self._activations()
        self._dataflow()
        self._settled()
        self._ownership()
        self._iteration_loans()

    # ------------------------------------------------------------ blocks

    def _blocks(self) -> bool:
        rows = self.ent.facts("at")
        if not rows:
            self.err("R501", self.ent.line, f"`{self.ent.name}` has no steps; its first block is `begin`")
            return False
        for r in rows:
            label, verb = r.text(0), r.text(1)
            if label not in self.blocks:
                self.blocks[label] = []
                self.order.append(label)
            elif self.order[-1] != label:
                self.err("R501", r.line, f"the rows of block `{label}` are not together; a block's steps are contiguous")
            self.blocks[label].append(Step(r.line, label, verb, [t.raw for t in r.args[2:]]))
        if self.order[0] != "begin":
            self.err("R501", rows[0].line, "the first block of an operation is labelled `begin`")
        return True

    def _labels(self) -> None:
        last_group, last_fact, group_order = None, -1, []
        for r in self.ent.facts("label"):
            lab, fact = r.text(0), r.text(1)
            vals = [t.raw for t in r.args[2:]]
            d = self.decl.setdefault(lab, {})
            if fact in d:
                self.err("R305", r.line, f"label `{lab}` already states `{fact}` on line {d[fact][0]}")
            d[fact] = (r.line, vals)
            if lab != last_group:
                if lab in group_order:
                    self.err("R301", r.line, f"the label rows for `{lab}` are not together")
                group_order.append(lab)
                last_group, last_fact = lab, -1
            idx = S.LABEL_ORDER.index(fact)
            if idx < last_fact:
                self.err("R301", r.line, f"label facts come in the order: {', '.join(S.LABEL_ORDER)}")
            last_fact = max(last_fact, idx)
        known = [g for g in group_order if g in self.blocks]
        if known != [b for b in self.order if b in known]:
            self.err("R301", self.ent.line, "label declarations come in the same order as the blocks")
        for lab in group_order:
            if lab not in self.blocks:
                self.err("R305", self.decl[lab][next(iter(self.decl[lab]))][0], f"label `{lab}` is declared but has no block")
        for lab in self.order:
            d = self.decl.get(lab, {})
            for fact in ("loopKind", "within"):
                if fact not in d:
                    self.err("R305", self.blocks[lab][0].line, f"block `{lab}` needs `{self.ent.name} label {lab} "
                             f"{fact} ...` ({'none' if fact == 'within' else 'none, or a loop kind'} if it is not a loop)")
            self.kinds[lab] = d.get("loopKind", (0, ["none"]))[1][0]
            self.within[lab] = d.get("within", (0, ["none"]))[1][0]

    def _structure(self) -> None:
        for lab, steps in self.blocks.items():
            in_match = False
            for i, st in enumerate(steps):
                last = i == len(steps) - 1
                if st.verb in ("return", "goto", "branch") and not last:
                    self.err("R501", st.line, f"`{st.verb}` ends a block; nothing may follow it in `{lab}`")
                if in_match and st.verb != "case":
                    self.err("R501", st.line, "after `match`, a block holds only `case` rows")
                if st.verb == "case" and not in_match:
                    self.err("R501", st.line, "`case` follows a `match` row in the same block")
                if st.verb == "match":
                    in_match = True
                    if last:
                        self.err("R501", st.line, "a `match` is followed by one `case` row per variant")
                for tgt in self._targets(st):
                    if tgt not in self.blocks:
                        self.err("R502", st.line, f"no block is labelled `{tgt}`")
                    else:
                        self.edges.append((st.line, lab, tgt))
            if steps[-1].verb not in S.TERMINATORS:
                self.err("R501", steps[-1].line, f"block `{lab}` must end in `return`, `goto`, `branch`, or a `match`")
        reach, stack = {"begin"}, ["begin"]
        succ: dict[str, list[str]] = {}
        for _l, a, b in self.edges:
            succ.setdefault(a, []).append(b)
        while stack:
            for nxt in succ.get(stack.pop(), []):
                if nxt not in reach:
                    reach.add(nxt)
                    stack.append(nxt)
        for lab in self.order:
            if lab not in reach and lab in self.blocks:
                self.err("R511", self.blocks[lab][0].line, f"block `{lab}` cannot be reached from `begin`")

    @staticmethod
    def _targets(st: Step) -> list[str]:
        a = st.args
        if st.verb == "goto":
            return a[:1]
        if st.verb == "branch":
            return [a[-4], a[-1]]
        if st.verb == "case":
            return a[-1:]
        return []

    # ------------------------------------------------------------ loops

    def _ancestors(self, lab: str) -> set[str]:
        out, cur = set(), self.within.get(lab, "none")
        while cur != "none" and cur not in out:
            out.add(cur)
            cur = self.within.get(cur, "none")
        return out

    def _loops(self) -> None:
        for lab in self.order:
            d = self.decl.get(lab, {})
            k = self.kinds[lab]
            w = self.within[lab]
            line = d.get("loopKind", (self.blocks[lab][0].line,))[0]
            if w != "none" and self.kinds.get(w, "none") == "none":
                self.err("R503", line, f"block `{lab}` is `within {w}`, which is not a loop header")
            if w == lab:
                self.err("R503", line, f"block `{lab}` cannot be within itself")
            loop_only = ("maxIterations", "counter", "over")
            if k == "none":
                for f in loop_only:
                    if f in d:
                        self.err("R503", d[f][0], f"`{f}` belongs on a loop header; `{lab}` has `loopKind none`")
                continue
            bound = d.get("maxIterations")
            if bound is None:
                self.err("R503", line, f"loop `{lab}` states no `maxIterations`")
            elif (bound[1][0] == "unbounded") != (k == "forever"):
                self.err("R503", bound[0], "`maxIterations unbounded` goes with `loopKind forever`, and only with it")
            elif bound[1][0] not in ("unbounded",) and not S.INT.match(bound[1][0]):
                b = self.op.bindings.get(bound[1][0])
                if b is None or b.type != "Int64" or b.mutable:
                    self.err("R503", bound[0], f"a loop bound is an integer or an immutable `Int64` value; "
                             f"`{bound[1][0]}` is not one")
            for kk, need in (("counted", "counter"), ("forEach", "over"), ("forever", "rationale")):
                if (k == kk) != (need in d):
                    self.err("R503", d[need][0] if need in d else line,
                             f"`{need}` is stated on a `{kk}` loop, and only there")
            if k == "counted" and "counter" in d:
                self._counted(lab, d["counter"])
            if k == "forEach":
                steps = self.blocks[lab]
                if len(steps) != 1 or steps[0].verb != "branch" or steps[0].args[0] != "ifNext":
                    self.err("R503", steps[0].line, f"a `forEach` header holds exactly one row, `branch ifNext ...`")
                elif "over" in d and steps[0].args[1] != d["over"][1][0]:
                    self.err("R503", steps[0].line, f"`{lab}` is `over {d['over'][1][0]}` but its `ifNext` reads "
                             f"`{steps[0].args[1]}`")
                # a table's rows are known when the program is checked, so its loop bound is checked then too;
                # a list's length is known only at run time, where passing the bound traps (D-45)
                table = self.m.tables.get(d["over"][1][0]) if "over" in d else None
                if table is not None and bound is not None and S.INT.match(bound[1][0]):
                    rows = len(table.facts("row"))
                    if rows > int(bound[1][0]):
                        self.err("R503", bound[0], f"`{lab}` reads table `{table.name}`, which has {rows} rows, but "
                                 f"states `maxIterations {bound[1][0]}`; the bound covers every row")
        for lab, steps in self.blocks.items():
            for st in steps:
                if st.verb == "branch" and st.args[0] == "ifNext" and self.kinds.get(lab) != "forEach":
                    self.err("R503", st.line, "`branch ifNext` is the header of a `forEach` loop")
        # single entry: a block inside loop H is entered only from H or from blocks inside H
        for line, a, b in self.edges:
            h = self.within.get(b, "none")
            if h != "none" and a != h and h not in self._ancestors(a):
                self.err("R504", line, f"jump from `{a}` into the middle of loop `{h}` at `{b}`; a loop is entered "
                         f"only at its header")
        # every cycle passes through a declared loop header
        graph: dict[str, set[str]] = {}
        for _l, a, b in self.edges:
            if self.kinds.get(b, "none") == "none":
                graph.setdefault(a, set()).add(b)
        color: dict[str, int] = {}

        def visit(n: str) -> None:
            color[n] = 1
            for nxt in sorted(graph.get(n, ())):
                if color.get(nxt) == 1:
                    self.err("R504", self.blocks[nxt][0].line, f"blocks `{n}` and `{nxt}` form a cycle with no "
                             "declared loop header; declare the block the cycle returns to with a `loopKind`")
                elif nxt not in color:
                    visit(nxt)
            color[n] = 2

        for lab in self.order:
            if lab not in color:
                visit(lab)
        # back edges target only headers, from inside their loop
        for line, a, b in self.edges:
            if self.kinds.get(b, "none") != "none" and (a == b or b in self._ancestors(a)):
                continue
            if self.kinds.get(b, "none") != "none" and self._reaches(b, a, stop=self._ancestors(b)):
                self.err("R504", line, f"`{a}` jumps back to loop `{b}` but does not state `within {b}`")

    def _reaches(self, start: str, goal: str, stop: frozenset | set = frozenset()) -> bool:
        """Whether `goal` is reachable from `start` without passing through a block in `stop` (the headers
        of the loops around `start`: leaving through an outer header and coming back is a new entry)."""
        succ: dict[str, list[str]] = {}
        for _l, a, b in self.edges:
            succ.setdefault(a, []).append(b)
        seen, stack = set(), [start]
        while stack:
            cur = stack.pop()
            if cur == goal:
                return True
            if cur in seen or cur in stop:
                continue
            seen.add(cur)
            stack.extend(succ.get(cur, ()))
        return False

    def _counted(self, header: str, counter: tuple[int, list[str]]) -> None:
        """LR-23 / A14: a counted loop's header compares the counter with an immutable limit, the body
        sets the counter exactly once per pass from counter +/- an immutable non-zero step, the
        counter moves toward the exit, and a constant trip count equals `maxIterations`."""
        name = counter[1][0]
        line = counter[0]
        b = self.op.bindings.get(name)
        if b is None or b.kind != "let" or not b.mutable or b.type != "Int64":
            self.err("R505", line, f"a counted loop's counter is a mutable `Int64` let; `{name}` is not one")
            return
        inside = {lab for lab in self.order if header in self._ancestors(lab)}
        succ: dict[str, list[str]] = {}
        for _l, a, c in self.edges:
            succ.setdefault(a, []).append(c)
        sets = {lab: [st for st in self.blocks[lab] if st.verb == "set" and st.args[0] == name] for lab in self.order}
        bad: list[int] = []
        paths = 0

        def walk(node: str, count: int, seen: frozenset) -> None:
            nonlocal paths
            if paths > 5000:
                return
            for nxt in succ.get(node, ()):
                if nxt == header:
                    paths += 1
                    if count != 1:
                        bad.append(count)
                elif nxt in inside and nxt not in seen:
                    walk(nxt, count + len(sets[nxt]), seen | {nxt})

        walk(header, len(sets[header]), frozenset({header}))
        if bad or paths == 0:
            self.err("R505", line, f"every pass of counted loop `{header}` sets `{name}` exactly once; "
                     f"{'some pass sets it ' + str(bad[0]) + ' times' if bad else 'no path returns to the header'}")
            return
        # D-24: a block outside the loop may start the counter only when it enters the loop directly
        # (its last step is `goto <header>`) and sets it from an immutable `Int64` let, so a nested counted
        # loop restarts its counter on every pass of the loop around it.
        entry_values: list[object] = []
        outside_sets = []
        for lab in self.order:
            if lab in inside or lab == header:
                continue
            for st in sets[lab]:
                last = self.blocks[lab][-1]
                src = self.op.bindings.get(st.args[1])
                if (last.verb == "goto" and last.args[0] == header and src is not None and src.kind == "let"
                        and not src.mutable and src.type == "Int64"):
                    entry_values.append(src.literal if isinstance(src.literal, int) else None)
                else:
                    outside_sets.append(st)
        if outside_sets:
            self.err("R505", outside_sets[0].line, f"`{name}` is the counter of loop `{header}`; only the loop sets it, "
                     f"or the block that enters it with `goto {header}` sets it from an immutable `Int64` let")
        # header shape: `do <compare call>` then `branch if <its result> goto ... else goto ...`
        steps = self.blocks[header]
        shape = (len(steps) == 2 and steps[0].verb == "do" and steps[1].verb == "branch" and steps[1].args[0] == "if")
        cmp = self.op.calls.get(steps[0].args[0]) if shape else None
        target = cmp.entity.value("invokes") if cmp is not None else None
        ops = {"lessThan": "lt", "lessOrEqual": "le", "greaterThan": "gt", "greaterOrEqual": "ge"}
        cmp_op = None
        if target and target.startswith("compare.") and target.endswith("Int64"):
            cmp_op = ops.get(target[len("compare."):-len("Int64")])
        if not shape or cmp is None or cmp_op is None or cmp.out is None or cmp.out[0] != steps[1].args[1]:
            self.err("R505", steps[0].line, f"a counted loop's header is `do <check>` then `branch if <check result>`, "
                     "where the check is `compare.lessThanInt64`, `lessOrEqualInt64`, `greaterThanInt64`, or "
                     "`greaterOrEqualInt64`")
            return
        vals = {slot: value for slot, _t, value, _m, _l in cmp.args}
        if name not in (vals.get("left"), vals.get("right")) or vals.get("left") == vals.get("right"):
            self.err("R505", steps[0].line, f"the header check of `{header}` compares the counter `{name}` with a limit")
            return
        counter_left = vals.get("left") == name
        limit = vals.get("right") if counter_left else vals.get("left")
        lb = self.op.bindings.get(limit)
        if lb is None or lb.type != "Int64" or (lb.kind == "let" and lb.mutable) or lb.kind not in ("let", "input"):
            self.err("R505", steps[0].line, f"the limit of counted loop `{header}` is an immutable `Int64` let or input; "
                     f"`{limit}` is not")
            return
        yes, no = steps[1].args[-4], steps[1].args[-1]
        yes_in, no_in = yes in inside, no in inside
        if yes_in == no_in:
            self.err("R505", steps[1].line, f"the header branch of `{header}` has one target inside the loop and one outside")
            return
        exit_when_true = not yes_in
        # the single set: `set <counter> <result of math.addInt64 or math.subtractInt64 on counter and a step>`
        the_set = next(st for lab in inside | {header} for st in sets[lab])
        step_call = next((ci for ci in self.op.calls.values() if ci.out and ci.out[0] == the_set.args[1]), None)
        step_target = step_call.entity.value("invokes") if step_call is not None else None
        if step_target not in ("math.addInt64", "math.subtractInt64"):
            self.err("R505", the_set.line, f"a counted loop sets `{name}` from `math.addInt64` or `math.subtractInt64` "
                     "of the counter and a step")
            return
        sv = {slot: value for slot, _t, value, _m, _l in step_call.args}
        if sv.get("left") != name or sv.get("right") == name:
            self.err("R505", the_set.line, f"the step call takes the counter `{name}` as `left` and the step as `right`")
            return
        sb = self.op.bindings.get(sv.get("right"))
        if sb is None or sb.kind != "let" or sb.mutable or not isinstance(sb.literal, int) or sb.literal == 0:
            self.err("R505", the_set.line, "the step of a counted loop is an immutable `Int64` let with a non-zero value")
            return
        delta = sb.literal if step_target == "math.addInt64" else -sb.literal
        true_for_large = (counter_left and cmp_op in ("gt", "ge")) or (not counter_left and cmp_op in ("lt", "le"))
        exits_when_large = true_for_large == exit_when_true
        if exits_when_large != (delta > 0):
            self.err("R505", the_set.line, f"`{name}` moves away from the exit of loop `{header}`; it never ends")
            return
        # constant trip count
        inits = [self._let_literal(name)] + entry_values
        lim = lb.literal if lb.kind == "let" else None
        bound = self.decl.get(header, {}).get("maxIterations")
        if all(isinstance(i, int) for i in inits) and isinstance(lim, int) and bound is not None:
            def compare(c: int) -> bool:
                x, y = (c, lim) if counter_left else (lim, c)
                return {"lt": x < y, "le": x <= y, "gt": x > y, "ge": x >= y}[cmp_op]

            def trip(c: int) -> int:
                passes = 0
                while compare(c) != exit_when_true and passes <= 10_000_000:
                    passes += 1
                    c += delta
                return passes
            passes = max(trip(i) for i in inits)
            if bound[1][0] != str(passes):
                self.err("R505", bound[0], f"counted loop `{header}` runs at most {passes} times per entry, so it "
                         f"states `maxIterations {passes}`")

    def _let_literal(self, name: str):
        for r in self.ent.facts("let"):
            if r.text(0) == name and r.args[2].kind == "word" and S.INT.match(r.args[2].raw):
                return int(r.args[2].raw)
        return None

    # ------------------------------------------------------------ ownership on every path (LR-20 rules 6 and 8)

    def _ownership(self) -> None:
        op, owner = self.op, self.ent.name
        world = self.world
        tracked = {n for n, b in op.bindings.items() if b.kind == "input" and b.mode == "owned"}
        acquirers: dict[str, str] = {}
        for ci in op.calls.values():
            if ci.out and ci.entity.value("ownedBy") == owner:
                tracked.add(ci.out[0])
                acquirers[ci.entity.name] = ci.out[0]
        workers = {c.value("runs") for c in op.owned.values() if c.kind == "cleanup"}
        views = {n for n, b in op.bindings.items()
                 if b.type != "Region" and not world.plain(b.type) and
                 ((b.kind == "input" and b.mode in ("borrowed", "borrowedMutable")) or b.view_of is not None)}
        # borrowed values never leave their loan (rule 8)
        for lab in self.order:
            for st in self.blocks[lab]:
                if st.verb in ("do", "start"):
                    ci = op.calls.get(st.args[0])
                    if ci is None:
                        continue
                    for slot, _t, value, mode, line in ci.args:
                        if mode == "give" and value in views:
                            self.err("R514", line, f"`{value}` is only borrowed, so it cannot be given away")
                if st.verb == "return" and st.args[0] == "ok" and st.args[1] in views:
                    self.err("R514", st.line, f"`{st.args[1]}` is only borrowed, so it cannot be returned; return a "
                             "value allocated in the caller's region")
        if not tracked:
            return
        start = {n: frozenset({"owned"} if op.bindings[n].kind == "input" else {"none"}) for n in tracked}
        IN: dict[str, Optional[dict]] = {lab: None for lab in self.order}
        IN["begin"] = dict(start)
        for _ in range(len(self.order) + 5):
            changed = False
            outs = []
            for lab in self.order:
                if IN[lab] is not None:
                    outs += self._own_block(lab, dict(IN[lab]), tracked, acquirers, workers, report=False)
            for lab in self.order:
                if lab == "begin":
                    continue
                incoming = [s for (dst, s) in outs if dst == lab]
                if not incoming:
                    continue
                merged = {n: frozenset().union(*(s[n] for s in incoming)) for n in tracked}
                if merged != IN[lab]:
                    IN[lab] = merged
                    changed = True
            if not changed:
                break
        for lab in self.order:
            if IN[lab] is not None:
                self._own_block(lab, dict(IN[lab]), tracked, acquirers, workers, report=True)

    def _own_block(self, lab: str, state: dict, tracked: set, acquirers: dict, workers: set, report: bool):
        op = self.op
        outs = []
        pending: Optional[str] = None  # value acquired on the success arm of the next ifError

        def err(line, msg):
            if report:
                self.err("R513", line, msg)

        def acquire(n: str, line: int, st: dict) -> None:
            if "owned" in st[n]:
                err(line, f"a previous `{n}` may still be owned here and would leak; release, give, or return it first")
            st[n] = frozenset({"owned"})

        for st in self.blocks[lab]:
            a, v = st.args, st.verb
            if v in ("do", "start"):
                ci = op.calls.get(a[0])
                if ci is None or ci.entity.name in workers:
                    continue
                for slot, _t, value, mode, line in ci.args:
                    if value not in tracked:
                        continue
                    s = state[value]
                    if mode == "give":
                        if "given" in s:
                            err(line, f"`{value}` may already have been given away on some path")
                        elif "deferred" in s:
                            err(line, f"`{value}` has a deferred cleanup, so it cannot be given away")
                        state[value] = frozenset({"given"})
                    elif "given" in s:
                        err(line, f"`{value}` may already have been given away on some path, so it cannot be used")
                if v == "do" and ci.entity.name in acquirers:
                    if ci.catch is None:
                        acquire(acquirers[ci.entity.name], st.line, state)
                    else:
                        pending = acquirers[ci.entity.name]
            elif v == "join":
                ci = op.calls.get(a[0])
                if ci is not None and ci.entity.name in acquirers:
                    if ci.catch is None:
                        acquire(acquirers[ci.entity.name], st.line, state)
                    else:
                        pending = acquirers[ci.entity.name]
            elif v == "defer":
                c = op.owned.get(a[0])
                n = c.value("cleans") if c is not None else None
                if n in tracked:
                    if "given" in state[n]:
                        err(st.line, f"`{n}` may already have been given away, so it cannot be cleaned up here")
                    state[n] = frozenset({"deferred"})
            elif v == "set":
                if a[1] in tracked:
                    err(st.line, f"`{a[1]}` is owned; it moves by `give` or `return`, never by `set`")
            elif v == "return":
                returned = a[1] if a[0] == "ok" else None
                if returned in tracked:
                    if "deferred" in state[returned]:
                        err(st.line, f"`{returned}` has a deferred cleanup, so it cannot be returned")
                    elif "given" in state[returned]:
                        err(st.line, f"`{returned}` may already have been given away")
                for n in sorted(tracked):
                    if n != returned and "owned" in state[n]:
                        err(st.line, f"`{n}` may still be owned at this return; register a cleanup with `defer`, "
                                     "give it away, or return it")
            elif v == "goto":
                outs.append((a[0], dict(state)))
            elif v == "branch":
                yes, no = a[-4], a[-1]
                if a[0] == "ifError" and pending is not None:
                    ok = dict(state)
                    acquire(pending, st.line, ok)
                    outs += [(yes, dict(state)), (no, ok)]
                    pending = None
                else:
                    outs += [(yes, dict(state)), (no, dict(state))]
            elif v == "case":
                outs.append((a[-1], dict(state)))
        return outs

    # ------------------------------------------------------------ activations

    def _suppression(self, ent, error_type, discards: bool, line: int) -> None:
        """D-54: an activation whose failure is dropped names, in `suppresses` rows, exactly the variants of its error
        type; one whose failure is handled states `suppresses none`. A new variant then breaks every discard that
        does not name it, instead of disappearing silently."""
        if error_type is None:
            return  # the error type did not resolve; that is reported where it is named
        rows = [r for r in ent.facts("suppresses") if r.text(0) != "none"]
        info = self.world.type_info(error_type)
        variants = [n for n, _p in info.variants] if info is not None and info.variants else []
        if not discards:
            for r in rows:
                self.err("R506", r.line, f"`{ent.name}` handles its failure, so it suppresses nothing; write "
                         f"`{ent.name} suppresses none`")
            return
        named = {}
        for r in rows:
            v = resolve_variant(self.world, self.m, r.text(0), r.line, quiet=True)
            if v is None or v[0] != error_type:
                self.err("R506", r.line, f"`{r.text(0)}` is not a variant of `{error_type}`, the error `{ent.name}` "
                         "can raise")
            else:
                named[v[1]] = r.line
        missing = [v for v in variants if v not in named]
        if missing:
            want = "; ".join(f"`{ent.name} suppresses {_variant_text(self.m, error_type, v)}`" for v in missing)
            self.err("R506", (ent.fact("suppresses") or ent).line, f"`{ent.name}`'s failure is dropped at line {line}, "
                     f"so it names every variant it drops; add {want}")

    def _group_catch(self, name: str):
        """(error name, type) a task group states with `catch`, or None (D-48)."""
        g = self.op.owned.get(name)
        row = g.fact("catch") if g is not None and g.kind == "taskGroup" else None
        if row is None or row.text(0) == "none":
            return None
        b = self.op.bindings.get(row.text(0))
        return row.text(0), b.type if b is not None else None

    def _grouped_error(self, task: str, ci) -> None:
        """D-48: a fallible task started into a group raises the error type the group states."""
        for lab in self.order:
            for st in self.blocks[lab]:
                if st.verb == "start" and st.args[0] == task and st.args[2] != "none":
                    caught = self._group_catch(st.args[2])
                    if caught is None:
                        self.err("R403", ci.entity.fact("catch").line, f"task `{task}` can fail, so group "
                                 f"`{st.args[2]}` states `catch <name> {ci.catch[1]}` to receive its error")
                    elif caught[1] is not None and ci.catch[1] != caught[1]:
                        self.err("R403", ci.entity.fact("catch").line, f"task `{task}` raises `{ci.catch[1]}`, but "
                                 f"group `{st.args[2]}` catches `{caught[1]}`; a group's tasks raise its one error type")

    @property
    def _grouped(self) -> set[str]:
        return {st.args[0] for lab in self.order for st in self.blocks[lab]
                if st.verb == "start" and st.args[2] != "none"}

    def _activations(self) -> None:
        op = self.op
        count: dict[str, dict[str, list[int]]] = {}
        for lab in self.order:
            steps = self.blocks[lab]
            for i, st in enumerate(steps):
                if st.verb not in ("do", "start", "join", "cancel", "awaitSlot", "defer"):
                    if st.verb == "branch" and st.args[0] == "ifError":
                        prev = steps[i - 1] if i > 0 else None
                        if prev is None or prev.verb not in ("do", "join") or prev.args[0] != st.args[1]:
                            self.err("R506", st.line, f"`branch ifError {st.args[1]}` comes directly after "
                                     f"`do {st.args[1]}` or `join {st.args[1]}`")
                    continue
                target = st.args[0]
                ent = op.owned.get(target)
                want = {"do": {"call"}, "start": {"task"}, "join": {"task", "taskGroup"}, "cancel": {"task", "taskGroup"},
                        "awaitSlot": {"taskGroup"}, "defer": {"cleanup"}}[st.verb]
                if ent is None:
                    self.err("R401", st.line, f"`{target}` is not owned by `{self.ent.name}`")
                    continue
                if ent.kind not in want:
                    self.err("R402", st.line, f"`{st.verb}` takes a {' or '.join(sorted(want))}; `{target}` is a {ent.kind}")
                    continue
                count.setdefault(target, {}).setdefault(st.verb, []).append(st.line)
                if st.verb == "start" and st.args[2] != "none":
                    g = op.owned.get(st.args[2])
                    if g is None or g.kind != "taskGroup":
                        self.err("R402", st.line, f"`start ... into` names a task group; `{st.args[2]}` is not one")
                ci = op.calls.get(target)
                fallible = (ci is not None and ci.catch is not None) or \
                    (ent.kind == "taskGroup" and self._group_catch(target) is not None)
                if fallible and ((st.verb == "do" and ent.kind == "call") or
                                 (st.verb == "join" and ent.kind in ("task", "taskGroup"))):
                    nxt = steps[i + 1] if i + 1 < len(steps) else None
                    if nxt is None or nxt.verb != "branch" or nxt.args[:2] != ["ifError", target]:
                        self.err("R506", st.line, f"`{target}` can fail, so `branch ifError {target} goto ... else "
                                 "goto ...` comes directly after it")
                if st.verb == "branch":
                    pass
        workers = {c.value("runs"): c.name for c in op.owned.values() if c.kind == "cleanup"}
        for name, ent in op.owned.items():
            c = count.get(name, {})
            if ent.kind == "call":
                n = len(c.get("do", [])) + (1 if name in workers else 0)
                if n != 1:
                    where = c.get("do", [ent.line])
                    self.err("R510", where[-1] if n > 1 else ent.line,
                             f"call `{name}` is activated {n} times; a call is run by exactly one `do` step or by "
                             "exactly one cleanup")
            elif ent.kind == "task":
                if len(c.get("start", [])) != 1:
                    self.err("R510", ent.line, f"task `{name}` is started {len(c.get('start', []))} times; exactly once")
                if name in self._grouped:
                    ci = op.calls.get(name)
                    if c.get("join") or c.get("cancel"):
                        self.err("R510", ent.line, f"task `{name}` is started into a group; join or cancel the group, "
                                 "not the task")
                    if ci is not None and ci.out is not None:
                        self.err("R510", ent.line, f"task `{name}` is started into a group, so its result cannot be "
                                 f"read; it has `result none`")
                    if ci is not None and ci.catch is not None:
                        self._grouped_error(name, ci)
                elif not c.get("join") and not c.get("cancel"):
                    self.err("R510", ent.line, f"task `{name}` is never joined or cancelled")
            elif ent.kind == "cleanup":
                if len(c.get("defer", [])) != 1:
                    self.err("R510", ent.line, f"cleanup `{name}` is deferred {len(c.get('defer', []))} times; exactly once")
        policy: dict = {}  # entity -> [entity, error type, line of a discard or None] (D-54)

        def note(ent, error_type, discards, line):
            entry = policy.setdefault(ent.name + "@" + str(ent.line), [ent, error_type, None])
            if discards and entry[2] is None:
                entry[2] = line

        for st_lab in self.order:
            for st in self.blocks[st_lab]:
                if st.verb == "branch" and st.args[0] == "ifError":
                    ci = op.calls.get(st.args[1])
                    group = op.owned.get(st.args[1])
                    if group is not None and group.kind == "taskGroup":
                        caught = self._group_catch(st.args[1])
                        if caught is None:
                            self.err("R506", st.line, f"task group `{st.args[1]}` cannot fail (`catch none`), so it has "
                                     "no error branch")
                        else:
                            if st.args[-4] == st.args[-1] and not group.facts("rationale"):
                                self.err("R506", st.line, f"both arms go to `{st.args[-1]}`, which ignores the failure; "
                                         f"`{st.args[1]}` needs a `rationale` row saying why")
                            note(group, caught[1], st.args[-4] == st.args[-1], st.line)
                        continue
                    if ci is None:
                        self.err("R401", st.line, f"`{st.args[1]}` is not a call or task of `{self.ent.name}`")
                    elif ci.catch is None:
                        self.err("R506", st.line, f"`{st.args[1]}` cannot fail (`catch none`), so it has no error branch")
                    else:
                        if st.args[-4] == st.args[-1] and not ci.entity.facts("rationale"):
                            self.err("R506", st.line, f"both arms go to `{st.args[-1]}`, which ignores the failure; "
                                     f"`{st.args[1]}` needs a `rationale` row saying why")
                        note(ci.entity, ci.catch[1], st.args[-4] == st.args[-1], st.line)
        for c in op.owned.values():
            if c.kind == "cleanup":
                worker = op.calls.get(c.value("runs") or "")
                if worker is not None and worker.catch is not None:
                    note(worker.entity, worker.catch[1], c.value("onError") == "suppress",
                         (c.fact("onError") or c).line)
        for ent, error_type, discard_line in policy.values():
            self._suppression(ent, error_type, discard_line is not None, discard_line or ent.line)

    # ------------------------------------------------------------ definite assignment and types

    def _dataflow(self) -> None:
        op = self.op
        entry = {n for n, b in op.bindings.items()
                 if b.kind in ("input", "region", "group") or (b.kind == "let" and not b.unset)}
        universe = set(op.bindings)
        IN: dict[str, set] = {lab: (set(entry) if lab == "begin" else set(universe)) for lab in self.order}
        for _ in range(len(self.order) + 5):
            outs = self._transfer_all(IN, report=False)
            changed = False
            for lab in self.order:
                if lab == "begin":
                    continue
                incoming = [s for (src, dst), s in outs if dst == lab]
                new = set.intersection(*incoming) if incoming else set(universe)
                if new != IN[lab]:
                    IN[lab] = new
                    changed = True
            if not changed:
                break
        self._transfer_all(IN, report=True)
        # D-56: a loop's bound may be a value computed at run time, but it is read when the loop starts, so it is set
        # on every path into the loop's header (back edges included: a value first set inside the loop is not).
        for header in self.kinds:
            if self.kinds[header] == "none":
                continue
            bound = self.decl.get(header, {}).get("maxIterations")
            if bound is None or bound[1][0] == "unbounded" or S.INT.match(bound[1][0]):
                continue
            name = bound[1][0]
            if name in op.bindings and name not in IN.get(header, set()):
                self.err("R507", bound[0], f"`{name}` may not be set when loop `{header}` starts; a loop's bound is set "
                         "on every path into the loop, before its first pass")

    def _transfer_all(self, IN: dict[str, set], report: bool):
        outs = []
        for lab in self.order:
            outs += self._transfer(lab, set(IN[lab]), report)
        return outs

    def _use(self, name: str, cur: set, line: int, want: Optional[str], what: str, report: bool) -> None:
        if not report:
            return
        op = self.op
        if name in op.bindings:
            if name not in cur:
                self.err("R507", line, f"`{name}` may not be set here; some path reaches this {what} without setting it")
            t = op.bindings[name].type
            if want is not None and t is not None and t != want:
                self.err("R403", line, f"{what} needs `{want}`, but `{name}` is `{t}`")
        elif name not in self.m.ops and name not in self.m.tables:
            self.err("R401", line, f"`{name}` is not a value in `{self.ent.name}`")

    def _call_uses(self, ci: CallInfo, cur: set, line: int, report: bool) -> None:
        for slot, t, value, _mode, aline in ci.args:
            if value in self.op.bindings:
                self._use(value, cur, line, None, f"argument `{slot}` of `{ci.entity.name}`", report)
        if ci.reference is not None and ci.reference in self.op.bindings:
            self._use(ci.reference, cur, line, None, f"reference called by `{ci.entity.name}`", report)

    def _transfer(self, lab: str, cur: set, report: bool):
        op = self.op
        outs: list = []
        steps = self.blocks[lab]
        pending_split: Optional[tuple[set, set]] = None  # (error-arm gens, else-arm gens)
        for st in steps:
            a = st.args
            v = st.verb
            if v == "do":
                ci = op.calls.get(a[0])
                if ci is None:
                    continue
                self._call_uses(ci, cur, st.line, report)
                gen = {ci.out[0]} if ci.out else set()
                if ci.catch:
                    pending_split = ({ci.catch[0]}, gen)
                else:
                    cur |= gen
            elif v == "start":
                ci = op.calls.get(a[0])
                if ci is not None:
                    self._call_uses(ci, cur, st.line, report)
            elif v == "join":
                ci = op.calls.get(a[0])
                if ci is None and self._group_catch(a[0]) is not None:
                    pending_split = ({self._group_catch(a[0])[0]}, set())
                if ci is not None:
                    gen = {ci.out[0]} if ci.out else set()
                    if ci.catch:
                        pending_split = ({ci.catch[0]}, gen)
                    else:
                        cur |= gen
            elif v == "defer":
                c = op.owned.get(a[0])
                if c is not None and c.kind == "cleanup":
                    cleans = c.value("cleans")
                    if cleans:
                        self._use(cleans, cur, st.line, None, f"value cleaned by `{c.name}`", report)
                    w = op.calls.get(c.value("runs"))
                    if w is not None:
                        for slot, _t, value, _m, _l in w.args:
                            if value != cleans and value in op.bindings:
                                self._use(value, cur, st.line, None, f"argument `{slot}` of `{w.entity.name}`", report)
            elif v == "set":
                tgt, src = a[0], a[1]
                b = op.bindings.get(tgt)
                if report and (b is None or b.kind != "let" or not b.mutable):
                    self.err("R403", st.line, f"only a `mutable` let can be set; `{tgt}` is not one")
                self._use(src, cur, st.line, b.type if b else None, f"`set {tgt}`", report)
                cur.add(tgt)
            elif v == "goto":
                outs.append(((lab, a[0]), set(cur)))
            elif v == "branch":
                yes, no = a[-4], a[-1]
                if a[0] == "if":
                    self._use(a[1], cur, st.line, "Bool", "`branch if`", report)
                    outs += [((lab, yes), set(cur)), ((lab, no), set(cur))]
                elif a[0] == "ifError":
                    err_gen, ok_gen = pending_split or (set(), set())
                    outs += [((lab, yes), cur | err_gen), ((lab, no), cur | ok_gen)]
                    pending_split = None
                elif a[0] == "ifNext":
                    coll, item, item_t = a[1], a[3], a[4]
                    self._ifnext_types(coll, item_t, st.line, report)
                    if coll in op.bindings:
                        self._use(coll, cur, st.line, None, "`ifNext`", report)
                    outs += [((lab, yes), cur | {item}), ((lab, no), set(cur))]
            elif v == "match":
                self._match(lab, st, cur, outs, report)
                break
            elif v == "return":
                self._return(st, cur, report)
        if pending_split is not None and report:
            pass  # R506 already reports a fallible step without its branch
        return outs

    def _ifnext_types(self, coll: str, item_t: str, line: int, report: bool) -> None:
        if not report:
            return
        m, op = self.m, self.op
        want = None
        if coll in m.tables:
            want = resolve_type(self.world, m, m.tables[coll].value("rowType"), line, quiet=True)
        elif coll in op.bindings:
            info = self.world.type_info(op.bindings[coll].type)
            if info is None or info.generic not in ("list.List", "map.Map"):
                self.err("R402", line, f"`ifNext` reads a table, a list, or a map; `{coll}` is none of them")
                return
            want = info.args[0]  # a list's items; a map's keys, in the order they were first put (D-62)
        else:
            self.err("R401", line, f"`{coll}` is not a table or a list in scope")
            return
        got = resolve_type(self.world, m, item_t, line, self.op.tparams, quiet=True)
        if want is not None and got is not None and want != got:
            self.err("R403", line, f"items of `{coll}` are `{want}`, not `{got}`")

    def _match(self, lab: str, st: Step, cur: set, outs: list, report: bool) -> None:
        value, type_text = st.args
        canon = resolve_type(self.world, self.m, type_text, st.line, self.op.tparams, quiet=not report)
        self._use(value, cur, st.line, canon, "`match`", report)
        info = self.world.type_info(canon)
        variants = dict(info.variants) if info is not None else {}
        if report and canon is not None and not variants:
            self.err("R402", st.line, f"`match` inspects an enum; `{type_text}` is not one")
        seen: dict[str, int] = {}
        for cs in self.blocks[lab]:
            if cs.verb != "case":
                continue
            var_text, _bind, bname, btype, _goto, target = cs.args
            gen = set() if bname == "none" else {bname}
            outs.append(((lab, target), cur | gen))
            if not report:
                continue
            v = resolve_variant(self.world, self.m, var_text, cs.line)
            if v is None:
                continue
            ecanon, vname, payload = v
            if ecanon != canon:
                self.err("R509", cs.line, f"`{var_text}` is not a variant of `{type_text}`")
                continue
            if vname in seen:
                self.err("R509", cs.line, f"variant `{vname}` already has a case on line {seen[vname]}")
            seen[vname] = cs.line
            if payload is None and bname != "none":
                self.err("R509", cs.line, f"`{var_text}` carries no payload; write `bind none none`")
            if payload is not None:
                if bname == "none":
                    self.err("R509", cs.line, f"`{var_text}` carries a `{payload}`; bind it with "
                             f"`bind <name> {payload}`")
                else:
                    got = resolve_type(self.world, self.m, btype, cs.line, self.op.tparams, quiet=True)
                    if got is not None and got != payload:
                        self.err("R403", cs.line, f"the payload of `{var_text}` is `{payload}`, not `{got}`")
        if report:
            for vname in variants:
                if vname not in seen:
                    self.err("R509", st.line, f"`match` on `{type_text}` has no case for `{vname}`; every variant "
                             "has exactly one case")

    def _return(self, st: Step, cur: set, report: bool) -> None:
        how, value = st.args
        op = self.op
        if how == "ok":
            if value == "none":
                if report and op.output is not None:
                    self.err("R508", st.line, f"`{self.ent.name}` returns a `{op.output}`; `return ok none` is for "
                             "operations with `output none`")
            else:
                if report and op.output is None and self.ent.value("output") == "none":
                    self.err("R508", st.line, f"`{self.ent.name}` has `output none`, so it returns `ok none`")
                self._use(value, cur, st.line, op.output, "`return ok`", report)
        else:
            if report and op.raises is None:
                self.err("R508", st.line, f"`return error` needs `raises <ErrorEnum>`; `{self.ent.name}` raises none")
            self._use(value, cur, st.line, op.raises, "`return error`", report)

    # ------------------------------------------------------------ tasks and groups settled at returns

    def _settled(self) -> None:
        op = self.op
        groups = {n for n, e in op.owned.items() if e.kind == "taskGroup"}
        tasks = {n for n, e in op.owned.items() if e.kind == "task"}
        if not groups and not tasks:
            return
        # pending tasks: may-analysis; settled groups: must-analysis. A cancelled task is tracked as
        # `cancelled:<name>`: it may still be running until it is joined, so its loans stay live and the return
        # still needs its `join` (D-39, D-44).
        PEND = {lab: set() for lab in self.order}
        SETT = {lab: (set() if lab == "begin" else set(groups)) for lab in self.order}
        succ: dict[str, list[str]] = {}
        for _l, a, b in self.edges:
            succ.setdefault(a, []).append(b)
        for _ in range(len(self.order) + 5):
            changed = False
            new_p = {lab: set() for lab in self.order}
            new_s = {lab: (set() if lab == "begin" else set(groups)) for lab in self.order}
            for lab in self.order:
                p, s = self._settle_block(lab, set(PEND[lab]), set(SETT[lab]), report=False)
                for nxt in succ.get(lab, ()):
                    new_p[nxt] |= p
                    if nxt != "begin":
                        new_s[nxt] &= s
            for lab in self.order:
                if new_p[lab] != PEND[lab] or (lab != "begin" and new_s[lab] != SETT[lab]):
                    changed = True
            PEND, SETT = new_p, {lab: (set() if lab == "begin" else new_s[lab]) for lab in self.order}
            if not changed:
                break
        for lab in self.order:
            self._settle_block(lab, set(PEND[lab]), set(SETT[lab]), report=True, groups=groups)
        self._joins_on_every_path(tasks - self._grouped)

    def _joins_on_every_path(self, tasks: set) -> None:
        """D-50: a `join` or `cancel` needs the task live (started and not yet joined) on EVERY path that reaches
        it, not just on some; otherwise one path would join a task twice, or join one it never started."""
        if not tasks:
            return
        preds: dict[str, list[str]] = {}
        for _l, a, b in self.edges:
            preds.setdefault(b, []).append(a)

        def transfer(lab: str, cur: set, may: set, report: bool):
            for st in self.blocks[lab]:
                a = st.args
                if st.verb == "start" and a[0] in tasks:
                    cur.add(a[0])
                    may.add(a[0])
                elif st.verb in ("join", "cancel") and a[0] in tasks:
                    if report and a[0] in may and a[0] not in cur:
                        self.err("R510", st.line, f"`{st.verb} {a[0]}` is reached on a path where `{a[0]}` was "
                                 "never started or was already joined; every path to it starts the task and has not "
                                 "joined it yet")
                    if st.verb == "join":
                        cur.discard(a[0])
                        may.discard(a[0])
            return cur, may

        MUST = {lab: (set() if lab == "begin" else set(tasks)) for lab in self.order}
        MAY = {lab: set() for lab in self.order}
        for _ in range(len(self.order) + 5):
            outs = {lab: transfer(lab, set(MUST[lab]), set(MAY[lab]), False) for lab in self.order}
            new_must, new_may = {}, {}
            for lab in self.order:
                if lab == "begin":
                    new_must[lab], new_may[lab] = set(), set()
                    continue
                ps = [p for p in preds.get(lab, []) if p in outs]
                new_must[lab] = set.intersection(*[outs[p][0] for p in ps]) if ps else set(tasks)
                new_may[lab] = set.union(*[outs[p][1] for p in ps]) if ps else set()
            if new_must == MUST and new_may == MAY:
                break
            MUST, MAY = new_must, new_may
        for lab in self.order:
            if lab == "begin" or preds.get(lab):
                transfer(lab, set(MUST[lab]), set(MAY[lab]), True)

    def _iteration_loans(self) -> None:
        """D-39: a `forEach` loop reads its collection on every pass, so inside the loop the collection may be
        read but not changed, lent exclusively, or given away."""
        for header, kind in self.kinds.items():
            if kind != "forEach":
                continue
            steps = self.blocks.get(header, [])
            if not steps or steps[0].verb != "branch" or steps[0].args[0] != "ifNext":
                continue
            coll = steps[0].args[1]
            for lab in self.order:
                if header not in self._ancestors(lab) and lab != header:
                    continue
                for st in self.blocks[lab]:
                    for value, how, line in self._step_uses(st):
                        if value == coll and how in ("lendMutable", "give", "set"):
                            verb = {"lendMutable": "lent exclusively", "give": "given away", "set": "changed"}[how]
                            self.err("R515", line, f"`{coll}` is being iterated by loop `{header}`, so it cannot be "
                                     f"{verb} inside the loop")

    def _loans_of(self, holder: str) -> list[tuple[str, str, str]]:
        """(value, mode, task) for every `lend` / `lendMutable` argument a running task or group holds."""
        op = self.op
        names = [holder]
        ent = op.owned.get(holder)
        if ent is not None and ent.kind == "taskGroup":
            names = [st.args[0] for lab in self.order for st in self.blocks[lab]
                     if st.verb == "start" and st.args[2] == holder]
        out = []
        for n in names:
            ci = op.calls.get(n)
            if ci is None:
                continue
            for _slot, _t, value, mode, _line in ci.args:
                if mode in ("lend", "lendMutable"):
                    out.append((value, mode, n))
        return out

    def _step_uses(self, st) -> list[tuple[str, str, int]]:
        """(value, how, line) for every value a step reads or changes; how is copy, lend, lendMutable, give,
        set, or read."""
        op, a = self.op, st.args
        if st.verb in ("do", "start"):
            ci = op.calls.get(a[0])
            return [(value, mode, line) for _s, _t, value, mode, line in (ci.args if ci else [])]
        if st.verb == "set":
            return [(a[0], "set", st.line), (a[1], "read", st.line)]
        if st.verb == "return" and a[0] in ("ok", "error") and a[1] != "none":
            return [(a[1], "read", st.line)]
        if st.verb == "branch" and a[0] in ("if", "ifNext"):
            return [(a[1], "read", st.line)]
        if st.verb == "match":
            return [(a[0], "read", st.line)]
        return []

    def _check_loans(self, st, pend: set) -> None:
        """D-39: a running task's loans are live from `start` to `join` or `cancel`."""
        own = st.args[0] if st.verb == "start" else None
        live = []
        for holder in sorted(p.split(":", 1)[-1] for p in pend):
            live += [(v, m, t) for v, m, t in self._loans_of(holder) if t != own]
        for value, how, line in self._step_uses(st):
            for lent, mode, task in live:
                if lent != value:
                    continue
                if mode == "lendMutable":
                    self.err("R515", line, f"`{value}` is lent exclusively to task `{task}`, which may still be "
                             f"running; join it (a `cancel` only asks it to stop) before using `{value}`")
                elif how in ("lendMutable", "give", "set"):
                    verb = {"lendMutable": "lent exclusively", "give": "given away", "set": "changed"}[how]
                    self.err("R515", line, f"`{value}` is lent to task `{task}`, which may still be running, so it "
                             f"cannot be {verb}; join `{task}` first")

    def _settle_block(self, lab: str, pend: set, sett: set, report: bool, groups: set = frozenset()):
        for st in self.blocks[lab]:
            a = st.args
            if report and st.verb in ("do", "start", "set", "return", "branch", "match"):
                self._check_loans(st, pend)
            if st.verb == "start":
                if a[2] != "none":
                    pend.add(a[2])
                    sett.discard(a[2])
                else:
                    if report and a[0] in pend:
                        self.err("R510", st.line, f"task `{a[0]}` is started again while it may still be running; "
                                 "join it before each new start")
                    pend.add(a[0])
                    pend.discard(f"cancelled:{a[0]}")
            elif st.verb == "cancel":
                if a[0] not in groups and report and a[0] not in pend:
                    self.err("R510", st.line, f"task `{a[0]}` is not running here; it was never started on this path, "
                             "or it was already joined or cancelled")
                if a[0] not in groups:
                    pend.discard(a[0])
                    pend.add(f"cancelled:{a[0]}")
            elif st.verb == "join":
                if (a[0] not in groups and report and a[0] not in pend and f"cancelled:{a[0]}" not in pend):
                    self.err("R510", st.line, f"task `{a[0]}` is not running here; it was never started on this path, "
                             "or it was already joined")
                pend.discard(a[0])
                pend.discard(f"cancelled:{a[0]}")
                sett.add(a[0])
            elif st.verb == "return" and report:
                for t in sorted(pend - groups):
                    if t.startswith("cancelled:"):
                        self.err("R512", st.line, f"task `{t.split(':', 1)[1]}` was cancelled but is not joined on this "
                                 "path; `cancel` only asks a task to stop, so `join` it to wait for it and see its outcome")
                        continue
                    self.err("R512", st.line, f"task `{t}` may still be running at this return; join it on every path "
                             "(after a `cancel` if it should stop early)")
                for g in sorted(groups - sett):
                    self.err("R512", st.line, f"task group `{g}` is not joined on every path to this return; `cancel` "
                             "only asks its tasks to stop, so `join` it to wait for them")
        return pend, sett


def _variant_text(m: Module, error_type: str, variant: str) -> str:
    """How module `m` writes a variant of `error_type`: `Enum.variant` for its own enums, `module.Enum.variant`
    for another module's or the standard library's."""
    mod, name = error_type.split(".", 1) if "." in error_type else ("", error_type)
    return f"{name}.{variant}" if mod == m.short else f"{error_type}.{variant}"
