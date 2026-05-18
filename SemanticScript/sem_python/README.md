# sem_python/

This directory is reserved for future SemanticScript mirrors of the programs in
`../../python/`.

Current state: no `.sscript` mirror programs are committed here, and there is no
active `tests/python_parity.py` harness in this tree. Earlier notes about
math-only mirrors and bootstrap-general parity were experimental planning
notes, not the current repository state.

The realistic path is still the same:

1. Add hand-written `.sscript` mirrors only when the language can express the
   behavior honestly.
2. Keep the Python reference compiler and `bootstrap_general.sscript` results
   separate in the parity matrix.
3. Do not claim coverage for Python threading, asyncio, multiprocessing, or
   hashing programs until the relevant SemanticScript runtime features or C
   bindings exist.
