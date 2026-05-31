/* eav_ffi.c — WS3-016 FFI out-param ABI demo (the native build's copy; the JIT
 * registers an in-process Python implementation of the same ABI).
 *
 * Demonstrates the C-out-param seam that EAV binds through with `outParam`:
 * the result is written through a trailing pointer and the function returns an
 * i32 status (0 = ok, non-zero = error), exactly the convention sqlite/http C
 * APIs use (e.g. sqlite3_open(path, &db) -> int). The compiler allocates the
 * result slot, passes its address, calls, and loads the written value back —
 * the value never crosses the FFI boundary by-value.
 */
#include <stdint.h>

#ifdef _WIN32
#define EAV_EXPORT __declspec(dllexport)
#else
#define EAV_EXPORT __attribute__((visibility("default")))
#endif

EAV_EXPORT int32_t eav_ffi_add(int64_t a, int64_t b, int64_t *out) {
    if (a < 0) {
        return 1;  /* error status; leaves *out unwritten */
    }
    *out = a + b;
    return 0;  /* ok */
}
