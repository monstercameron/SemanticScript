"""End-to-end wasm build tests: SemanticScript -> LLVM IR -> emcc -> node.

These verify the emscripten backend path produces a `.wasm` whose runtime
behaviour matches the native JIT baseline. They are skipped automatically when
the emscripten toolchain (the `third_party/emsdk` submodule) has not been
installed, so the suite stays green in environments without the ~2GB toolchain.

Install the toolchain (emsdk is an opt-in `update = none` submodule):
    git submodule update --init --checkout third_party/emsdk
    python third_party/emsdk/emsdk.py install latest
    python third_party/emsdk/emsdk.py activate latest

Run from repo root:
    python -m unittest SemanticScript/tests/test_wasm_build.py -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "SemanticScript" / "tools"))

import build_wasm  # noqa: E402

SEM_DIR = REPO_ROOT / "SemanticScript" / "sem"

# (program, substring expected in wasm stdout) — outputs mirror the native JIT
# baseline (`semsc --run`).
CASES = [
    ("hello_world", "Hello, world!"),
    ("factorial", "3628800"),
    ("sum_of_squares", "385"),
    ("simple_calculator", "power    2 5 => 32"),
]


@unittest.skipUnless(
    build_wasm.toolchain_ready(),
    "emscripten toolchain not installed under third_party/emsdk",
)
class WasmBuildTest(unittest.TestCase):
    def _build_and_run(self, name: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            out_js = Path(tmp) / f"{name}.js"
            build_wasm.build_wasm(SEM_DIR / f"{name}.sem", out_js)
            self.assertTrue(out_js.with_suffix(".wasm").is_file())
            return build_wasm.run_wasm(out_js)

    def test_programs_run_in_wasm(self):
        for name, expected in CASES:
            with self.subTest(program=name):
                self.assertIn(expected, self._build_and_run(name))


if __name__ == "__main__":
    unittest.main()
