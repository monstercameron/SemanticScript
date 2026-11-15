/* The scanf family: sscanf over many conversions, then scanf and getchar over standard input. */
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

int main(void) {
    int a = 0, b = 0, n = 0;
    unsigned u = 0;
    long l = 0;
    long long ll = 0;
    short h = 0;
    signed char hh = 0;
    double d = 0;
    float f = 0;
    long double ld = 0;
    char word[32] = {0}, set[32] = {0}, chars[8] = {0};
    void *p = 0;

    printf("%d\n", sscanf("  42 -0x1F 017 99", "%d %i %i %u", &a, &b, &n, &u));
    printf("%d %d %d %u\n", a, b, n, u);
    printf("%d\n", sscanf("123456789012 -5 70000 300", "%ld %lld %hd %hhd", &l, &ll, &h, &hh));
    printf("%ld %lld %d %d\n", l, ll, h, hh);
    printf("%d\n", sscanf("3.25e2 -0.5 0x1.8p1 inf", "%lf %f %Lf %lf", &d, &f, &ld, &d));
    printf("%g %g %Lg %g\n", d, f, ld, d);
    printf("%d\n", sscanf("nan(123) 1e400 1e-400", "%lf %lf %f", &d, &d, &f));
    printf("%g %g\n", d, f);
    printf("%d\n", sscanf("hello world", "%s %3s", word, set));
    printf("[%s] [%s]\n", word, set);
    printf("%d\n", sscanf("abc123def", "%[a-z]%[0-9]%2c", word, set, chars));
    printf("[%s] [%s] [%.2s]\n", word, set, chars);
    printf("%d\n", sscanf("]x-y^", "%[]x-]%[^z]", word, set));
    printf("[%s] [%s]\n", word, set);
    printf("%d\n", sscanf("12 34", "%*d %d%n", &a, &n));
    printf("%d %d\n", a, n);
    printf("%d\n", sscanf("ff 0x10", "%x %p", &u, &p));
    printf("%x %p\n", u, p);
    printf("%d\n", sscanf("10%5", "%d%%%d", &a, &b));
    printf("%d %d\n", a, b);
    printf("%d %d %d\n", sscanf("", "%d", &a), sscanf("   ", "%d", &a), sscanf("x", "%d", &a));
    printf("%d\n", sscanf("1 2", "%d %d %d", &a, &b, &n));
    printf("%d\n", sscanf("abc", "abd"));
    printf("%d\n", sscanf("12345", "%3d%d", &a, &b));
    printf("%d %d\n", a, b);
    wchar_t wide[8] = {0};
    printf("%d\n", sscanf("wide", "%ls", wide));
    printf("%d %d %d\n", (int) wide[0], (int) wide[3], (int) wide[4]);

    char *after = NULL;
    printf("0b: %d", sscanf("0b101 0B11", "%i %i", &a, &b));
    printf(" %d %d", a, b);
    printf(" | strtol %ld", strtol("0b101", &after, 0));
    printf(" [%s] %ld\n", after, strtoul("0b11", NULL, 2));

    int first = getchar();
    printf("getchar %c\n", first);
    printf("%d\n", scanf("%d %s", &a, word));
    printf("%d [%s]\n", a, word);
    printf("%d\n", scanf("%d", &a));
    printf("rest [%c]\n", getchar());
    printf("%d\n", scanf("%d", &a));
    return 0;
}
