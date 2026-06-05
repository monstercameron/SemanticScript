#!/usr/bin/env bash
# R-134: build + run the native-runtime safety harnesses under AddressSanitizer
# and UndefinedBehaviorSanitizer. Single source of truth for the native-safety CI
# job and local runs. Requires clang (or $CC) with ASAN/UBSAN — i.e. Linux/macOS
# x64 runners (the sanitizer runtimes are not shipped for aarch64-windows).
#
#   - Every harness_*.c is a NORMAL, correct exercise of a memory-owning runtime
#     and MUST pass with zero sanitizer findings.
#   - seed_uaf.c is a deliberate use-after-free that ASAN MUST catch (non-zero
#     exit); if it passes, the sanitizer is not actually active and we fail loudly.
set -euo pipefail

CC="${CC:-clang}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# -fno-sanitize-recover=all: turn every UBSAN finding into a hard abort (non-zero
# exit) so a finding actually fails CI instead of just printing.
SAN_FLAGS=(-g -O1 -fsanitize=address,undefined -fno-sanitize-recover=all
           -fno-omit-frame-pointer -Wall -Wextra)
export ASAN_OPTIONS="detect_leaks=1:abort_on_error=1"
export UBSAN_OPTIONS="print_stacktrace=1"

status=0

echo "== clean runtime harnesses (must pass, zero findings) =="
for src in "$HERE"/harness_*.c; do
    name="$(basename "$src" .c)"
    echo "--- building $name ---"
    "$CC" "${SAN_FLAGS[@]}" "$src" -o "$TMP/$name"
    echo "--- running $name ---"
    if ! "$TMP/$name"; then
        echo "FAIL: $name reported a sanitizer finding (or non-zero exit)"
        status=1
    fi
done

echo "== sanitizer self-test: seed_uaf.c MUST be caught by ASAN =="
"$CC" "${SAN_FLAGS[@]}" "$HERE/seed_uaf.c" -o "$TMP/seed_uaf"
if "$TMP/seed_uaf"; then
    echo "FAIL: seed_uaf exited 0 — AddressSanitizer is NOT active, so the clean"
    echo "      harness 'zero findings' result above is meaningless."
    status=1
else
    echo "OK: ASAN caught the planted use-after-free (non-zero exit, as required)"
fi

if [ "$status" -eq 0 ]; then
    echo "native-safety: ALL CLEAN"
fi
exit "$status"
