#!/usr/bin/env python3
"""R-251: the supply-chain effect-allowlist gate runs on a real build/run.

`verify_supply_chain` (SS2805) was only ever called from unit tests — `cmd_build`
and `cmd_run` built/ran a project without loading `build.sem.lock` or checking it
against `build.sem`'s `allowEffect`, so the control was dead code in the pipeline.
The commands now enforce it: a project whose lock `effectSurface` requests an
effect absent from `allowEffect` is rejected; a single file or a project without a
lock is a no-op.
"""
import importlib
import json
import os

import pytest

ss = importlib.import_module("semanticscript")

_BUILD_ALLOW_DB = ("Demo is project\nDemo module m\nDemo target console\nDemo entry main\n"
                   "Demo allowEffect read database\n")
_MAIN = ('m is module\nm path src.main\nm purpose "p"\nm invariant "i"\nm exports main\n'
         "ExitCode is alias\nExitCode for Int32\n"
         "main is operation\nmain out ExitCode\nmain async no\n"
         'main purpose "p"\nmain invariant "i"\nmain let okc immutable ExitCode 0\nmain return okc\n')


def _project(tmp_path, lock_surface):
    (tmp_path / "src").mkdir()
    (tmp_path / "build.sem").write_text(_BUILD_ALLOW_DB, encoding="utf-8")
    (tmp_path / "build.sem.lock").write_text(
        "Demo is project\n" + lock_surface, encoding="utf-8")
    (tmp_path / "src" / "main.sem").write_text(_MAIN, encoding="utf-8")
    return str(tmp_path)


def test_unallowed_effect_surface_is_rejected(tmp_path):
    # lock requests `write console.stdout`, build.sem only allows `read database`
    proj = _project(tmp_path, "Demo effectSurface write console.stdout\n")
    with pytest.raises(ss.EavError) as exc:
        ss._verify_supply_chain_for_path(proj)
    assert getattr(exc.value, "code", None) == "SS2805"


def test_compliant_effect_surface_passes(tmp_path):
    proj = _project(tmp_path, "Demo effectSurface read database\n")
    ss._verify_supply_chain_for_path(proj)        # no raise


def test_no_lock_is_noop(tmp_path):
    (tmp_path / "build.sem").write_text(_BUILD_ALLOW_DB, encoding="utf-8")
    ss._verify_supply_chain_for_path(str(tmp_path))   # no lock -> no raise


def test_single_file_is_noop(tmp_path):
    f = tmp_path / "p.sem"
    f.write_text(_MAIN, encoding="utf-8")
    ss._verify_supply_chain_for_path(str(f))          # not a project dir -> no raise


def test_cmd_run_enforces_gate(tmp_path, capsys):
    proj = _project(tmp_path, "Demo effectSurface write console.stdout\n")
    import argparse
    args = argparse.Namespace(path=proj, json=True, strict=False, entry=None, jit_child=False)
    # the SS2805 raise propagates to main()'s handler; here we assert cmd_run raises
    with pytest.raises(ss.EavError) as exc:
        ss.cmd_run(args)
    assert getattr(exc.value, "code", None) == "SS2805"
