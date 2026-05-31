/* eav_panic — WS1-130 structured trap report (the native build's copy; the JIT
 * registers an in-process Python implementation of the same ABI).
 *
 * The compiler injects a call to this helper at every no-UB guard site (integer
 * divide/modulo by zero, a violated numeric precondition, and — as WS1-131
 * lands — out-of-bounds / narrowing / recursion), instead of a bare trap. So a
 * program that would have died on a silent SIGILL/ud2 instead prints *why* it
 * died — code, kind, operation, source row, reason, and the operands — then
 * exits 134 (128 + SIGABRT, the conventional aborted status). No undefined
 * execution: the report is emitted and the process is torn down deterministically.
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>

#ifdef _WIN32
#define EAV_NORETURN __declspec(noreturn)
#else
#define EAV_NORETURN __attribute__((noreturn))
#endif

EAV_NORETURN void eav_panic(const char *code, const char *kind, const char *op,
                            int32_t row, const char *reason,
                            int64_t left, int64_t right) {
    fflush(stdout);
    fprintf(stderr,
            "\nEAV PANIC %s %s\n"
            "  op:       %s\n"
            "  at line:  %d\n"
            "  reason:   %s\n"
            "  operands: left=%lld right=%lld\n",
            code ? code : "", kind ? kind : "", op ? op : "", (int)row,
            reason ? reason : "", (long long)left, (long long)right);
    fflush(stderr);
    _Exit(134);
}
