"""sieve.py - Sieve of Eratosthenes up to LIMIT, repeated REPEATS times.

Mirrors sieve.c's algorithm and checksum, written in idiomatic fast Python:
  - a bytearray holds 1 for "still prime", 0 for "composite";
  - composites are struck out with a single strided slice assignment per prime
    (a C-level bulk store) instead of a Python-level inner loop;
  - the outer loop only runs to sqrt(LIMIT), since every composite has a prime
    factor at or below its square root;
  - the prime count is sum() over the bytearray, another C-level pass.

This is the form a competent Python developer writes for speed. The task and
the resulting prime count are identical to the other three languages; only the
in-language mechanics differ. Timed with time.perf_counter().
"""

import time
from math import isqrt


def main():
    limit = 2000000
    repeats = 20
    array_size = limit + 1
    sqrt_limit = isqrt(limit)
    total_prime_count = 0

    start = time.perf_counter()
    for _ in range(repeats):
        sieve = bytearray([1]) * array_size
        sieve[0:2] = b"\x00\x00"
        for candidate in range(2, sqrt_limit + 1):
            if sieve[candidate]:
                first_composite = candidate * candidate
                composite_count = (limit - first_composite) // candidate + 1
                sieve[first_composite::candidate] = b"\x00" * composite_count
        prime_count = sum(sieve)
        total_prime_count += prime_count
    end = time.perf_counter()

    elapsed_seconds = end - start
    print(f"checksum={total_prime_count} elapsedSeconds={elapsed_seconds:.6f}")


if __name__ == "__main__":
    main()
