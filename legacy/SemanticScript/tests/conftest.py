"""Pytest process hygiene for SemanticScript tests."""

from __future__ import annotations

import os
import subprocess
from typing import Iterator

import pytest


_ORIGINAL_POPEN = subprocess.Popen


def _terminate_process_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        killer = _ORIGINAL_POPEN(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            killer.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(autouse=True)
def cleanup_subprocesses(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Prevent timed-out tests from leaving compiler/app child processes alive.

    Most tests use ``subprocess.run``, which already kills its direct child on a
    timeout. Full-suite interruptions can still strand direct ``Popen`` children
    or, on Windows, process trees below a direct child. Tracking Popen per test
    gives every pytest test a final cleanup pass without changing command
    semantics during normal execution.
    """
    started: list[subprocess.Popen] = []

    def tracked_popen(*args, **kwargs):
        process = _ORIGINAL_POPEN(*args, **kwargs)
        started.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", tracked_popen)
    try:
        yield
    finally:
        for process in reversed(started):
            _terminate_process_tree(process)
