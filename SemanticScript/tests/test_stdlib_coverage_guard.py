"""Standard-library coverage guard (component lane).

Two jobs, both cheap and build-free:

1. **Component check** - every `std/<module>/main.sem` parses cleanly through
   the compiler front end (`--parse-only`). This is the lightest lane that
   touches every module's real source, so a parser/grammar regression in any
   module is caught here without a full build.

2. **Completeness guard** - the set of modules discovered on disk must exactly
   match the set of modules registered in an integration harness. Concretely
   every module is covered by one of:
     - `test_stdlib.py` JIT smoke (`OK_MODULES` + the `stdio` special case),
     - `test_stdlib.py` quarantine (`QUARANTINED_MODULES`, e.g. http),
     - `test_native_stdlib_smoke.py` native-exe smoke (`NATIVE_SMOKE_MODULES`).
   If someone adds `std/foo/` without wiring it into a harness, this fails -
   that is the regression `net` nearly slipped through historically.

Run from the repo root:
    python -m unittest SemanticScript/tests/test_stdlib_coverage_guard.py -v
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"
STD_ROOT = REPO_ROOT / "SemanticScript" / "std"

# Modules whose runtime is exercised as a native executable (not JIT) and are
# therefore registered in test_native_stdlib_smoke.py rather than test_stdlib.py.
# Keep in lockstep with that file's test methods.
NATIVE_SMOKE_MODULES = {"log", "bcrypt", "jwt", "net"}

# Modules that legitimately have no `main.test.sem` self-test, with the reason.
SELF_TEST_EXEMPT = {
    "net": "contract module (type aliases + net.fetch* intrinsics), no runnable body",
}


def _discovered_modules() -> set[str]:
    return {
        path.parent.name
        for path in STD_ROOT.glob("*/main.sem")
    }


def _registered_modules() -> set[str]:
    # Imported lazily so a syntax error in test_stdlib surfaces as this test's
    # failure rather than a collection error elsewhere.
    from SemanticScript.tests.test_stdlib import OK_MODULES, QUARANTINED_MODULES

    jit_counted = set(OK_MODULES) | {"stdio"}
    quarantined = set(QUARANTINED_MODULES)
    return jit_counted | quarantined | NATIVE_SMOKE_MODULES


class TestStdlibCoverageGuard(unittest.TestCase):
    def test_every_module_parses_clean(self) -> None:
        discovered = sorted(_discovered_modules())
        self.assertTrue(discovered, "no stdlib modules discovered under std/")
        for module in discovered:
            with self.subTest(module=module):
                source = STD_ROOT / module / "main.sem"
                proc = subprocess.run(
                    [sys.executable, str(SEMSC), str(source), "--parse-only"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                self.assertEqual(
                    0, proc.returncode,
                    f"{module}/main.sem failed --parse-only:\n{proc.stderr}",
                )

    def test_no_unregistered_modules(self) -> None:
        unregistered = _discovered_modules() - _registered_modules()
        self.assertEqual(
            set(), unregistered,
            "stdlib module(s) on disk are not wired into any integration "
            f"harness: {sorted(unregistered)}. Register each in test_stdlib.py "
            "(OK_MODULES / QUARANTINED_MODULES) or test_native_stdlib_smoke.py "
            "(then add to NATIVE_SMOKE_MODULES here).",
        )

    def test_no_stale_registrations(self) -> None:
        stale = _registered_modules() - _discovered_modules()
        self.assertEqual(
            set(), stale,
            f"harness(es) register stdlib module(s) absent from disk: {sorted(stale)}.",
        )

    def test_self_test_present_or_exempt(self) -> None:
        for module in sorted(_discovered_modules()):
            with self.subTest(module=module):
                has_self_test = (STD_ROOT / module / "main.test.sem").exists()
                if not has_self_test:
                    self.assertIn(
                        module, SELF_TEST_EXEMPT,
                        f"{module} has no main.test.sem and is not a documented "
                        "exemption; add a self-test or record why it cannot have one.",
                    )


if __name__ == "__main__":
    unittest.main()
