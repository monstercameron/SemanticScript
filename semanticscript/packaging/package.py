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
import importlib.util
import json
import os
import shutil
import subprocess
import sys

# R-149: the freeze can wedge on a stuck PyInstaller import scan, an AV/file-lock
# stall, or a bad local install. Bound it (override with SEM_PACKAGE_TIMEOUT) and
# surface failures as a machine-readable sem.package.v1 envelope, like the rest of
# the toolchain — instead of an unbounded hang or a raw CalledProcessError.
PACKAGE_SURFACE = "sem.package.v1"


def _default_timeout() -> int:
    try:
        return max(1, int(os.environ.get("SEM_PACKAGE_TIMEOUT", "1800")))
    except ValueError:
        return 1800


class PackagingError(Exception):
    """A bounded, machine-readable packaging failure (R-149). `.envelope` is a
    sem.package.v1 body an agent/CI can branch on (ok:false + status + phase)."""

    def __init__(self, status: str, phase: str, message: str, detail: str = ""):
        super().__init__(message)
        self.envelope = {
            "surface": PACKAGE_SURFACE, "version": "v1", "ok": False,
            "status": status, "phase": phase, "message": message,
        }
        if detail:
            self.envelope["detail"] = detail


def _tail(text: str, limit: int = 2000) -> str:
    """The trailing slice of captured output — enough to diagnose a failure
    without dumping a multi-megabyte PyInstaller log."""
    if not text:
        return ""
    return text[-limit:]


def _check_pyinstaller() -> None:
    """R-149: a missing/broken PyInstaller is a structured dependency error up
    front, not a late ModuleNotFoundError traceback from the freeze subprocess."""
    if importlib.util.find_spec("PyInstaller") is None:
        raise PackagingError(
            "dependency-missing", "preflight",
            "PyInstaller is not installed; run `pip install pyinstaller` to build "
            "the frozen toolchain executable")


def _run_bounded(cmd: list, timeout: int, phase: str) -> subprocess.CompletedProcess:
    """Run a packaging subprocess with a timeout and captured output. A timeout,
    a spawn failure, or a non-zero exit each become a named-phase PackagingError
    instead of an unbounded hang or a bare CalledProcessError (R-149)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise PackagingError(
            "timeout", phase,
            f"{phase} exceeded the {timeout}s packaging timeout "
            f"(set SEM_PACKAGE_TIMEOUT to adjust)",
            detail=_tail(exc.stdout.decode() if isinstance(exc.stdout, bytes)
                         else (exc.stdout or ""))) from exc
    except OSError as exc:
        raise PackagingError(
            "spawn-failed", phase, f"could not launch {phase}: {exc}") from exc
    if proc.returncode != 0:
        raise PackagingError(
            "freeze-failed", phase,
            f"{phase} failed with exit {proc.returncode}",
            detail=_tail(proc.stderr) or _tail(proc.stdout))
    return proc


_SMOKE_HELLO = (
    "Hi is project\nHi module m\nHi target console\nHi entry main\n"
    "m is module\nm path smoke.hi\nm exports main\n"
    'm purpose "frozen-exe smoke"\nm invariant "prints a line"\n'
    "ExitCode is alias\nExitCode for Int32\n"
    "outCap is capability\noutCap grants write console.stdout\noutCap purpose \"w\"\n"
    "main is operation\nmain out ExitCode\nmain effect write console.stdout\n"
    "main uses outCap\nmain async no\n"
    'main purpose "p"\nmain invariant "i"\n'
    'main let msg immutable String "packaging-smoke-ok"\n'
    "main let okCode immutable ExitCode 0\n"
    "main do say\nmain return okCode\n"
    "say is call\nsay in main\nsay invokes console.writeLine\nsay arg text String msg\n"
)


def _check_version_output(rc: int, stdout: str) -> str:
    """Validate a `version --json` smoke result (factored out so the contract is
    unit-testable without a real frozen exe). Returns the reported version."""
    if rc != 0:
        raise PackagingError("smoke-failed", "smoke",
                             f"`version --json` exited {rc}", detail=_tail(stdout))
    try:
        body = json.loads(stdout)
    except ValueError as exc:
        raise PackagingError("smoke-failed", "smoke",
                             "`version --json` did not emit JSON",
                             detail=_tail(stdout)) from exc
    if not body.get("ok", False):
        raise PackagingError("smoke-failed", "smoke",
                             "`version --json` envelope was not ok")
    return str(body.get("version", ""))


def _smoke(exe: str, timeout: int) -> str:
    """R-149: prove the produced exe actually runs before claiming success —
    `version --json` (a valid envelope) plus a hello-world JIT run."""
    try:
        ver = subprocess.run([exe, "version", "--json"], capture_output=True,
                             text=True, timeout=min(timeout, 120))
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise PackagingError("smoke-failed", "smoke",
                             f"`version --json` did not complete: {exc}") from exc
    version = _check_version_output(ver.returncode, ver.stdout)
    try:
        run = subprocess.run([exe, "run", "-"], input=_SMOKE_HELLO,
                             capture_output=True, text=True, timeout=min(timeout, 180))
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise PackagingError("smoke-failed", "smoke",
                             f"hello-world `run -` did not complete: {exc}") from exc
    if run.returncode != 0:
        raise PackagingError("smoke-failed", "smoke",
                             f"hello-world `run -` exited {run.returncode}",
                             detail=_tail(run.stderr))
    return version


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


def build(timeout: int = None, smoke: bool = True) -> str:
    # R-149: fail fast with a structured dependency error if PyInstaller is absent.
    _check_pyinstaller()
    timeout = timeout if timeout is not None else _default_timeout()
    dist = os.path.join(HERE, "dist")
    work = os.path.join(HERE, "_pyi_build")
    # R-149: clear a stale partial work dir so a previous wedged/cancelled run
    # cannot poison this freeze (PyInstaller reuses --workpath).
    if os.path.isdir(work):
        shutil.rmtree(work, ignore_errors=True)
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

    # The language guide (R-119): `search`/spec retrieval reads docs/LANGUAGE.md
    # at _bundle_dir()/../docs/LANGUAGE.md, i.e. _MEIPASS/docs/LANGUAGE.md when
    # frozen — so bundle it there. Without it the frozen exe's `search` returns no
    # spec hits and `docs/LANGUAGE.md` refs dangle.
    guide = os.path.join(ROOT, "docs", "LANGUAGE.md")
    if os.path.isfile(guide):
        cmd += ["--add-data", guide + os.pathsep + "docs"]

    # Embed the Windows version resource + MCP bootstrap metadata.
    if sys.platform == "win32":
        cmd += ["--version-file", _write_version_info(work, version)]

    cmd.append(os.path.join(PKG, "compiler", "semanticscript.py"))
    # R-149: bounded + captured freeze with a named phase, not `check=True`.
    _run_bounded(cmd, timeout, "pyinstaller-freeze")
    exe = os.path.join(dist, "semanticscript" + (".exe" if sys.platform == "win32" else ""))
    if not os.path.isfile(exe):
        raise PackagingError(
            "no-artifact", "verify",
            "PyInstaller reported success but the executable is missing", detail=exe)
    if smoke:
        _smoke(exe, timeout)
    return exe


if __name__ == "__main__":
    _want_json = "--json" in sys.argv[1:]
    _no_smoke = "--no-smoke" in sys.argv[1:]
    try:
        _exe = build(smoke=not _no_smoke)
    except PackagingError as exc:
        # R-149: a structured sem.package.v1 failure on stderr + nonzero exit.
        sys.stderr.write(json.dumps(exc.envelope, indent=2) + "\n")
        raise SystemExit(1)
    if _want_json:
        print(json.dumps({
            "surface": PACKAGE_SURFACE, "version": "v1", "ok": True,
            "status": "built", "executable": _exe, "smoked": not _no_smoke,
        }, indent=2))
    else:
        print(_exe)
