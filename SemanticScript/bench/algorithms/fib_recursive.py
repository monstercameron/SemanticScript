"""fib_recursive.py - naive recursive Fibonacci.

Mirrors fib_recursive.c: same n, same checksum, same output contract.
Timed with time.perf_counter() (high-resolution monotonic clock).
"""

import sys
import time


def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)


def main():
    sys.setrecursionlimit(100000)
    n = 38
    start = time.perf_counter()
    checksum = fib(n)
    end = time.perf_counter()
    elapsed_seconds = end - start
    print(f"checksum={checksum} elapsedSeconds={elapsed_seconds:.6f}")


if __name__ == "__main__":
    main()
