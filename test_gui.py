#!/usr/bin/env python3
"""Win32 GUI runtime test (WS3-044). Runs gui_health_demo.sem, which binds the
SemanticScript Win32 GUI runtime via ss_gui_health_check: it creates a real
window with an auto-close handler, runs the Win32 message loop, and tears down,
returning 0. On a desktop the window flashes briefly; with no interactive
desktop the runtime reports unavailable, which the check maps to 0.

Separate from run_examples (so the suite never flashes a window). Exit 0 iff the
GUI runtime built, loaded, ran, and returned a success status.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEMANTICSCRIPT = os.path.join(HERE, "semanticscript.py")
DEMO = os.path.join(HERE, "gui_health_demo.sem")


def main():
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", DEMO],
                          capture_output=True, text=True)
    ok = proc.returncode == 0
    detail = (proc.stdout or proc.stderr or "").strip()[:200]
    print("gui health check: exit=%d %s-> %s"
          % (proc.returncode, (detail + " ") if detail else "", "PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
