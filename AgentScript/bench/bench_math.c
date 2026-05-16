/* bench_math.c — sqrt + log + sin loop. The iteration variable converts to
 * double inside the loop so the optimizer cannot pre-compute the sum.
 *
 * Compile with: clang -O2 -o bench_math.exe bench_math.c
 */

#include <stdio.h>
#include <math.h>
#include <time.h>

int main(void) {
    long long iterations = 5000000LL;
    double accumulator = 0.0;

    clock_t start_ticks = clock();
    for (long long iteration = 1; iteration <= iterations; iteration++) {
        double value = (double)iteration;
        accumulator += sqrt(value) + log(value) + sin(value);
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld accumulator=%.6f clockTicks=%lld\n",
           iterations, accumulator,
           (long long)(end_ticks - start_ticks));
    return 0;
}
