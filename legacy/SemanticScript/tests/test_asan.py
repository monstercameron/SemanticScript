"""AddressSanitizer memory-safety tests for the hand-written C runtime.

The native runtime (`sem_async_runtime.c` and friends) is hand-written C - the
highest memory-safety risk in the project, and the place static contract checks
in the compiler can't reach. This builds the runtime's self-contained demo
drivers with `-fsanitize=address -fsanitize=undefined` and runs them, failing if
ASan/UBSan reports a use-after-free, overflow, double-free, or UB.

Capability gate: ASan needs a toolchain whose target ships the sanitizer
runtime. That is true for clang on Linux/macOS but NOT for `zig cc` targeting
Windows (no `__asan_init`). When no ASan-capable compiler is available the test
SKIPs with a clear reason rather than silently passing - and the Linux CI lane
(clang) is where it actually executes. This is a capability-gated skip, not a
no-op: where a sanitizer exists, it runs.

Run from the repo root (on an ASan-capable toolchain):
    python -m unittest SemanticScript/tests/test_asan.py -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ASYNC_DIR = REPO_ROOT / "SemanticScript" / "runtime" / "native_async"
RUNTIME_C = ASYNC_DIR / "sem_async_runtime.c"
DEMOS = ["health_demo.c", "manual_timer_order_demo.c"]

SAN_FLAGS = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g", "-O1"]
# Focus on memory-corruption (UAF/overflow/double-free) + UB; leak noise from
# demo drivers that intentionally don't free is not the signal we want here.
ASAN_ENV = {"ASAN_OPTIONS": "detect_leaks=0:abort_on_error=0", "UBSAN_OPTIONS": "halt_on_error=1"}


def _cc() -> list[str] | None:
    clang = shutil.which("clang")
    if clang:
        return [clang]
    zig = shutil.which("zig")
    if zig:
        return [zig, "cc"]
    return None


def _asan_capable(cc: list[str], work: Path) -> bool:
    """True iff this toolchain can build AND run an ASan binary."""
    src = work / "probe.c"
    src.write_text("#include <stdlib.h>\nint main(void){char*p=malloc(4);p[0]=1;free(p);return 0;}\n")
    exe = work / ("probe.exe" if os.name == "nt" else "probe")
    build = subprocess.run([*cc, "-fsanitize=address", str(src), "-o", str(exe)],
                           capture_output=True, text=True, timeout=120)
    if build.returncode != 0 or not exe.exists():
        return False
    try:
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60,
                             env={**os.environ, **ASAN_ENV})
    except OSError:
        return False
    return run.returncode == 0


class TestAddressSanitizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cc = _cc()
        if cls.cc is None:
            raise unittest.SkipTest("no C compiler (clang / zig cc) available")
        cls._tmp = tempfile.TemporaryDirectory(prefix="ss_asan_")
        cls.work = Path(cls._tmp.name)
        if not _asan_capable(cls.cc, cls.work):
            raise unittest.SkipTest(
                f"toolchain {cls.cc} cannot build+run an ASan binary on this "
                f"platform (e.g. zig cc targeting Windows lacks the ASan "
                f"runtime); the Linux CI lane runs this for real")

    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_tmp", None):
            cls._tmp.cleanup()

    def _build_and_run(self, demo: str) -> subprocess.CompletedProcess:
        exe = self.work / (demo.rsplit(".", 1)[0] + "_asan")
        build = subprocess.run(
            [*self.cc, *SAN_FLAGS, f"-I{ASYNC_DIR}",
             str(ASYNC_DIR / demo), str(RUNTIME_C), "-o", str(exe)],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(0, build.returncode,
                         f"ASan build failed for {demo}:\n{build.stderr}")
        return subprocess.run([str(exe)], capture_output=True, text=True, timeout=120,
                              env={**os.environ, **ASAN_ENV})

    def test_async_runtime_demos_are_sanitizer_clean(self) -> None:
        for demo in DEMOS:
            with self.subTest(demo=demo):
                if not (ASYNC_DIR / demo).exists():
                    self.skipTest(f"{demo} not present")
                result = self._build_and_run(demo)
                combined = result.stdout + result.stderr
                self.assertNotIn("runtime error:", combined, f"UBSan flagged {demo}:\n{combined}")
                self.assertNotIn("AddressSanitizer", combined, f"ASan flagged {demo}:\n{combined}")
                self.assertEqual(0, result.returncode,
                                 f"{demo} exited {result.returncode} under sanitizers:\n{combined}")


if __name__ == "__main__":
    unittest.main()
