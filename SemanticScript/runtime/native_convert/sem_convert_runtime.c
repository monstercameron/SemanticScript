/* SemanticScript standard.convert native runtime adapter.
 *
 * Provides natively-linking numeric -> decimal-text formatters. A
 * standard-library operation with an ordinary SemanticScript body does NOT link
 * in native / webServer builds (SSCG002), so `convert.convertSignedInt64ToString`
 * (which has a body) is unavailable there and callers were forced down to
 * `c.snprintf` with format-string crash risk, or to reading integer columns as
 * SQL TEXT. These ABI shims give convert.* a native, typed, crash-free path: the
 * caller owns the scratch buffer (no allocation, no Result), mirroring the
 * standard.http `ss_http_html_escape` idiom.
 *
 * Linked into any native build that imports `standard.convert` via the module's
 * `nativeRuntimeSource` row. */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

/* Format a signed 64-bit integer as null-terminated decimal text into the
 * caller's bounded buffer. Returns `out`, or NULL on bad args OR when the buffer
 * is too small. Unlike HTML escaping, a TRUNCATED number is a wrong number, so
 * insufficient capacity fails closed (NULL) rather than returning partial text;
 * the caller must check. A 64-bit decimal needs at most 21 bytes (sign + 19
 * digits + NUL). */
const char *ss_convert_int64_to_string(int64_t value, char *out, int32_t out_capacity) {
    if (out == NULL || out_capacity <= 0) {
        return NULL;
    }
    int written = snprintf(out, (size_t)out_capacity, "%lld", (long long)value);
    if (written < 0 || written >= out_capacity) {
        return NULL;
    }
    return out;
}

/* Format a double as the SHORTEST null-terminated decimal text that still
 * round-trips back to the same double, into the caller's bounded buffer. Returns
 * `out`, or NULL on bad args / insufficient capacity. The shortest-round-trip
 * search (increasing %g precision until strtod recovers the input) keeps common
 * values clean (0.1 -> "0.1", not "0.10000000000000001") while guaranteeing no
 * precision is lost. Non-finite inputs format as "nan" / "inf" / "-inf". */
const char *ss_convert_float64_to_string(double value, char *out, int32_t out_capacity) {
    if (out == NULL || out_capacity <= 0) {
        return NULL;
    }
    for (int precision = 1; precision <= 17; precision++) {
        int written = snprintf(out, (size_t)out_capacity, "%.*g", precision, value);
        if (written < 0 || written >= out_capacity) {
            return NULL;
        }
        if (strtod(out, NULL) == value) {
            return out;
        }
    }
    /* Loop exhausted at precision 17 (the IEEE-754 round-trip bound); `out`
     * already holds that maximally-precise rendering, which round-trips for any
     * finite double. */
    return out;
}
