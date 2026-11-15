"""A program that waits for an interrupt and says when it came (D-147), and how to interrupt it on each system.

tests/test_runtime_nolibc.py builds it with the runtime in SemanticScript and interrupts it as `refined run` is
interrupted in tests/test_tooling.py: on Linux with SIGINT; on Windows with CTRL+C, which a process can only send to
every process of its console, so `ctrlc.py` runs in a console of its own, starts the program there, and sends it.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "suite"))

import caselib  # noqa: E402
import sembuild as sb  # noqa: E402
from caselib import allows_rows  # noqa: E402


def write_project(d: str) -> None:
    """Print `ready`, wait up to ten seconds for an interrupt, and print `interrupted` when it comes (exit 0) or
    exit 1 when it does not."""
    p = sb.Prog("interrupts", "Wait for an interrupt and report it",
                imports=["standard.console", "standard.signal", "standard.time"])
    p.add(sb.STDOUT_CAP).add(sb.show_text())
    p.add('interruptReader is capability\ninterruptReader purpose "Authority to observe interrupts"\n'
          "interruptReader grants read signal.interrupts none")
    p.add(sb.op("main", "Print ready, wait for an interrupt, and say it came",
                [("begin", "do printReady"), ("begin", "do makeDeadline"), ("begin", "start waitIt into none"),
                 ("begin", "join waitIt"), ("begin", "branch ifError waitIt goto failed else goto got"),
                 ("got", "do printGot"), ("got", "return ok okCode"), ("failed", "return ok failCode")],
                output="ExitCode", effects=("read signal.interrupts", "write console.stdout"),
                uses=("interruptReader", "stdoutWriter"), waits=True,
                lets=('ready String "ready" immutable', 'gotText String "interrupted" immutable',
                      "tenSeconds Int64 10000 immutable", "okCode ExitCode 0 immutable",
                      "failCode ExitCode 1 immutable")))
    p.add(sb.printer("main", "printReady", "String", "ready"))
    p.add(sb.printer("main", "printGot", "String", "gotText"))
    p.add(sb.call("makeDeadline", "main", "time.Deadline.after", ("milliseconds Int64 tenSeconds copy",),
                  out="deadline time.Deadline"))
    p.add(sb.call("waitIt", "main", "signal.waitForInterrupt", ("deadline time.Deadline deadline copy",),
                  catch="waitError signal.SignalError", kind="task"))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "build.sem"), "w", encoding="utf-8") as fh:
        fh.write('interruptsProject is project\ninterruptsProject purpose "Wait for an interrupt"\n'
                 'interruptsProject target console\ninterruptsProject version "0.1.0"\n'
                 "interruptsProject language refined 1\ninterruptsProject standardLibrary 1\n"
                 + "\n".join(allows_rows("interruptsProject", [p.render()])) + "\n"
                 "interruptsProject requires none\ninterruptsProject includesModule interrupts\n"
                 "interruptsProject entry interrupts.main\n")
    caselib.approve(d)
    with open(os.path.join(d, "interrupts.sem"), "w", encoding="utf-8") as fh:
        fh.write(p.render())
