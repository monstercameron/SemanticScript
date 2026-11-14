"""What stage0's own modules use, and what of it stage0 does not compile.

Reads the modules build.sem includes (not their tests) and lists the entity kinds, predicates (by entity kind),
steps, loop kinds, and call targets they use, with counts, then checks each against the subset as build.py and the
.dsl files describe it: the kinds of model.dsl, the predicates and steps of build.py, the standard library targets
of build.py's BUILTINS, and the members stage0 derives for the program's records, enums, lists, maps, and tables.
The last line is the number of uses outside the subset; stage0 compiles itself when it is 0.

    python usage.py
"""
import collections
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402

STAGE0 = build.STAGE0
KINDS = re.findall(r'text="(\w+)"', open(os.path.join(HERE, "model.dsl"), encoding="utf-8").read())
PREDICATES = set(build.CONTEXT) | set(build.PREDICATES) | {"is"}
STEPS = {w for w, _v in build.STEPS}
LOOPS = {w for w, _n in build.LOOPS}
BUILTINS = {t for t, *_s in build.BUILTINS}
MEMBERS = {"list": {"new", "append", "length", "get", "getOrTrap", "set"},
           "map": {"new", "put", "get", "contains", "remove", "length"}, "table": {"rowAt", "length"}}


def modules():
    rows = open(os.path.join(STAGE0, "build.sem"), encoding="utf-8").read().split("\n")
    return [ln.split()[2] for ln in rows if len(ln.split()) == 3 and ln.split()[1] == "includesModule"]


def main():
    kinds, preds, steps, loops, targets = (collections.Counter() for _ in range(5))
    declared = {"string.Position": {"new", "offset", "line", "column", "with"}}
    ops = set()
    total = 0
    for module in modules():
        entities = {}
        current = None
        for ln in open(os.path.join(STAGE0, module + ".sem"), encoding="utf-8").read().split("\n"):
            t = ln.split()
            if not t or t[0].startswith("#"):
                continue
            total += 1
            if t[1] == "is":
                current = (t[0], t[2])
                entities[t[0]] = [t[2], []]
                kinds[t[2]] += 1
                if t[2] == "operation":
                    ops.update({t[0], f"{module}.{t[0]}"})
                continue
            kind = current[1]
            preds[(kind, t[1])] += 1
            entities[current[0]][1].append(t)
            if t[1] == "at":
                verb = t[3] + (" " + t[4] if t[3] in ("branch", "return") else "")
                steps[verb] += 1
            elif t[1] == "label" and t[3] == "loopKind":
                loops[t[4]] += 1
            elif t[1] in ("invokes", "invokesReference"):
                targets[t[2] if t[1] == "invokes" else "invokesReference"] += 1
        for name, (kind, rows) in entities.items():
            members = set()
            if kind == "record":
                members = {"new", "with"} | {r[2] for r in rows if r[1] == "field"}
            elif kind == "enum":
                members = {r[2] for r in rows if r[1] == "variant"}
            elif kind == "typeInstance":
                generic = [r[2] for r in rows if r[1] == "instantiates"][0]
                members = MEMBERS.get(generic.split(".")[0], set())
            elif kind == "table":
                members = MEMBERS["table"]
            for key in (name, f"{module}.{name}"):
                declared[key] = members
    outside = []
    for kind in kinds:
        if kind not in KINDS:
            outside.append(f"entity kind {kind}")
    for (kind, pred) in preds:
        if pred not in PREDICATES:
            outside.append(f"predicate {kind}.{pred}")
    for verb in steps:
        if verb.split()[0] not in STEPS:
            outside.append(f"step {verb}")
    for loop in loops:
        if loop not in LOOPS:
            outside.append(f"loop {loop}")
    for target in targets:
        owner, _dot, member = target.rpartition(".")
        if target == "invokesReference" or target in BUILTINS or target in ops or member in declared.get(owner, ()):
            continue
        outside.append(f"target {target}")
    print(f"stage0's own modules ({', '.join(modules())}): {total} rows")
    print("entity kinds:", ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    print("steps:", ", ".join(f"{k} {n}" for k, n in sorted(steps.items())))
    print("loop kinds:", ", ".join(f"{k} {n}" for k, n in sorted(loops.items())))
    print("predicates:", ", ".join(f"{k}.{p} {n}" for (k, p), n in sorted(preds.items())))
    std = sorted(t for t in targets if t in BUILTINS)
    print(f"call targets: {len(targets)} distinct, {sum(targets.values())} calls; standard library: {', '.join(std)}")
    for item in outside:
        print("outside the subset:", item)
    print(f"{len(outside)} uses outside the stage0 subset")
    return 1 if outside else 0


if __name__ == "__main__":
    sys.exit(main())
