/*
 * eav_sqlite.c — return-value shim exposing the SemanticScript sqlite runtime
 * to the EAV front end (eavc), at parity with the original semsc.py
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
 */

#include "sem_sqlite_runtime.h"

#ifdef _WIN32
#define EAV_EXPORT __declspec(dllexport)
#else
#define EAV_EXPORT __attribute__((visibility("default")))
#endif

/* ---- database lifecycle (open/query use out-params -> adapted) ---- */

EAV_EXPORT void *eav_sqlite_open(const char *filesystem_path) {
    SSSqliteDatabase *database = 0;
    int flags = SS_SQLITE_OPEN_READWRITE | SS_SQLITE_OPEN_CREATE;
    if (ss_sqlite_database_open(filesystem_path, flags, &database) != SS_SQLITE_OK)
        return 0;
    return database;
}

EAV_EXPORT void *eav_sqlite_open_memory(void) {
    SSSqliteDatabase *database = 0;
    int flags = SS_SQLITE_OPEN_READWRITE | SS_SQLITE_OPEN_CREATE | SS_SQLITE_OPEN_MEMORY;
    if (ss_sqlite_database_open(":memory:", flags, &database) != SS_SQLITE_OK)
        return 0;
    return database;
}

EAV_EXPORT int eav_sqlite_close(void *db) {
    return ss_sqlite_database_close((SSSqliteDatabase *)db);
}

EAV_EXPORT const char *eav_sqlite_errmsg(void *db) {
    return ss_sqlite_database_errmsg((SSSqliteDatabase *)db);
}

EAV_EXPORT long long eav_sqlite_last_insert_rowid(void *db) {
    return ss_sqlite_database_last_insert_rowid((SSSqliteDatabase *)db);
}

EAV_EXPORT int eav_sqlite_changes(void *db) {
    return ss_sqlite_database_changes((SSSqliteDatabase *)db);
}

EAV_EXPORT int eav_sqlite_enable_wal(void *db) {
    return ss_sqlite_database_enable_wal((SSSqliteDatabase *)db);
}

/* ---- one-shot SQL + scalar read (query uses out-param -> adapted) ---- */

EAV_EXPORT int eav_sqlite_exec(void *db, const char *sql_text) {
    return ss_sqlite_exec((SSSqliteDatabase *)db, sql_text);
}

EAV_EXPORT long long eav_sqlite_query_scalar(void *db, const char *sql_text) {
    long long value = 0;
    ss_sqlite_query_scalar_int64((SSSqliteDatabase *)db, sql_text, &value);
    return value;
}

/* ---- transactions ---- */

EAV_EXPORT int eav_sqlite_begin_immediate(void *db) {
    return ss_sqlite_transaction_begin_immediate((SSSqliteDatabase *)db);
}

EAV_EXPORT int eav_sqlite_commit(void *db) {
    return ss_sqlite_transaction_commit((SSSqliteDatabase *)db);
}

EAV_EXPORT int eav_sqlite_rollback(void *db) {
    return ss_sqlite_transaction_rollback((SSSqliteDatabase *)db);
}

/* ---- prepared statements (prepare uses out-param -> adapted) ---- */

EAV_EXPORT void *eav_sqlite_prepare(void *db, const char *sql_text) {
    SSSqliteStatement *statement = 0;
    if (ss_sqlite_statement_prepare((SSSqliteDatabase *)db, sql_text, &statement) != SS_SQLITE_OK)
        return 0;
    return statement;
}

EAV_EXPORT int eav_sqlite_finalize(void *stmt) {
    return ss_sqlite_statement_finalize((SSSqliteStatement *)stmt);
}

EAV_EXPORT int eav_sqlite_reset(void *stmt) {
    return ss_sqlite_statement_reset((SSSqliteStatement *)stmt);
}

EAV_EXPORT int eav_sqlite_step(void *stmt) {
    return ss_sqlite_statement_step((SSSqliteStatement *)stmt);
}

/* ---- parameter binding (1-based) ---- */

EAV_EXPORT int eav_sqlite_bind_int64(void *stmt, int index, long long value) {
    return ss_sqlite_statement_bind_int64((SSSqliteStatement *)stmt, index, value);
}

EAV_EXPORT int eav_sqlite_bind_double(void *stmt, int index, double value) {
    return ss_sqlite_statement_bind_double((SSSqliteStatement *)stmt, index, value);
}

EAV_EXPORT int eav_sqlite_bind_text(void *stmt, int index, const char *value) {
    return ss_sqlite_statement_bind_text((SSSqliteStatement *)stmt, index, value);
}

EAV_EXPORT int eav_sqlite_bind_null(void *stmt, int index) {
    return ss_sqlite_statement_bind_null((SSSqliteStatement *)stmt, index);
}

/* ---- column readers (0-based) ---- */

EAV_EXPORT int eav_sqlite_column_count(void *stmt) {
    return ss_sqlite_statement_column_count((SSSqliteStatement *)stmt);
}

EAV_EXPORT int eav_sqlite_column_type(void *stmt, int col) {
    return ss_sqlite_statement_column_type((SSSqliteStatement *)stmt, col);
}

EAV_EXPORT const char *eav_sqlite_column_name(void *stmt, int col) {
    return ss_sqlite_statement_column_name((SSSqliteStatement *)stmt, col);
}

EAV_EXPORT long long eav_sqlite_column_int64(void *stmt, int col) {
    return ss_sqlite_statement_column_int64((SSSqliteStatement *)stmt, col);
}

EAV_EXPORT double eav_sqlite_column_double(void *stmt, int col) {
    return ss_sqlite_statement_column_double((SSSqliteStatement *)stmt, col);
}

EAV_EXPORT const char *eav_sqlite_column_text(void *stmt, int col) {
    return ss_sqlite_statement_column_text((SSSqliteStatement *)stmt, col);
}

EAV_EXPORT long long eav_sqlite_column_bytes(void *stmt, int col) {
    return (long long)ss_sqlite_statement_column_bytes((SSSqliteStatement *)stmt, col);
}

/* ---- diagnostics ---- */

EAV_EXPORT const char *eav_sqlite_library_version(void) {
    return ss_sqlite_library_version();
}
