"""Windows: run a command in this process's console, wait for it to print `ready`, send CTRL+C to the console (every
process attached to it, this one included, which ignores it), and write the command's exit code and output as JSON.

    ctrlc.py RESULT.json [--twice] COMMAND ...

Run it with CREATE_NEW_CONSOLE, so the console it interrupts is its own and nothing else's (tests/interrupttour.py).
"""
import ctypes
import json
import signal
import subprocess
import sys
import time

result_path, args = sys.argv[1], sys.argv[2:]
twice = args[:1] == ["--twice"]
if twice:
    args = args[1:]
# CTRL+C on, whatever started this process turned it off (the setting is inherited), for this process and so for
# the command it starts; this process lets it pass with a handler that does nothing (not SIG_IGN, which would turn it
# off again)
ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
signal.signal(signal.SIGINT, lambda _signum, _frame: None)
proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
first = proc.stdout.readline()
time.sleep(0.5)
ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0)
if twice:
    time.sleep(0.5)
    ctypes.windll.kernel32.GenerateConsoleCtrlEvent(0, 0)
out, err = proc.communicate(timeout=60)
with open(result_path, "w", encoding="utf-8") as fh:
    json.dump({"code": proc.returncode, "stdout": (first + out).decode("utf-8", "replace"),
               "stderr": err.decode("utf-8", "replace")}, fh)
