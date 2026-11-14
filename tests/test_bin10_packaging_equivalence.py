#!/usr/bin/env python3
"""BIN-10: packaging behavioral equivalence (frozen exe ≡ source).

A packaged (PyInstaller-frozen) `semanticscript` must behave identically to running
from a source checkout. The behavioral equivalence rests on two invariants:

  1. Resource resolution is frozen-aware and layout-identical. The bundled
     runtime/sigs/std/docs are found the same way in both modes — frozen builds
     preserve the repo layout under _MEIPASS/semanticscript, so manifest-relative
     paths and the relative #includes in the runtime C sources resolve the same.
  2. Child self-invocation differs correctly: a frozen exe re-invokes itself via
     sys.executable; a source run re-invokes python on this file.

If either drifts, a frozen build would fail to find its runtime/signatures or
mis-spawn its compile/run children while source works — the classic packaging
divergence. These tests pin both without needing to actually build the exe.
"""
import importlib
import os
import sys

semanticscript = importlib.import_module("semanticscript")


def test_bin10_source_bundle_carries_all_runtime_resources():
    # The frozen bundle mirrors this layout, so verifying it here proves the
    # packaged exe has the same resources to resolve.
    bundle = semanticscript._bundle_dir()
    assert os.path.basename(bundle) == "semanticscript"
    assert os.path.exists(os.path.join(semanticscript._runtime_dir(), "manifest.json"))
    assert any(f.endswith(".semsig") for f in os.listdir(semanticscript._sigs_dir()))


def test_bin10_resource_resolvers_are_frozen_aware(tmp_path, monkeypatch):
    # Simulate a frozen extraction: _MEIPASS/semanticscript/{runtime,sigs}.
    pkg = tmp_path / "semanticscript"
    (pkg / "runtime").mkdir(parents=True)
    (pkg / "sigs").mkdir(parents=True)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert semanticscript._bundle_dir() == str(pkg)
    assert semanticscript._runtime_dir() == str(pkg / "runtime")
    assert semanticscript._sigs_dir() == str(pkg / "sigs")

    # Without _MEIPASS (source mode) the resolvers fall back to the checkout, and
    # crucially the RELATIVE layout (bundle -> runtime/sigs) is identical to frozen.
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    src_bundle = semanticscript._bundle_dir()
    assert semanticscript._runtime_dir() == os.path.join(src_bundle, "runtime")
    assert semanticscript._sigs_dir() == os.path.join(src_bundle, "sigs")


def test_bin10_child_self_invocation_frozen_vs_source(monkeypatch):
    # Source mode: re-invoke python on this module file.
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    src_argv = semanticscript._self_cli_argv()
    assert src_argv[0] == sys.executable and len(src_argv) == 2
    assert src_argv[1].endswith("semanticscript.py")

    # Frozen mode: the packaged exe IS the interpreter — re-invoke it directly.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen_argv = semanticscript._self_cli_argv()
    assert frozen_argv == [sys.executable]
