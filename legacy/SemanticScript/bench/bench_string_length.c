/* bench_string_length.c — native C baseline for the stdlib string-length op.
 *
 * Mirrors SemanticScript's standard.string.stringByteLength: walk a
 * NUL-terminated buffer and count bytes. NOTE: at -O2 both sides lower to a
 * `tail call @strlen` (LLVM's loop-idiom pass rewrites the SemanticScript
 * scalar scan, and the C side calls strlen directly), so this case measures
 * call/inline/profile parity, not the stdlib's hand-written scan. See
 * bench/README.md for the idiom-defeat follow-up that exercises real codegen.
 *
 * Each iteration writes one printable byte (never NUL) at offset 0 before the
 * length scan so the optimizer cannot prove the buffer is loop-invariant and
 * hoist the strlen out of the loop. The written byte is always in 32..126, so
 * the string length is constant every iteration and both sides do identical
 * work.
 *
 * Compile with: clang -O2 -o bench_string_length.c.exe bench_string_length.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(void) {
    long long iterations = 300000000LL;
    /* 31 visible bytes + NUL == 32 bytes. */
    const char *seed = "abcdefghijklmnopqrstuvwxyz01234";
    char *buffer = (char *)malloc(64);
    if (buffer == NULL) {
        return 1;
    }
    memcpy(buffer, seed, 32);

    long long observation_accumulator = 0;
    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        /* Printable byte 32..126, never NUL, so length stays constant. */
        buffer[0] = (char)((iteration % 95) + 32);
        observation_accumulator += (long long)strlen(buffer);
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld accumulator=%lld clockTicks=%lld\n",
           iterations, observation_accumulator,
           (long long)(end_ticks - start_ticks));

    free(buffer);
    return 0;
}
