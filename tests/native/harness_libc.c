/*
 * harness_libc.c — R-199 native-runtime safety harness for the raw c.* heap/file
 * shims (ss_libc.c). Exercises the orderings that USED to be allocator/CRT
 * corruption before R-199 — double free, free of a foreign pointer, double
 * fclose, fgets/fprintf after fclose — as well as the normal paths, all as a
 * single clean run. Built with ASAN+UBSAN by run_sanitizers.sh; a clean run must
 * report ZERO findings (including leaks: every live alloc/stream is released).
 */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>

#include "../../semanticscript/runtime/ss_libc.c"

int main(void) {
    /* normal malloc/use/free */
    long long p = ss_c_malloc(64);
    assert(p != 0);
    ss_c_memset(p, 0, 64);
    ss_c_free(p);

    /* R-199: a double free is a no-op (membership fails), not allocator
     * corruption; freeing a foreign/stack pointer is likewise ignored. */
    ss_c_free(p);                 /* double free of the just-freed block */
    long long stack_marker = 0;
    ss_c_free((long long)(intptr_t)&stack_marker);  /* foreign pointer */
    ss_c_free(0);                 /* NULL */

    /* a fresh allocation after the misuse still works and is independent */
    long long q = ss_c_malloc(16);
    assert(q != 0 && q != p);     /* (q may reuse p's address only after our free) */
    ss_c_free(q);

    /* normal fopen/fprintf/fclose round-trip */
    const char *path = "harness_libc_tmp.txt";
    long long f = ss_c_fopen(path, "wb");
    assert(f != 0);
    assert(ss_c_fprintf(f, "line %d\n", 7) > 0);
    assert(ss_c_fflush(f) == 0);
    assert(ss_c_fclose(f) == 0);

    /* R-199: a double fclose is a no-op; fprintf/fgets/fflush after close fail
     * closed instead of touching the freed FILE object. */
    assert(ss_c_fclose(f) == 0);          /* double close -> no-op */
    assert(ss_c_fprintf(f, "x") == -1);   /* write after close -> rejected */
    char buf[64];
    assert(ss_c_fgets((long long)(intptr_t)buf, (int)sizeof(buf), f) == 0); /* read after close */
    assert(ss_c_fflush(f) == EOF);        /* flush after close -> rejected */

    /* the standard streams remain usable (not tracked, but allowed) */
    assert(ss_c_fprintf((long long)(intptr_t)stdout, "%s", "") == 0);

    /* a real read of the file we wrote, then clean up */
    long long rf = ss_c_fopen(path, "rb");
    assert(rf != 0);
    long long got = ss_c_fgets((long long)(intptr_t)buf, (int)sizeof(buf), rf);
    assert(got != 0 && strncmp(buf, "line 7", 6) == 0);
    assert(ss_c_fclose(rf) == 0);
    remove(path);

    printf("harness_libc: OK\n");
    return 0;
}
