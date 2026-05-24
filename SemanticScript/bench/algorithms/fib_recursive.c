/* fib_recursive.c - naive recursive Fibonacci.
 *
 * Measures function-call / recursion overhead: fib(n) makes ~2*fib(n+1)
 * calls and does almost no arithmetic per call, so the cost is dominated by
 * call/return and branch prediction rather than the body.
 *
 * Timing uses QueryPerformanceCounter for sub-microsecond resolution so the
 * compute region is measured precisely regardless of how fast it runs.
 *
 * Build: clang -O2 -o fib_recursive.c.exe fib_recursive.c
 */

#include <stdio.h>
#include <windows.h>

static long long fib(long long n) {
    if (n < 2) {
        return n;
    }
    return fib(n - 1) + fib(n - 2);
}

int main(void) {
    long long n = 38;

    LARGE_INTEGER frequency;
    LARGE_INTEGER start_counter;
    LARGE_INTEGER end_counter;
    QueryPerformanceFrequency(&frequency);

    QueryPerformanceCounter(&start_counter);
    long long checksum = fib(n);
    QueryPerformanceCounter(&end_counter);

    double elapsed_seconds =
        (double)(end_counter.QuadPart - start_counter.QuadPart) /
        (double)frequency.QuadPart;

    printf("checksum=%lld elapsedSeconds=%.6f\n", checksum, elapsed_seconds);
    return 0;
}
