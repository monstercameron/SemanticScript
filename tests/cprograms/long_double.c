/* long double: strtold and wcstold correctly rounded (with their ends and ERANGE), the exact <math.h> l functions,
   printf's %L conversions and scanf's %Lf; each line printed the same way under glibc and under the runtime. */
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>

static void read_text(const char *text) {
    char *end;
    errno = 0;
    long double value = strtold(text, &end);
    int saved = errno;
    /* %La of a subnormal is left out: what matters here is the value, which %.25Lg's exact digits show */
    if (fpclassify(value) == FP_SUBNORMAL)
        printf("strtold(\"%s\") = subnormal %.25Lg end %d errno %d\n", text, value, (int)(end - text), saved);
    else
        printf("strtold(\"%s\") = %La %.25Lg end %d errno %d\n", text, value, value, (int)(end - text), saved);
}

int main(void) {
    const char *texts[] = {
        "0.1", "-2.5e-3", "1e4000", "1.2e4932", "1.18e4932", "3.6451995318824746025e-4951", "1e-5000",
        "18446744073709551617", "123456789012345678901234567890.125", "0x1.00000000000000018p0", "0x1p-16445",
        "  +inf", "-nan", "nan(7)", "0x", ".e1", "1e", "-0", "1.7976931348623159e308", "6.02214076e23 mol",
    };
    for (unsigned i = 0; i < sizeof texts / sizeof texts[0]; i++)
        read_text(texts[i]);

    static const wchar_t wide_text[] = L"  0.3333333333333333333333333xyz";
    wchar_t *wend;
    long double wide = wcstold(wide_text, &wend);
    printf("wcstold = %La end %d\n", wide, (int)(wend - wide_text));

    long double x = -7.75L, y = 2.0L;
    int exponent = 0;
    long double fraction = frexpl(x, &exponent);
    printf("fabsl %La copysignl %La frexpl %La %d ldexpl %La\n", fabsl(x), copysignl(3.0L, x), fraction, exponent,
           ldexpl(fraction, exponent));
    printf("trunc %La floor %La ceil %La round %La rint %La\n", truncl(x), floorl(x), ceill(x), roundl(x), rintl(x));
    printf("lrintl %ld llroundl %lld lroundl %ld\n", lrintl(2.5L), llroundl(-2.5L), lroundl(2.5L));
    long double whole;
    long double part = modfl(x, &whole);
    printf("modfl %La %La\n", part, whole);
    int quotient = 0;
    long double rem = remquol(x, y, &quotient);
    printf("fmodl %La remainderl %La remquol %La %d\n", fmodl(x, y), remainderl(x, y), rem, quotient);
    printf("sqrtl %La %La %.30Lg\n", sqrtl(6.25L), sqrtl(2.0L), sqrtl(2.0L));
    printf("nextafterl %La %La nexttowardl %La\n", nextafterl(1.0L, 2.0L), nextafterl(0.0L, -1.0L),
           nexttowardl(1.0L, 0.0L));
    printf("nexttoward %a nexttowardf %a\n", nexttoward(1.0, 2.0L), (double)nexttowardf(1.0f, 0.0L));
    printf("fmaxl %La fminl %La fdiml %La\n", fmaxl(nanl(""), -1.0L), fminl(2.0L, -1.0L), fdiml(5.0L, 1.5L));
    printf("ilogbl %d logbl %La scalbnl %La scalblnl %La\n", ilogbl(48.0L), logbl(48.0L), scalbnl(3.0L, 10),
           scalblnl(3.0L, -2L));
    errno = 0;
    long double huge = ldexpl(1.0L, 20000);
    printf("ldexpl overflow %La errno %d\n", huge, errno);

    long double scanned = 0;
    int got = sscanf("  2.718281828459045235360287471352662497757 rest", "%Lf", &scanned);
    printf("sscanf %d %La %.30Lg\n", got, scanned, scanned);
    long double tiny = 0;
    got = sscanf("0x1.8p-16000", "%La", &tiny);
    printf("sscanf %d %La\n", got, tiny);
    return 0;
}
