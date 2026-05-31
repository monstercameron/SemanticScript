/* bench_byte_hash.c — native C baseline for stdlib SCALAR codegen.
 *
 * Mirrors standard.memory.hashMemoryBytesWithFnv1a exactly: a per-byte fold
 * with a carried multiply dependency (hash = (hash + u*256 + u) * prime). This
 * is the benchmark that actually exercises the SemanticScript stdlib's
 * hand-written scalar loop, because:
 *   - there is NO libc idiom for an FNV-style fold, so LLVM cannot rewrite it
 *     into a library call the way it rewrites a NUL scan into @strlen, and
 *   - the carried `hash = hash * prime` dependency blocks vectorization, so
 *     both sides run the same scalar loop instruction-for-instruction.
 *
 * Constants match SemanticScript/std/memory/main.sem:
 *   fnvOneAOffsetBasis  = -3750763034362895579 (i64) = 14695981039346656037 (u64)
 *   fnvOneAPrime        = 1099511628211
 *   byteRoleAdjustmentValue = 256
 * Arithmetic is done in uint64_t for well-defined two's-complement wraparound
 * (the SemanticScript side uses wrapping Int64), so results are bit-identical.
 *
 * Each outer iteration writes a printable byte (32..126) at offset 0 before
 * hashing. Because byte[0] is folded first, the entire hash depends on it, so
 * the result varies every iteration and cannot be hoisted or constant-folded.
 *
 * Compile with: clang -O2 -o bench_byte_hash.c.exe bench_byte_hash.c
 */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(void) {
    long long iterations = 50000000LL;
    /* 31 visible bytes + NUL == 32 bytes; only the first 31 are hashed. */
    const char *seed = "abcdefghijklmnopqrstuvwxyz01234";
    long long content_length = 31;
    unsigned char *buffer = (unsigned char *)malloc(64);
    if (buffer == NULL) {
        return 1;
    }
    memcpy(buffer, seed, 32);

    const uint64_t fnv_offset = 14695981039346656037ULL;
    const uint64_t fnv_prime = 1099511628211ULL;

    uint64_t observation_accumulator = 0;
    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        buffer[0] = (unsigned char)((iteration % 95) + 32);
        uint64_t hash = fnv_offset;
        for (long long j = 0; j < content_length; j++) {
            int64_t b = (signed char)buffer[j];
            int64_t shifted = b + 256;
            int64_t u = shifted % 256;
            uint64_t mixed = (uint64_t)u * 256ULL;
            hash = hash + mixed;
            hash = hash + (uint64_t)u;
            hash = hash * fnv_prime;
        }
        observation_accumulator += hash;
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld accumulator=%llu clockTicks=%lld\n",
           iterations, (unsigned long long)observation_accumulator,
           (long long)(end_ticks - start_ticks));

    free(buffer);
    return 0;
}
