/* bench_strlen.c — repeatedly call strlen on a runtime-provided string so
 * the optimizer cannot fold the result at compile time. The string comes
 * from getenv("PATH") so its length isn't a constant the optimizer can see.
 *
 * Compile with: clang -O2 -o bench_strlen.exe bench_strlen.c
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(void) {
    const char *probe = getenv("PATH");
    if (probe == NULL) probe = "fallback-string-when-PATH-is-unset";

    long long iterations = 200000000LL;
    long long accumulator = 0;

    clock_t start_ticks = clock();
    for (long long iteration = 0; iteration < iterations; iteration++) {
        accumulator += (long long)strlen(probe);
    }
    clock_t end_ticks = clock();

    printf("iterations=%lld accumulator=%lld clockTicks=%lld\n",
           iterations, accumulator,
           (long long)(end_ticks - start_ticks));
    return 0;
}
