/* bench_arith.c — pure-codegen benchmark with a data-dependency chain that
 * resists closed-form folding. Each iteration's b depends on the previous
 * a+b, so the loop must actually execute. Measures the compiler's own
 * codegen quality with no libc calls inside the inner loop.
 *
 * Compile with: clang -O2 -o bench_arith.exe bench_arith.c
 */

#include <stdio.h>
#include <time.h>

int main(void) {
    long long iterations = 200000000LL;
    long long a = 1;
    long long b = 1;

    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        long long next = a + b;
        a = b;
        b = next;
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld accumulator=%lld clockTicks=%lld\n",
           iterations, b,
           (long long)(end_ticks - start_ticks));
    return 0;
}
