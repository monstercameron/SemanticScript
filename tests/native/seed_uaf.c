/*
 * seed_uaf.c — R-134 sanitizer self-test. A DELIBERATE heap-use-after-free that
 * AddressSanitizer must detect. The native-safety job builds this with ASAN and
 * asserts it exits NON-ZERO: if a future toolchain/flag change silently disabled
 * the sanitizer, this seed would pass (exit 0) and fail the job, proving the
 * clean-harness "zero findings" result is actually meaningful.
 *
 * NOT a runtime file — it is never linked into the product; it exists only to
 * prove ASAN is live in CI. Keep it trivially, obviously buggy.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void) {
    char *p = (char *)malloc(16);
    if (!p) return 2;
    memcpy(p, "hello", 6);
    free(p);
    /* use-after-free: read freed memory. ASAN aborts here. */
    volatile char c = p[0];
    printf("seed_uaf: read '%c' after free (ASAN should have aborted)\n", c);
    return 0;
}
