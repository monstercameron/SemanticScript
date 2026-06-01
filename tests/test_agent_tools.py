#!/usr/bin/env python3
"""Agentic CLI tool audit (TOOL-2).

Exercises every agent-facing command on a real fixture and asserts it runs (rc 0)
and returns its documented surface — a versioned `sem.<tool>.v1` JSON envelope for
the structured tools, or meaningful text for the content tools (explain/describe/
trace/scaffold). Guards the agent surface (and its response structures) against
regression. Exit 0 iff every tool behaves.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SEM = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")
F = "examples/hello_world.sem"

# (label, argv, kind, expect)
#   kind "json": stdout parses as JSON whose `surface` == expect
#   kind "text": rc 0 and `expect` substring appears in stdout
CASES = [
    ("agent-docs", ["agent-docs", "--json"], "json", "sem.agentDocs.v1"),
    ("skills list", ["skills", "--json"], "json", "sem.skills.v1"),
    ("skills get", ["skills", "eav-syntax", "--json"], "json", "sem.skills.v1"),
    ("check", ["check", F, "--json"], "json", "sem.check.v1"),
    ("query", ["query", "effects", F, "--json"], "json", "sem.query.v1"),
    ("graph", ["graph", F, "--json"], "json", "sem.graph.v1"),
    ("fix --plan", ["fix", "--plan", F, "--json"], "json", "sem.fixPlan.v1"),
    ("eval", ["eval", F, "--json"], "json", "sem.eval.v1"),
    ("docs", ["docs", F, "--json"], "json", "sem.docsIndex.v1"),
    ("deps", ["deps", F, "--json"], "json", "sem.deps.v1"),
    ("context", ["context", F, "--json"], "json", "sem.context.v1"),
    ("symbols", ["symbols", F, "--json"], "json", "sem.symbols.v1"),
    ("size", ["size", F, "--json"], "json", "sem.size.v1"),
    ("readiness", ["readiness", "--json"], "json", "sem.readiness.v1"),
    ("explain", ["explain", "SS1502"], "text", "SS1502"),
    ("describe", ["describe", F, "main"], "text", "main"),
    ("trace", ["trace", F, "main"], "text", "live"),
    ("scaffold", ["scaffold", "console-program"], "text", "is project"),
    ("emit-ir", ["emit-ir", F], "text", "ModuleID"),
    ("emit-ir --optimized", ["emit-ir", F, "--optimized"], "text", "ModuleID"),
    ("inspect-ir", ["inspect-ir", F, "--json"], "json", "sem.inspectIr.v1"),
    ("status", ["status", "--json"], "json", "sem.status.v1"),
    ("index", ["index", "--json"], "json", "sem.codeIndex.v1"),
    ("search", ["search", "cleanup", "--json"], "json", "sem.search.v1"),
]


def main():
    failures = []
    for label, argv, kind, expect in CASES:
        proc = subprocess.run([sys.executable, SEM, *argv],
                              capture_output=True, text=True, cwd=ROOT, timeout=120)
        out = proc.stdout
        if proc.returncode != 0:
            failures.append((label, "rc=%d: %s" % (proc.returncode,
                                                   (proc.stderr or out).strip()[:80])))
            continue
        if kind == "json":
            try:
                surface = json.loads(out).get("surface")
            except json.JSONDecodeError:
                failures.append((label, "not JSON: %r" % out[:60]))
                continue
            if surface != expect:
                failures.append((label, "surface %r != %r" % (surface, expect)))
        else:  # text
            if expect not in out:
                failures.append((label, "missing %r in output" % expect))

    print("agent tools: %d/%d OK" % (len(CASES) - len(failures), len(CASES)))
    for label, detail in failures:
        print("  FAIL %-14s %s" % (label, detail))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
