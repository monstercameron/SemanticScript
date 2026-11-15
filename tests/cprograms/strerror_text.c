/* strerror's message for every number glibc knows and some it does not, perror's line, and printf's %m. */
#include <errno.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    for (int number = -3; number < 140; number++) printf("%d: %s\n", number, strerror(number));
    printf("%d: %s\n", 4096, strerror(4096));
    errno = ENOENT;
    perror("opening");
    errno = EACCES;
    perror("");
    errno = 0;
    perror(NULL);
    errno = ERANGE;
    printf("[%m] [%20.5m]\n");
    fflush(stdout);
    errno = EDOM;
    fprintf(stderr, "stderr %m\n");
    return 0;
}
