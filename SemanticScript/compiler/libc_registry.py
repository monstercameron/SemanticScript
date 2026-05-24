"""
libc_registry.py — comprehensive C standard library function signatures.

Each entry maps an SemanticScript call target of the form `c.<funcName>` to a
tuple:

    (return_type, [param_type, …], var_args)

where each type is a spec-compliant SemanticScript alias declared in
semsc.py's `llvm_type_for`. Every name carries width + signedness, or an
explicit ABI role, or the encoding contract for pointer-shaped types
(spec §6, §10):

    Int8, UInt8             i8
    Int16, UInt16           i16
    Int32, UInt32           i32
    Int64, UInt64           i64
    ByteCount, SignedByteCount,
        AddressOffset,
        UnixSecondsSinceEpoch,
        CpuClockTicks,
        FileByteOffset,
        DurationMilliseconds,
        MonotonicMilliseconds,
        UtcMilliseconds                     i64 (role aliases)
    Float32                               f32
    Float64                               f64
    String              i8*
    OpaquePointer                   i8*
    FileHandle                            i8*  (FILE *)
    DecomposedTimeAddress                 i8*  (struct tm *)
    SetjmpRegisterBuffer                  i8*  (jmp_buf)
    Bool                                   i1
    Void                                   void

The registry uses the current canonical primitive and role spellings
throughout. Callers should reference the current surface directly rather
than relying on older alias names.

This file aims for C90 + C99 + C11 coverage of the freestanding and hosted
standard library function set as defined by ISO/IEC 9899. Functions that
are spec-defined as macros (assert, va_*, offsetof, isnan-when-NAN-disabled,
etc.) are NOT exposed here — they require lexical rewriting, not an external
call. Functions that exist in the spec but have implementation-defined
ABI on Windows (e.g. lround returning long) use the canonical i64 lowering.

The registry is the single source of truth for `c.*` call targets. The
compiler reads it on demand: when an SemanticScript program calls `c.fname`,
the compiler looks up the signature, declares `LLVMfname` as an external,
and emits a direct call. There is no SemanticScript-side trampoline, so the
call cost is the same as a native C call to the same libc function.

camelCase SemanticScript-facing aliases
---------------------------
SemanticScript source code, per spec §5, restricts identifier punctuation to
`.`, `"`, `#`, and `/` — the underscore character `_` is NOT a legal
identifier character. A number of C standard library functions, however,
carry underscores in their canonical symbol names (e.g. `aligned_alloc`,
`thrd_create`, `mtx_lock`, `memcpy_s`, `_Exit`, `timespec_get`). To let
SemanticScript programs invoke these targets without violating the lexical
rules, this module publishes `SEMANTICSCRIPT_FACING_ALIASES`, a dict mapping
spec-legal camelCase names (e.g. `alignedAlloc`, `threadCreate`,
`mutexLock`, `memcpySafe`, `processExitWithoutCleanup`, `timespecGet`)
to their underscored C symbol. The dispatcher should route calls through
`resolve_c_symbol(semantic_name)` before consulting `ALL_FUNCTIONS`.

The original underscored keys remain in `ALL_FUNCTIONS` for backward
compatibility with internal code paths and prior-generation programs;
the camelCase aliases are purely additive. New SemanticScript source should
always prefer the camelCase form because it is the only form the parser
will accept.
"""

# ---- <stdio.h> ----
STDIO = {
    "printf":     ("Int32", ["String"], True),
    "fprintf":    ("Int32", ["FileHandle", "String"], True),
    "sprintf":    ("Int32", ["String", "String"], True),
    "snprintf":   ("Int32", ["String", "ByteCount", "String"], True),
    "vprintf":    ("Int32", ["String", "OpaquePointer"], False),
    "vfprintf":   ("Int32", ["FileHandle", "String", "OpaquePointer"], False),
    "vsprintf":   ("Int32", ["String", "String", "OpaquePointer"], False),
    "vsnprintf":  ("Int32", ["String", "ByteCount", "String", "OpaquePointer"], False),
    "scanf":      ("Int32", ["String"], True),
    "fscanf":     ("Int32", ["FileHandle", "String"], True),
    "sscanf":     ("Int32", ["String", "String"], True),
    "vscanf":     ("Int32", ["String", "OpaquePointer"], False),
    "vfscanf":    ("Int32", ["FileHandle", "String", "OpaquePointer"], False),
    "vsscanf":    ("Int32", ["String", "String", "OpaquePointer"], False),
    "fopen":      ("FileHandle", ["String", "String"], False),
    "freopen":    ("FileHandle", ["String", "String", "FileHandle"], False),
    "fclose":     ("Int32", ["FileHandle"], False),
    "fflush":     ("Int32", ["FileHandle"], False),
    "fread":      ("ByteCount", ["OpaquePointer", "ByteCount", "ByteCount", "FileHandle"], False),
    "fwrite":     ("ByteCount", ["OpaquePointer", "ByteCount", "ByteCount", "FileHandle"], False),
    "fseek":      ("Int32", ["FileHandle", "Int64", "Int32"], False),
    "ftell":      ("Int64", ["FileHandle"], False),
    "fsetpos":    ("Int32", ["FileHandle", "OpaquePointer"], False),
    "fgetpos":    ("Int32", ["FileHandle", "OpaquePointer"], False),
    "rewind":     ("Void", ["FileHandle"], False),
    "fgetc":      ("Int32", ["FileHandle"], False),
    "fputc":      ("Int32", ["Int32", "FileHandle"], False),
    "getc":       ("Int32", ["FileHandle"], False),
    "putc":       ("Int32", ["Int32", "FileHandle"], False),
    "getchar":    ("Int32", [], False),
    "putchar":    ("Int32", ["Int32"], False),
    "fgets":      ("String", ["String", "Int32", "FileHandle"], False),
    "fputs":      ("Int32", ["String", "FileHandle"], False),
    "gets_s":     ("String", ["String", "ByteCount"], False),
    "puts":       ("Int32", ["String"], False),
    "ungetc":     ("Int32", ["Int32", "FileHandle"], False),
    "feof":       ("Int32", ["FileHandle"], False),
    "ferror":     ("Int32", ["FileHandle"], False),
    "clearerr":   ("Void", ["FileHandle"], False),
    "perror":     ("Void", ["String"], False),
    "remove":     ("Int32", ["String"], False),
    "rename":     ("Int32", ["String", "String"], False),
    "tmpfile":    ("FileHandle", [], False),
    "tmpnam":     ("String", ["String"], False),
    "setbuf":     ("Void", ["FileHandle", "String"], False),
    "setvbuf":    ("Int32", ["FileHandle", "String", "Int32", "ByteCount"], False),
}

# ---- <conio.h> Windows console helpers ----
CONIO = {
    "_getch":     ("Int32", [], False),
}

# ---- SemanticScript native terminal adapter ----
SEM_TERMINAL = {
    "ss_terminal_enable_raw":      ("Int32", [], False),
    "ss_terminal_disable_raw":     ("Int32", [], False),
    "ss_terminal_read_key":        ("Int32", [], False),
    "ss_terminal_get_window_rows": ("Int64", [], False),
    "ss_terminal_get_window_cols": ("Int64", [], False),
    "ss_terminal_first_argument":  ("String", [], False),
}

# ---- <stdlib.h> ----
# Non-cryptographic PRNG symbols (CWE-338). Single source of truth for the
# SS4601 security rule (semsc derives its target set from this; the semlint
# floor mirrors it under a parity test). Listing the full POSIX `random`/
# `drand48` family — not just the `rand`/`srand` wired in STDLIB today — makes
# the rule forward-safe: if any of these is later added as a callable target it
# is automatically covered. `rand_s` (Windows CSPRNG) is deliberately absent.
INSECURE_PRNG_SYMBOLS = frozenset({
    "rand", "srand", "random", "srandom", "rand_r", "random_r",
    "drand48", "lrand48", "mrand48", "srand48", "seed48", "lcong48",
    "initstate", "setstate",
})

STDLIB = {
    "malloc":     ("OpaquePointer", ["ByteCount"], False),
    "calloc":     ("OpaquePointer", ["ByteCount", "ByteCount"], False),
    "realloc":    ("OpaquePointer", ["OpaquePointer", "ByteCount"], False),
    "free":       ("Void", ["OpaquePointer"], False),
    "aligned_alloc": ("OpaquePointer", ["ByteCount", "ByteCount"], False),
    "exit":       ("Void", ["Int32"], False),
    "_Exit":      ("Void", ["Int32"], False),
    "quick_exit": ("Void", ["Int32"], False),
    "atexit":     ("Int32", ["OpaquePointer"], False),
    "at_quick_exit": ("Int32", ["OpaquePointer"], False),
    "abort":      ("Void", [], False),
    "atoi":       ("Int32", ["String"], False),
    "atol":       ("Int64", ["String"], False),
    "atoll":      ("Int64", ["String"], False),
    "atof":       ("Float64", ["String"], False),
    "strtol":     ("Int64", ["String", "OpaquePointer", "Int32"], False),
    "strtoll":    ("Int64", ["String", "OpaquePointer", "Int32"], False),
    "strtoul":    ("Int64", ["String", "OpaquePointer", "Int32"], False),
    "strtoull":   ("Int64", ["String", "OpaquePointer", "Int32"], False),
    "strtof":     ("Float32", ["String", "OpaquePointer"], False),
    "strtod":     ("Float64", ["String", "OpaquePointer"], False),
    "strtold":    ("Float64", ["String", "OpaquePointer"], False),
    "strtoimax":  ("Int64", ["String", "OpaquePointer", "Int32"], False),
    "strtoumax":  ("Int64", ["String", "OpaquePointer", "Int32"], False),
    "rand":       ("Int32", [], False),
    "srand":      ("Void", ["UInt32"], False),
    "rand_s":     ("Int32", ["OpaquePointer"], False),
    "qsort":      ("Void", ["OpaquePointer", "ByteCount", "ByteCount", "OpaquePointer"], False),
    "qsort_s":    ("Int32", ["OpaquePointer", "ByteCount", "ByteCount", "OpaquePointer", "OpaquePointer"], False),
    "bsearch":    ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount", "ByteCount", "OpaquePointer"], False),
    "abs":        ("Int32", ["Int32"], False),
    "labs":       ("Int64", ["Int64"], False),
    "llabs":      ("Int64", ["Int64"], False),
    "div":        ("Int64", ["Int32", "Int32"], False),
    "ldiv":       ("Int64", ["Int64", "Int64"], False),
    "lldiv":      ("Int64", ["Int64", "Int64"], False),
    "imaxabs":    ("Int64", ["Int64"], False),
    "imaxdiv":    ("Int64", ["Int64", "Int64"], False),
    "getenv":     ("String", ["String"], False),
    "getenv_s":   ("Int32", ["OpaquePointer", "String", "ByteCount", "String"], False),
    "system":     ("Int32", ["String"], False),
    "mblen":      ("Int32", ["String", "ByteCount"], False),
    "mbtowc":     ("Int32", ["OpaquePointer", "String", "ByteCount"], False),
    "wctomb":     ("Int32", ["String", "Int32"], False),
    "mbstowcs":   ("ByteCount", ["OpaquePointer", "String", "ByteCount"], False),
    "wcstombs":   ("ByteCount", ["String", "OpaquePointer", "ByteCount"], False),
}

# ---- <string.h> ----
STRING = {
    "strlen":     ("ByteCount", ["String"], False),
    "strnlen_s":  ("ByteCount", ["String", "ByteCount"], False),
    "strcpy":     ("String", ["String", "String"], False),
    "strncpy":    ("String", ["String", "String", "ByteCount"], False),
    "strcpy_s":   ("Int32", ["String", "ByteCount", "String"], False),
    "strncpy_s":  ("Int32", ["String", "ByteCount", "String", "ByteCount"], False),
    "strcat":     ("String", ["String", "String"], False),
    "strncat":    ("String", ["String", "String", "ByteCount"], False),
    "strcat_s":   ("Int32", ["String", "ByteCount", "String"], False),
    "strncat_s":  ("Int32", ["String", "ByteCount", "String", "ByteCount"], False),
    "strcmp":     ("Int32", ["String", "String"], False),
    "strncmp":    ("Int32", ["String", "String", "ByteCount"], False),
    "strcoll":    ("Int32", ["String", "String"], False),
    "strxfrm":    ("ByteCount", ["String", "String", "ByteCount"], False),
    "strchr":     ("String", ["String", "Int32"], False),
    "strrchr":    ("String", ["String", "Int32"], False),
    "strspn":     ("ByteCount", ["String", "String"], False),
    "strcspn":    ("ByteCount", ["String", "String"], False),
    "strpbrk":    ("String", ["String", "String"], False),
    "strstr":     ("String", ["String", "String"], False),
    "strtok":     ("String", ["String", "String"], False),
    "strtok_s":   ("String", ["String", "OpaquePointer", "String", "OpaquePointer"], False),
    "memcpy":     ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "memcpy_s":   ("Int32", ["OpaquePointer", "ByteCount", "OpaquePointer", "ByteCount"], False),
    "memmove":    ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "memmove_s":  ("Int32", ["OpaquePointer", "ByteCount", "OpaquePointer", "ByteCount"], False),
    "memcmp":     ("Int32", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "memchr":     ("OpaquePointer", ["OpaquePointer", "Int32", "ByteCount"], False),
    "memset":     ("OpaquePointer", ["OpaquePointer", "Int32", "ByteCount"], False),
    "memset_s":   ("Int32", ["OpaquePointer", "ByteCount", "Int32", "ByteCount"], False),
    "strerror":   ("String", ["Int32"], False),
    "strerror_s": ("Int32", ["String", "ByteCount", "Int32"], False),
    "strerrorlen_s": ("ByteCount", ["Int32"], False),
}

# ---- <math.h> ----  (signatures use Float64 universally; the float-suffix
# `f` variants take/return Float32 and the long-double `l` variants take/return
# Float64 — long double is treated as double for ABI parity.)
def _math_double(name):
    return (name, ("Float64", ["Float64"], False))


def _math_double_2(name):
    return (name, ("Float64", ["Float64", "Float64"], False))


MATH = dict([
    _math_double("sin"), _math_double("cos"), _math_double("tan"),
    _math_double("asin"), _math_double("acos"), _math_double("atan"),
    _math_double_2("atan2"),
    _math_double("sinh"), _math_double("cosh"), _math_double("tanh"),
    _math_double("asinh"), _math_double("acosh"), _math_double("atanh"),
    _math_double("exp"), _math_double("exp2"), _math_double("expm1"),
    _math_double("log"), _math_double("log10"), _math_double("log2"),
    _math_double("log1p"),
    _math_double_2("pow"),
    _math_double("sqrt"), _math_double("cbrt"),
    _math_double_2("hypot"),
    _math_double("ceil"), _math_double("floor"),
    _math_double_2("fmod"),
    _math_double("trunc"), _math_double("round"),
    ("lround", ("Int64", ["Float64"], False)),
    ("llround", ("Int64", ["Float64"], False)),
    _math_double("rint"),
    ("lrint", ("Int64", ["Float64"], False)),
    ("llrint", ("Int64", ["Float64"], False)),
    _math_double("nearbyint"),
    ("frexp", ("Float64", ["Float64", "OpaquePointer"], False)),
    ("ldexp", ("Float64", ["Float64", "Int32"], False)),
    ("modf", ("Float64", ["Float64", "OpaquePointer"], False)),
    ("scalbn", ("Float64", ["Float64", "Int32"], False)),
    ("scalbln", ("Float64", ["Float64", "Int64"], False)),
    ("ilogb", ("Int32", ["Float64"], False)),
    _math_double("logb"),
    _math_double_2("copysign"),
    _math_double_2("nextafter"),
    _math_double_2("nexttoward"),
    _math_double_2("fdim"),
    _math_double_2("fmax"),
    _math_double_2("fmin"),
    ("fma", ("Float64", ["Float64", "Float64", "Float64"], False)),
    _math_double("fabs"),
    _math_double("erf"), _math_double("erfc"),
    _math_double("lgamma"), _math_double("tgamma"),
    # NOTE: signbit / isfinite / isinf / isnan / isnormal / fpclassify are
    # spec-defined as macros in <math.h>, not externs. They are intercepted
    # in semsc._emit_run and lowered to LLVM fcmp / bit-twiddling instead of
    # extern calls. Listing them here would yield link errors against most
    # libc implementations.
    # extra C99 double-precision functions
    _math_double_2("remainder"),
    ("remquo", ("Float64", ["Float64", "Float64", "OpaquePointer"], False)),
    ("nan", ("Float64", ["String"], False)),
    ("nanf", ("Float32", ["String"], False)),
    ("nanl", ("Float64", ["String"], False)),
])

# All C99 math functions also exist in `<name>f` (float) and `<name>l`
# (long-double) variants. We declare the float and long-double variants
# programmatically; on x86-64 Windows the long-double ABI happens to match
# double for our purposes, so `<name>l` lowers to the same primitive.
_FL_VARIANTS = [
    "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
    "sinh", "cosh", "tanh", "asinh", "acosh", "atanh",
    "exp", "exp2", "expm1", "log", "log10", "log2", "log1p",
    "pow", "sqrt", "cbrt", "hypot",
    "ceil", "floor", "fmod", "trunc", "round", "rint", "nearbyint",
    "scalbn", "scalbln", "logb",
    "copysign", "nextafter", "nexttoward",
    "fdim", "fmax", "fmin", "fma",
    "fabs", "erf", "erfc", "lgamma", "tgamma",
    "remainder", "remquo",
]

# Each entry above gets `f` (float ABI) and `l` (long double ABI) suffix
# declarations. The arity of the original `name` (already in MATH) drives
# the variant signature. `l` is treated as double on Windows x86-64.
for _stem in _FL_VARIANTS:
    base = MATH.get(_stem)
    if base is None:
        continue
    _ret, _params, _vararg = base
    # Float variant: every Float64 becomes Float32. We special-case `ldexp`
    # and `scalbn` which keep an int second arg.
    def _to_float(t):
        return "Float32" if t == "Float64" else t
    _f_ret = _to_float(_ret)
    _f_params = [_to_float(p) for p in _params]
    MATH[_stem + "f"] = (_f_ret, _f_params, _vararg)
    # Long-double variant: identical to double on this ABI.
    MATH[_stem + "l"] = (_ret, _params, _vararg)

# `ldexp` and `frexp` are listed in MATH already with mixed types — handle
# their f/l variants explicitly to preserve the Int32/OpaquePointer second arg.
MATH["ldexpf"] = ("Float32", ["Float32", "Int32"], False)
MATH["ldexpl"] = ("Float64", ["Float64", "Int32"], False)
MATH["frexpf"] = ("Float32", ["Float32", "OpaquePointer"], False)
MATH["frexpl"] = ("Float64", ["Float64", "OpaquePointer"], False)
MATH["modff"]  = ("Float32", ["Float32", "OpaquePointer"], False)
MATH["modfl"]  = ("Float64", ["Float64", "OpaquePointer"], False)
MATH["ilogbf"] = ("Int32", ["Float32"], False)
MATH["ilogbl"] = ("Int32", ["Float64"], False)
MATH["lroundf"] = ("Int64", ["Float32"], False)
MATH["lroundl"] = ("Int64", ["Float64"], False)
MATH["llroundf"] = ("Int64", ["Float32"], False)
MATH["llroundl"] = ("Int64", ["Float64"], False)
MATH["lrintf"] = ("Int64", ["Float32"], False)
MATH["lrintl"] = ("Int64", ["Float64"], False)
MATH["llrintf"] = ("Int64", ["Float32"], False)
MATH["llrintl"] = ("Int64", ["Float64"], False)

# ---- <ctype.h> ----
CTYPE = {
    "isalpha":    ("Int32", ["Int32"], False),
    "isdigit":    ("Int32", ["Int32"], False),
    "isalnum":    ("Int32", ["Int32"], False),
    "isspace":    ("Int32", ["Int32"], False),
    "isupper":    ("Int32", ["Int32"], False),
    "islower":    ("Int32", ["Int32"], False),
    "iscntrl":    ("Int32", ["Int32"], False),
    "isprint":    ("Int32", ["Int32"], False),
    "ispunct":    ("Int32", ["Int32"], False),
    "isxdigit":   ("Int32", ["Int32"], False),
    "isblank":    ("Int32", ["Int32"], False),
    "isgraph":    ("Int32", ["Int32"], False),
    "toupper":    ("Int32", ["Int32"], False),
    "tolower":    ("Int32", ["Int32"], False),
}

# ---- <time.h> ----
TIME = {
    "time":       ("UnixSecondsSinceEpoch", ["OpaquePointer"], False),
    "clock":      ("CpuClockTicks", [], False),
    "difftime":   ("Float64", ["UnixSecondsSinceEpoch", "UnixSecondsSinceEpoch"], False),
    "mktime":     ("UnixSecondsSinceEpoch", ["OpaquePointer"], False),
    "gmtime":     ("DecomposedTimeAddress", ["OpaquePointer"], False),
    "localtime":  ("DecomposedTimeAddress", ["OpaquePointer"], False),
    "asctime":    ("String", ["OpaquePointer"], False),
    "ctime":      ("String", ["OpaquePointer"], False),
    "strftime":   ("ByteCount", ["String", "ByteCount", "String", "OpaquePointer"], False),
    "timespec_get": ("Int32", ["OpaquePointer", "Int32"], False),
}

# ---- <setjmp.h> ----
SETJMP = {
    "setjmp":     ("Int32", ["SetjmpRegisterBuffer"], False),
    "longjmp":    ("Void", ["SetjmpRegisterBuffer", "Int32"], False),
}

# ---- <signal.h> ----
SIGNAL = {
    "signal":     ("OpaquePointer", ["Int32", "OpaquePointer"], False),
    "raise":      ("Int32", ["Int32"], False),
}

# ---- <locale.h> ----
LOCALE = {
    "setlocale":  ("String", ["Int32", "String"], False),
    "localeconv": ("OpaquePointer", [], False),
}

# ---- <wchar.h> — full C99 surface ----
WCHAR = {
    # string-length & search
    "wcslen":     ("ByteCount", ["OpaquePointer"], False),
    "wcsnlen_s":  ("ByteCount", ["OpaquePointer", "ByteCount"], False),
    "wcschr":     ("OpaquePointer", ["OpaquePointer", "Int32"], False),
    "wcsrchr":    ("OpaquePointer", ["OpaquePointer", "Int32"], False),
    "wcsstr":     ("OpaquePointer", ["OpaquePointer", "OpaquePointer"], False),
    "wcspbrk":    ("OpaquePointer", ["OpaquePointer", "OpaquePointer"], False),
    "wcsspn":     ("ByteCount", ["OpaquePointer", "OpaquePointer"], False),
    "wcscspn":    ("ByteCount", ["OpaquePointer", "OpaquePointer"], False),
    "wcstok":     ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "OpaquePointer"], False),
    # comparison
    "wcscmp":     ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "wcsncmp":    ("Int32", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "wcscoll":    ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "wcsxfrm":    ("ByteCount", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    # copy / concat
    "wcscpy":     ("OpaquePointer", ["OpaquePointer", "OpaquePointer"], False),
    "wcsncpy":    ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "wcscat":     ("OpaquePointer", ["OpaquePointer", "OpaquePointer"], False),
    "wcsncat":    ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    # wmemory
    "wmemcpy":    ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "wmemmove":   ("OpaquePointer", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "wmemcmp":    ("Int32", ["OpaquePointer", "OpaquePointer", "ByteCount"], False),
    "wmemchr":    ("OpaquePointer", ["OpaquePointer", "Int32", "ByteCount"], False),
    "wmemset":    ("OpaquePointer", ["OpaquePointer", "Int32", "ByteCount"], False),
    # numeric conversion
    "wcstol":     ("Int64", ["OpaquePointer", "OpaquePointer", "Int32"], False),
    "wcstoll":    ("Int64", ["OpaquePointer", "OpaquePointer", "Int32"], False),
    "wcstoul":    ("Int64", ["OpaquePointer", "OpaquePointer", "Int32"], False),
    "wcstoull":   ("Int64", ["OpaquePointer", "OpaquePointer", "Int32"], False),
    "wcstof":     ("Float32", ["OpaquePointer", "OpaquePointer"], False),
    "wcstod":     ("Float64", ["OpaquePointer", "OpaquePointer"], False),
    "wcstold":    ("Float64", ["OpaquePointer", "OpaquePointer"], False),
    "wcstoimax":  ("Int64", ["OpaquePointer", "OpaquePointer", "Int32"], False),
    "wcstoumax":  ("Int64", ["OpaquePointer", "OpaquePointer", "Int32"], False),
    # time formatting
    "wcsftime":   ("ByteCount", ["OpaquePointer", "ByteCount", "OpaquePointer", "OpaquePointer"], False),
    # wide formatted I/O
    "wprintf":    ("Int32", ["OpaquePointer"], True),
    "fwprintf":   ("Int32", ["FileHandle", "OpaquePointer"], True),
    "swprintf":   ("Int32", ["OpaquePointer", "ByteCount", "OpaquePointer"], True),
    "vwprintf":   ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "vfwprintf":  ("Int32", ["FileHandle", "OpaquePointer", "OpaquePointer"], False),
    "vswprintf":  ("Int32", ["OpaquePointer", "ByteCount", "OpaquePointer", "OpaquePointer"], False),
    "wscanf":     ("Int32", ["OpaquePointer"], True),
    "fwscanf":    ("Int32", ["FileHandle", "OpaquePointer"], True),
    "swscanf":    ("Int32", ["OpaquePointer", "OpaquePointer"], True),
    "vwscanf":    ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "vfwscanf":   ("Int32", ["FileHandle", "OpaquePointer", "OpaquePointer"], False),
    "vswscanf":   ("Int32", ["OpaquePointer", "OpaquePointer", "OpaquePointer"], False),
    # wide character I/O
    "fgetwc":     ("Int32", ["FileHandle"], False),
    "fputwc":     ("Int32", ["Int32", "FileHandle"], False),
    "getwc":      ("Int32", ["FileHandle"], False),
    "putwc":      ("Int32", ["Int32", "FileHandle"], False),
    "getwchar":   ("Int32", [], False),
    "putwchar":   ("Int32", ["Int32"], False),
    "fgetws":     ("OpaquePointer", ["OpaquePointer", "Int32", "FileHandle"], False),
    "fputws":     ("Int32", ["OpaquePointer", "FileHandle"], False),
    "ungetwc":    ("Int32", ["Int32", "FileHandle"], False),
    "fwide":      ("Int32", ["FileHandle", "Int32"], False),
    # multibyte conversion
    "mbsinit":    ("Int32", ["OpaquePointer"], False),
    "mbrlen":     ("ByteCount", ["OpaquePointer", "ByteCount", "OpaquePointer"], False),
    "mbrtowc":    ("ByteCount", ["OpaquePointer", "OpaquePointer", "ByteCount", "OpaquePointer"], False),
    "wcrtomb":    ("ByteCount", ["OpaquePointer", "Int32", "OpaquePointer"], False),
    "mbsrtowcs":  ("ByteCount", ["OpaquePointer", "OpaquePointer", "ByteCount", "OpaquePointer"], False),
    "wcsrtombs":  ("ByteCount", ["OpaquePointer", "OpaquePointer", "ByteCount", "OpaquePointer"], False),
    "btowc":      ("Int32", ["Int32"], False),
    "wctob":      ("Int32", ["Int32"], False),
}

# ---- <fenv.h> — C99 floating-point environment ----
FENV = {
    "feclearexcept":  ("Int32", ["Int32"], False),
    "fegetexceptflag": ("Int32", ["OpaquePointer", "Int32"], False),
    "feraiseexcept":  ("Int32", ["Int32"], False),
    "fesetexceptflag": ("Int32", ["OpaquePointer", "Int32"], False),
    "fetestexcept":   ("Int32", ["Int32"], False),
    "fegetround":     ("Int32", [], False),
    "fesetround":     ("Int32", ["Int32"], False),
    "fegetenv":       ("Int32", ["OpaquePointer"], False),
    "fesetenv":       ("Int32", ["OpaquePointer"], False),
    "feholdexcept":   ("Int32", ["OpaquePointer"], False),
    "feupdateenv":    ("Int32", ["OpaquePointer"], False),
}

# ---- <complex.h> — C99 complex math (declarations only) ----
# Complex doubles are spec-defined as `_Complex double` which has no clean
# LLVM lowering at the IR level; on x86-64 ABI they're passed as a pair of
# doubles. We declare them with the same shape and let the linker resolve;
# the SemanticScript-side type aliases CComplexDouble / CComplexFloat are not currently
# materialized but the declarations exist for completeness.
COMPLEX = {
    "cabs":    ("Float64", ["Float64", "Float64"], False),
    "carg":    ("Float64", ["Float64", "Float64"], False),
    "creal":   ("Float64", ["Float64", "Float64"], False),
    "cimag":   ("Float64", ["Float64", "Float64"], False),
    "conj":    ("Float64", ["Float64", "Float64"], False),
    "cproj":   ("Float64", ["Float64", "Float64"], False),
    "cexp":    ("Float64", ["Float64", "Float64"], False),
    "clog":    ("Float64", ["Float64", "Float64"], False),
    "cpow":    ("Float64", ["Float64", "Float64", "Float64", "Float64"], False),
    "csqrt":   ("Float64", ["Float64", "Float64"], False),
    "csin":    ("Float64", ["Float64", "Float64"], False),
    "ccos":    ("Float64", ["Float64", "Float64"], False),
    "ctan":    ("Float64", ["Float64", "Float64"], False),
    "casin":   ("Float64", ["Float64", "Float64"], False),
    "cacos":   ("Float64", ["Float64", "Float64"], False),
    "catan":   ("Float64", ["Float64", "Float64"], False),
    "csinh":   ("Float64", ["Float64", "Float64"], False),
    "ccosh":   ("Float64", ["Float64", "Float64"], False),
    "ctanh":   ("Float64", ["Float64", "Float64"], False),
    "casinh":  ("Float64", ["Float64", "Float64"], False),
    "cacosh":  ("Float64", ["Float64", "Float64"], False),
    "catanh":  ("Float64", ["Float64", "Float64"], False),
    # float variants
    "cabsf":   ("Float32", ["Float32", "Float32"], False),
    "csqrtf":  ("Float32", ["Float32", "Float32"], False),
    "csinf":   ("Float32", ["Float32", "Float32"], False),
    "ccosf":   ("Float32", ["Float32", "Float32"], False),
    "ctanf":   ("Float32", ["Float32", "Float32"], False),
    "cexpf":   ("Float32", ["Float32", "Float32"], False),
    "clogf":   ("Float32", ["Float32", "Float32"], False),
    "cpowf":   ("Float32", ["Float32", "Float32", "Float32", "Float32"], False),
    "crealf":  ("Float32", ["Float32", "Float32"], False),
    "cimagf":  ("Float32", ["Float32", "Float32"], False),
    "conjf":   ("Float32", ["Float32", "Float32"], False),
}

# ---- <uchar.h> — C11 char16/char32 conversions ----
UCHAR = {
    "mbrtoc16":  ("ByteCount", ["OpaquePointer", "OpaquePointer", "ByteCount", "OpaquePointer"], False),
    "c16rtomb":  ("ByteCount", ["OpaquePointer", "Int16", "OpaquePointer"], False),
    "mbrtoc32":  ("ByteCount", ["OpaquePointer", "OpaquePointer", "ByteCount", "OpaquePointer"], False),
    "c32rtomb":  ("ByteCount", ["OpaquePointer", "Int32", "OpaquePointer"], False),
}

# ---- <threads.h> — C11 optional threading (Annex K conditional) ----
THREADS = {
    "thrd_create":    ("Int32", ["OpaquePointer", "OpaquePointer", "OpaquePointer"], False),
    "thrd_equal":     ("Int32", ["Int64", "Int64"], False),
    "thrd_current":   ("Int64", [], False),
    "thrd_sleep":     ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "thrd_yield":     ("Void", [], False),
    "thrd_exit":      ("Void", ["Int32"], False),
    "thrd_detach":    ("Int32", ["Int64"], False),
    "thrd_join":      ("Int32", ["Int64", "OpaquePointer"], False),
    "mtx_init":       ("Int32", ["OpaquePointer", "Int32"], False),
    "mtx_lock":       ("Int32", ["OpaquePointer"], False),
    "mtx_trylock":    ("Int32", ["OpaquePointer"], False),
    "mtx_timedlock":  ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "mtx_unlock":     ("Int32", ["OpaquePointer"], False),
    "mtx_destroy":    ("Void", ["OpaquePointer"], False),
    "cnd_init":       ("Int32", ["OpaquePointer"], False),
    "cnd_signal":     ("Int32", ["OpaquePointer"], False),
    "cnd_broadcast":  ("Int32", ["OpaquePointer"], False),
    "cnd_wait":       ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "cnd_timedwait":  ("Int32", ["OpaquePointer", "OpaquePointer", "OpaquePointer"], False),
    "cnd_destroy":    ("Void", ["OpaquePointer"], False),
    "tss_create":     ("Int32", ["OpaquePointer", "OpaquePointer"], False),
    "tss_get":        ("OpaquePointer", ["Int64"], False),
    "tss_set":        ("Int32", ["Int64", "OpaquePointer"], False),
    "tss_delete":     ("Void", ["Int64"], False),
    "call_once":      ("Void", ["OpaquePointer", "OpaquePointer"], False),
}

# ---- <wctype.h> minimal ----
WCTYPE = {
    "iswalpha":   ("Int32", ["Int32"], False),
    "iswdigit":   ("Int32", ["Int32"], False),
    "iswspace":   ("Int32", ["Int32"], False),
    "towupper":   ("Int32", ["Int32"], False),
    "towlower":   ("Int32", ["Int32"], False),
}

# ---- merge everything into a single dispatch dict ----
ALL_FUNCTIONS = {}
for bucket in (STDIO, CONIO, SEM_TERMINAL, STDLIB, STRING, MATH, CTYPE, TIME,
               SETJMP, SIGNAL, LOCALE, WCHAR, WCTYPE,
               FENV, COMPLEX, UCHAR, THREADS):
    for name, sig in bucket.items():
        ALL_FUNCTIONS[name] = sig


# ---- SemanticScript-facing camelCase aliases ----
# Spec §5 forbids `_` in identifiers, so every libc symbol containing an
# underscore (plus a handful of cryptically-named C11 symbols like the
# `mbrtoc16` / `c32rtomb` family) is republished here under a camelCase
# alias. SemanticScript source code uses the keys on the left; the registry
# itself still keys signatures by the C symbol on the right. The compiler
# resolves SemanticScript-facing names through `resolve_c_symbol()` below.
SEMANTICSCRIPT_FACING_ALIASES = {
    # ---- <stdio.h> ----
    "getsSafe":                    "gets_s",
    # ---- <conio.h> ----
    "consoleGetch":                "_getch",
    # ---- SemanticScript native terminal adapter ----
    "terminalEnableRaw":           "ss_terminal_enable_raw",
    "terminalDisableRaw":          "ss_terminal_disable_raw",
    "terminalReadKey":             "ss_terminal_read_key",
    "terminalGetWindowRows":       "ss_terminal_get_window_rows",
    "terminalGetWindowCols":       "ss_terminal_get_window_cols",
    "terminalFirstArgument":       "ss_terminal_first_argument",
    # ---- <stdlib.h> ----
    "alignedAlloc":                "aligned_alloc",
    "processExitWithoutCleanup":   "_Exit",
    "quickExit":                   "quick_exit",
    "atQuickExit":                 "at_quick_exit",
    "randSafe":                    "rand_s",
    "qsortSafe":                   "qsort_s",
    "getenvSafe":                  "getenv_s",
    # ---- <string.h> ----
    "strnlenSafe":                 "strnlen_s",
    "strcpySafe":                  "strcpy_s",
    "strncpySafe":                 "strncpy_s",
    "strcatSafe":                  "strcat_s",
    "strncatSafe":                 "strncat_s",
    "strtokSafe":                  "strtok_s",
    "memcpySafe":                  "memcpy_s",
    "memmoveSafe":                 "memmove_s",
    "memsetSafe":                  "memset_s",
    "strerrorSafe":                "strerror_s",
    "strerrorLengthSafe":          "strerrorlen_s",
    # ---- <time.h> ----
    "timespecGet":                 "timespec_get",
    # ---- <wchar.h> ----
    "wcsnlenSafe":                 "wcsnlen_s",
    # ---- <uchar.h> (cryptic abbreviations, no underscores but unreadable) ----
    "multibyteRestartableToChar16": "mbrtoc16",
    "char16RestartableToMultibyte": "c16rtomb",
    "multibyteRestartableToChar32": "mbrtoc32",
    "char32RestartableToMultibyte": "c32rtomb",
    # ---- <threads.h> thrd_* → thread* ----
    "threadCreate":                "thrd_create",
    "threadEqual":                 "thrd_equal",
    "threadCurrent":               "thrd_current",
    "threadSleep":                 "thrd_sleep",
    "threadYield":                 "thrd_yield",
    "threadExit":                  "thrd_exit",
    "threadDetach":                "thrd_detach",
    "threadJoin":                  "thrd_join",
    # ---- <threads.h> mtx_* → mutex* ----
    "mutexInit":                   "mtx_init",
    "mutexLock":                   "mtx_lock",
    "mutexTryLock":                "mtx_trylock",
    "mutexTimedLock":              "mtx_timedlock",
    "mutexUnlock":                 "mtx_unlock",
    "mutexDestroy":                "mtx_destroy",
    # ---- <threads.h> cnd_* → condition* ----
    "conditionInit":               "cnd_init",
    "conditionSignal":             "cnd_signal",
    "conditionBroadcast":          "cnd_broadcast",
    "conditionWait":               "cnd_wait",
    "conditionTimedWait":          "cnd_timedwait",
    "conditionDestroy":            "cnd_destroy",
    # ---- <threads.h> tss_* → threadStorage* ----
    "threadStorageCreate":         "tss_create",
    "threadStorageGet":            "tss_get",
    "threadStorageSet":            "tss_set",
    "threadStorageDelete":         "tss_delete",
    # ---- <threads.h> misc ----
    "callOnce":                    "call_once",
}


def resolve_c_symbol(semantic_name: str) -> str:
    """Translate an SemanticScript-facing call target to its C symbol.

    SemanticScript source code is forbidden by spec §5 from using `_` in
    identifiers, so libc functions like `aligned_alloc` cannot be
    written directly as `c.aligned_alloc`. Instead, SemanticScript source writes
    the camelCase alias (e.g. `c.alignedAlloc`), and the compiler
    routes the call through this function to recover the underscored
    C symbol name (`aligned_alloc`) used by `ALL_FUNCTIONS` and by
    the linker.

    If `semantic_name` is already a legal C symbol (i.e. has no SemanticScript-facing
    alias registered), it is returned unchanged. This means call
    sites that pre-date the alias system, or that target functions
    without underscores in their C names, work without modification.
    """
    return SEMANTICSCRIPT_FACING_ALIASES.get(semantic_name, semantic_name)


# ---- standard <stdio.h> stream globals ----
# Three FILE* globals are exposed as the c.stdin / c.stdout / c.stderr
# call-time symbols. They are not call targets — they are operand symbols
# that resolve to extern globals declared on demand by the codegen.
STDIO_STREAMS = ("stdin", "stdout", "stderr")


# ---- <errno.h> ----
# errno is a thread-local int. Most C runtimes expose it through a function
# (`_errno` on MSVC, `__errno_location` on glibc) rather than a flat global.
# We expose `c.errnoGet` as the canonical SemanticScript accessor.
ERRNO_ACCESSOR = ("errnoGet", "Int32", [])


def coverage_summary() -> dict:
    """Return a {header: count} map summarizing the registry's coverage."""
    return {
        "stdio.h":   len(STDIO),
        "stdlib.h":  len(STDLIB),
        "string.h":  len(STRING),
        "math.h":    len(MATH),
        "ctype.h":   len(CTYPE),
        "time.h":    len(TIME),
        "setjmp.h":  len(SETJMP),
        "signal.h":  len(SIGNAL),
        "locale.h":  len(LOCALE),
        "wchar.h":   len(WCHAR),
        "wctype.h":  len(WCTYPE),
        "fenv.h":    len(FENV),
        "complex.h": len(COMPLEX),
        "uchar.h":   len(UCHAR),
        "threads.h": len(THREADS),
    }


if __name__ == "__main__":
    summary = coverage_summary()
    total = sum(summary.values())
    print(f"SemanticScript libc registry — {total} functions across {len(summary)} headers:")
    for k, v in summary.items():
        print(f"  {k:<12} {v:>3}")
