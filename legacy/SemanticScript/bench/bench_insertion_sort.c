/* bench_insertion_sort.c — native C baseline for stdlib in-place sort codegen.
 *
 * Mirrors standard.sort.sortBytesWithInsertionSortInPlace exactly: an in-place
 * insertion sort over a byte buffer, comparing unsigned byte values, shifting
 * greater elements right and inserting the key. This stresses a different part
 * of codegen than the scan benchmarks: data-dependent branches, in-place
 * mutable stores, and a doubly-nested loop. There is no libc idiom for it
 * (qsort takes a function-pointer comparator and is a different algorithm), so
 * LLVM cannot rewrite it into a library call on either side.
 *
 * Each outer iteration refills the buffer with a descending run rotated by the
 * iteration counter: buf[j] = (n-1-j+iteration) % 256. Descending input is
 * near the O(n^2) worst case (maximal shifts), the rotation makes the contents
 * depend on the iteration so the sorted result varies and cannot be hoisted,
 * and buf[0] (the minimum) is accumulated so the sort's effect is observed.
 *
 * Compile with: clang -O2 -o bench_insertion_sort.c.exe bench_insertion_sort.c
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

int main(void) {
    long long iterations = 3000000LL;
    long long n = 64;
    unsigned char *buffer = (unsigned char *)malloc(64);
    if (buffer == NULL) {
        return 1;
    }

    /* Signed accumulation to match the SemanticScript side: its
     * pointer.loadByte sign-extends the observed byte (i8 -> i64), so buf[0]
     * is read as a signed value there; mirror that here so both binaries print
     * the same accumulator. The sort itself compares UNSIGNED bytes on both
     * sides (unsigned char buffer here; (b+256)%256 normalize there). */
    int64_t observation_accumulator = 0;
    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        for (long long j = 0; j < n; j++) {
            buffer[j] = (unsigned char)((n - 1 - j + iteration) % 256);
        }
        /* insertion sort, mirroring the stdlib op */
        for (long long outer = 1; outer < n; outer++) {
            unsigned char key = buffer[outer];
            long long inner = outer - 1;
            while (inner >= 0 && buffer[inner] > key) {
                buffer[inner + 1] = buffer[inner];
                inner--;
            }
            buffer[inner + 1] = key;
        }
        observation_accumulator += (int64_t)(signed char)buffer[0];
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld accumulator=%llu clockTicks=%lld\n",
           iterations, (unsigned long long)observation_accumulator,
           (long long)(end_ticks - start_ticks));

    free(buffer);
    return 0;
}
