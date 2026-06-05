/*
 * harness_libc.c — native-runtime safety harness for the raw c.* libc shims
 * (ss_libc.c). Exercises the orderings that USED to be allocator/CRT corruption
 * before R-199 — double free, free of a foreign pointer, double fclose,
 * fgets/fprintf after fclose — plus R-187 signed-size/null raw-pointer guards for
 * memmove/snprintf/fgets, as well as normal paths. Built with ASAN+UBSAN by
 * run_sanitizers.sh; a clean run must report ZERO findings (including leaks:
 * every live alloc/stream is released).
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
    assert(q != 0);               /* malloc may legally reuse p's freed address */
    ss_c_free(q);

    /* R-187: valid overlapping memmove is preserved, but negative counts and
     * NULL src/dest fail closed before libc sees a huge size_t or bad pointer. */
    char overlap[16] = "abcdefghi";
    long long overlap_dest = (long long)(intptr_t)(overlap + 2);
    assert(ss_c_memmove(overlap_dest, (long long)(intptr_t)overlap, 5) == overlap_dest);
    assert(strcmp(overlap, "ababcdehi") == 0);
    char dst[8] = "keep";
    char src[8] = "from";
    assert(ss_c_memmove((long long)(intptr_t)dst, (long long)(intptr_t)src, -1) == 0);
    assert(strcmp(dst, "keep") == 0);
    assert(ss_c_memmove(0, (long long)(intptr_t)src, 1) == 0);
    assert(ss_c_memmove((long long)(intptr_t)dst, 0, 1) == 0);
    assert(ss_c_memmove((long long)(intptr_t)dst, (long long)(intptr_t)src, 0)
           == (long long)(intptr_t)dst);
    assert(strcmp(dst, "keep") == 0);

    /* R-187: valid bounded snprintf still formats/truncates normally; invalid
     * signed size / NULL buffer / NULL format fail closed. */
    char fmtbuf[8] = {0};
    assert(ss_c_snprintf((long long)(intptr_t)fmtbuf, (long long)sizeof(fmtbuf),
                         "a%d", 12) == 3);
    assert(strcmp(fmtbuf, "a12") == 0);
    char small[4] = {0};
    assert(ss_c_snprintf((long long)(intptr_t)small, (long long)sizeof(small),
                         "abcd") == 4);
    assert(strcmp(small, "abc") == 0);
    strcpy(fmtbuf, "guard");
    assert(ss_c_snprintf((long long)(intptr_t)fmtbuf, -1, "x") == -1);
    assert(strcmp(fmtbuf, "guard") == 0);
    assert(ss_c_snprintf(0, 8, "x") == -1);
    assert(ss_c_snprintf((long long)(intptr_t)fmtbuf, 8, NULL) == -1);
    assert(ss_c_snprintf((long long)(intptr_t)fmtbuf, 0, "x") == -1);

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
    strcpy(buf, "unchanged");
    assert(ss_c_fgets((long long)(intptr_t)buf, 0, rf) == 0);
    assert(strcmp(buf, "unchanged") == 0);
    assert(ss_c_fgets((long long)(intptr_t)buf, -1, rf) == 0);
    assert(strcmp(buf, "unchanged") == 0);
    assert(ss_c_fgets(0, (int)sizeof(buf), rf) == 0);
    long long got = ss_c_fgets((long long)(intptr_t)buf, (int)sizeof(buf), rf);
    assert(got != 0 && strncmp(buf, "line 7", 6) == 0);
    assert(ss_c_fclose(rf) == 0);
    remove(path);

    printf("harness_libc: OK\n");
    return 0;
}
