/*
 * ss_sqlite.c — return-value shim exposing the SemanticScript sqlite runtime
 * to the EAV front end (semanticscript), at parity with the original semsc.py
 * `standard.sqlite` surface.
 *
 * The vendored engine (third_party/sqlite/sqlite3.c) is wrapped by
 * SemanticScript/runtime/native_sqlite/sem_sqlite_runtime.c into the clean
 * `ss_sqlite_*` ABI. semsc.py reaches that ABI through compiler-owned `sqlite.*`
 * intrinsics; eav deliberately does NOT put sqlite in the compiler (README
 * ss26/ss34). Instead every parity entry point is re-exported here as a plain
 * `args -> single return` function so it binds through the compiler's generic
 * `body runtimeBinding <symbol>` seam, and `std/standard.sqlite.sem` owns the
 * typed contract. The three `ss_sqlite_*` entry points that use C out-params
 * (open, prepare, query-scalar) are adapted to return their result directly.
 *
 * Handles flow through EAV as OpaquePointer (i64); on x86-64 a pointer and an
 * i64 share the argument/return register, so the lowering is ABI-compatible.
 * Text-returning helpers copy the sqlite-owned string before crossing the EAV
 * boundary. The language does not have a general string-free surface yet, so
 * these match string.concat / convert.toString's process-lifetime allocation
 * model instead of handing callers a dangling sqlite3_column_text pointer.
 */

#include "sem_sqlite_runtime.h"
#include "ss_runtime_export.h"

#include <stdlib.h>
#include <string.h>

static const char *ss_sqlite_dup_text(const char *text) {
    if (text == 0) {
        return 0;
    }
    size_t n = strlen(text);
    char *copy = (char *)malloc(n + 1);
    if (copy == 0) {
        return 0;
    }
    memcpy(copy, text, n + 1);
    return copy;
}

/* ---- database lifecycle (open/query use out-params -> adapted) ---- */

SS_EXPORT void *ss_sqlite_open(const char *filesystem_path) {
    SSSqliteDatabase *database = 0;
    int flags = SS_SQLITE_OPEN_READWRITE | SS_SQLITE_OPEN_CREATE;
    if (ss_sqlite_database_open(filesystem_path, flags, &database) != SS_SQLITE_OK)
        return 0;
    return database;
}

SS_EXPORT void *ss_sqlite_open_memory(void) {
    SSSqliteDatabase *database = 0;
    int flags = SS_SQLITE_OPEN_READWRITE | SS_SQLITE_OPEN_CREATE | SS_SQLITE_OPEN_MEMORY;
    if (ss_sqlite_database_open(":memory:", flags, &database) != SS_SQLITE_OK)
        return 0;
    return database;
}

SS_EXPORT int ss_sqlite_close(void *db) {
    return ss_sqlite_database_close((SSSqliteDatabase *)db);
}

SS_EXPORT const char *ss_sqlite_errmsg(void *db) {
    return ss_sqlite_dup_text(ss_sqlite_database_errmsg((SSSqliteDatabase *)db));
}

SS_EXPORT long long ss_sqlite_last_insert_rowid(void *db) {
    return ss_sqlite_database_last_insert_rowid((SSSqliteDatabase *)db);
}

SS_EXPORT int ss_sqlite_changes(void *db) {
    return ss_sqlite_database_changes((SSSqliteDatabase *)db);
}

SS_EXPORT int ss_sqlite_enable_wal(void *db) {
    return ss_sqlite_database_enable_wal((SSSqliteDatabase *)db);
}

/* ---- one-shot SQL + scalar read (query uses out-param -> adapted) ---- */


SS_EXPORT long long ss_sqlite_query_scalar(void *db, const char *sql_text) {
    long long value = 0;
    ss_sqlite_query_scalar_int64((SSSqliteDatabase *)db, sql_text, &value);
    return value;
}

/* ---- transactions ---- */

SS_EXPORT int ss_sqlite_begin_immediate(void *db) {
    return ss_sqlite_transaction_begin_immediate((SSSqliteDatabase *)db);
}

SS_EXPORT int ss_sqlite_commit(void *db) {
    return ss_sqlite_transaction_commit((SSSqliteDatabase *)db);
}

SS_EXPORT int ss_sqlite_rollback(void *db) {
    return ss_sqlite_transaction_rollback((SSSqliteDatabase *)db);
}

/* ---- prepared statements (prepare uses out-param -> adapted) ---- */

SS_EXPORT void *ss_sqlite_prepare(void *db, const char *sql_text) {
    SSSqliteStatement *statement = 0;
    if (ss_sqlite_statement_prepare((SSSqliteDatabase *)db, sql_text, &statement) != SS_SQLITE_OK)
        return 0;
    return statement;
}

SS_EXPORT int ss_sqlite_finalize(void *stmt) {
    return ss_sqlite_statement_finalize((SSSqliteStatement *)stmt);
}

SS_EXPORT int ss_sqlite_reset(void *stmt) {
    return ss_sqlite_statement_reset((SSSqliteStatement *)stmt);
}

SS_EXPORT int ss_sqlite_step(void *stmt) {
    return ss_sqlite_statement_step((SSSqliteStatement *)stmt);
}

/* ---- parameter binding (1-based) ---- */

SS_EXPORT int ss_sqlite_bind_int64(void *stmt, int index, long long value) {
    return ss_sqlite_statement_bind_int64((SSSqliteStatement *)stmt, index, value);
}

SS_EXPORT int ss_sqlite_bind_double(void *stmt, int index, double value) {
    return ss_sqlite_statement_bind_double((SSSqliteStatement *)stmt, index, value);
}

SS_EXPORT int ss_sqlite_bind_text(void *stmt, int index, const char *value) {
    return ss_sqlite_statement_bind_text((SSSqliteStatement *)stmt, index, value);
}

SS_EXPORT int ss_sqlite_bind_null(void *stmt, int index) {
    return ss_sqlite_statement_bind_null((SSSqliteStatement *)stmt, index);
}

/* ---- column readers (0-based) ---- */

SS_EXPORT int ss_sqlite_column_count(void *stmt) {
    return ss_sqlite_statement_column_count((SSSqliteStatement *)stmt);
}

SS_EXPORT int ss_sqlite_column_type(void *stmt, int col) {
    return ss_sqlite_statement_column_type((SSSqliteStatement *)stmt, col);
}

SS_EXPORT const char *ss_sqlite_column_name(void *stmt, int col) {
    return ss_sqlite_dup_text(ss_sqlite_statement_column_name((SSSqliteStatement *)stmt, col));
}

SS_EXPORT long long ss_sqlite_column_int64(void *stmt, int col) {
    return ss_sqlite_statement_column_int64((SSSqliteStatement *)stmt, col);
}

SS_EXPORT double ss_sqlite_column_double(void *stmt, int col) {
    return ss_sqlite_statement_column_double((SSSqliteStatement *)stmt, col);
}

SS_EXPORT const char *ss_sqlite_column_text(void *stmt, int col) {
    return ss_sqlite_dup_text(ss_sqlite_statement_column_text((SSSqliteStatement *)stmt, col));
}

SS_EXPORT long long ss_sqlite_column_bytes(void *stmt, int col) {
    return (long long)ss_sqlite_statement_column_bytes((SSSqliteStatement *)stmt, col);
}

/* ---- diagnostics ---- */
