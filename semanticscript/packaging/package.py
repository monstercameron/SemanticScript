"""Freeze the semanticscript toolchain into ONE self-contained executable (X-025).

The goal is a single portable binary: the EAV compiler, linter, formatter, the
JIT (llvmlite + its LLVM libraries), the MCP stdio server, the bundled stdlib /
signatures / native runtime sources, AND the vendored C toolchain inputs
(third_party/{sqlite,libuv,bcrypt}) — everything needed to parse, lint, lower,
JIT-run, and emit/link native programs offline. The only external requirement
left is a C compiler (clang/zig) on PATH for the native `build` path; embedding a
full C toolchain in the exe is out of scope.

What ships inside the exe:
  * compiler/semanticscript.py            (the toolchain entry point)
  * std/, sigs/, runtime/                 (stdlib, .semsig signatures, native C runtime)
  * third_party/{sqlite,libuv,bcrypt}     (vendored sources the runtime manifest links)
  * version.json                          (so `semanticscript version` reports the release)
  * llvmlite + its LLVM binaries          (the JIT / IR backend)

The frozen exe resolves bundled data through sys._MEIPASS (see _bundle_dir /
_runtime_link_path / _release_version in semanticscript.py). Native build
artifacts are written to a user-writable cache (_runtime_cache_dir), never back
into the read-only _MEIPASS extraction.

Build:  python package.py            -> dist/semanticscript[.exe]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The `semanticscript/` package root (parent of this packaging/ dir): std/sigs/
# runtime live here; the compiler is under compiler/.
PKG = os.path.dirname(HERE)
# The repo root (parent of the package): version.json and third_party/ live here.
ROOT = os.path.dirname(PKG)

# Only the vendored trees the runtime manifest actually links are bundled
# (emsdk/h2o are wasm-only / unused and are skipped to keep the exe lean).
THIRD_PARTY_DIRS = ("sqlite", "libuv", "bcrypt")

# Minimal MCP bootstrap, embedded in the Windows version resource so an agent
# inspecting the exe metadata learns how to drive it.
_MCP_COMMENT = (
    "SemanticScript CLI + MCP stdio server. "
    "Run `semanticscript mcp` for the MCP stdio JSON-RPC server. "
    'MCP client config: command "semanticscript.exe"; args ["mcp"]; cwd project root. '
    "Start with the `agent_docs` and `skills` tools."
)


def _version() -> str:
    try:
        with open(os.path.join(ROOT, "version.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version", "0.0.0")
    except (OSError, ValueError):
        return "0.0.0"


def _write_version_info(work: str, version: str) -> str:
    """Write a Windows VERSIONINFO resource file (PyInstaller format) carrying the
    release version and the MCP bootstrap comment. Returns the file path."""
    nums = [int(p) for p in version.split("+")[0].split("-")[0].split(".")][:4]
    while len(nums) < 4:
        nums.append(0)
    quad = ", ".join(str(n) for n in nums)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({quad}), prodvers=({quad}),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'SemanticScript'),
      StringStruct('FileDescription', 'SemanticScript CLI and MCP stdio server'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('ProductName', 'SemanticScript toolchain'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('Comments', {_MCP_COMMENT!r}),
      StringStruct('McpServerCommand', 'semanticscript.exe mcp'),
      StringStruct('McpServerTransport', 'stdio'),
    ])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
"""
    os.makedirs(work, exist_ok=True)
    path = os.path.join(work, "version_info.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def build() -> str:
    dist = os.path.join(HERE, "dist")
    work = os.path.join(HERE, "_pyi_build")
    version = _version()
    cmd = [
        sys.executable, "-m", "PyInstaller", "--onefile", "--noconfirm",
        "--name", "semanticscript", "--collect-all", "llvmlite",
        "--distpath", dist, "--workpath", work, "--specpath", work,
    ]

    # Bundled package data: std / sigs / runtime. The repo directory structure is
    # PRESERVED inside the bundle (_MEIPASS/semanticscript/<name>) so that the
    # relative `#include`s baked into the runtime C sources (e.g.
    # `../../../third_party/bcrypt/crypt_blowfish.h`) resolve the same way they do
    # from a checkout. _bundle_dir() points at _MEIPASS/semanticscript to match.
    for data_dir in ("std", "sigs", "runtime"):
        src = os.path.join(PKG, data_dir)
        if os.path.isdir(src):
            cmd += ["--add-data", src + os.pathsep + os.path.join("semanticscript", data_dir)]

    # Vendored C sources the runtime links. Placed at the bundle root (alongside
    # semanticscript/, mirroring the repo) so `runtime/../../third_party/...` and
    # the C sources' relative includes both resolve under _MEIPASS.
    for name in THIRD_PARTY_DIRS:
        src = os.path.join(ROOT, "third_party", name)
        if os.path.isdir(src):
            cmd += ["--add-data", src + os.pathsep + os.path.join("third_party", name)]

    # version.json so `semanticscript version` reports the release (resolved at
    # _MEIPASS/version.json when frozen).
    vj = os.path.join(ROOT, "version.json")
    if os.path.isfile(vj):
        cmd += ["--add-data", vj + os.pathsep + "."]

    # Embed the Windows version resource + MCP bootstrap metadata.
    if sys.platform == "win32":
        cmd += ["--version-file", _write_version_info(work, version)]

    cmd.append(os.path.join(PKG, "compiler", "semanticscript.py"))
    subprocess.run(cmd, check=True)
    exe = os.path.join(dist, "semanticscript" + (".exe" if sys.platform == "win32" else ""))
    return exe


if __name__ == "__main__":
    print(build())
