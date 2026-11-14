#!/usr/bin/env bash
# R-134: object-only build of the memory-owning native runtime translation units
# so CodeQL's c-cpp analysis can trace them (the CodeQL config ignores the
# vendored third_party C, so this surfaces the runtime code we own). Not a product
# build — no link — just enough compilation for static analysis.
set -euo pipefail

CC="${CC:-clang}"
RT="semanticscript/runtime"
OBJ="$(mktemp -d)"

echo "CodeQL c-cpp build: compiling native runtime TUs for tracing"
set -x
"$CC" -c -g "$RT/ss_event.c" -o "$OBJ/ss_event.o"
"$CC" -c -g -I "$RT/native_json" "$RT/ss_json.c" -o "$OBJ/ss_json.o"
"$CC" -c -g -I "$RT/native_http" "$RT/ss_http.c" -o "$OBJ/ss_http.o"
"$CC" -c -g -DSEM_ASYNC_WITH_LIBUV -I "$RT/native_async" \
    -I third_party/libuv/include "$RT/ss_async.c" -o "$OBJ/ss_async.o"
for h in tests/native/harness_*.c; do
    "$CC" -c -g "$h" -o "$OBJ/$(basename "$h" .c).o"
done
set +x
echo "CodeQL c-cpp build: done"
