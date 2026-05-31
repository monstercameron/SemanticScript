/*
 * ss_native_libc.c — native-build libc anchors.
 *
 * On Windows the UCRT exposes printf/vprintf (and the snprintf family) only as
 * header *inlines* that forward to the exported __stdio_common_vfprintf; there is
 * no exported `printf` symbol. The console code generator emits a direct call to
 * `printf` (e.g. console.writeIntegerLine -> printf("%lld\n", v)), so a native
 * link against the UCRT leaves `printf` undefined. This file is linked into every
 * native executable to provide a real `printf` symbol that delegates to the
 * exported UCRT entry point. (The JIT path is unaffected: it resolves printf from
 * the in-process CRT, and this file is not part of the JIT runtime libraries.)
 */
#include <stdarg.h>

/* The real UCRT exports. __acrt_iob_func(1) is stdout. */
typedef struct _iobuf SSNativeFile;
SSNativeFile *__acrt_iob_func(unsigned index);
__int64 __stdio_common_vfprintf(unsigned __int64 options, SSNativeFile *stream,
                                const char *format, void *locale, va_list args);

int printf(const char *format, ...) {
    va_list args;
    va_start(args, format);
    /* options 0 = the default printf behavior the UCRT printf inline uses. */
    __int64 written = __stdio_common_vfprintf(0ULL, __acrt_iob_func(1),
                                              format, 0, args);
    va_end(args);
    return (int)written;
}
