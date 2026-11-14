'use strict';

// Force process.stdout into blocking (synchronous) mode so the listen-banner
// in long-running benchmarks flushes immediately, even when the parent
// harness terminates the Node process before it would normally drain its
// async write queue. Loaded via `node -r` from compare.py.
if (process.stdout._handle && typeof process.stdout._handle.setBlocking === 'function') {
    process.stdout._handle.setBlocking(true);
}
