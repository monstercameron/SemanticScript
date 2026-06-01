import os
import subprocess
from pathlib import Path

import semanticscript


class _FakeModule:
    triple = "x86_64-test-target"

    def __str__(self):
        return "; fake llvm module\n"


def test_native_build_reuses_cached_runtime_objects_and_invalidates(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    include = runtime / "include"
    include.mkdir(parents=True)
    (runtime / "manifest.json").write_text('{"schema": 2, "libraries": []}\n', encoding="utf-8")
    (runtime / "shim.c").write_text(
        '#include "shim.h"\nint ss_demo_value(void) { return SEM_VALUE; }\n',
        encoding="utf-8",
    )
    header = include / "shim.h"
    header.write_text("#define SEM_VALUE 1\n", encoding="utf-8")

    cache = tmp_path / "cache"
    lib = {
        "name": "ss_demo",
        "provides": ["ss_demo_"],
        "sources": ["shim.c"],
        "include": ["include"],
        "defines": ["SEM_DEMO"],
        "libs": [],
    }
    compiler_id = {"value": "fakecc|v1"}
    compile_cmds = []
    link_cmds = []
    created_objects = []

    monkeypatch.setattr(semanticscript, "_runtime_dir", lambda: str(runtime))
    monkeypatch.setattr(semanticscript, "_runtime_cache_dir", lambda create=True: str(cache))
    monkeypatch.setattr(semanticscript, "_find_c_compiler", lambda: ["fakecc"])
    monkeypatch.setattr(semanticscript, "_compiler_identity", lambda cc: compiler_id["value"])
    monkeypatch.setattr(semanticscript, "_runtime_libs_for", lambda program: [lib])
    monkeypatch.setattr(semanticscript, "lower_to_llvm", lambda program, platform=None: _FakeModule())
    monkeypatch.setattr(semanticscript, "_entry_name", lambda program: "main")

    def fake_run(cmd, capture_output, text, timeout):
        out = Path(cmd[cmd.index("-o") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        if "-c" in cmd:
            compile_cmds.append(list(cmd))
            created_objects.append(str(out))
            out.write_bytes(f"object-{len(compile_cmds)}".encode("ascii"))
        else:
            link_cmds.append(list(cmd))
            out.write_bytes(b"exe")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    out1 = tmp_path / "one.exe"
    semanticscript.build_executable(object(), str(out1))
    assert out1.exists()
    assert len(compile_cmds) == 1
    assert len(link_cmds) == 1
    first_object = created_objects[-1].removesuffix(f".tmp{os.getpid()}")
    assert first_object in link_cmds[-1]
    assert str(runtime / "shim.c") in compile_cmds[-1]
    assert str(runtime / "shim.c") not in link_cmds[-1]

    out2 = tmp_path / "two.exe"
    semanticscript.build_executable(object(), str(out2))
    assert out2.exists()
    assert len(compile_cmds) == 1
    assert len(link_cmds) == 2
    assert first_object in link_cmds[-1]

    header.write_text("#define SEM_VALUE 2\n", encoding="utf-8")
    semanticscript.build_executable(object(), str(tmp_path / "three.exe"))
    assert len(compile_cmds) == 2
    header_invalidated_object = created_objects[-1].removesuffix(f".tmp{os.getpid()}")
    assert header_invalidated_object != first_object
    assert header_invalidated_object in link_cmds[-1]

    compiler_id["value"] = "fakecc|v2"
    semanticscript.build_executable(object(), str(tmp_path / "four.exe"))
    assert len(compile_cmds) == 3
    compiler_invalidated_object = created_objects[-1].removesuffix(f".tmp{os.getpid()}")
    assert compiler_invalidated_object not in {first_object, header_invalidated_object}
    assert compiler_invalidated_object in link_cmds[-1]
    assert any("--target=x86_64-test-target" in cmd for cmd in compile_cmds)
