import subprocess
import sys
from pathlib import Path


# Runs every finite Python benchmark script in this folder.
SCRIPT_ORDER = [
    "threaded_pipeline.py",
    "bank_transfer_deadlock_avoidance.py",
    "reader_writer_cache.py",
    "barrier_condition_phases.py",
    "asyncio_timeout_orchestrator.py",
    "process_pool_checksums.py",
    "hybrid_thread_process_orchestrator.py",
    "async_thread_bridge.py",
    "priority_scheduler_cancellation.py",
    "watchdog_supervisor.py",
    "race_condition_showcase.py",
    "math_api_integer_combinatorics.py",
    "math_api_float_classification.py",
    "math_api_exponents_logs.py",
    "math_api_trig_hyperbolic.py",
    "math_api_vectors_precision.py",
    "math_api_special_functions.py",
    "math_api_coverage_check.py",
]


def run_script(script_path):
    print("")
    print(">>> python {}".format(script_path.name))

    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(script_path.parent),
        text=True,
        capture_output=True,
        check=False,
    )

    if completed.stdout:
        print(completed.stdout, end="")

    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    if completed.returncode != 0:
        raise RuntimeError("{} exited with {}".format(script_path.name, completed.returncode))


def main():
    script_directory = Path(__file__).resolve().parent

    for script_name in SCRIPT_ORDER:
        run_script(script_directory / script_name)


if __name__ == "__main__":
    main()
