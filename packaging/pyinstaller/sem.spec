# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


ROOT = Path(SPECPATH).resolve().parents[1]


llvmlite_datas, llvmlite_binaries, llvmlite_hiddenimports = collect_all("llvmlite")


def tree(source: str, target: str | None = None) -> tuple[str, str]:
    return (str(ROOT / source), target or source.replace("\\", "/"))


datas = [
    (str(ROOT / "version.json"), "."),
    tree("SemanticScript/compiler"),
    tree("SemanticScript/tools"),
    tree("SemanticScript/shared"),
    tree("SemanticScript/linter"),
    tree("SemanticScript/formatter"),
    tree("SemanticScript/bench"),
    tree("SemanticScript/std"),
    tree("SemanticScript/runtime"),
    tree("docs"),
    tree("apps/taskforge-web"),
    tree("experiments/agent-first-tooling-research"),
    tree("third_party/sqlite"),
    tree("third_party/bcrypt"),
    *llvmlite_datas,
]


a = Analysis(
    [str(ROOT / "packaging" / "pyinstaller" / "sem_launcher.py")],
    pathex=[str(ROOT), str(ROOT / "SemanticScript")],
    binaries=llvmlite_binaries,
    datas=datas,
    hiddenimports=[
        "SemanticScript.tools.sem",
        "SemanticScript.compiler.semsc",
        "SemanticScript.linter.semlint",
        "SemanticScript.formatter.semfmt",
        "SemanticScript.bench.run_benchmarks",
        "SemanticScript.tools.syntax_migration",
        *llvmlite_hiddenimports,
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
