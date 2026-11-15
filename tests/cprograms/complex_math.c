/* complex.h as glibc's libm gives it, against the library's: every function of double complex and float complex on
   ordinary values (printed to 9 significant digits, so a difference of a few units in the last place of a result does
   not show), on infinities and NaN (a NaN is printed as "nan" whatever its sign bit), and on the branch cuts, where
   the sign of a zero imaginary part picks the side. */
#include <complex.h>
#include <math.h>
#include <stdio.h>

static void number(double x) {
    if (isnan(x))
        printf("nan");
    else if (isinf(x))
        printf(x < 0 ? "-inf" : "inf");
    else if (x == 0)
        printf(signbit(x) ? "-0" : "0");
    else
        printf("%.9g", x);
}

static void part(double x, int sign_matters) {
    if (!sign_matters && x == 0)
        printf("0");
    else
        number(x);
}

static void show(const char *what, double complex z, int signs) {
    printf("%-26s (", what);
    part(creal(z), signs);
    printf(", ");
    part(cimag(z), signs);
    printf(")\n");
}

static void showf(const char *what, float complex z, int signs) {
    show(what, (double complex) (crealf(z) + I * cimagf(z)), signs);
}

static void show_real(const char *what, double x) {
    printf("%-26s ", what);
    number(x);
    printf("\n");
}

/* inputs the compiler cannot fold */
static volatile double zero = 0.0, one = 1.0, minus_one = -1.0, half = 0.5, two = 2.0, three = 3.0, four = 4.0,
                       big = 1e300, tiny = 1e-300, inf = 1.0 / 0.0, nan_value = 0.0 / 0.0;

#define EACH(f)                                                                                                       \
    f(cexp) f(clog) f(csqrt) f(csin) f(ccos) f(ctan) f(casin) f(cacos) f(catan) f(csinh) f(ccosh) f(ctanh) f(casinh)    \
        f(cacosh) f(catanh)

int main(void) {
    double complex ordinary[] = {1.0 + 1.0 * I, 0.5 - 0.25 * I, -2.0 + 3.0 * I, 3.0 + 4.0 * I, -0.75 - 1.5 * I,
                                 2.5 + 0.125 * I, 0.125 + 2.5 * I, -1.5 + 0.5 * I};
    float complex ordinaryf[] = {1.0f + 1.0f * I, 0.5f - 0.25f * I, -2.0f + 3.0f * I, 3.0f + 4.0f * I, -0.75f - 1.5f * I};
    double complex z;
    int i;
    for (i = 0; i < 8; i++) {
        z = ordinary[i];
        printf("-- (%g, %g)\n", creal(z), cimag(z));
        show_real("cabs", cabs(z));
        show_real("carg", carg(z));
        show_real("creal", creal(z));
        show_real("cimag", cimag(z));
        show("conj", conj(z), 1);
        show("cproj", cproj(z), 1);
#define CALL(f) show(#f, f(z), 1);
        EACH(CALL)
#undef CALL
        show("cpow(z, 2)", cpow(z, 2.0), 1);
        show("cpow(z, 0.5+0.5i)", cpow(z, 0.5 + 0.5 * I), 1);
    }
    for (i = 0; i < 5; i++) {
        float complex w = ordinaryf[i];
        printf("-- float (%g, %g)\n", crealf(w), cimagf(w));
        show_real("cabsf", cabsf(w));
        show_real("cargf", cargf(w));
        showf("conjf", conjf(w), 1);
        showf("cexpf", cexpf(w), 1);
        showf("clogf", clogf(w), 1);
        showf("csqrtf", csqrtf(w), 1);
        showf("csinf", csinf(w), 1);
        showf("ccosf", ccosf(w), 1);
        showf("ctanf", ctanf(w), 1);
        showf("casinf", casinf(w), 1);
        showf("cacosf", cacosf(w), 1);
        showf("catanf", catanf(w), 1);
        showf("csinhf", csinhf(w), 1);
        showf("ccoshf", ccoshf(w), 1);
        showf("ctanhf", ctanhf(w), 1);
        showf("casinhf", casinhf(w), 1);
        showf("cacoshf", cacoshf(w), 1);
        showf("catanhf", catanhf(w), 1);
        showf("cpowf(w, 2)", cpowf(w, 2.0f), 1);
    }

    /* Annex G's special values: infinities and NaN in each part (zeros print without a sign) */
    double specials[] = {0.0, 1.0, -2.0, 1.0 / 0.0, -1.0 / 0.0, 0.0 / 0.0};
    int a, b;
    for (a = 0; a < 6; a++)
        for (b = 0; b < 6; b++) {
            double x = specials[a] * (one), y = specials[b] * (one);
            if (a == 0)
                x = zero;
            if (b == 0)
                y = zero;
            z = x + y * I;
            if (a == 5)
                z = nan_value + y * I;
            if (b == 5)
                z = x + nan_value * I;
            if (a == 5 && b == 5)
                z = nan_value + nan_value * I;
            if (isinf(x) && isinf(y))
                z = x + y * I;
            printf("== special %d %d\n", a, b);
            show_real("cabs", cabs(z));
            show("cproj", cproj(z), 0);
#define CALL(f) show(#f, f(z), 0);
            EACH(CALL)
#undef CALL
        }

    /* branch cuts: the sign of a zero imaginary part picks the side, so zeros print with their signs */
    show("clog(-1 + 0i)", clog(-one + zero * I), 1);
    show("clog(-1 - 0i)", clog(-one - zero * I), 1);
    show("csqrt(-4 + 0i)", csqrt(-four + zero * I), 1);
    show("csqrt(-4 - 0i)", csqrt(-four - zero * I), 1);
    show("casin(2 + 0i)", casin(two + zero * I), 1);
    show("casin(2 - 0i)", casin(two - zero * I), 1);
    show("casin(-2 + 0i)", casin(-two + zero * I), 1);
    show("cacos(2 + 0i)", cacos(two + zero * I), 1);
    show("cacos(2 - 0i)", cacos(two - zero * I), 1);
    show("cacos(-2 + 0i)", cacos(-two + zero * I), 1);
    show("catan(0 + 2i)", catan(zero + two * I), 1);
    show("catan(-0 + 2i)", catan(-zero + two * I), 1);
    show("catanh(2 + 0i)", catanh(two + zero * I), 1);
    show("catanh(2 - 0i)", catanh(two - zero * I), 1);
    show("catanh(-2 + 0i)", catanh(-two + zero * I), 1);
    show("casinh(0 + 2i)", casinh(zero + two * I), 1);
    show("casinh(-0 + 2i)", casinh(-zero + two * I), 1);
    show("cacosh(-2 + 0i)", cacosh(-two + zero * I), 1);
    show("cacosh(-2 - 0i)", cacosh(-two - zero * I), 1);
    show("cacosh(0.5 + 0i)", cacosh(half + zero * I), 1);
    show("cacosh(0.5 - 0i)", cacosh(half - zero * I), 1);

    /* signed zeros of results the annex fixes */
    show("cexp(0 + 0i)", cexp(zero + zero * I), 1);
    show("cexp(0 - 0i)", cexp(zero - zero * I), 1);
    show("csinh(0 + 0i)", csinh(zero + zero * I), 1);
    show("csinh(-0 + 0i)", csinh(-zero + zero * I), 1);
    show("ctanh(0 + 0i)", ctanh(zero + zero * I), 1);
    show("ctanh(-0 - 0i)", ctanh(-zero - zero * I), 1);
    show("casinh(0 + 0i)", casinh(zero + zero * I), 1);
    show("catanh(0 + 0i)", catanh(zero + zero * I), 1);
    show("csqrt(0 + 0i)", csqrt(zero + zero * I), 1);
    show("csqrt(-0 - 0i)", csqrt(-zero - zero * I), 1);
    show("cproj(inf - 3i)", cproj(inf - three * I), 1);
    show("cproj(1 + inf i)", cproj(one + inf * I), 1);
    show("conj(1 + 0i)", conj(one + zero * I), 1);

    /* range: results that overflow or underflow in one part only, and arguments near the limits of the double */
    show("cexp(710 + 1i)", cexp(710.0 + one * I), 0);
    show("cexp(1000 + 0i)", cexp(1000.0 + zero * I), 1);
    show("csinh(710 + 1i)", csinh(710.0 + one * I), 0);
    show("ccosh(-710 + 1i)", ccosh(-710.0 + one * I), 0);
    show("ctanh(1000 + 1i)", ctanh(1000.0 + one * I), 0);
    show("csqrt(1e300 + 1e300i)", csqrt(big + big * I), 0);
    show("csqrt(1e-300 + 1e-300i)", csqrt(tiny + tiny * I), 0);
    show("clog(1e300 + 1e300i)", clog(big + big * I), 0);
    show("clog(1e-300 + 1e-300i)", clog(tiny + tiny * I), 0);
    show_real("cabs(1e300 + 1e300i)", cabs(big + big * I));
    show_real("cabs(3e-300 + 4e-300i)", cabs(3 * tiny + 4 * tiny * I));
    show("casinh(1e300 + 1e300i)", casinh(big + big * I), 0);
    show("cacosh(1e300 + 1e300i)", cacosh(big + big * I), 0);
    show("catanh(1e300 + 1e300i)", catanh(big + big * I), 0);
    show("casin(1e-300 + 1e-300i)", casin(tiny + tiny * I), 0);
    show("catan(1e-300 + 1e-300i)", catan(tiny + tiny * I), 0);
    return 0;
}
