#!/usr/bin/env python3
"""Full CLI-surface smoke (rigorous parity gate).

Runs EVERY semanticscript subcommand on a real fixture and asserts each one
works -- exits 0 (or its documented status) and emits the expected output
shape (a versioned `sem.<tool>.v1` envelope for the JSON tools, or a known
substring for the text tools). File-modifying and build/codegen commands run
against throwaway temp copies so the gate is hermetic and repeatable.

This complements the narrower suites:
  - test_agent_tools.py : the agent-facing JSON tools + response structures
  - test_mcp.py         : the MCP stdio server / tools-list / tools-call
  - test_apps.py        : the seven apps run end-to-end
  - run_examples.py     : the example corpus compiles+runs

Together they answer "does the whole toolchain actually work". Exit 0 iff the
entire surface behaves.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEM = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")
F = "examples/hello_world.sem"


def run(argv, timeout=180):
    return subprocess.run([sys.executable, SEM, *argv],
                          capture_output=True, text=True, cwd=ROOT, timeout=timeout)


def surface(name):
    def check(p):
        if p.returncode != 0:
            return "rc=%d: %s" % (p.returncode, (p.stderr or p.stdout).strip()[:90])
        try:
            got = json.loads(p.stdout).get("surface")
        except json.JSONDecodeError:
            return "not JSON: %r" % p.stdout[:60]
        return None if got == name else "surface %r != %r" % (got, name)
    return check


def has(sub):
    def check(p):
        if p.returncode != 0:
            return "rc=%d: %s" % (p.returncode, (p.stderr or p.stdout).strip()[:90])
        return None if sub in p.stdout else "missing %r in output" % sub
    return check


def rc0(p):
    return None if p.returncode == 0 else "rc=%d: %s" % (
        p.returncode, (p.stderr or p.stdout).strip()[:90])


# (label, argv, check) -- the commands that read a fixture or are global.
CASES = [
    # global / registry-free
    ("version",      ["version", "--json"],          surface("sem.version.v1")),
    ("agent-docs",   ["agent-docs", "--json"],        surface("sem.agentDocs.v1")),
    ("skills list",  ["skills", "--json"],            surface("sem.skills.v1")),
    ("skills get",   ["skills", "eav-syntax", "--json"], surface("sem.skills.v1")),
    ("readiness",    ["readiness", "--json"],          surface("sem.readiness.v1")),
    ("status",       ["status", "--json"],             surface("sem.status.v1")),
    ("index",        ["index", "--json"],              surface("sem.codeIndex.v1")),
    ("clean",        ["clean", "--json"],              surface("sem.clean.v1")),
    ("explain",      ["explain", "SS1502"],            has("SS1502")),
    ("search",       ["search", "add a route", "--limit", "3", "--json"], surface("sem.search.v1")),
    ("scaffold",     ["scaffold", "console-program"],  has("is project")),
    ("task",         ["task", "add-route", "--json"],  surface("sem.task.v1")),
    ("lint registry", ["lint", "--explain", "SS1502", "--json"], rc0),
    # front-end / IR pipeline
    ("lex",          ["lex", F],                       rc0),
    ("parse",        ["parse", F],                     rc0),
    ("lower",        ["lower", F],                     has("ModuleID")),
    ("emit-ir",      ["emit-ir", F],                   has("ModuleID")),
    ("emit-ir --opt", ["emit-ir", F, "--optimized"],   has("ModuleID")),
    ("inspect-ir",   ["inspect-ir", F, "--json"],      surface("sem.inspectIr.v1")),
    # analysis (path)
    ("check",        ["check", F, "--json"],           surface("sem.check.v1")),
    ("lint",         ["lint", F],                      rc0),
    ("deps",         ["deps", F, "--json"],            surface("sem.deps.v1")),
    ("context",      ["context", F, "--json"],         surface("sem.context.v1")),
    ("symbols",      ["symbols", F, "--json"],         surface("sem.symbols.v1")),
    ("size",         ["size", F, "--json"],            surface("sem.size.v1")),
    ("dev",          ["dev", F, "--json"],             surface("sem.dev.v1")),
    ("doctor",       ["doctor", F],                    rc0),
    ("inventory",    ["inventory", F],                 rc0),
    ("docs",         ["docs", F, "--json"],            surface("sem.docsIndex.v1")),
    ("docs --get",   ["docs", F, "--get", "main", "--json"], surface("sem.docs.v1")),
    ("graph",        ["graph", F, "--json"],           surface("sem.graph.v1")),
    ("graph calls",  ["graph", F, "--kind", "calls"],  has("digraph")),
    ("describe",     ["describe", F, "main"],           has("main")),
    ("trace",        ["trace", F, "main"],              rc0),
    ("query",        ["query", "effects", F, "--json"], surface("sem.query.v1")),
    ("slice",        ["slice", F, "main", "--json"],    rc0),
    ("pack",         ["pack", F, "main"],               has("slice")),
    ("fix --plan",   ["fix", "--plan", F, "--json"],    surface("sem.fixPlan.v1")),
    ("fmt (stdout)", ["fmt", F],                        has("operation")),
    ("normalize",    ["normalize", F, "--preview"],     rc0),
    ("verify-patch", ["verify-patch", F],               has("OK")),
    ("diff",         ["diff", F, F],                    rc0),
    ("bench",        ["bench", F, "--runs", "2", "--json"], surface("sem.bench.v1")),
    ("eval",         ["eval", F, "--json"],             surface("sem.eval.v1")),
    ("run",          ["run", F],                        rc0),
    ("test",         ["test", F, "--allow-empty"],      surface("sem.test.v1")),
]


def temp_copy(td, name="prog.sem"):
    dst = os.path.join(td, name)
    shutil.copy(os.path.join(ROOT, F), dst)
    return dst


def special(td):
    """File-modifying / project / codegen commands -- each in its own temp area."""
    out = []

    # new: scaffold a fresh project skeleton (emits sem.new.v1 by default)
    proj = os.path.join(td, "proj")
    p = run(["new", proj])
    ok = (surface("sem.new.v1")(p) is None
          and os.path.exists(os.path.join(proj, "build.sem")))
    out.append(("new", None if ok else "new did not scaffold build.sem"))

    # fmt round-trip: canonical stdout must satisfy --check (rc 0), and --check
    # must DETECT drift on a non-canonical file (rc != 0). Both directions.
    canon = os.path.join(td, "canon.sem")
    with open(canon, "w", encoding="utf-8") as fh:
        fh.write(run(["fmt", F]).stdout)
    clean = run(["fmt", canon, "--check"])
    drift = run(["fmt", F, "--check"])
    ok = clean.returncode == 0 and drift.returncode != 0
    out.append(("fmt --check", None if ok else
                "canon rc=%d (want 0), drift rc=%d (want !=0)"
                % (clean.returncode, drift.returncode)))

    # repin: write a lock, then --check reports up-to-date. The dependency must be
    # materializable (SS2804/R-081) — a bare `require` with no registry/replace/
    # vendor artifact can't be locked — so it is satisfied by a local `replace`.
    bld = os.path.join(td, "rp")
    os.makedirs(os.path.join(bld, "dep"), exist_ok=True)
    with open(os.path.join(bld, "dep", "dep.sem"), "w", encoding="utf-8") as fh:
        fh.write("ExitCode is alias\nExitCode for Int32\n"
                 "depOp is operation\ndepOp out ExitCode\ndepOp async no\n"
                 'depOp purpose "p"\ndepOp invariant "i"\n')
    with open(os.path.join(bld, "build.sem"), "w", encoding="utf-8") as fh:
        fh.write("RepinDemo is project\nRepinDemo module m\nRepinDemo target console\n"
                 "RepinDemo entry main\nRepinDemo require example.org/u v1.0.0\n"
                 'RepinDemo replace example.org/u "dep"\n')
    w = run(["repin", bld, "--json"])
    c = run(["repin", bld, "--check", "--json"])
    try:
        ok = (json.loads(w.stdout).get("surface") == "sem.repin.v1"
              and json.loads(c.stdout).get("upToDate") is True)
    except (json.JSONDecodeError, AttributeError):
        ok = False
    out.append(("repin", None if ok else "write/--check round-trip failed"))

    # add: append a named entity to a copy (must still parse afterward)
    src = temp_copy(td, "add.sem")
    a = run(["add", src, "Helper"])
    chk = run(["check", src, "--json"])
    out.append(("add", None if (a.returncode == 0 and chk.returncode == 0)
                else "add rc=%d / check rc=%d" % (a.returncode, chk.returncode)))

    # rename: rename main -> entry on a copy, result must still parse
    src = temp_copy(td, "ren.sem")
    r = run(["rename", src, "main", "entrypoint"])
    chk = run(["check", src, "--json"])
    out.append(("rename", None if (r.returncode == 0 and chk.returncode == 0)
                else "rename rc=%d / check rc=%d" % (r.returncode, chk.returncode)))

    # patch: a fix-plan, then patch --dry-run consumes it (no write)
    plan = os.path.join(td, "plan.json")
    fp = run(["fix", "--plan", F, "--json"])
    with open(plan, "w", encoding="utf-8") as fh:
        fh.write(fp.stdout)
    pp = run(["patch", plan, "--dry-run", "--json"])
    out.append(("patch", None if pp.returncode == 0
                else "patch rc=%d: %s" % (pp.returncode, (pp.stderr or pp.stdout)[:80])))

    # build: native executable, then run it (console hello_world exits 0)
    exe = os.path.join(td, "hw.exe")
    b = run(["build", F, "--output", exe], timeout=300)
    if b.returncode == 0 and os.path.exists(exe):
        rp = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        out.append(("build", None if rp.returncode == 0
                    else "built exe rc=%d" % rp.returncode))
    else:
        out.append(("build", "build rc=%d: %s" % (b.returncode, (b.stderr or b.stdout)[:80])))

    # wasm: emit module + cjs runner
    w = os.path.join(td, "hw.wasm")
    wb = run(["wasm", F, "--output", w], timeout=300)
    out.append(("wasm", None if (wb.returncode == 0 and os.path.exists(w))
                else "wasm rc=%d: %s" % (wb.returncode, (wb.stderr or wb.stdout)[:80])))

    return out


def main():
    results = []
    for label, argv, check in CASES:
        try:
            results.append((label, check(run(argv))))
        except subprocess.TimeoutExpired:
            results.append((label, "TIMEOUT"))

    with tempfile.TemporaryDirectory() as td:
        results.extend(special(td))

    failures = [(l, d) for l, d in results if d is not None]
    print("cli surface: %d/%d OK" % (len(results) - len(failures), len(results)))
    for label, detail in failures:
        print("  FAIL %-14s %s" % (label, detail))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
