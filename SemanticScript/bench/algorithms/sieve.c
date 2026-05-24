/* sieve.c - Sieve of Eratosthenes up to LIMIT, repeated REPEATS times.
 *
 * All four language versions use the same structure: a byte array starts as
 * all-prime (1), composites are struck out (0) by walking each prime's
 * multiples for primes up to sqrt(LIMIT), and the prime count is a final pass
 * over the array. The work is dominated by streaming byte writes across a
 * multi-megabyte array, so this exercises memory throughput and simple integer
 * indexing. The sieve is run REPEATS times and the per-run prime counts are
 * summed, so every repeat is observable in the checksum.
 *
 * Build: clang -O2 -o sieve.c.exe sieve.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>

int main(void) {
    long long limit = 2000000;
    long long repeats = 40;
    long long array_size = limit + 1;

    unsigned char *sieve = (unsigned char *)malloc((size_t)array_size);
    if (sieve == NULL) {
        return 1;
    }

    long long total_prime_count = 0;

    LARGE_INTEGER frequency;
    LARGE_INTEGER start_counter;
    LARGE_INTEGER end_counter;
    QueryPerformanceFrequency(&frequency);

    QueryPerformanceCounter(&start_counter);
    for (long long repeat = 0; repeat < repeats; repeat++) {
        memset(sieve, 1, (size_t)array_size);
        sieve[0] = 0;
        sieve[1] = 0;
        for (long long candidate = 2; candidate * candidate <= limit; candidate++) {
            if (sieve[candidate]) {
                for (long long multiple = candidate * candidate;
                     multiple <= limit; multiple += candidate) {
                    sieve[multiple] = 0;
                }
            }
        }
        long long prime_count = 0;
        for (long long index = 2; index <= limit; index++) {
            prime_count += sieve[index];
        }
        total_prime_count += prime_count;
    }
    QueryPerformanceCounter(&end_counter);

    double elapsed_seconds =
        (double)(end_counter.QuadPart - start_counter.QuadPart) /
        (double)frequency.QuadPart;

    printf("checksum=%lld elapsedSeconds=%.6f\n", total_prime_count,
           elapsed_seconds);

    free(sieve);
    return 0;
}
