"""Generate the runtime's modules from their DSL files (docs/refined-examples/stage0/tools/semgen.py).

    python build.py            # every module
    python build.py memory     # some modules

Each `<module>.dsl` here is written out as `../<module>.sem`, its `@tests` section as `../<module>.test.sem`, with
the comment header in `<module>.header` (and `<module>.test.header`). The generated `.sem` files are the runtime;
regenerating must leave `git status` clean. The floats module's test cases, values with what Python writes and
reads for them, are written into floats.dsl by floatcases.py.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(RUNTIME))
sys.path.insert(0, os.path.join(REPO, "docs", "refined-examples", "stage0", "tools"))
from semgen import Generator, Module, Program  # noqa: E402

# in the order build.sem includes them: a module's DSL may call only the modules above it
MODULES = ["kernel", "memory", "numbers", "output", "frames", "heap", "tables", "values", "handles", "regions", "slots", "bignum", "floats", "wide", "clibrary", "clong", "cformat", "cstreams", "cstart", "ctime", "cprocess", "cthreads", "cextra", "cmathbits", "cmathexp", "cmathtrig", "cmathspecial", "cmathcomplex", "cwide", "cwidetime", "loader", "tasks", "interrupts", "files", "sockets", "processes", "hashes", "generators", "requests", "documents", "host", "start"]


def lines_of(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return fh.read().rstrip("\n").split("\n")


def generate() -> dict:
    """Every generated file's text, by its path under semanticscript/runtime."""
    prog = Program()
    out = {}
    for name in MODULES:
        with open(os.path.join(HERE, name + ".dsl"), encoding="utf-8") as fh:
            text = fh.read()
        m = Module(name)
        prog.modules[name] = m
        g = Generator(prog, m)
        g.declare(text)
        g.parse(text)
        f, tf = g.render(lines_of(os.path.join(HERE, name + ".header")) or [],
                         lines_of(os.path.join(HERE, name + ".test.header")))
        out[name + ".sem"] = f
        if tf is not None:
            out[name + ".test.sem"] = tf
    return out


def main(which):
    for rel, text in generate().items():
        if rel.split(".")[0] not in which:
            continue
        with open(os.path.join(RUNTIME, rel), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"{rel}: {text.count(chr(10))} lines")


if __name__ == "__main__":
    main(sys.argv[1:] or MODULES)
