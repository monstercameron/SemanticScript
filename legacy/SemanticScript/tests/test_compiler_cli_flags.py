"""Coverage for compiler CLI flags not exercised elsewhere.

`--emit-optimized-ir` and `--cpu-baseline` had no test references; this builds
a minimal self-contained project and drives each flag, asserting the compiler
succeeds and (for the IR-emitting flags) produces real LLVM IR.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
SEMSC = REPO_ROOT / "SemanticScript" / "compiler" / "semsc.py"

_BUILD_TAPE = "\n".join([
    "buildProject flagProbe",
    "project FlagProbe",
    "modulePath flagProbe github.com/example/flag-probe",
    "languageVersion flagProbe \"1.0\"",
    "projectVersion flagProbe \"1.0.0\"",
    "projectLicense flagProbe MIT",
    "sourceRoot flagProbe \".\"",
    "targetRuntime flagProbe nativeExe",
    "buildProfile flagProbe dev",
    "optLevel flagProbe 2",
    "runtimeChecks flagProbe panic",
    "persistLlvmIr flagProbe auto",
    "target console",
    "runtime native 1",
    "entry console main",
    "registerModule flagProbe app.flagprobe \"main.sem\"",
    "mainFile flagProbe \"main.sem\"",
    "mainOperation flagProbe main",
    "import flagprobe app.flagprobe",
]) + "\n"

_MAIN = "\n".join([
    "module app.flagprobe",
    "operation main",
    "output operation main ExitCode",
    "purpose operation main \"minimal flag-probe entry\"",
    "return value 0",
]) + "\n"


def _project(root: Path) -> Path:
    (root / "build.sem").write_text(_BUILD_TAPE, encoding="utf-8", newline="\n")
    (root / "main.sem").write_text(_MAIN, encoding="utf-8", newline="\n")
    return root / "build.sem"


def _run(build_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SEMSC), str(build_path), *extra, "--quiet"],
        capture_output=True, text=True, timeout=120,
    )


class TestCompilerCliFlags(unittest.TestCase):
    def test_emit_ir_baseline(self) -> None:
        with TemporaryDirectory() as tmp:
            build = _project(Path(tmp))
            ir = Path(tmp) / "out.ll"
            proc = _run(build, "--emit-ir", str(ir))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(ir.exists())
            self.assertIn("define", ir.read_text(encoding="utf-8"))

    def test_emit_optimized_ir_produces_ir(self) -> None:
        # --emit-optimized-ir captures the post-optimization module from the
        # JIT pipeline, so it only writes when combined with --run.
        with TemporaryDirectory() as tmp:
            build = _project(Path(tmp))
            ir = Path(tmp) / "opt.ll"
            proc = _run(build, "--run", "--emit-optimized-ir", str(ir))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(ir.exists(), "optimized IR file not written")
            text = ir.read_text(encoding="utf-8")
            self.assertIn("define", text)
            self.assertIn("@main", text)

    def test_cpu_baseline_accepted(self) -> None:
        with TemporaryDirectory() as tmp:
            build = _project(Path(tmp))
            ir = Path(tmp) / "tuned.ll"
            proc = _run(build, "--emit-ir", str(ir), "--cpu-baseline", "x86_64_v2")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue(ir.exists())

    def test_invalid_cpu_baseline_rejected(self) -> None:
        with TemporaryDirectory() as tmp:
            build = _project(Path(tmp))
            proc = _run(build, "--emit-ir", str(Path(tmp) / "x.ll"),
                        "--cpu-baseline", "not_a_real_cpu")
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
