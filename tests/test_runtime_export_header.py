from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "semanticscript" / "runtime"
EXPORT_HEADER = RUNTIME / "ss_runtime_export.h"


def test_runtime_shims_use_shared_export_header():
    header = EXPORT_HEADER.read_text(encoding="utf-8")
    assert "SS_EXPORT __declspec(dllexport)" in header
    assert "SS_EXPORT __attribute__((visibility(\"default\")))" in header
    assert "SS_RUNTIME_STATIC" in header
    assert "SS_RUNTIME_IMPORT_DLL" in header

    offenders = []
    missing_include = []
    for path in sorted(RUNTIME.glob("ss_*.c")):
        text = path.read_text(encoding="utf-8")
        if "SS_EXPORT" not in text:
            continue
        if "#define SS_EXPORT" in text:
            offenders.append(path.name)
        if '#include "ss_runtime_export.h"' not in text:
            missing_include.append(path.name)

    assert offenders == []
    assert missing_include == []
