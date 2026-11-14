/* collatz.c - sum of Collatz stopping times for every start in 1..N.
 *
 * For each k the inner loop applies the Collatz map (n even -> n/2,
 * n odd -> 3n+1) until it reaches 1, counting steps. The grand total of all
 * step counts is the checksum. This is an integer, branch-heavy workload with
 * a data-dependent inner loop the optimizer cannot collapse.
 *
 * Build: clang -O2 -o collatz.c.exe collatz.c
 */

#include <stdio.h>
#include <windows.h>

int main(void) {
    long long n = 1000000;
    long long total_steps = 0;

    LARGE_INTEGER frequency;
    LARGE_INTEGER start_counter;
    LARGE_INTEGER end_counter;
    QueryPerformanceFrequency(&frequency);

    QueryPerformanceCounter(&start_counter);
    for (long long start = 1; start <= n; start++) {
        long long value = start;
        long long steps = 0;
        while (value != 1) {
            if (value % 2 == 0) {
                value = value / 2;
            } else {
                value = 3 * value + 1;
            }
            steps++;
        }
        total_steps += steps;
    }
    QueryPerformanceCounter(&end_counter);

    double elapsed_seconds =
        (double)(end_counter.QuadPart - start_counter.QuadPart) /
        (double)frequency.QuadPart;

    printf("checksum=%lld elapsedSeconds=%.6f\n", total_steps, elapsed_seconds);
    return 0;
}
