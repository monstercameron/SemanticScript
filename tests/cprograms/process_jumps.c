/* setjmp and longjmp, signal handlers and raise, exit handlers, quick_exit's, ldiv and lldiv, and system. */
#include <inttypes.h>
#include <limits.h>
#include <setjmp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>

static jmp_buf target;
static volatile sig_atomic_t seen = 0;

static void handler(int number) { seen = number; }

static void deep(int depth) {
    if (depth == 0) longjmp(target, 7);
    deep(depth - 1);
}

static void last_words(void) { puts("atexit: registered first, runs last"); }
static void first_words(void) { puts("atexit: registered last, runs first"); }

int main(void) {
    volatile int count = 0;
    int value = setjmp(target);
    count++;
    printf("setjmp gave %d (pass %d)\n", value, count);
    if (value == 0) deep(50);
    if (setjmp(target) == 0) longjmp(target, 0);
    else puts("longjmp with 0 returns 1");

    printf("signal before: %s\n", signal(SIGUSR1, handler) == SIG_DFL ? "SIG_DFL" : "other");
    printf("raise: %d, seen %d\n", raise(SIGUSR1), (int) seen);
    printf("signal again gives the handler: %d\n", signal(SIGUSR1, SIG_IGN) == handler);
    printf("raise ignored: %d\n", raise(SIGUSR1));
    printf("SIGKILL: %s\n", signal(SIGKILL, handler) == SIG_ERR ? "SIG_ERR" : "installed");

    ldiv_t q = ldiv(-7L, 2L);
    lldiv_t r = lldiv(LLONG_MIN + 1, 10LL);
    imaxdiv_t t = imaxdiv(INTMAX_MAX, 3);
    printf("ldiv %ld %ld lldiv %lld %lld imaxdiv %jd %jd\n", q.quot, q.rem, r.quot, r.rem, t.quot, t.rem);

    printf("system(NULL) %d\n", system(NULL) != 0);
    fflush(stdout);
    int status = system("exit 3");
    printf("system status %d\n", status);

    atexit(last_words);
    atexit(first_words);
    puts("main returns 4");
    return 4;
}
