#!/usr/bin/env python3
"""R-206: list/map handles are tombstoned against use-after-release.

`list.release`/`map.release` retain the header and poison its capacity slot to a
negative sentinel (idempotent: a double release is a no-op, no double-free); every
consumer op guards on that sentinel via `_guard_collection_live` and raises a
structured `ss_panic` (SSR0023) instead of dereferencing the freed data buffer.

Source-level guard (the normal create/append/get/length/release round-trip is
exercised end-to-end by examples/collections_list*.sem and collections_map.sem via
run_examples; a use-after-release fixture would terminate the in-process JIT via
ss_panic, so the runtime trap is left to the example harness / manual repro).
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "semanticscript", "compiler", "semanticscript.py")


def _src():
    return open(SRC, encoding="utf-8").read()


def test_use_after_release_trap_code_registered():
    src = _src()
    assert '"SSR0023"' in src and "use-after-release" in src
    assert "_guard_collection_live" in src


def test_consumer_ops_guard_liveness():
    # Every op that dereferences a list/map handle must guard it first.
    src = _src()
    for op in ("list.length", "list.append", "list.get",
               "map.size", "map.get", "map.put"):
        # the op's lowering branch must call the live-guard with that op name
        assert f'_guard_collection_live(builder, h, "{op}"' in src, op


def test_release_is_idempotent_and_tombstoning():
    # release must NOT unconditionally free the header; it branches on the poison
    # sentinel (idempotent) and stores -1 into the capacity slot to mark dead.
    src = _src()
    for fn in ("list.release", "map.release"):
        m = re.search(re.escape(f'target == "{fn}"') + r".*?result = ir\.Constant",
                      src, re.S)
        assert m, fn
        body = m.group(0)
        assert "icmp_signed(\"<\", cap, ir.Constant(i64, 0))" in body, fn  # poison check
        assert "ir.Constant(i64, -1)" in body, fn                          # poison store
        assert "ReleaseDo" in body and "ReleaseDone" in body, fn           # idempotent branch
