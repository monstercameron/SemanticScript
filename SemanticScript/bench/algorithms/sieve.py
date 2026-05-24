"""sieve.py - Sieve of Eratosthenes up to LIMIT, repeated REPEATS times.

Mirrors sieve.c: same LIMIT/REPEATS, same checksum, same output contract.
Uses a bytearray (flat byte buffer) re-zeroed each repeat. Timed with
time.perf_counter().
"""

import time


def main():
    limit = 2000000
    repeats = 20
    array_size = limit + 1

    sieve = bytearray(array_size)
    total_prime_count = 0

    start = time.perf_counter()
    for _ in range(repeats):
        sieve[:] = bytes(array_size)
        prime_count = 0
        for candidate in range(2, limit + 1):
            if sieve[candidate] == 0:
                prime_count += 1
                for multiple in range(candidate * candidate, limit + 1, candidate):
                    sieve[multiple] = 1
        total_prime_count += prime_count
    end = time.perf_counter()

    elapsed_seconds = end - start
    print(f"checksum={total_prime_count} elapsedSeconds={elapsed_seconds:.6f}")


if __name__ == "__main__":
    main()
