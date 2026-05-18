"""
libc_registry.py — comprehensive C standard library function signatures.

Each entry maps an SemanticScript call target of the form `c.<funcName>` to a
tuple:

    (return_type, [param_type, …], var_args)

where each type is a spec-compliant SemanticScript alias declared in
semsc.py's `llvm_type_for`. Every name carries width + signedness, or an
explicit ABI role, or the encoding contract for pointer-shaped types
(spec §6, §10):

    CSignedByte, CUnsignedByte             i8
    CSignedInt16, CUnsignedInt16           i16
    CSignedInt32, CUnsignedInt32           i32
    CSignedInt64, CUnsignedInt64           i64
    CByteCount, CSignedByteCount,
        CAddressOffset,
        CUnixSecondsSinceEpoch,
        CCpuClockTicks,
        CFileByteOffset,
        CMaxSignedInt, CMaxUnsignedInt     i64 (role aliases)
    CFloat32                               f32
    CFloat64                               f64
    CNullTerminatedByteString              i8*
    COpaqueMemoryAddress                   i8*
    CFileHandle                            i8*  (FILE *)
    CDecomposedTimeAddress                 i8*  (struct tm *)
    CSetjmpRegisterBuffer                  i8*  (jmp_buf)
    Bool                                   i1
    Void                                   void

The short legacy aliases (`CInt`, `CDouble`, `CSize`, `CString`,
`CVoidPtr`, `CFilePtr`, `CTm`, `CJmpBuf`, `CChar`, `CLong`, etc.) are
still accepted by `llvm_type_for` for backward compatibility with the
first revision of the registry.

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
    "printf":     ("CSignedInt32", ["CNullTerminatedByteString"], True),
    "fprintf":    ("CSignedInt32", ["CFileHandle", "CNullTerminatedByteString"], True),
    "sprintf":    ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString"], True),
    "snprintf":   ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString"], True),
    "vprintf":    ("CSignedInt32", ["CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "vfprintf":   ("CSignedInt32", ["CFileHandle", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "vsprintf":   ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "vsnprintf":  ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "scanf":      ("CSignedInt32", ["CNullTerminatedByteString"], True),
    "fscanf":     ("CSignedInt32", ["CFileHandle", "CNullTerminatedByteString"], True),
    "sscanf":     ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString"], True),
    "vscanf":     ("CSignedInt32", ["CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "vfscanf":    ("CSignedInt32", ["CFileHandle", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "vsscanf":    ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "fopen":      ("CFileHandle", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "freopen":    ("CFileHandle", ["CNullTerminatedByteString", "CNullTerminatedByteString", "CFileHandle"], False),
    "fclose":     ("CSignedInt32", ["CFileHandle"], False),
    "fflush":     ("CSignedInt32", ["CFileHandle"], False),
    "fread":      ("CByteCount", ["COpaqueMemoryAddress", "CByteCount", "CByteCount", "CFileHandle"], False),
    "fwrite":     ("CByteCount", ["COpaqueMemoryAddress", "CByteCount", "CByteCount", "CFileHandle"], False),
    "fseek":      ("CSignedInt32", ["CFileHandle", "CSignedInt64", "CSignedInt32"], False),
    "ftell":      ("CSignedInt64", ["CFileHandle"], False),
    "fsetpos":    ("CSignedInt32", ["CFileHandle", "COpaqueMemoryAddress"], False),
    "fgetpos":    ("CSignedInt32", ["CFileHandle", "COpaqueMemoryAddress"], False),
    "rewind":     ("Void", ["CFileHandle"], False),
    "fgetc":      ("CSignedInt32", ["CFileHandle"], False),
    "fputc":      ("CSignedInt32", ["CSignedInt32", "CFileHandle"], False),
    "getc":       ("CSignedInt32", ["CFileHandle"], False),
    "putc":       ("CSignedInt32", ["CSignedInt32", "CFileHandle"], False),
    "getchar":    ("CSignedInt32", [], False),
    "putchar":    ("CSignedInt32", ["CSignedInt32"], False),
    "fgets":      ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CSignedInt32", "CFileHandle"], False),
    "fputs":      ("CSignedInt32", ["CNullTerminatedByteString", "CFileHandle"], False),
    "gets_s":     ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CByteCount"], False),
    "puts":       ("CSignedInt32", ["CNullTerminatedByteString"], False),
    "ungetc":     ("CSignedInt32", ["CSignedInt32", "CFileHandle"], False),
    "feof":       ("CSignedInt32", ["CFileHandle"], False),
    "ferror":     ("CSignedInt32", ["CFileHandle"], False),
    "clearerr":   ("Void", ["CFileHandle"], False),
    "perror":     ("Void", ["CNullTerminatedByteString"], False),
    "remove":     ("CSignedInt32", ["CNullTerminatedByteString"], False),
    "rename":     ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "tmpfile":    ("CFileHandle", [], False),
    "tmpnam":     ("CNullTerminatedByteString", ["CNullTerminatedByteString"], False),
    "setbuf":     ("Void", ["CFileHandle", "CNullTerminatedByteString"], False),
    "setvbuf":    ("CSignedInt32", ["CFileHandle", "CNullTerminatedByteString", "CSignedInt32", "CByteCount"], False),
}

# ---- <stdlib.h> ----
STDLIB = {
    "malloc":     ("COpaqueMemoryAddress", ["CByteCount"], False),
    "calloc":     ("COpaqueMemoryAddress", ["CByteCount", "CByteCount"], False),
    "realloc":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CByteCount"], False),
    "free":       ("Void", ["COpaqueMemoryAddress"], False),
    "aligned_alloc": ("COpaqueMemoryAddress", ["CByteCount", "CByteCount"], False),
    "exit":       ("Void", ["CSignedInt32"], False),
    "_Exit":      ("Void", ["CSignedInt32"], False),
    "quick_exit": ("Void", ["CSignedInt32"], False),
    "atexit":     ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "at_quick_exit": ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "abort":      ("Void", [], False),
    "atoi":       ("CSignedInt32", ["CNullTerminatedByteString"], False),
    "atol":       ("CSignedInt64", ["CNullTerminatedByteString"], False),
    "atoll":      ("CSignedInt64", ["CNullTerminatedByteString"], False),
    "atof":       ("CFloat64", ["CNullTerminatedByteString"], False),
    "strtol":     ("CSignedInt64", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "strtoll":    ("CSignedInt64", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "strtoul":    ("CSignedInt64", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "strtoull":   ("CSignedInt64", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "strtof":     ("CFloat32", ["CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "strtod":     ("CFloat64", ["CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "strtold":    ("CFloat64", ["CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "strtoimax":  ("CSignedInt64", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "strtoumax":  ("CSignedInt64", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "rand":       ("CSignedInt32", [], False),
    "srand":      ("Void", ["CUnsignedInt32"], False),
    "rand_s":     ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "qsort":      ("Void", ["COpaqueMemoryAddress", "CByteCount", "CByteCount", "COpaqueMemoryAddress"], False),
    "qsort_s":    ("CSignedInt32", ["COpaqueMemoryAddress", "CByteCount", "CByteCount", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "bsearch":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount", "CByteCount", "COpaqueMemoryAddress"], False),
    "abs":        ("CSignedInt32", ["CSignedInt32"], False),
    "labs":       ("CSignedInt64", ["CSignedInt64"], False),
    "llabs":      ("CSignedInt64", ["CSignedInt64"], False),
    "div":        ("CSignedInt64", ["CSignedInt32", "CSignedInt32"], False),
    "ldiv":       ("CSignedInt64", ["CSignedInt64", "CSignedInt64"], False),
    "lldiv":      ("CSignedInt64", ["CSignedInt64", "CSignedInt64"], False),
    "imaxabs":    ("CSignedInt64", ["CSignedInt64"], False),
    "imaxdiv":    ("CSignedInt64", ["CSignedInt64", "CSignedInt64"], False),
    "getenv":     ("CNullTerminatedByteString", ["CNullTerminatedByteString"], False),
    "getenv_s":   ("CSignedInt32", ["COpaqueMemoryAddress", "CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString"], False),
    "system":     ("CSignedInt32", ["CNullTerminatedByteString"], False),
    "mblen":      ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount"], False),
    "mbtowc":     ("CSignedInt32", ["COpaqueMemoryAddress", "CNullTerminatedByteString", "CByteCount"], False),
    "wctomb":     ("CSignedInt32", ["CNullTerminatedByteString", "CSignedInt32"], False),
    "mbstowcs":   ("CByteCount", ["COpaqueMemoryAddress", "CNullTerminatedByteString", "CByteCount"], False),
    "wcstombs":   ("CByteCount", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CByteCount"], False),
}

# ---- <string.h> ----
STRING = {
    "strlen":     ("CByteCount", ["CNullTerminatedByteString"], False),
    "strnlen_s":  ("CByteCount", ["CNullTerminatedByteString", "CByteCount"], False),
    "strcpy":     ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strncpy":    ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString", "CByteCount"], False),
    "strcpy_s":   ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString"], False),
    "strncpy_s":  ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString", "CByteCount"], False),
    "strcat":     ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strncat":    ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString", "CByteCount"], False),
    "strcat_s":   ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString"], False),
    "strncat_s":  ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString", "CByteCount"], False),
    "strcmp":     ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strncmp":    ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString", "CByteCount"], False),
    "strcoll":    ("CSignedInt32", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strxfrm":    ("CByteCount", ["CNullTerminatedByteString", "CNullTerminatedByteString", "CByteCount"], False),
    "strchr":     ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CSignedInt32"], False),
    "strrchr":    ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CSignedInt32"], False),
    "strspn":     ("CByteCount", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strcspn":    ("CByteCount", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strpbrk":    ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strstr":     ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strtok":     ("CNullTerminatedByteString", ["CNullTerminatedByteString", "CNullTerminatedByteString"], False),
    "strtok_s":   ("CNullTerminatedByteString", ["CNullTerminatedByteString", "COpaqueMemoryAddress", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "memcpy":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "memcpy_s":   ("CSignedInt32", ["COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress", "CByteCount"], False),
    "memmove":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "memmove_s":  ("CSignedInt32", ["COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress", "CByteCount"], False),
    "memcmp":     ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "memchr":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32", "CByteCount"], False),
    "memset":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32", "CByteCount"], False),
    "memset_s":   ("CSignedInt32", ["COpaqueMemoryAddress", "CByteCount", "CSignedInt32", "CByteCount"], False),
    "strerror":   ("CNullTerminatedByteString", ["CSignedInt32"], False),
    "strerror_s": ("CSignedInt32", ["CNullTerminatedByteString", "CByteCount", "CSignedInt32"], False),
    "strerrorlen_s": ("CByteCount", ["CSignedInt32"], False),
}

# ---- <math.h> ----  (signatures use CDouble universally; the float-suffix
# `f` variants take/return CFloat and the long-double `l` variants take/return
# CDouble — long double is treated as double for ABI parity.)
def _math_double(name):
    return (name, ("CFloat64", ["CFloat64"], False))


def _math_double_2(name):
    return (name, ("CFloat64", ["CFloat64", "CFloat64"], False))


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
    ("lround", ("CSignedInt64", ["CFloat64"], False)),
    ("llround", ("CSignedInt64", ["CFloat64"], False)),
    _math_double("rint"),
    ("lrint", ("CSignedInt64", ["CFloat64"], False)),
    ("llrint", ("CSignedInt64", ["CFloat64"], False)),
    _math_double("nearbyint"),
    ("frexp", ("CFloat64", ["CFloat64", "COpaqueMemoryAddress"], False)),
    ("ldexp", ("CFloat64", ["CFloat64", "CSignedInt32"], False)),
    ("modf", ("CFloat64", ["CFloat64", "COpaqueMemoryAddress"], False)),
    ("scalbn", ("CFloat64", ["CFloat64", "CSignedInt32"], False)),
    ("scalbln", ("CFloat64", ["CFloat64", "CSignedInt64"], False)),
    ("ilogb", ("CSignedInt32", ["CFloat64"], False)),
    _math_double("logb"),
    _math_double_2("copysign"),
    _math_double_2("nextafter"),
    _math_double_2("nexttoward"),
    _math_double_2("fdim"),
    _math_double_2("fmax"),
    _math_double_2("fmin"),
    ("fma", ("CFloat64", ["CFloat64", "CFloat64", "CFloat64"], False)),
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
    ("remquo", ("CFloat64", ["CFloat64", "CFloat64", "COpaqueMemoryAddress"], False)),
    ("nan", ("CFloat64", ["CNullTerminatedByteString"], False)),
    ("nanf", ("CFloat32", ["CNullTerminatedByteString"], False)),
    ("nanl", ("CFloat64", ["CNullTerminatedByteString"], False)),
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
    # Float variant: every CDouble becomes CFloat. We special-case `ldexp`
    # and `scalbn` which keep an int second arg.
    def _to_float(t):
        return "CFloat32" if t == "CFloat64" else t
    _f_ret = _to_float(_ret)
    _f_params = [_to_float(p) for p in _params]
    MATH[_stem + "f"] = (_f_ret, _f_params, _vararg)
    # Long-double variant: identical to double on this ABI.
    MATH[_stem + "l"] = (_ret, _params, _vararg)

# `ldexp` and `frexp` are listed in MATH already with mixed types — handle
# their f/l variants explicitly to preserve the CInt/CVoidPtr second arg.
MATH["ldexpf"] = ("CFloat32", ["CFloat32", "CSignedInt32"], False)
MATH["ldexpl"] = ("CFloat64", ["CFloat64", "CSignedInt32"], False)
MATH["frexpf"] = ("CFloat32", ["CFloat32", "COpaqueMemoryAddress"], False)
MATH["frexpl"] = ("CFloat64", ["CFloat64", "COpaqueMemoryAddress"], False)
MATH["modff"]  = ("CFloat32", ["CFloat32", "COpaqueMemoryAddress"], False)
MATH["modfl"]  = ("CFloat64", ["CFloat64", "COpaqueMemoryAddress"], False)
MATH["ilogbf"] = ("CSignedInt32", ["CFloat32"], False)
MATH["ilogbl"] = ("CSignedInt32", ["CFloat64"], False)
MATH["lroundf"] = ("CSignedInt64", ["CFloat32"], False)
MATH["lroundl"] = ("CSignedInt64", ["CFloat64"], False)
MATH["llroundf"] = ("CSignedInt64", ["CFloat32"], False)
MATH["llroundl"] = ("CSignedInt64", ["CFloat64"], False)
MATH["lrintf"] = ("CSignedInt64", ["CFloat32"], False)
MATH["lrintl"] = ("CSignedInt64", ["CFloat64"], False)
MATH["llrintf"] = ("CSignedInt64", ["CFloat32"], False)
MATH["llrintl"] = ("CSignedInt64", ["CFloat64"], False)

# ---- <ctype.h> ----
CTYPE = {
    "isalpha":    ("CSignedInt32", ["CSignedInt32"], False),
    "isdigit":    ("CSignedInt32", ["CSignedInt32"], False),
    "isalnum":    ("CSignedInt32", ["CSignedInt32"], False),
    "isspace":    ("CSignedInt32", ["CSignedInt32"], False),
    "isupper":    ("CSignedInt32", ["CSignedInt32"], False),
    "islower":    ("CSignedInt32", ["CSignedInt32"], False),
    "iscntrl":    ("CSignedInt32", ["CSignedInt32"], False),
    "isprint":    ("CSignedInt32", ["CSignedInt32"], False),
    "ispunct":    ("CSignedInt32", ["CSignedInt32"], False),
    "isxdigit":   ("CSignedInt32", ["CSignedInt32"], False),
    "isblank":    ("CSignedInt32", ["CSignedInt32"], False),
    "isgraph":    ("CSignedInt32", ["CSignedInt32"], False),
    "toupper":    ("CSignedInt32", ["CSignedInt32"], False),
    "tolower":    ("CSignedInt32", ["CSignedInt32"], False),
}

# ---- <time.h> ----
TIME = {
    "time":       ("CUnixSecondsSinceEpoch", ["COpaqueMemoryAddress"], False),
    "clock":      ("CCpuClockTicks", [], False),
    "difftime":   ("CFloat64", ["CUnixSecondsSinceEpoch", "CUnixSecondsSinceEpoch"], False),
    "mktime":     ("CUnixSecondsSinceEpoch", ["COpaqueMemoryAddress"], False),
    "gmtime":     ("CDecomposedTimeAddress", ["COpaqueMemoryAddress"], False),
    "localtime":  ("CDecomposedTimeAddress", ["COpaqueMemoryAddress"], False),
    "asctime":    ("CNullTerminatedByteString", ["COpaqueMemoryAddress"], False),
    "ctime":      ("CNullTerminatedByteString", ["COpaqueMemoryAddress"], False),
    "strftime":   ("CByteCount", ["CNullTerminatedByteString", "CByteCount", "CNullTerminatedByteString", "COpaqueMemoryAddress"], False),
    "timespec_get": ("CSignedInt32", ["COpaqueMemoryAddress", "CSignedInt32"], False),
}

# ---- <setjmp.h> ----
SETJMP = {
    "setjmp":     ("CSignedInt32", ["CSetjmpRegisterBuffer"], False),
    "longjmp":    ("Void", ["CSetjmpRegisterBuffer", "CSignedInt32"], False),
}

# ---- <signal.h> ----
SIGNAL = {
    "signal":     ("COpaqueMemoryAddress", ["CSignedInt32", "COpaqueMemoryAddress"], False),
    "raise":      ("CSignedInt32", ["CSignedInt32"], False),
}

# ---- <locale.h> ----
LOCALE = {
    "setlocale":  ("CNullTerminatedByteString", ["CSignedInt32", "CNullTerminatedByteString"], False),
    "localeconv": ("COpaqueMemoryAddress", [], False),
}

# ---- <wchar.h> — full C99 surface ----
WCHAR = {
    # string-length & search
    "wcslen":     ("CByteCount", ["COpaqueMemoryAddress"], False),
    "wcsnlen_s":  ("CByteCount", ["COpaqueMemoryAddress", "CByteCount"], False),
    "wcschr":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcsrchr":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcsstr":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcspbrk":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcsspn":     ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcscspn":    ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcstok":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    # comparison
    "wcscmp":     ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcsncmp":    ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "wcscoll":    ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcsxfrm":    ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    # copy / concat
    "wcscpy":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcsncpy":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "wcscat":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcsncat":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    # wmemory
    "wmemcpy":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "wmemmove":   ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "wmemcmp":    ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount"], False),
    "wmemchr":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32", "CByteCount"], False),
    "wmemset":    ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32", "CByteCount"], False),
    # numeric conversion
    "wcstol":     ("CSignedInt64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcstoll":    ("CSignedInt64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcstoul":    ("CSignedInt64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcstoull":   ("CSignedInt64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcstof":     ("CFloat32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcstod":     ("CFloat64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcstold":    ("CFloat64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wcstoimax":  ("CSignedInt64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CSignedInt32"], False),
    "wcstoumax":  ("CSignedInt64", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CSignedInt32"], False),
    # time formatting
    "wcsftime":   ("CByteCount", ["COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    # wide formatted I/O
    "wprintf":    ("CSignedInt32", ["COpaqueMemoryAddress"], True),
    "fwprintf":   ("CSignedInt32", ["CFileHandle", "COpaqueMemoryAddress"], True),
    "swprintf":   ("CSignedInt32", ["COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], True),
    "vwprintf":   ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "vfwprintf":  ("CSignedInt32", ["CFileHandle", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "vswprintf":  ("CSignedInt32", ["COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "wscanf":     ("CSignedInt32", ["COpaqueMemoryAddress"], True),
    "fwscanf":    ("CSignedInt32", ["CFileHandle", "COpaqueMemoryAddress"], True),
    "swscanf":    ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], True),
    "vwscanf":    ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "vfwscanf":   ("CSignedInt32", ["CFileHandle", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "vswscanf":   ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    # wide character I/O
    "fgetwc":     ("CSignedInt32", ["CFileHandle"], False),
    "fputwc":     ("CSignedInt32", ["CSignedInt32", "CFileHandle"], False),
    "getwc":      ("CSignedInt32", ["CFileHandle"], False),
    "putwc":      ("CSignedInt32", ["CSignedInt32", "CFileHandle"], False),
    "getwchar":   ("CSignedInt32", [], False),
    "putwchar":   ("CSignedInt32", ["CSignedInt32"], False),
    "fgetws":     ("COpaqueMemoryAddress", ["COpaqueMemoryAddress", "CSignedInt32", "CFileHandle"], False),
    "fputws":     ("CSignedInt32", ["COpaqueMemoryAddress", "CFileHandle"], False),
    "ungetwc":    ("CSignedInt32", ["CSignedInt32", "CFileHandle"], False),
    "fwide":      ("CSignedInt32", ["CFileHandle", "CSignedInt32"], False),
    # multibyte conversion
    "mbsinit":    ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "mbrlen":     ("CByteCount", ["COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], False),
    "mbrtowc":    ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], False),
    "wcrtomb":    ("CByteCount", ["COpaqueMemoryAddress", "CSignedInt32", "COpaqueMemoryAddress"], False),
    "mbsrtowcs":  ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], False),
    "wcsrtombs":  ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], False),
    "btowc":      ("CSignedInt32", ["CSignedInt32"], False),
    "wctob":      ("CSignedInt32", ["CSignedInt32"], False),
}

# ---- <fenv.h> — C99 floating-point environment ----
FENV = {
    "feclearexcept":  ("CSignedInt32", ["CSignedInt32"], False),
    "fegetexceptflag": ("CSignedInt32", ["COpaqueMemoryAddress", "CSignedInt32"], False),
    "feraiseexcept":  ("CSignedInt32", ["CSignedInt32"], False),
    "fesetexceptflag": ("CSignedInt32", ["COpaqueMemoryAddress", "CSignedInt32"], False),
    "fetestexcept":   ("CSignedInt32", ["CSignedInt32"], False),
    "fegetround":     ("CSignedInt32", [], False),
    "fesetround":     ("CSignedInt32", ["CSignedInt32"], False),
    "fegetenv":       ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "fesetenv":       ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "feholdexcept":   ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "feupdateenv":    ("CSignedInt32", ["COpaqueMemoryAddress"], False),
}

# ---- <complex.h> — C99 complex math (declarations only) ----
# Complex doubles are spec-defined as `_Complex double` which has no clean
# LLVM lowering at the IR level; on x86-64 ABI they're passed as a pair of
# doubles. We declare them with the same shape and let the linker resolve;
# the SemanticScript-side type aliases CComplexDouble / CComplexFloat are not currently
# materialized but the declarations exist for completeness.
COMPLEX = {
    "cabs":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "carg":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "creal":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "cimag":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "conj":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "cproj":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "cexp":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "clog":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "cpow":    ("CFloat64", ["CFloat64", "CFloat64", "CFloat64", "CFloat64"], False),
    "csqrt":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "csin":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "ccos":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "ctan":    ("CFloat64", ["CFloat64", "CFloat64"], False),
    "casin":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "cacos":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "catan":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "csinh":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "ccosh":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "ctanh":   ("CFloat64", ["CFloat64", "CFloat64"], False),
    "casinh":  ("CFloat64", ["CFloat64", "CFloat64"], False),
    "cacosh":  ("CFloat64", ["CFloat64", "CFloat64"], False),
    "catanh":  ("CFloat64", ["CFloat64", "CFloat64"], False),
    # float variants
    "cabsf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
    "csqrtf":  ("CFloat32", ["CFloat32", "CFloat32"], False),
    "csinf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
    "ccosf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
    "ctanf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
    "cexpf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
    "clogf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
    "cpowf":   ("CFloat32", ["CFloat32", "CFloat32", "CFloat32", "CFloat32"], False),
    "crealf":  ("CFloat32", ["CFloat32", "CFloat32"], False),
    "cimagf":  ("CFloat32", ["CFloat32", "CFloat32"], False),
    "conjf":   ("CFloat32", ["CFloat32", "CFloat32"], False),
}

# ---- <uchar.h> — C11 char16/char32 conversions ----
UCHAR = {
    "mbrtoc16":  ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], False),
    "c16rtomb":  ("CByteCount", ["COpaqueMemoryAddress", "CSignedInt16", "COpaqueMemoryAddress"], False),
    "mbrtoc32":  ("CByteCount", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "CByteCount", "COpaqueMemoryAddress"], False),
    "c32rtomb":  ("CByteCount", ["COpaqueMemoryAddress", "CSignedInt32", "COpaqueMemoryAddress"], False),
}

# ---- <threads.h> — C11 optional threading (Annex K conditional) ----
THREADS = {
    "thrd_create":    ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "thrd_equal":     ("CSignedInt32", ["CSignedInt64", "CSignedInt64"], False),
    "thrd_current":   ("CSignedInt64", [], False),
    "thrd_sleep":     ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "thrd_yield":     ("Void", [], False),
    "thrd_exit":      ("Void", ["CSignedInt32"], False),
    "thrd_detach":    ("CSignedInt32", ["CSignedInt64"], False),
    "thrd_join":      ("CSignedInt32", ["CSignedInt64", "COpaqueMemoryAddress"], False),
    "mtx_init":       ("CSignedInt32", ["COpaqueMemoryAddress", "CSignedInt32"], False),
    "mtx_lock":       ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "mtx_trylock":    ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "mtx_timedlock":  ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "mtx_unlock":     ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "mtx_destroy":    ("Void", ["COpaqueMemoryAddress"], False),
    "cnd_init":       ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "cnd_signal":     ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "cnd_broadcast":  ("CSignedInt32", ["COpaqueMemoryAddress"], False),
    "cnd_wait":       ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "cnd_timedwait":  ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "cnd_destroy":    ("Void", ["COpaqueMemoryAddress"], False),
    "tss_create":     ("CSignedInt32", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
    "tss_get":        ("COpaqueMemoryAddress", ["CSignedInt64"], False),
    "tss_set":        ("CSignedInt32", ["CSignedInt64", "COpaqueMemoryAddress"], False),
    "tss_delete":     ("Void", ["CSignedInt64"], False),
    "call_once":      ("Void", ["COpaqueMemoryAddress", "COpaqueMemoryAddress"], False),
}

# ---- <wctype.h> minimal ----
WCTYPE = {
    "iswalpha":   ("CSignedInt32", ["CSignedInt32"], False),
    "iswdigit":   ("CSignedInt32", ["CSignedInt32"], False),
    "iswspace":   ("CSignedInt32", ["CSignedInt32"], False),
    "towupper":   ("CSignedInt32", ["CSignedInt32"], False),
    "towlower":   ("CSignedInt32", ["CSignedInt32"], False),
}

# ---- merge everything into a single dispatch dict ----
ALL_FUNCTIONS = {}
for bucket in (STDIO, STDLIB, STRING, MATH, CTYPE, TIME,
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
ERRNO_ACCESSOR = ("errnoGet", "CSignedInt32", [])


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
