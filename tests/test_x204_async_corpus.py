#!/usr/bin/env python3
"""X-204: end-to-end coverage for the async / task-lifecycle corpus.

Each async example is a self-asserting `tag test` program (prints `PASS …` and
exits 0). This runs every shipped async example through the real `run` lane and
asserts it reaches its golden value — the §X1c e2e contract for the async area
(start/join, fanout, event-loop poll, timeout/timer, channel, interval). The
negative cases (start-in-sync-op, single-thread determinism) are covered by the
existing async tests in test_semanticscript.py.
"""
import importlib
import os
import subprocess
import sys

import pytest

semanticscript = importlib.import_module("semanticscript")
SEMANTICSCRIPT = semanticscript.__file__
EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")

# example -> the golden value its self-assertion reaches
_ASYNC = {
    "async_start_join": "42",     # asyncStartJoin: start + join
    "async_fanout": "60",         # asyncFanoutTwo/Many: 10+20+30
    "async_event_loop": "42",     # asyncPollReady: await(delay(0,42))
    "async_timeout": "42",        # asyncTimeoutTimer: fast work under timeout
    "async_channel": "20",        # channel: earliest producer value
    "async_demo": "42",           # basic async demo
    "async_interval": "1",        # interval: first tick count
}


@pytest.mark.parametrize("name,expected", sorted(_ASYNC.items()))
def test_async_example_runs_to_golden(name, expected):
    path = os.path.join(EXAMPLES, name + ".sem")
    assert os.path.isfile(path), path
    proc = subprocess.run([sys.executable, SEMANTICSCRIPT, "run", path],
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout, proc.stdout       # self-assertion passed
    assert "FAIL" not in proc.stdout
    assert expected in proc.stdout                  # reached its golden value


def test_async_area_has_at_least_seven_runnable_examples():
    present = [n for n in _ASYNC if os.path.isfile(os.path.join(EXAMPLES, n + ".sem"))]
    assert len(present) >= 7, present
