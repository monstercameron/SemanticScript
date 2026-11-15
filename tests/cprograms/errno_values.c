/* errno as the library's functions set it, against glibc's: files that are not there, a directory opened for
   writing, a stream used the wrong way, a seek on a pipe, numbers out of range, memory that cannot be had, signals
   that are no signals, and errno's own cell. */
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static void show(const char *what, int failed) {
    printf("%-28s failed %d errno %d\n", what, failed, errno);
    errno = 0;
}

int main(void) {
    errno = 0;
    show("fopen of a missing file", fopen("no-such-dir/no-such-file", "r") == NULL);
    show("fopen of a directory to write", fopen(".", "w") == NULL);
    show("fopen with exclusive create", (fclose(fopen("errno-made.txt", "w")), fopen("errno-made.txt", "wx")) == NULL);
    show("remove of a missing file", remove("no-such-file") != 0);
    show("rename of a missing file", rename("no-such-file", "other-name") != 0);
    show("remove of a full directory", remove("..") != 0);
    FILE *readonly = fopen("errno-made.txt", "r");
    show("fputc on a read stream", fputc('x', readonly) == EOF);
    fclose(readonly);
    remove("errno-made.txt");
    show("fseek on standard input", fseek(stdin, 10, SEEK_SET) != 0);
    show("ftell on standard input", ftell(stdin) < 0);
    show("strtol past LONG_MAX", strtol("99999999999999999999", NULL, 10) != LONG_MAX);
    show("strtod past DBL_MAX", strtod("1e400", NULL) == 0);
    show("strtoul with base 99", strtoul("12", NULL, 99) != 0);
    show("malloc of PTRDIFF_MAX+1", malloc((size_t) PTRDIFF_MAX + 1) != NULL);
    show("calloc that overflows", calloc(SIZE_MAX / 2, 4) != NULL);
    show("signal for SIGKILL", signal(SIGKILL, SIG_IGN) == SIG_ERR);
    show("signal for 0", signal(0, SIG_IGN) == SIG_ERR);
    show("raise of 0", raise(0) != 0);
    show("raise of 65", raise(65) != 0);
    show("setvbuf with mode 7", setvbuf(stdout, NULL, 7, 0) != 0);
    show("fseek with whence 9", fseek(stdout, 0, 9) != 0);
    printf("errno cell is the same each time %d\n", &errno == &errno);
    return 0;
}
