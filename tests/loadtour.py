"""Shared libraries an executable loads with the runtime's own loader on Linux (D-154), and what they find in the
runtime's C library (D-153).

tests/test_runtime_nolibc.py compiles the C below on Linux with the system's C compiler and builds the programs
below with the runtime in SemanticScript:

- `libprobe.so` (linked with the C library, a constructor, a data pointer to strlen, and `libdep.so` found through
  RUNPATH `$ORIGIN`) has `probe(kind, index, facet)`, which calls the C library's functions on hundreds of inputs
  (strtol and its kin in every base, strtod, atoi, ctype's functions and tables, the string functions, malloc and its
  kin, math, qsort and bsearch, getenv, div) and gives one number each. The probe tour prints every number, and the
  test requires each to be what ctypes gives calling the same library with glibc. It also binds `probe_hello`, which
  writes with puts, putchar, fputs, and fwrite, binds strlen through the library's scope, and a missing name.
- `libbare.so`, linked with no C library at all, calls strlen, which the loader finds in the runtime's C library.
- A file that is not a library, and a name no file has, are notFound.
- The refusal tour opens a library that has thread-local storage, one with an ifunc, or one that needs a function no
  library defines, and must trap saying why.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "docs", "refined-examples", "stage0", "tools"))

PROBE_C = r'''
/* The probes of tests/loadtour.py. No headers: every call is a plain call the compiler cannot inline or check. */
typedef unsigned long size_t;
long strtol(const char *, char **, int);
unsigned long strtoul(const char *, char **, int);
long long strtoll(const char *, char **, int);
unsigned long long strtoull(const char *, char **, int);
double strtod(const char *, char **);
int atoi(const char *);
long atol(const char *);
long long atoll(const char *);
double atof(const char *);
int *__errno_location(void);
size_t strlen(const char *);
size_t strnlen(const char *, size_t);
int strcmp(const char *, const char *);
int strncmp(const char *, const char *, size_t);
int strcasecmp(const char *, const char *);
int strncasecmp(const char *, const char *, size_t);
char *strchr(const char *, int);
char *strrchr(const char *, int);
char *strstr(const char *, const char *);
size_t strspn(const char *, const char *);
size_t strcspn(const char *, const char *);
char *strpbrk(const char *, const char *);
void *memchr(const void *, int, size_t);
int memcmp(const void *, const void *, size_t);
void *memcpy(void *, const void *, size_t);
void *memmove(void *, const void *, size_t);
void *memset(void *, int, size_t);
char *strcpy(char *, const char *);
char *strncpy(char *, const char *, size_t);
char *strcat(char *, const char *);
char *strncat(char *, const char *, size_t);
char *strdup(const char *);
char *strndup(const char *, size_t);
void *malloc(size_t);
void *calloc(size_t, size_t);
void *realloc(void *, size_t);
void free(void *);
void qsort(void *, size_t, size_t, int (*)(const void *, const void *));
void *bsearch(const void *, const void *, size_t, size_t, int (*)(const void *, const void *));
char *getenv(const char *);
int abs(int);
long labs(long);
typedef struct { int quot, rem; } div_t;
div_t div(int, int);
int isalnum(int); int isalpha(int); int isblank(int); int iscntrl(int); int isdigit(int); int isgraph(int);
int islower(int); int isprint(int); int ispunct(int); int isspace(int); int isupper(int); int isxdigit(int);
int toupper(int); int tolower(int);
const unsigned short **__ctype_b_loc(void);
const int **__ctype_toupper_loc(void);
const int **__ctype_tolower_loc(void);
double fabs(double); double floor(double); double ceil(double); double trunc(double); double round(double);
double sqrt(double); double fmod(double, double); double copysign(double, double);
int puts(const char *); int putchar(int); int fputs(const char *, void *);
size_t fwrite(const void *, size_t, size_t, void *);
int fflush(void *);
extern void *stdout;
extern void *stderr;
int dep_value(void);

#define COUNT(a) ((long) (sizeof(a) / sizeof((a)[0])))

static const char *const whole[] = {
    "0", "1", "-1", "+1", "  42", "\t\n\v\f\r 42", "-42xyz", "0x1f", "0X1F", "0x", "0xg", "0x 1", "-0x10", "0777",
    "0779", "08", "0b101", "z", "Zz", "zz9", "101", "  +", "-", "", "   ", "9223372036854775807",
    "9223372036854775808", "-9223372036854775808", "-9223372036854775809", "18446744073709551615",
    "18446744073709551616", "-18446744073709551615", "-18446744073709551616", "99999999999999999999999",
    "7fffffffffffffff", "8000000000000000", "ffffffffffffffff", "10000000000000000", "-0", "00000000000000000001",
    "1_000", "12e3", "\xff9"};
static const int bases[] = {0, 2, 8, 10, 16, 36, 1, 37, -1, 3};

static const char *const reals[] = {
    "0", "-0", "1", "+1.5", "  -2.5e-3", ".5", "5.", ".", "-.", "1e", "1e+", "1e-2", "1E2x", "1.5e+308", "1e309",
    "-1e309", "1e-400", "-1e-400", "0e999999", "123456789012345678901234567890", "0.1", "0.30000000000000004",
    "2.2250738585072014e-308", "1.7976931348623157e308", "1.7976931348623158e308", "1.7976931348623159e308",
    "inf", "-INF", "Infinity", "infinit", "infinityx", "nan", "-NaN", "nan(123)", "nan(abc_9)", "nan(", "nan(x y)",
    "0x1p0", "0x1.8p1", "-0x.8", "0x1P-1022", "0x1p-1074", "0x1p-1075", "0x1.8p-1074", "0x1p1023", "0x1p1024",
    "0x1.fffffffffffff8p0", "0x1.00000000000008p0", "0x1.00000000000018p0", "0x1.000000000000081p0",
    "0xffffffffffffffffffffp0", "0x0p5", "0x", "0xg", "0x.p1", "0x1p", "0x1p+", "0x1p-x", "  \t0x10", "1.5e3abc",
    "00012.5000", "1e-310", "4.9406564584124654e-324", "2.4703282292062328e-324", "2.4703282292062327e-324",
    "9007199254740993", "9007199254740995", "1.00000000000000011102230246251565404236316680908203125",
    "1.000000000000000111022302462515654042363166809082031251", "x", ""};

static const char *const strings[] = {
    "", "a", "hello", "help", "HELLO", "hello, world", "world", "wor", "o", "ehlo", " ,", "zzz", "abcabc", "cab",
    "\xff\x80", "\x7f", "hello\xff"};

static long sign(long v) { return (v > 0) - (v < 0); }

static long bits_of(double d) {
    long b;
    if (d != d)
        return 0x7ff8000000000000L;
    memcpy(&b, &d, sizeof b);
    return b;
}

static long offset_of(const char *found, const char *base) { return found ? (long) (found - base) : -1; }

static long checksum(const char *text, long bytes) {
    long sum = 0;
    for (long i = 0; i < bytes; i++)
        sum = sum * 31 + (unsigned char) text[i];
    return sum;
}

static int initialized;
__attribute__((constructor)) static void start(void) { initialized = 41; }

size_t (*const length_of)(const char *) = strlen;
static const char *const words[] = {"semantic", "script", "loader"};

static int compare_ints(const void *left, const void *right) {
    int a = *(const int *) left, b = *(const int *) right;
    return (a > b) - (a < b);
}

static int compare_keys(const void *left, const void *right) {
    return (*(const int *) left / 10) - (*(const int *) right / 10);
}

static const double doubles[] = {
    0.0, -0.0, 0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 0.49999999999999994, 1.0, -1.0, 3.75, -3.75, 4503599627370495.5,
    -4503599627370495.5, 4503599627370497.0, 1e300, -1e300, 5e-324, -5e-324, 2.2250738585072014e-308,
    1.7976931348623157e308, 1.0 / 0.0, -1.0 / 0.0, 0.0 / 0.0, 2.0, 0.1, 1e22, 7.25, -7.25, 1e-310};

static long strtol_probe(long index, long facet) {
    const char *text = whole[index / COUNT(bases)];
    int base = bases[index % COUNT(bases)];
    char *end = 0;
    long value;
    *__errno_location() = 0;
    switch (facet / 3) {
    case 0: value = strtol(text, &end, base); break;
    case 1: value = (long) strtoul(text, &end, base); break;
    case 2: value = (long) strtoll(text, &end, base); break;
    default: value = (long) strtoull(text, &end, base); break;
    }
    if (facet % 3 == 0)
        return value;
    if (facet % 3 == 1)
        return end ? (long) (end - text) : -1;
    return *__errno_location();
}

static long strtod_probe(long index, long facet) {
    const char *text = reals[index];
    char *end = 0;
    double value;
    *__errno_location() = 0;
    if (facet == 3)
        return bits_of(atof(text));
    value = strtod(text, &end);
    if (facet == 0)
        return bits_of(value);
    if (facet == 1)
        return end ? (long) (end - text) : -1;
    return *__errno_location();
}

static long ctype_probe(long index, long facet) {
    int c = (int) index - 128;
    switch (facet) {
    case 0: return isalnum(c);
    case 1: return isalpha(c);
    case 2: return isblank(c);
    case 3: return iscntrl(c);
    case 4: return isdigit(c);
    case 5: return isgraph(c);
    case 6: return islower(c);
    case 7: return isprint(c);
    case 8: return ispunct(c);
    case 9: return isspace(c);
    case 10: return isupper(c);
    case 11: return isxdigit(c);
    case 12: return toupper(c);
    case 13: return tolower(c);
    case 14: return (*__ctype_b_loc())[c];
    case 15: return (*__ctype_toupper_loc())[c];
    default: return (*__ctype_tolower_loc())[c];
    }
}

static long string_probe(long index, long facet) {
    const char *a = strings[index / COUNT(strings)];
    const char *b = strings[index % COUNT(strings)];
    char buffer[64];
    char *copy;
    long result;
    switch (facet) {
    case 0: return (long) strlen(a);
    case 1: return (long) strnlen(a, 3);
    case 2: return sign(strcmp(a, b));
    case 3: return sign(strncmp(a, b, 2));
    case 4: return sign(strcasecmp(a, b));
    case 5: return sign(strncasecmp(a, b, 3));
    case 6: return offset_of(strchr(a, b[0]), a);
    case 7: return offset_of(strrchr(a, b[0]), a);
    case 8: return offset_of(strstr(a, b), a);
    case 9: return (long) strspn(a, b);
    case 10: return (long) strcspn(a, b);
    case 11: return offset_of(strpbrk(a, b), a);
    case 12: return offset_of(memchr(a, b[0] ? b[0] : 'l', strlen(a)), a);
    case 13: return sign(memcmp(a, b, (strlen(a) < strlen(b) ? strlen(a) : strlen(b)) + 1));
    case 14:
        memset(buffer, 'x', sizeof buffer);
        strcpy(buffer, a);
        strcat(buffer, b);
        return checksum(buffer, sizeof buffer);
    case 15:
        memset(buffer, 'x', sizeof buffer);
        buffer[40] = 0;
        strncpy(buffer, a, 8);
        strncat(buffer, b, 3);
        return checksum(buffer, sizeof buffer);
    case 16:
        copy = strdup(a);
        result = checksum(copy, (long) strlen(a) + 1);
        free(copy);
        return result;
    case 17:
        copy = strndup(b, 2);
        result = checksum(copy, (long) strlen(copy) + 1);
        free(copy);
        return result;
    default:
        memcpy(buffer, "0123456789", 11);
        memmove(buffer + 2, buffer, 5);
        memmove(buffer, buffer + 3, 4);
        return checksum(buffer, 11);
    }
}

static long memory_probe(long index, long facet) {
    size_t size = (size_t) 1 << index;
    unsigned char *block;
    long ok = 1;
    switch (facet) {
    case 0:
        block = malloc(size);
        ok = block != 0 && ((unsigned long) block % 16) == 0;
        memset(block, 0x5a, size);
        free(block);
        return ok;
    case 1:
        block = calloc(size, 3);
        for (size_t i = 0; i < size * 3; i++)
            ok = ok && block[i] == 0;
        free(block);
        return ok;
    case 2:
        block = malloc(size);
        for (size_t i = 0; i < size; i++)
            block[i] = (unsigned char) i;
        block = realloc(block, size * 4 + 1);
        for (size_t i = 0; i < size; i++)
            ok = ok && block[i] == (unsigned char) i;
        block = realloc(block, size / 2 + 1);
        ok = ok && block[0] == 0;
        free(block);
        return ok;
    default:
        free(0);
        block = realloc(0, size);
        ok = block != 0;
        free(block);
        return ok + (realloc(malloc(4), 0) == 0) * 2 + (calloc((size_t) -1, 16) == 0) * 4;
    }
}

static long math_probe(long index, long facet) {
    double x = doubles[index];
    switch (facet) {
    case 0: return bits_of(fabs(x));
    case 1: return bits_of(floor(x));
    case 2: return bits_of(ceil(x));
    case 3: return bits_of(trunc(x));
    case 4: return bits_of(round(x));
    case 5: return bits_of(sqrt(x));
    case 6: return bits_of(fmod(x, 2.5));
    case 7: return bits_of(fmod(x, -0.75));
    case 8: return bits_of(fmod(1e300, x));
    default: return bits_of(copysign(1.0, x));
    }
}

static long sort_probe(long index, long facet) {
    int numbers[40], keys[40], i, count = (int) index + 1, key;
    int *found;
    for (i = 0; i < count; i++) {
        numbers[i] = (i * 7919 + 13) % 101 - 50;
        keys[i] = ((i * 37) % 5) * 10 + i % 10;
    }
    switch (facet) {
    case 0:
        qsort(numbers, (size_t) count, sizeof numbers[0], compare_ints);
        return checksum((const char *) numbers, count * (long) sizeof numbers[0]);
    case 1:
        qsort(keys, (size_t) count, sizeof keys[0], compare_keys);
        return checksum((const char *) keys, count * (long) sizeof keys[0]);
    default:
        qsort(numbers, (size_t) count, sizeof numbers[0], compare_ints);
        key = (int) facet - 20;
        found = bsearch(&key, numbers, (size_t) count, sizeof numbers[0], compare_ints);
        return found ? (long) (found - numbers) : -1;
    }
}

static const char *const variables[] = {"PATH", "SEMANTICSCRIPT_LOADTOUR", "SEMANTICSCRIPT_LOADTOUR_EMPTY",
                                        "SEMANTICSCRIPT_SURELY_UNSET_42", "", "SEMANTICSCRIPT_LOADTOUR="};

static long environment_probe(long index, long facet) {
    const char *value = getenv(variables[index]);
    if (!value)
        return -1;
    return facet == 0 ? (long) strlen(value) : checksum(value, (long) strlen(value));
}

static const int numerators[] = {7, -7, 7, -7, 0, 2147483647, -2147483647, 1};
static const int denominators[] = {2, 2, -2, -2, 5, -1, 3, 7};

static long number_probe(long index, long facet) {
    div_t d = div(numerators[index], denominators[index]);
    switch (facet) {
    case 0: return d.quot;
    case 1: return d.rem;
    case 2: return abs(numerators[index]);
    default: return labs(-(long) numerators[index] * 1000003L);
    }
}

static long loader_probe(long index, long facet) {
    (void) index;
    switch (facet) {
    case 0: return initialized;
    case 1: return dep_value();
    case 2: return (long) length_of(words[0]);
    default: return checksum(words[2], (long) strlen(words[2]));
    }
}

static const long counts[][2] = {{COUNT(whole) * COUNT(bases), 12}, {COUNT(reals), 4}, {384, 17},
                                 {COUNT(strings) * COUNT(strings), 19}, {12, 4}, {COUNT(doubles), 10},
                                 {40, 30}, {COUNT(variables), 2}, {COUNT(numerators), 4}, {1, 4}};

long probe(long kind, long index, long facet) {
    if (kind < 0)
        return COUNT(counts);
    if (index < 0)
        return counts[kind][-index - 1];
    switch (kind) {
    case 0: return strtol_probe(index, facet);
    case 1: return strtod_probe(index, facet);
    case 2: return ctype_probe(index, facet);
    case 3: return string_probe(index, facet);
    case 4: return memory_probe(index, facet);
    case 5: return math_probe(index, facet);
    case 6: return sort_probe(index, facet);
    case 7: return environment_probe(index, facet);
    case 8: return number_probe(index, facet);
    default: return loader_probe(index, facet);
    }
}

long probe_hello(long unused) {
    (void) unused;
    puts("hello from C");
    putchar('!');
    putchar('\n');
    fputs("to stdout\n", stdout);
    fwrite("to stderr\n", 1, 10, stderr);
    fflush(stdout); /* stdout is fully buffered in a pipe, as glibc's is (D-160) */
    return 7;
}
'''

DEP_C = r'''
int dep_value(void) { return 42; }
'''

BARE_C = r'''
typedef unsigned long size_t;
size_t strlen(const char *);
long bare_length(long extra) { return (long) strlen("semanticscript") + extra; }
'''

TLS_C = r'''
__thread int counter;
int bump(void) { return ++counter; }
'''

IFUNC_C = r'''
static int one(void) { return 1; }
static int (*pick(void))(void) { return one; }
int chosen(void) __attribute__((ifunc("pick")));
int use_chosen(void) { return chosen(); }
'''

UNDEFINED_C = r'''
int semanticscript_defined_nowhere_42(void);
int calls(void) { return semanticscript_defined_nowhere_42(); }
'''

REFUSED = {"./libtls.so": "thread-local", "./libifunc.so": "ifunc",
           "./libundefined.so": "it needs `semanticscript_defined_nowhere_42`"}


def build_libraries(cc: list[str], folder: str) -> None:
    """Compile the libraries into `folder` with the system's C compiler (Linux)."""
    import subprocess
    sources = {"probe.c": PROBE_C, "dep.c": DEP_C, "bare.c": BARE_C, "tls.c": TLS_C, "ifunc.c": IFUNC_C,
               "undefined.c": UNDEFINED_C}
    for name, text in sources.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    steps = [["-shared", "-fPIC", "-O1", "-o", "libdep.so", "dep.c"],
             ["-shared", "-fPIC", "-O1", "-fno-builtin", "-o", "libprobe.so", "probe.c", "-L.", "-ldep",
              "-Wl,-rpath,$ORIGIN"],
             ["-shared", "-fPIC", "-O1", "-nostdlib", "-fno-builtin", "-fno-stack-protector", "-o", "libbare.so",
              "bare.c"],
             ["-shared", "-fPIC", "-O1", "-o", "libtls.so", "tls.c"],
             ["-shared", "-fPIC", "-O1", "-o", "libifunc.so", "ifunc.c"],
             ["-shared", "-fPIC", "-O1", "-o", "libundefined.so", "undefined.c"]]
    for step in steps:
        done = subprocess.run(cc + step, cwd=folder, capture_output=True, text=True)
        assert done.returncode == 0, (step, done.stdout, done.stderr)
    with open(os.path.join(folder, "libbad.so"), "w", encoding="utf-8") as fh:
        fh.write("this is not a shared library\n")


def expected_probes(folder: str) -> list[str]:
    """What probe gives for every kind, index, and facet when glibc is the C library (ctypes)."""
    import ctypes
    lib = ctypes.CDLL(os.path.join(folder, "libprobe.so"))
    lib.probe.restype = ctypes.c_long
    lib.probe.argtypes = [ctypes.c_long, ctypes.c_long, ctypes.c_long]
    out = []
    for kind in range(lib.probe(-1, 0, 0)):
        count, facets = lib.probe(kind, -1, 0), lib.probe(kind, -2, 0)
        for index in range(count):
            for facet in range(facets):
                out.append(str(lib.probe(kind, index, facet)))
    return out


EXPECTED_TAIL = ["hello from C", "!", "to stdout", "7", "strlen bound", "symbolMissing", "15", "symbolMissing",
                 "notFound", "notFound"]

PROBE_DSL = r'''module probetour "Load shared libraries with the runtime's loader and print what their probes give"
  path probetour
  imports standard.console standard.ffi standard.compare standard.math
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability probeLibrary "Authority to load the probe library" load ffi.libraries "./libprobe.so"

capability bareLibrary "Authority to load the library linked with no C library" load ffi.libraries "./libbare.so"

capability badLibrary "Authority to load a file that is not a library" load ffi.libraries "./libbad.so"

capability missingLibrary "Authority to load a library no file has" load ffi.libraries "./libnothere.so"

capability probeSymbol "Authority to bind probe" load ffi.symbols "probe"

capability helloSymbol "Authority to bind probe_hello" load ffi.symbols "probe_hello"

capability strlenSymbol "Authority to bind strlen" load ffi.symbols "strlen"

capability bareSymbol "Authority to bind bare_length" load ffi.symbols "bare_length"

capability missingSymbol "Authority to bind a name no library has" load ffi.symbols "semanticscriptNoSuchSymbol"

optype ProbeFunction "long probe(long kind, long index, long facet)"
  input kind Int64 copied
  input index Int64 copied
  input facet Int64 copied
  output Int64

optype LongFunction "long f(long)"
  input value Int64 copied
  output Int64

instance ProbeBinding "Binds the probe library's probe" ffi.Function ProbeFunction

instance LongBinding "Binds a C function of a long" ffi.Function LongFunction

op say "Write a line"
  input text String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeLine(text) ~
  return

op sayNumber "Write a whole number on a line"
  input value Int64 copied
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeIntegerLine(value) ~
  return

op probeAll "Write what probe gives for every kind, index, and facet"
  input callee ProbeFunction copied
  effect write console.stdout
  uses stdoutWriter
  let kind Int64 0 mut
  let index Int64 0 mut
  let facet Int64 0 mut
  let most Int64 1000000
:begin
  countKinds: kinds = *callee(minusOne=-1, zero=0, zero)
  goto eachKind
:eachKind loop=while max=most
  kindsDone: allKinds = compare.greaterOrEqualInt64(kind, kinds)
  if allKinds finish kindStart
:kindStart in=eachKind
  countIndices: count = *callee(kind, minusOne, zero)
  countFacets: facets = *callee(kind, minusTwo=-2, zero)
  set index zero
  goto eachIndex
:eachIndex loop=while max=most in=eachKind
  indicesDone: allIndices = compare.greaterOrEqualInt64(index, count)
  if allIndices nextKind indexStart
:indexStart in=eachIndex
  set facet zero
  goto eachFacet
:eachFacet loop=while max=most in=eachIndex
  facetsDone: allFacets = compare.greaterOrEqualInt64(facet, facets)
  if allFacets nextIndex probeOne
:probeOne in=eachFacet
  probeIt: value = *callee(kind, index, facet)
  showIt: sayNumber(value)
  stepFacet: nextFacetValue = math.addInt64(facet, one=1)
  set facet nextFacetValue
  goto eachFacet
:nextIndex in=eachIndex
  stepIndex: nextIndexValue = math.addInt64(index, one)
  set index nextIndexValue
  goto eachIndex
:nextKind in=eachKind
  stepKind: nextKindValue = math.addInt64(kind, one)
  set kind nextKindValue
  goto eachKind
:finish
  return

op probeLibraryTour "Bind and run the probe library's functions, strlen through its scope, and a name it lacks"
  input library ffi.Library borrowed
  effect load ffi.symbols
  effect write console.stdout
  uses probeSymbol
  uses helloSymbol
  uses strlenSymbol
  uses missingSymbol
  uses stdoutWriter
:begin
  bindProbe: probeFn = ProbeBinding.bind(library, probeName="probe") ? failed
  runProbes: probeAll(probeFn)
  bindHello: helloFn = LongBinding.bind(library, helloName="probe_hello") ? failed
  runHello: helloValue = *helloFn(zero=0)
  showHello: sayNumber(helloValue)
  bindStrlen: strlenFn = LongBinding.bind(library, strlenName="strlen") ? failed
  showStrlen: say(boundText="strlen bound")
  bindMissing: missingFn = LongBinding.bind(library, missingName="semanticscriptNoSuchSymbol") ! missingError
  iferr bindMissing reportMissing failed
:reportMissing
  showMissing: say(missingText="symbolMissing")
  return
:failed
  showFailed: say(failedText="failed")
  return

op bareLibraryTour "Bind the bare library's function, which calls strlen, and strlen, which its scope does not have"
  input library ffi.Library borrowed
  effect load ffi.symbols
  effect write console.stdout
  uses bareSymbol
  uses strlenSymbol
  uses stdoutWriter
:begin
  bindBare: bareFn = LongBinding.bind(library, bareName="bare_length") ? failed
  runBare: bareValue = *bareFn(one=1)
  showBare: sayNumber(bareValue)
  bindStrlen: strlenFn = LongBinding.bind(library, strlenName="strlen") ! strlenError
  iferr bindStrlen reportMissing failed
:reportMissing
  showMissing: say(missingText="symbolMissing")
  return
:failed
  showFailed: say(failedText="failed")
  return

op main "Load the probe library, the bare one, a file that is not a library, and a library no file has"
  output ExitCode
  effect load ffi.libraries
  effect load ffi.symbols
  effect write console.stdout
  uses probeLibrary
  uses bareLibrary
  uses badLibrary
  uses missingLibrary
  uses probeSymbol
  uses helloSymbol
  uses strlenSymbol
  uses bareSymbol
  uses missingSymbol
  uses stdoutWriter
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  openProbe: probe = ffi.open(probeName="./libprobe.so") ? failed
  tourProbe: probeLibraryTour(probe)
  closeProbe: ffi.close(probe)
  openBare: bare = ffi.open(bareName="./libbare.so") ? failed
  tourBare: bareLibraryTour(bare)
  closeBare: ffi.close(bare)
  openBad: bad = ffi.open(badName="./libbad.so") ! badError
  iferr openBad badRefused badOpened
:badOpened
  closeBad: ffi.close(bad)
  showOpened: say(openedText="opened")
  goto missing
:badRefused
  showBad: say(notFoundText="notFound")
  goto missing
:missing
  openMissing: nothing = ffi.open(nothingName="./libnothere.so") ! missingError
  iferr openMissing missingRefused missingOpened
:missingOpened
  closeNothing: ffi.close(nothing)
  showMissingOpened: say(openedText)
  return okCode
:missingRefused
  showMissing: say(notFoundText)
  return okCode
:failed
  return failCode
'''

REFUSE_DSL = r'''module refusetour "Load a library the runtime's loader cannot load right, named by the first argument"
  path refusetour
  imports standard.console standard.ffi standard.process
  exports main

capability stdoutWriter "Authority to write lines to standard output" write console.stdout none

capability tlsLibrary "Authority to load a library with thread-local storage" load ffi.libraries "./libtls.so"

capability ifuncLibrary "Authority to load a library with an ifunc" load ffi.libraries "./libifunc.so"

capability undefinedLibrary "Authority to load a library that needs a function nothing defines" load ffi.libraries "./libundefined.so"

capability argumentReader "Authority to read the program's arguments" read process.arguments none

op say "Write a line"
  input text String borrowed
  effect write console.stdout
  uses stdoutWriter
:begin
  write: console.writeLine(text) ~
  return

op main "Open the library the first argument names and say whether it opened"
  output ExitCode
  effect load ffi.libraries
  effect read process.arguments
  effect write console.stdout
  uses argumentReader
  uses tlsLibrary
  uses ifuncLibrary
  uses undefinedLibrary
  uses stdoutWriter
  region names 4096
  let okCode ExitCode 0
  let failCode ExitCode 1
:begin
  readName: name = process.argument(first=0, names) ? failed
  openIt: library = ffi.open(name) ! openError
  iferr openIt refused opened
:opened
  closeIt: ffi.close(library)
  showOpened: say(openedText="loaded")
  return okCode
:refused
  showRefused: say(notFoundText="notFound")
  return okCode
:failed
  return failCode
'''


def write_project(folder: str, which: str) -> None:
    """The project of one tour (`probetour` or `refusetour`): build.sem and its module, generated from its DSL."""
    from semgen import Generator, Module, Program
    from caselib import allows_rows
    dsl = PROBE_DSL if which == "probetour" else REFUSE_DSL
    prog = Program()
    m = Module(which)
    prog.modules[which] = m
    g = Generator(prog, m)
    g.declare(dsl)
    g.parse(dsl)
    sem, _tests = g.render([f"# Shared libraries through the runtime's loader (tests/loadtour.py)."], None)
    owner, target, lines = "", "", []
    for line in sem.split("\n"):
        parts = line.split()
        if len(parts) == 3 and parts[1] == "in":
            owner = parts[2]
        if len(parts) == 3 and parts[1] == "invokes":
            target = parts[2]
        if len(parts) == 3 and parts[1] == "ownedBy" and parts[2] == "none" and target == "ffi.open":
            line = line.replace("ownedBy none", f"ownedBy {owner}")
        lines.append(line)
    sem = "\n".join(lines)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, f"{which}.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(sem)
    rows = ["tourProject is project", 'tourProject purpose "Load shared libraries with the runtime\'s loader"',
            "tourProject target console", 'tourProject version "0.1.0"', "tourProject language refined 1",
            "tourProject standardLibrary 1", *allows_rows("tourProject", [sem]), "tourProject requires none",
            f"tourProject includesModule {which}", f"tourProject entry {which}.main"]
    with open(os.path.join(folder, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(rows) + "\n")
