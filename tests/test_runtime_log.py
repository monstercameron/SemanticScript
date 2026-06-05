import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "semanticscript" / "compiler"))
import semanticscript  # noqa: E402


def test_log_contract_is_runtime_backed_not_deferred():
    semsig = (ROOT / "semanticscript" / "sigs" / "standard.log.semsig").read_text(encoding="utf-8")
    lowered = semsig.lower()
    assert "deferred runtime" not in lowered
    assert "not lowered" not in lowered
    assert "ss_log_* native bindings" in semsig

    manifest = json.loads((ROOT / "semanticscript" / "runtime" / "manifest.json").read_text(encoding="utf-8"))
    log_libs = [library for library in manifest["libraries"] if library.get("name") == "ss_log"]
    assert log_libs == [{
        "name": "ss_log",
        "comment": "APP-RUN-6 structured logging (log.*). The app binds the native ss_log_* directly.",
        "provides": ["ss_log_"],
        "exports": ["ss_log_info", "ss_log_warn", "ss_log_set_path"],
        "sources": ["native_log/sem_log_runtime.c"],
        "include": ["native_log", "native_platform"],
    }]


def test_log_runtime_creates_nested_parent_directories():
    source = (ROOT / "semanticscript" / "runtime" / "native_log" / "sem_log_runtime.c").read_text(
        encoding="utf-8"
    )
    assert "static int log_ensure_parent_directory(void)" in source
    assert "if (errno == EEXIST)" in source
    assert "_stat(path, &st)" in source
    assert "stat(path, &st)" in source
    assert "if (!log_ensure_parent_directory()) return NULL;" in source
    assert "parent[i] = '\\0';" in source
    assert "log_mkdir_p_single(parent)" in source


def test_dx16_log_info_native_payload_reaches_log_file(tmp_path):
    if semanticscript._find_c_compiler() is None:
        pytest.skip("no C compiler available for native log build")
    source = tmp_path / "logged.sem"
    source.write_text(
        semanticscript.scaffold("logged-op").replace(
            "logged-op scaffold ran", "threaded payload"),
        encoding="utf-8",
    )
    exe = tmp_path / ("logged.exe" if os.name == "nt" else "logged")
    assert semanticscript.main([
        "build", str(source), "--output", str(exe), "--json",
    ]) == 0
    proc = subprocess.run([str(exe)], cwd=str(tmp_path), capture_output=True,
                          text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    body = (tmp_path / "scaffold.log").read_text(encoding="utf-8")
    assert '"message":"threaded payload"' in body
    assert '"message":""' not in body
