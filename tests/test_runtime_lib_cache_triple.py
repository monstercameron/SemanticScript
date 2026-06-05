#!/usr/bin/env python3
"""R-253: the JIT shared-runtime-lib cache key folds in the target triple.

The shared runtime DLL is compiled `--target=<jit triple>` and loaded into the
JIT process, but the cache path was keyed only by platform + compiler identity +
sources — not the triple (the sibling object cache already keyed on it). A cache
dir shared across ABIs (e.g. an x86_64-emulated JIT vs a native ARM64 default)
could therefore serve a wrong-arch DLL at the same path. The triple is now part
of the key.
"""
import importlib
import json
import os

ss = importlib.import_module("semanticscript")

_LIB = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                   "semanticscript", "runtime", "manifest.json")))["libraries"][0]
_CID = "clang|v1"


def test_distinct_triples_distinct_paths():
    x64 = ss._runtime_lib_cache_path(_LIB, None, _CID, "x86_64-pc-windows-msvc")
    arm = ss._runtime_lib_cache_path(_LIB, None, _CID, "aarch64-pc-windows-msvc")
    assert x64 != arm
    assert os.path.basename(x64) != os.path.basename(arm)


def test_same_triple_same_path():
    a = ss._runtime_lib_cache_path(_LIB, None, _CID, "x86_64-pc-windows-msvc")
    b = ss._runtime_lib_cache_path(_LIB, None, _CID, "x86_64-pc-windows-msvc")
    assert a == b


def test_triple_changes_the_key_vs_default():
    default = ss._runtime_lib_cache_path(_LIB, None, _CID)
    explicit = ss._runtime_lib_cache_path(_LIB, None, _CID, "aarch64-unknown-linux-gnu")
    assert default != explicit
