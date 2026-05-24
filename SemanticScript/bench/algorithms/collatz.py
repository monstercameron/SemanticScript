"""collatz.py - sum of Collatz stopping times for every start in 1..N.

Mirrors collatz.c: same N, same checksum, same output contract.
Timed with time.perf_counter().
"""

import time


def main():
    n = 600000
    total_steps = 0

    start = time.perf_counter()
    for k in range(1, n + 1):
        value = k
        steps = 0
        while value != 1:
            if value % 2 == 0:
                value = value // 2
            else:
                value = 3 * value + 1
            steps += 1
        total_steps += steps
    end = time.perf_counter()

    elapsed_seconds = end - start
    print(f"checksum={total_steps} elapsedSeconds={elapsed_seconds:.6f}")


if __name__ == "__main__":
    main()
