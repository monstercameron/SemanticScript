#!/usr/bin/env python3
"""W2 scale guards for project-root agent inspection surfaces."""
import importlib
import json
import os

import pytest

ss = importlib.import_module("semanticscript")


def _payload(capsys):
    return json.loads(capsys.readouterr().out)


def _write_scale_project(root, modules=24):
    src = root / "src"
    src.mkdir(parents=True)
    build_rows = [
        "ScaleProj is project",
        *[f"ScaleProj module mod{i}" for i in range(modules)],
        "ScaleProj target console",
        "ScaleProj entry main",
        "",
    ]
    (root / "build.sem").write_text("\n".join(build_rows), encoding="utf-8")

    for i in range(modules):
        rows = [
            f"mod{i} is module",
            f"mod{i} path src.m{i}",
        ]
        if i + 1 < modules:
            rows.append(f"mod{i} imports mod{i + 1} src.m{i + 1}")
        rows.extend([
            "mod0 exports main" if i == 0 else f"mod{i} exports op{i}",
            f'mod{i} purpose "scale module {i}"',
            f'mod{i} invariant "scale module {i} is parseable"',
            "",
        ])
        if i == 0:
            rows.extend([
                "ExitCode is alias",
                "ExitCode for Int32",
                "",
                "stdoutWriter is capability",
                "stdoutWriter grants write console.stdout",
                "",
                "main is operation",
                "main out ExitCode",
                "main effect write console.stdout",
                "main uses stdoutWriter",
                "main async no",
                'main purpose "entry point for a 24-module scale project"',
                'main invariant "returns zero after walking the helper chain"',
                "main let seed immutable Int64 0",
                "main let okCode immutable ExitCode 0",
                "main do call1",
                "main do printTotal",
                "main return okCode",
                "call1 is call",
                "call1 in main",
                "call1 invokes mod1.op1",
                "call1 arg n Int64 seed",
                "call1 out total Int64",
                "printTotal is call",
                "printTotal in main",
                "printTotal invokes console.writeIntegerLine",
                "printTotal arg value Int64 total",
            ])
        else:
            rows.extend([
                f"op{i} is operation",
                f"op{i} in n Int64",
                f"op{i} out Int64",
                f"op{i} async no",
                f'op{i} purpose "add one at module {i}"',
                f'op{i} invariant "returns the incremented chain value"',
                f"op{i} let one{i} immutable Int64 1",
                f"op{i} do add{i}",
            ])
            if i + 1 < modules:
                rows.extend([
                    f"op{i} do next{i}",
                    f"op{i} return nextValue{i}",
                ])
            else:
                rows.append(f"op{i} return local{i}")
            rows.extend([
                f"add{i} is call",
                f"add{i} in op{i}",
                f"add{i} invokes math.addInt64",
                f"add{i} arg left Int64 n",
                f"add{i} arg right Int64 one{i}",
                f"add{i} out local{i}",
            ])
            if i + 1 < modules:
                rows.extend([
                    f"next{i} is call",
                    f"next{i} in op{i}",
                    f"next{i} invokes mod{i + 1}.op{i + 1}",
                    f"next{i} arg n Int64 local{i}",
                    f"next{i} out nextValue{i}",
                ])
        (src / f"m{i}.sem").write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_w24_twenty_four_module_project_inspection_surfaces(tmp_path, capsys):
    project = tmp_path / "scale"
    _write_scale_project(project)

    assert ss.main(["check", str(project), "--json"]) == 0
    check = _payload(capsys)
    assert check["surface"] == "sem.check.v1"
    assert check["errorCount"] == 0

    assert ss.main(["context", str(project), "--json"]) == 0
    context = _payload(capsys)
    assert context["surface"] == "sem.context.v1"
    assert len(context["modules"]) == 24

    assert ss.main(["deps", str(project), "--json"]) == 0
    deps = _payload(capsys)
    assert deps["surface"] == "sem.deps.v1"
    assert len(deps["imports"]) == 23

    assert ss.main(["graph", str(project), "--kind", "calls", "--json"]) == 0
    graph = _payload(capsys)
    assert graph["surface"] == "sem.graph.v1"
    assert len(graph["edges"]) >= 24
    assert {"from": "main", "to": "mod1.op1"} in graph["edges"]

    assert ss.main(["slice", str(project), "main", "--json"]) == 0
    sliced = _payload(capsys)
    assert sliced["surface"] == "sem.slice.v1"
    assert "call1 invokes mod1.op1" in sliced["slice"]

    assert ss.main(["index", "--json"]) == 0
    index = _payload(capsys)
    assert index["surface"] == "sem.codeIndex.v1"
    assert index["count"] >= 20

    if ss._find_c_compiler() is None:
        pytest.skip("no C compiler available for native scale build")
    out = project / ("scale.exe" if os.name == "nt" else "scale")
    assert ss.main(["build", str(project), "--output", str(out), "--json"]) == 0
    built = _payload(capsys)
    assert built["surface"] == "sem.build.v1"
    assert built["status"] == "ok"
    assert os.path.exists(built["output"])
