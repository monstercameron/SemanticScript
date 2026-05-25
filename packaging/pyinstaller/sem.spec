# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parents[1]


llvmlite_datas, llvmlite_binaries, llvmlite_hiddenimports = collect_all("llvmlite")


# The MCP server (sem mcp) is optional. Bundle the SDK only when it is present
# in the build environment so `sem.exe mcp` works without making mcp a hard
# build dependency.
try:
    mcp_datas, mcp_binaries, mcp_hiddenimports = [], [], ["SemanticScript.tools.sem_mcp"]
    # mcp + its transitive runtime deps. pydantic_core is a compiled extension
    # and anyio's backends are dynamically imported, so PyInstaller needs them
    # collected explicitly rather than relying on static import discovery.
    # uvicorn + starlette back the streamable-http / sse transports.
    for _pkg in ("mcp", "pydantic", "pydantic_core", "anyio", "uvicorn", "starlette"):
        _d, _b, _h = collect_all(_pkg)
        mcp_datas += _d
        mcp_binaries += _b
        mcp_hiddenimports += _h
except Exception:
    mcp_datas, mcp_binaries, mcp_hiddenimports = [], [], []


# Docs semantic search dependencies are large. Bundle them only for an explicit
# docs-search build variant: `$env:SEM_BUNDLE_DOCS_EMBEDDINGS = "1"`.
docs_datas, docs_binaries, docs_hiddenimports = [], [], []
if os.environ.get("SEM_BUNDLE_DOCS_EMBEDDINGS") == "1":
    for _pkg in (
        "sentence_transformers",
        "transformers",
        "tokenizers",
        "safetensors",
        "huggingface_hub",
        "torch",
        "sklearn",
        "scipy",
        "numpy",
        "sqlite_vec",
    ):
        _d, _b, _h = collect_all(_pkg)
        docs_datas += _d
        docs_binaries += _b
        docs_hiddenimports += _h


def tree(source: str, target: str | None = None) -> tuple[str, str]:
    return (str(ROOT / source), target or source.replace("\\", "/"))


datas = [
    (str(ROOT / "version.json"), "."),
    (str(ROOT / "requirements-docs.txt"), "."),
    tree("SemanticScript/compiler"),
    tree("SemanticScript/tools"),
    tree("SemanticScript/shared"),
    tree("SemanticScript/linter"),
    tree("SemanticScript/formatter"),
    tree("SemanticScript/bench"),
    tree("SemanticScript/std"),
    tree("SemanticScript/runtime"),
    tree("docs"),
    tree("research"),
    tree("third_party/sqlite"),
    tree("third_party/bcrypt"),
    *llvmlite_datas,
    *mcp_datas,
    *docs_datas,
]


a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "sem_launcher.py")],
    pathex=[str(ROOT), str(ROOT / "SemanticScript")],
    binaries=[*llvmlite_binaries, *mcp_binaries, *docs_binaries],
    datas=datas,
    hiddenimports=[
        "SemanticScript.tools.sem",
        "SemanticScript.compiler.semsc",
        "SemanticScript.linter.semlint",
        "SemanticScript.formatter.semfmt",
        "SemanticScript.bench.run_benchmarks",
        "SemanticScript.tools.syntax_migration",
        *llvmlite_hiddenimports,
        *mcp_hiddenimports,
        *docs_hiddenimports,
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sem",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
