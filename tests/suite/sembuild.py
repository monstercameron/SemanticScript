"""Helpers that write refined-syntax entities as text, for the generated tests (stress, fuzz,
differential). Every helper expands to the full skeleton; nothing is implied."""
import os


class Prog:
    def __init__(self, module, purpose, imports=("standard.console",), exports=("main",)):
        self.module, self.purpose = module, purpose
        self.imports, self.exports = list(imports), list(exports)
        self.parts = []
        self.header = []

    def meta(self, covers, kind, expect, stdout=None, exit_code=None, extra=None):
        self.header = [f"# covers: {c}" for c in covers]
        self.header += [f"# kind: {kind}", f"# expect: {expect}"]
        if exit_code is not None:
            self.header.append(f"# exit: {exit_code}")
        for line in stdout or []:
            self.header.append(f"# stdout: {line}")
        for line in extra or []:
            self.header.append(f"# {line}")
        return self

    def add(self, text):
        self.parts.append(text.strip("\n"))
        return self

    def render(self):
        rows = [f"{self.module} is module", f'{self.module} purpose "{self.purpose}"', f"{self.module} path {self.module}"]
        rows += [f"{self.module} imports {i}" for i in (self.imports or ["none"])]
        rows += [f"{self.module} exports {e}" for e in (self.exports or ["none"])]
        return "\n".join(self.header) + "\n\n" + "\n".join(rows) + "\n\n" + "\n\n".join(self.parts) + "\n"

    def write(self, root, rel):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.render())


def op(name, purpose, steps, invariant="none", tparams=("none",), inputs=("none",), output="none", owner="none",
       raises="none", effects=("none",), uses=("none",), heap=False, waits=False, recursion="none", loops=None,
       lets=(), kind="operation", verifies=()):
    """steps: list of (label, step text). loops: {label: [fact rows after loopKind/within]} with kind/within."""
    loops = loops or {}
    rows = [f"{name} is {kind}", f'{name} purpose "{purpose}"']
    if kind == "operation":
        rows += [f"{name} invariant {invariant}"] if isinstance(invariant, str) else \
            [f'{name} invariant {i} "{t}"' for i, t in invariant]
    rows += [f"{name} verifies {v}" for v in verifies]
    rows += [f"{name} typeParam {t}" for t in tparams]
    rows += [f"{name} input {i}" for i in inputs]
    rows += [f"{name} output {output}", f"{name} outputOwner {owner}", f"{name} raises {raises}"]
    rows += [f"{name} effect {e}" for e in effects]
    rows += [f"{name} uses {u}" for u in uses]
    rows += [f"{name} memory heap {'true' if heap else 'false'}", f"{name} async {'true' if waits else 'false'}",
             f"{name} maxRecursion {recursion}"]
    labels = []
    for lab, _s in steps:
        if lab not in labels:
            labels.append(lab)
    for lab in labels:
        spec = loops.get(lab, {})
        rows.append(f"{name} label {lab} loopKind {spec.get('kind', 'none')}")
        rows.append(f"{name} label {lab} within {spec.get('within', 'none')}")
        for fact in spec.get("facts", []):
            rows.append(f"{name} label {lab} {fact}")
    rows += [f"{name} let {l}" for l in lets]
    rows += [f"{name} at {lab} {s}" for lab, s in steps]
    return "\n".join(rows)


def call(name, owner, target, args=("none",), out="none", owned="none", cleaned="none", borrows="none",
         catch="none", kind="call", rationale=None, reference=False):
    rows = [f"{name} is {kind}"]
    if rationale:
        rows.append(f'{name} rationale "{rationale}"')
    rows += [f"{name} in {owner}", f"{name} {'invokesReference' if reference else 'invokes'} {target}"]
    rows += [f"{name} arg {a}" for a in (args or ("none",))]
    rows += [f"{name} out {out}", f"{name} ownedBy {owned}", f"{name} cleanedBy {cleaned}",
             f"{name} borrows {borrows}", f"{name} catch {catch}"]
    return "\n".join(rows)


STDOUT_CAP = """stdoutWriter is capability
stdoutWriter purpose "Authority to write lines to standard output"
stdoutWriter grants write console.stdout
stdoutWriter scope none"""

_RATIONALE = "A test program has nowhere to report a failed write"


def show_int():
    return op("showInt", "Print one whole number on its own line",
              [("begin", "do writeValue"), ("begin", "branch ifError writeValue goto done else goto done"),
               ("done", "return ok none")],
              inputs=("value Int64 value",), effects=("write console.stdout",), uses=("stdoutWriter",)) + "\n\n" + \
        call("writeValue", "showInt", "console.writeIntegerLine", ("value Int64 value copy",),
             catch="writeError console.WriteError", rationale=_RATIONALE)


def show_text():
    return op("showText", "Print one line of text",
              [("begin", "do writeValue"), ("begin", "branch ifError writeValue goto done else goto done"),
               ("done", "return ok none")],
              inputs=("text String borrowed",), effects=("write console.stdout",), uses=("stdoutWriter",)) + "\n\n" + \
        call("writeValue", "showText", "console.writeLine", ("text String text lend",),
             catch="writeError console.WriteError", rationale=_RATIONALE)


def show_float():
    return op("showFloat", "Print one floating-point number on its own line",
              [("begin", "do writeValue"), ("begin", "branch ifError writeValue goto done else goto done"),
               ("done", "return ok none")],
              inputs=("value Float64 value",), effects=("write console.stdout",), uses=("stdoutWriter",)) + "\n\n" + \
        call("writeValue", "showFloat", "console.writeFloatLine", ("value Float64 value copy",),
             catch="writeError console.WriteError", rationale=_RATIONALE)


def show_bool():
    return op("showBool", "Print true or false on its own line",
              [("begin", "branch if flag goto sayTrue else goto sayFalse"),
               ("sayTrue", "do writeTrue"), ("sayTrue", "branch ifError writeTrue goto done else goto done"),
               ("sayFalse", "do writeFalse"), ("sayFalse", "branch ifError writeFalse goto done else goto done"),
               ("done", "return ok none")],
              inputs=("flag Bool value",), effects=("write console.stdout",), uses=("stdoutWriter",),
              lets=('trueText immutable String "true"', 'falseText immutable String "false"')) + "\n\n" + \
        call("writeTrue", "showBool", "console.writeLine", ("text String trueText lend",),
             catch="trueError console.WriteError", rationale=_RATIONALE) + "\n\n" + \
        call("writeFalse", "showBool", "console.writeLine", ("text String falseText lend",),
             catch="falseError console.WriteError", rationale=_RATIONALE)


SHOW = {"Int64": ("showInt", "value", "copy"), "String": ("showText", "text", "lend"),
        "Float64": ("showFloat", "value", "copy"), "Bool": ("showBool", "flag", "copy")}


def printer(owner, name, typ, value):
    target, slot, mode = SHOW[typ]
    return call(name, owner, target, (f"{slot} {typ} {value} {mode}",))


def main_op(steps, lets=(), loops=None, heap=False, purpose="Run the case and print what it computes", effects=True):
    return op("main", purpose, steps, output="ExitCode",
              effects=("write console.stdout",) if effects else ("none",),
              uses=("stdoutWriter",) if effects else ("none",),
              lets=tuple(lets) + ("okCode immutable ExitCode 0",), loops=loops, heap=heap)
