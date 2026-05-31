"""sieve.py - Sieve of Eratosthenes up to LIMIT, repeated REPEATS times.

Same structure as the other three languages (all-prime bytearray, strike out
composites for primes up to sqrt(LIMIT), then count surviving primes), written
with Python's idiomatic bulk primitives:
  - a bytearray holds 1 for "still prime", 0 for "composite";
  - composites are struck out with one strided slice assignment per prime (a
    C-level bulk store), where C/JS/SemanticScript walk the multiples in a loop;
  - the prime count is sum() over the bytearray, a C-level pass, where the other
    three accumulate in a loop.

Same algorithm and prime count; only the in-language primitive for the
mark/count passes differs. Timed with time.perf_counter().
"""

import time
from math import isqrt


def main():
    limit = 2000000
    repeats = 40
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
