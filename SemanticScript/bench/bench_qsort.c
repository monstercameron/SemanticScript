/* bench_qsort.c — qsort N integers, repeated K times to amortize startup.
 * The qsort callback is a real function pointer so the compiler cannot
 * fold the sort. Resets the array between sorts so each sort does real work.
 *
 * Compile with: clang -O2 -o bench_qsort.exe bench_qsort.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int compare_ints(const void *a, const void *b) {
    int left = *(const int *)a;
    int right = *(const int *)b;
    if (left < right) return -1;
    if (left > right) return 1;
    return 0;
}

int main(void) {
    long long array_length = 4096LL;
    long long iterations = 2000LL;

    int *workspace = (int *)malloc(array_length * sizeof(int));
    int *scratch = (int *)malloc(array_length * sizeof(int));
    if (!workspace || !scratch) return 1;

    /* Initialize with a pseudo-random pattern (LCG). */
    unsigned int seed = 2463534242u;
    for (long long i = 0; i < array_length; i++) {
        seed = seed * 1664525u + 1013904223u;
        workspace[i] = (int)seed;
    }

    long long accumulator = 0;
    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        memcpy(scratch, workspace, array_length * sizeof(int));
        qsort(scratch, (size_t)array_length, sizeof(int), compare_ints);
        accumulator += scratch[array_length - 1];
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld arrayLength=%lld accumulator=%lld clockTicks=%lld\n",
           iterations, array_length, accumulator,
           (long long)(end_ticks - start_ticks));

    free(workspace);
    free(scratch);
    return 0;
}
