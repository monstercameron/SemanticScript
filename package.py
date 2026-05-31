"""Freeze the eavc toolchain into a standalone executable (X-025).

Bundles eavc.py + llvmlite (with its LLVM binaries) + the std/sigs/runtime data
into a single self-contained binary via PyInstaller, so the EAV compiler and
tools ship without a Python install. Run:  python package.py

The frozen exe resolves bundled data through sys._MEIPASS (see _bundle_dir in
eavc.py). Output: dist/eavc[.exe].
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def build() -> str:
    dist = os.path.join(HERE, "dist")
    work = os.path.join(HERE, "_pyi_build")
    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm",
        "--name", "eavc", "--collect-all", "llvmlite",
        "--distpath", dist, "--workpath", work, "--specpath", work,
    ]
    for data_dir in ("std", "sigs", "runtime"):
        src = os.path.join(HERE, data_dir)
        if os.path.isdir(src):
            cmd += ["--add-data", src + os.pathsep + data_dir]
    cmd.append(os.path.join(HERE, "eavc.py"))
    subprocess.run(cmd, check=True)
    exe = os.path.join(dist, "eavc" + (".exe" if sys.platform == "win32" else ""))
    return exe


if __name__ == "__main__":
    print(build())
