# Python Standard Library Examples

Standard-library-only Python examples for benchmarking against SemanticScript.
This top-level folder is a 1.0 compatibility mirror of `samples/python/`.

## Contents

This folder contains standalone Python programs covering threading, asyncio,
multiprocessing, scheduling, race-condition demonstrations, watchdog logic, and
Python `math` API coverage.

## Current Status

Reference examples only. These scripts are not SemanticScript runtime code. For
new Python comparison samples, prefer `samples/python/`; keep this mirror aligned
when existing mirrored files change.

Run everything:

```text
python run_all.py
```

Scripts:

- `threaded_pipeline.py`: queue-based threaded pipeline with retries and metrics
- `bank_transfer_deadlock_avoidance.py`: ordered locking and invariant-preserving transfers
- `reader_writer_cache.py`: custom reader/writer lock around a shared cache
- `barrier_condition_phases.py`: condition start gate plus barrier-synchronized phases
- `asyncio_timeout_orchestrator.py`: async semaphore, timeouts, retries, and sorted results
- `process_pool_checksums.py`: process pool checksum work using `concurrent.futures`
- `hybrid_thread_process_orchestrator.py`: parser threads, process pool scoring, future aggregation
- `async_thread_bridge.py`: asyncio queues bridged to blocking thread-pool work
- `priority_scheduler_cancellation.py`: priority queue scheduling with retry and cancellation plumbing
- `watchdog_supervisor.py`: heartbeat monitoring and stalled-worker detection
- `race_condition_showcase.py`: deterministic lost-update race and lock-based fix
- `math_api_integer_combinatorics.py`: rounding, integer, combinatorics, GCD/LCM, integer square root, product
- `math_api_float_classification.py`: float decomposition, signs, finiteness, NaN/inf, next representable value, ULP
- `math_api_exponents_logs.py`: exponentials, logarithms, powers, roots, and Euler's constant
- `math_api_trig_hyperbolic.py`: constants, angle conversion, circular trig, inverse trig, and hyperbolic functions
- `math_api_vectors_precision.py`: exact-ish summation, vector distance, and multi-dimensional hypotenuse
- `math_api_special_functions.py`: error functions, gamma, and log-gamma
- `math_api_coverage_check.py`: verifies all public `math` APIs in the local Python runtime are covered
