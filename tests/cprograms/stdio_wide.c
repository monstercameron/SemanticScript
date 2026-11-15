/* Wide stdio: orientation (fwide, and byte functions refused on a wide stream), the wide printf family on a wide
   stdout and into wide memory, the wide scanf family, wide character input and pushback, and wcsftime. stdout is
   only ever written wide here; what is printed about it goes to stderr, which stays a byte stream. */
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <time.h>
#include <wchar.h>

static int format_into(wchar_t *target, size_t size, const wchar_t *format, ...) {
    va_list list;
    va_start(list, format);
    int result = vswprintf(target, size, format, list);
    va_end(list);
    return result;
}

static int print_wide(const wchar_t *format, ...) {
    va_list list;
    va_start(list, format);
    int result = vwprintf(format, list);
    va_end(list);
    return result;
}

int main(void) {
    fprintf(stderr, "fwide(stdout) before %d\n", fwide(stdout, 0));
    int count = wprintf(L"[%ls|%5d|%-4lc|%.3s|%c|%#x|%+.2e]\n", L"wide", 42, (wint_t)L'q', "bytes", 'z', 255, 1234.5);
    fprintf(stderr, "wprintf %d, fwide(stdout) after %d\n", count, fwide(stdout, 0) > 0);
    fprintf(stderr, "printf on the wide stdout %d, fputs %d\n", printf("refused\n"), fputs("refused\n", stdout));
    int seen = 0;
    wprintf(L"abc%n|%5.1f|%g|%La|%s\n", &seen, 3.14159, 1e-5, 1.5L, "\xe9t\xe9");
    fprintf(stderr, "%%n %d\n", seen);
    putwchar(L'A');
    putwc(L'B', stdout);
    fputwc(L'C', stdout);
    fputws(L"=fputws\n", stdout);
    fwprintf(stdout, L"fwprintf %ls %d\n", L"to stdout", -7);
    print_wide(L"vwprintf %d %ls\n", 3, L"args");

    wchar_t text[64];
    int made = swprintf(text, 64, L"%ls-%d-%lc-%3s", L"x", 7, (wint_t)0x4e2d, "ab");
    fprintf(stderr, "swprintf %d:", made);
    for (int i = 0; i < made; i++)
        fprintf(stderr, " %x", (unsigned)text[i]);
    fprintf(stderr, " end %x\n", (unsigned)text[made]);
    fprintf(stderr, "swprintf too small %d\n", swprintf(text, 4, L"%s", "toolong"));
    fprintf(stderr, "vswprintf %d\n", format_into(text, 64, L"%05.1f|%ls", 2.25, L"v"));
    wprintf(L"vswprintf gave %ls\n", text);

    int number = 0;
    wchar_t word[16];
    double real = 0;
    char bytes[16];
    int got = swscanf(L"  12 abc 3.5 xyz", L"%d %ls %lf %3s", &number, word, &real, bytes);
    fprintf(stderr, "swscanf %d: %d %ls %g %s\n", got, number, word, real, bytes);
    got = swscanf(L"7,8", L"%d,%d", &number, &got);
    fprintf(stderr, "swscanf %d\n", number);

    FILE *file = tmpfile();
    fprintf(stderr, "tmpfile fwide %d\n", fwide(file, 0));
    fputws(L"line one\nline two\n", file);
    fprintf(stderr, "after fputws fwide %d, fputs %d, fwide(-1) %d\n", fwide(file, 0), fputs("x", file),
            fwide(file, -1));
    rewind(file);
    wchar_t line[32];
    fgetws(line, 32, file);
    fprintf(stderr, "fgetws %ls", line);
    wint_t first = fgetwc(file);
    fprintf(stderr, "fgetwc %lc ungetwc %lc ", (wchar_t)first, (wchar_t)ungetwc(L'Q', file));
    fprintf(stderr, "getwc %lc\n", (wchar_t)getwc(file));
    int value = 0;
    wchar_t rest[16];
    rewind(file);
    got = fwscanf(file, L"line %ls", rest);
    fprintf(stderr, "fwscanf %d %ls\n", got, rest);
    while (fgetwc(file) != WEOF)
        ;
    fprintf(stderr, "at end %d, fgetws %p\n", feof(file) != 0, (void *)fgetws(line, 32, file));
    fclose(file);

    FILE *bytes_file = tmpfile();
    fputs("5", bytes_file);
    rewind(bytes_file);
    fprintf(stderr, "fwscanf on a byte stream %d, fputwc %d\n", fwscanf(bytes_file, L"%d", &value),
            (int)fputwc(L'x', bytes_file));
    fclose(bytes_file);

    struct tm when = {.tm_sec = 9, .tm_min = 7, .tm_hour = 13, .tm_mday = 5, .tm_mon = 2, .tm_year = 124,
                      .tm_wday = 2, .tm_yday = 64};
    wchar_t stamp[64];
    size_t length = wcsftime(stamp, 64, L"%Y-%m-%d %H:%M:%S %a %b %j %p", &when);
    wprintf(L"wcsftime %zu %ls\n", length, stamp);
    fprintf(stderr, "wcsftime too small %zu\n", wcsftime(stamp, 5, L"%Y-%m-%d", &when));
    return 0;
}
