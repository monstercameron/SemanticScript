/* printf's conversions, as tests/test_cprograms.py runs them linked with glibc and with the runtime's C library. */
#include <stdio.h>
#include <stdint.h>
#include <stddef.h>

static void show(const char *format, double value) {
    printf("[");
    printf(format, value);
    printf("]\n");
}

int main(void) {
    static const double values[] = {0.0, -0.0, 1.0, -1.5, 0.1, 2.5, 3.5, 1e-5, 123456.789, 1e21, 5e-324,
                                    2.2250738585072014e-308, 1.7976931348623157e308, 0.000123456, 9.9999999};
    static const char *formats[] = {"%f", "%.0f", "%.10f", "%e", "%.3e", "%E", "%g", "%.10g", "%#g", "%G",
                                    "%a", "%.2a", "%A", "%+12.4f", "%-12.2e|", "% 010.3f", "%.0e"};
    for (size_t i = 0; i < sizeof values / sizeof values[0]; i++)
        for (size_t j = 0; j < sizeof formats / sizeof formats[0]; j++)
            show(formats[j], values[i]);
    double inf = 1.0 / 0.0, nan = 0.0 / 0.0;
    printf("[%f|%F|%e|%g|%a|%5.1f|%-6f|]\n", inf, -inf, nan, -nan, inf, nan, inf);

    printf("[%d|%i|%u|%o|%x|%X]\n", -42, 42, 42u, 42u, 255u, 255u);
    printf("[%5d|%-5d|%05d|%+d|% d|%.3d|%.0d]\n", 42, 42, 42, 42, 42, 7, 0);
    printf("[%#o|%#x|%#X|%#.3o|%#5x]\n", 8u, 255u, 255u, 8u, 0u);
    printf("[%hhd|%hhu|%hd|%hu|%ld|%lu|%lld|%llu]\n", 300, 300, 70000, 70000, -1L, (unsigned long) -1L,
           (long long) INT64_MIN, (unsigned long long) UINT64_MAX);
    printf("[%jd|%zu|%td|%zd]\n", (intmax_t) -5, (size_t) 7, (ptrdiff_t) -9, (ptrdiff_t) 11);
    printf("[%c|%3c|%-3c|]\n", 'a', 'b', 'c');
    printf("[%s|%8s|%-8s|%.2s|%8.3s]\n", "hello", "hi", "hi", "hello", "hello");
    printf("[%p|%10p|%-10p|]\n", (void *) 0, (void *) 0, (void *) 0x1234);
    printf("[%p|%p]\n", (void *) 0x1000, (void *) 0xdeadbeef);
    printf("[%*d|%-*d|%.*f|%*.*e]\n", 6, 7, 6, 7, 2, 3.14159, 12, 3, 2.71828);
    printf("[%2$s %1$s|%3$*4$d]\n", "world", "hello", 5, 8);
    printf("[%%|%5%|%y]\n");
    int before = 0, after = 0;
    printf("abc%nde%nf\n", &before, &after);
    printf("[%d %d]\n", before, after);
    long double big = 1.0L / 3.0L;
    printf("[%Lf|%.20Le|%Lg|%La]\n", big, big, big, (long double) 1.0);
    char buffer[16];
    int wanted = snprintf(buffer, sizeof buffer, "%s-%d-%s", "abcdefgh", 12345, "xyz");
    printf("[%d|%s]\n", wanted, buffer);
    wanted = snprintf(buffer, 0, "%d", 123456);
    printf("[%d]\n", wanted);
    int written = sprintf(buffer, "%05.1f", 2.25);
    printf("[%d|%s]\n", written, buffer);
    fprintf(stdout, "to %s\n", "stdout");
    fprintf(stderr, "to %s %d\n", "stderr", 2);
    return 3;
}
