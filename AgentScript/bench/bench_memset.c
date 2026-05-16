/* bench_memset.c — baseline native C performance benchmark for memset.
 *
 * Allocates one 64 KiB buffer and memsets it 200,000 times. The loop reads a
 * varying byte each iteration into an accumulator so the optimizer cannot
 * elide the memset calls.
 *
 * Compile with: clang -O2 -o bench_memset.exe bench_memset.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(void) {
    long long iterations = 200000LL;
    long long buffer_size = 65536LL;
    unsigned char *buffer = (unsigned char *)malloc((size_t)buffer_size);
    if (buffer == NULL) {
        return 1;
    }

    long long observation_accumulator = 0;
    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        memset(buffer, (int)(iteration & 0xff), (size_t)buffer_size);
        /* Read a varying byte so each memset has an observable effect. */
        observation_accumulator += (long long)buffer[iteration % buffer_size];
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld bufferSize=%lld accumulator=%lld clockTicks=%lld\n",
           iterations, buffer_size, observation_accumulator,
           (long long)(end_ticks - start_ticks));

    free(buffer);
    return 0;
}
