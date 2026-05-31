#!/usr/bin/env python3
"""WebAssembly backend test (WS3-161). Compiles wasm_demo.sem to a .wasm via
`eavc wasm` (LLVM IR -> clang --target=wasm32 -> wasm-ld), then runs it under
node and asserts the exported entry returns 42. Exit 0 iff it does.

Separate from run_examples (which JIT-runs console programs); this exercises the
wasm codegen + a real WebAssembly runtime (node).
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EAVC = os.path.join(HERE, "eavc.py")
SRC = os.path.join(HERE, "wasm_demo.sem")
WASM = os.path.join(HERE, "wasm_demo.wasm")
RUNNER = os.path.join(HERE, "wasm_demo.run.cjs")


def main():
    node = shutil.which("node")
    if node is None:
        print("SKIP: node not found (needed to run the wasm module)")
        return 0
    try:
        build = subprocess.run([sys.executable, EAVC, "wasm", SRC],
                               capture_output=True, text=True)
        if build.returncode != 0:
            print("FAIL: wasm build: %s" % build.stderr.strip())
            return 1
        run = subprocess.run([node, RUNNER], capture_output=True, text=True)
        out = (run.stdout or "").strip()
        ok = "main() = 42" in out and (run.returncode & 0xFF) == 42
        print("wasm: %r exit=%d -> %s" % (out, run.returncode, "PASS" if ok else "FAIL"))
        return 0 if ok else 1
    finally:
        for f in (WASM, RUNNER):
            try:
                os.remove(f)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
