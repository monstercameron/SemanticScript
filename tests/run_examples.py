#!/usr/bin/env python3
"""standard.test example runner — runs every examples/*.sem through semanticscript and
aggregates the per-program harness summaries into one report.

Each positive example is a self-checking test built on the `standard.test`
harness: it prints `PASS`/`FAIL` lines and a `---- N passed, M failed ----`
summary, and exits with the number of failed assertions (0 == all green). This
runner executes them all, tallies the assertions, and reports a grand total.

The three negative examples are compile/gate rejection tests (they cannot run a
runtime harness): `div_by_zero_trap` must be rejected at compile time, and
`capability_ungranted_use` / `failure_unhandled_propagate` must run by default
but be rejected under `--strict`.

Usage:
    python run_examples.py            # full report
    python run_examples.py --quiet    # only failures + totals
Exit code: 0 iff every example behaves as expected.
"""
import os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))          # tests/
ROOT = os.path.dirname(HERE)                               # repo root
EXAMPLES = os.path.join(ROOT, "examples")
SEMANTICSCRIPT = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")

MIN_APPS = 150                                       # X-214 corpus coverage floor
HARD_NEG = {"div_by_zero_trap"}                      # rejected at compile time
STRICT_NEG = {"capability_ungranted_use", "failure_unhandled_propagate"}  # blocked under --strict
# WS1-130: compiles + runs, then traps at runtime via ss_panic — must exit 134
# with the named SSR#### structured report on stderr.
TRAP_NEG = {"panic_div0_report": "SSR0010",
            "panic_narrowing_report": "SSR0012",
            "panic_recursion_report": "SSR0013",
            "deep_recursion_trap": "SSR0013"}
SUMMARY_RE = re.compile(r"----\s*(\d+) passed,\s*(\d+) failed\s*----")
# Keystone slices that intentionally print raw output via console.writeLine (no
# self-checking harness), per README §18 (hello_world) / §30.1.1 (replay_demo).
# Validated by exact stdout + a clean exit instead of a harness summary.
RAW_OUT = {"hello_world": "hello world", "replay_demo": "replay me"}


# EAV source/output is UTF-8 (README §33.2); decode child pipes as UTF-8 so
# non-ASCII comments (em-dash, →, ✓) survive the round-trip on Windows cp1252.
# cwd=ROOT so compile-time CWD-relative paths (e.g. asset_embed's
# literalSource "examples/assets/banner.txt") resolve no matter where the
# harness is launched from.
_UTF8 = dict(capture_output=True, text=True, encoding="utf-8", cwd=ROOT)

# R-096: bound every per-example subprocess so one hanging example (an infinite
# loop, a runtime stall, a compiler regression) can't consume the whole CI job
# and hide the offending file. Configurable; generous enough for native builds.
_EXAMPLE_TIMEOUT = float(os.environ.get("SEMANTICSCRIPT_EXAMPLE_TIMEOUT", "") or 90)


def run(path, strict=False):
    argv = [sys.executable, SEMANTICSCRIPT, "run"] + (["--strict"] if strict else []) + [path]
    try:
        p = subprocess.run(argv, timeout=_EXAMPLE_TIMEOUT, **_UTF8)
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT: '{path}' exceeded {_EXAMPLE_TIMEOUT:g}s (run phase)"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def fmt_idempotent(path):
    """fmt(src) must equal fmt(fmt(src)) — the formatter is a fixed point
    (README §22; guards the WS4-005 de-indent class of bugs). Returns
    (ok, detail)."""
    try:
        a = subprocess.run([sys.executable, SEMANTICSCRIPT, "fmt", path],
                           timeout=_EXAMPLE_TIMEOUT, **_UTF8)
        if a.returncode != 0:
            return False, "fmt failed: " + (a.stderr or "").strip()[:60]
        b = subprocess.run([sys.executable, SEMANTICSCRIPT, "fmt", "-"],
                           input=a.stdout, timeout=_EXAMPLE_TIMEOUT, **_UTF8)
    except subprocess.TimeoutExpired:
        return False, f"TIMEOUT: '{path}' exceeded {_EXAMPLE_TIMEOUT:g}s (fmt phase)"
    if b.returncode != 0:
        return False, "second fmt failed: " + (b.stderr or "").strip()[:60]
    if a.stdout != b.stdout:
        return False, "fmt not idempotent (fmt(x) != fmt(fmt(x)))"
    return True, ""


def main():
    quiet = "--quiet" in sys.argv
    files = sorted(f for f in os.listdir(EXAMPLES)
                   if f.endswith(".sem") and not f.startswith("_"))
    rows = []                  # (status, name, detail)
    tests = passed = failed = 0
    neg_ok = neg_total = 0
    fmt_ok = fmt_total = 0
    suite_ok = True

    for fn in files:
        name = fn[:-4]
        path = os.path.join(EXAMPLES, fn)

        # Every example that parses must be a fixed point of fmt. HARD_NEG
        # programs are intentionally rejected at parse/validate time (e.g.
        # div-by-constant-zero, SS3111), so they have no canonical formatting
        # and are exempt from the idempotence guard.
        if name not in HARD_NEG:
            fmt_total += 1
            fi_ok, fi_detail = fmt_idempotent(path)
            fmt_ok += fi_ok
            suite_ok &= fi_ok
            if not fi_ok:
                rows.append(("FMT-BAD", name, fi_detail))

        if name in HARD_NEG:
            neg_total += 1
            code, _ = run(path)
            ok = code != 0
            neg_ok += ok
            suite_ok &= ok
            rows.append(("NEG-OK" if ok else "NEG-BAD", name,
                         "rejected at compile time" if ok else "should have been rejected"))
            continue

        if name in STRICT_NEG:
            neg_total += 1
            d, _ = run(path)
            s, _ = run(path, strict=True)
            ok = (d == 0 and s != 0)
            neg_ok += ok
            suite_ok &= ok
            rows.append(("NEG-OK" if ok else "NEG-BAD", name,
                         "runs by default, blocked under --strict" if ok else "strict gate did not block"))
            continue

        if name in TRAP_NEG:
            neg_total += 1
            want = TRAP_NEG[name]
            code, out = run(path)
            ok = (code == 134 and ("EAV PANIC " + want) in out)
            neg_ok += ok
            suite_ok &= ok
            rows.append(("NEG-OK" if ok else "NEG-BAD", name,
                         f"runtime panic {want}, exit 134" if ok
                         else f"expected panic {want}/exit 134, got exit {code}"))
            continue

        if name in RAW_OUT:
            want = RAW_OUT[name]
            code, out = run(path)
            ok = (code == 0 and want in out)
            suite_ok &= ok
            rows.append(("PASS" if ok else "FAIL", name,
                         f"raw output {want!r}" if ok
                         else f"expected {want!r}, got exit {code}"))
            continue

        code, out = run(path)
        m = SUMMARY_RE.search(out)
        if m:
            p_n, f_n = int(m.group(1)), int(m.group(2))
        else:
            p_n, f_n = 0, 0
        tests += p_n + f_n
        passed += p_n
        failed += f_n
        ok = (code == 0 and f_n == 0 and m is not None)
        suite_ok &= ok
        if m is None:
            detail = "no harness summary (exit=%d)" % code
        else:
            detail = "%d passed" % p_n + ("" if f_n == 0 else ", %d failed" % f_n)
        rows.append(("PASS" if ok else "FAIL", name, detail))

    # ---- report ----
    print("SemanticScript example test runner (standard.test)")
    print("=" * 60)
    width = max(len(n) for _, n, _ in rows)
    for status, name, detail in rows:
        if quiet and status in ("PASS", "NEG-OK"):
            continue
        print(f"{status:<7} {name:<{width}}  {detail}")
    print("=" * 60)
    examples_passed = sum(1 for s, _, _ in rows if s in ("PASS", "NEG-OK"))
    count_ok = len(files) >= MIN_APPS
    suite_ok &= count_ok
    print(f"Examples : {len(files)}   ok: {examples_passed}   not-ok: {len(files)-examples_passed}"
          + ("" if count_ok else f"   COVERAGE-FAIL: < {MIN_APPS} apps"))
    print(f"Negatives: {neg_ok}/{neg_total} behaved as expected")
    print(f"Fmt      : {fmt_ok}/{fmt_total} idempotent (fmt(x) == fmt(fmt(x)))")
    print(f"Assertions across all harness tests: {passed} passed, {failed} failed")
    print("RESULT   : " + ("ALL GREEN" if suite_ok else "FAILURES PRESENT"))
    return 0 if suite_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
