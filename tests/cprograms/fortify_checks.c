/* _FORTIFY_SOURCE's checked functions: built at -O2 with _FORTIFY_SOURCE=2, glibc's headers call __memcpy_chk,
   __sprintf_chk, __fgets_chk and their kin; the last copy overflows its buffer, which glibc reports and aborts. */
#undef _FORTIFY_SOURCE
#define _FORTIFY_SOURCE 2
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv) {
    char small[8];
    char text[32];
    volatile int n = argc + 4;
    memcpy(small, "abcdefg", (size_t) n + 3);
    memset(small + 2, 'z', 2);
    printf("[%.7s]\n", small);
    strcpy(text, "fortified");
    strcat(text, " copy");
    strncat(text, " and more text", 5);
    printf("[%s]\n", text);
    int written = sprintf(text, "%d-%s", 42, "x");
    printf("[%d %s]\n", written, text);
    written = snprintf(text, sizeof text, "%s", "a fairly long line of text here");
    printf("[%d %s]\n", written, text);
    fprintf(stdout, "fprintf %d\n", n);
    FILE *in = tmpfile();
    fputs("one\ntwo\n", in);
    rewind(in);
    char line[8];
    printf("fgets [%s]", fgets(line, sizeof line, in));
    printf("fread %zu\n", fread(line, 1, 4, in));
    fclose(in);
    fflush(stdout);
    char *name = argv[0];
    char tiny[4];
    strcpy(tiny, name + strlen(name) - (size_t) n - 2);
    puts(tiny);
    return 0;
}
