/* C11 threads: threads that add under a mutex, a condition variable that hands a value over, thread-specific
   storage with a destructor, call_once, errno kept per thread, malloc and printf from several threads, joins. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <threads.h>

static mtx_t lock;
static cnd_t ready;
static int handed = 0;
static long total = 0;
static once_flag once = ONCE_FLAG_INIT;
static int once_calls = 0;
static tss_t key;
static int destroyed = 0;

static void count_once(void) { once_calls++; }

static void forget(void *value) {
    mtx_lock(&lock);
    destroyed++;
    mtx_unlock(&lock);
    free(value);
}

static int adder(void *argument) {
    int id = *(int *) argument;
    call_once(&once, count_once);
    int *mine = malloc(sizeof *mine);
    *mine = id;
    tss_set(key, mine);
    errno = id;
    for (int i = 0; i < 20000; i++) {
        mtx_lock(&lock);
        total += 1;
        mtx_unlock(&lock);
    }
    char *scratch = malloc(64);
    snprintf(scratch, 64, "thread %d", id);
    int same = errno == id && *(int *) tss_get(key) == id && strlen(scratch) == 8;
    free(scratch);
    return same ? id * 10 : -1;
}

static int waiter(void *argument) {
    (void) argument;
    mtx_lock(&lock);
    while (handed == 0) cnd_wait(&ready, &lock);
    int got = handed;
    mtx_unlock(&lock);
    return got + 1;
}

int main(void) {
    mtx_init(&lock, mtx_plain);
    cnd_init(&ready);
    tss_create(&key, forget);
    thrd_t threads[4];
    int ids[4] = {1, 2, 3, 4};
    for (int i = 0; i < 4; i++)
        if (thrd_create(&threads[i], adder, &ids[i]) != thrd_success) return 9;
    thrd_t other;
    thrd_create(&other, waiter, NULL);
    struct timespec pause = {0, 2000000};
    thrd_sleep(&pause, NULL);
    mtx_lock(&lock);
    handed = 41;
    cnd_signal(&ready);
    mtx_unlock(&lock);
    for (int i = 0; i < 4; i++) {
        int result = 0;
        thrd_join(threads[i], &result);
        printf("thread %d gave %d\n", ids[i], result);
    }
    int waited = 0;
    thrd_join(other, &waited);
    printf("waiter gave %d\n", waited);
    printf("total %ld, call_once ran %d time(s), destructors %d\n", total, once_calls, destroyed);
    printf("main is itself: %d, others differ: %d\n", thrd_equal(thrd_current(), thrd_current()) != 0,
           thrd_equal(thrd_current(), threads[0]) != 0);
    mtx_t recursive;
    mtx_init(&recursive, mtx_recursive);
    mtx_lock(&recursive);
    printf("recursive trylock %d\n", mtx_trylock(&recursive) == thrd_success);
    mtx_unlock(&recursive);
    mtx_unlock(&recursive);
    mtx_lock(&lock);
    printf("plain trylock while held %d\n", mtx_trylock(&lock) == thrd_busy);
    struct timespec past = {1, 0};
    mtx_t timed;
    mtx_init(&timed, mtx_timed);
    mtx_lock(&timed);
    printf("timedlock past its deadline %d\n", mtx_timedlock(&timed, &past) == thrd_timedout);
    printf("timedwait past its deadline %d\n", cnd_timedwait(&ready, &lock, &past) == thrd_timedout);
    mtx_unlock(&timed);
    mtx_unlock(&lock);
    mtx_destroy(&lock);
    cnd_destroy(&ready);
    return 0;
}
