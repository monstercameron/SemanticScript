#!/usr/bin/env python3
"""standard.test example runner — runs every examples/*.sem through eavc and
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

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(HERE, "examples")
EAVC = os.path.join(HERE, "eavc.py")

HARD_NEG = {"div_by_zero_trap"}                      # rejected at compile time
STRICT_NEG = {"capability_ungranted_use", "failure_unhandled_propagate"}  # blocked under --strict
SUMMARY_RE = re.compile(r"----\s*(\d+) passed,\s*(\d+) failed\s*----")


def run(path, strict=False):
    argv = [sys.executable, EAVC, "run"] + (["--strict"] if strict else []) + [path]
    p = subprocess.run(argv, capture_output=True, text=True)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    quiet = "--quiet" in sys.argv
    files = sorted(f for f in os.listdir(EXAMPLES)
                   if f.endswith(".sem") and not f.startswith("_"))
    rows = []                  # (status, name, detail)
    tests = passed = failed = 0
    neg_ok = neg_total = 0
    suite_ok = True

    for fn in files:
        name = fn[:-4]
        path = os.path.join(EXAMPLES, fn)

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
    print(f"Examples : {len(files)}   ok: {examples_passed}   not-ok: {len(files)-examples_passed}")
    print(f"Negatives: {neg_ok}/{neg_total} behaved as expected")
    print(f"Assertions across all harness tests: {passed} passed, {failed} failed")
    print("RESULT   : " + ("ALL GREEN" if suite_ok else "FAILURES PRESENT"))
    return 0 if suite_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
