"""collatz.py - sum of Collatz stopping times for every start in 1..N.

Mirrors collatz.c's algorithm and checksum. Uses bitwise parity/halving
(`value & 1`, `value >> 1`), which is correct for Python's arbitrary-precision
ints and faster than `% 2` / `// 2`. (The JavaScript port cannot do this: its
bitwise operators are 32-bit and Collatz peaks exceed 2^31.) Timed with
time.perf_counter().
"""

import time


def main():
    n = 1000000
    total_steps = 0

    start = time.perf_counter()
    for k in range(1, n + 1):
        value = k
        steps = 0
        while value != 1:
            if value & 1:
                value = 3 * value + 1
            else:
                value >>= 1
            steps += 1
        total_steps += steps
    end = time.perf_counter()

    elapsed_seconds = end - start
    print(f"checksum={total_steps} elapsedSeconds={elapsed_seconds:.6f}")


if __name__ == "__main__":
    main()
