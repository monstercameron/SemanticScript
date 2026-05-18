#ifndef SEM_SQLITE_RUNTIME_H
#define SEM_SQLITE_RUNTIME_H

/*
 * SemanticScript-owned C ABI for embedded SQL storage.
 *
 * This header MUST stay self-contained — it deliberately does not include
 * `sqlite3.h`. Callers (generated SemanticScript code, hand-written demos,
 * future bindings in other languages) should only need this one header.
 * The underlying SQLite engine is an implementation detail of the adapter;
 * swapping or upgrading the engine must not require touching this surface.
 *
 * Conventions:
 *
 *   - All entry points return an int status code from the `SS_SQLITE_*`
 *     enums below. Step iteration uses `SS_SQLITE_STEP_ROW` /
 *     `SS_SQLITE_STEP_DONE` to distinguish "another row is available" from
 *     "iteration finished." Any other negative-or-positive value is treated
 *     as a runtime error and `ss_sqlite_database_errmsg()` carries the
 *     human-readable detail until the next call on the same database.
 *
 *   - We define our own status enums (rather than re-exporting
 *     `SQLITE_OK`, `SQLITE_ROW`, etc.) so a future SQLite version bump can't
 *     silently shift our ABI numbering under callers compiled against older
 *     headers.
 *
 *   - Strings and blobs returned from column accessors point into
 *     SQLite-owned memory and are only valid until the NEXT call on the
 *     same statement (`step`, `reset`, `finalize`, or another column
 *     accessor that converts the value). Callers must copy if they need
 *     the data to outlive that window. This matches sqlite3_column_text()
 *     semantics and is the only memory model that avoids a per-row malloc.
 */

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SSSqliteDatabase SSSqliteDatabase;
typedef struct SSSqliteStatement SSSqliteStatement;

enum {
    SS_SQLITE_OK             = 0,
    SS_SQLITE_ERR_CONFIG     = 1,  /* NULL inputs or malformed arguments. */
    SS_SQLITE_ERR_OPEN       = 2,  /* sqlite3_open_v2 returned non-OK. */
    SS_SQLITE_ERR_CLOSE      = 3,  /* sqlite3_close_v2 reported pending statements. */
    SS_SQLITE_ERR_EXEC       = 4,  /* sqlite3_exec failure (one-shot SQL). */
    SS_SQLITE_ERR_PREPARE    = 5,  /* sqlite3_prepare_v2 returned non-OK. */
    SS_SQLITE_ERR_BIND       = 6,  /* sqlite3_bind_* returned non-OK. */
    SS_SQLITE_ERR_STEP       = 7,  /* sqlite3_step returned a SQLite error. */
    SS_SQLITE_ERR_RESET      = 8,  /* sqlite3_reset returned non-OK. */
    SS_SQLITE_ERR_FINALIZE   = 9   /* sqlite3_finalize returned non-OK. */
};

/*
 * step() result codes are deliberately above the error range so callers
 * can write `if (rc == SS_SQLITE_STEP_ROW) { ... }` without colliding
 * with the error enum.
 */
enum {
    SS_SQLITE_STEP_ROW       = 100,
    SS_SQLITE_STEP_DONE      = 101
};

/*
 * Column type tags returned by ss_sqlite_statement_column_type().
 * Numerically aligned with the SQLITE_INTEGER/FLOAT/TEXT/BLOB/NULL
 * constants so the adapter can forward sqlite3_column_type() directly,
 * but redeclared here to keep the ABI independent of `sqlite3.h`.
 */
enum {
    SS_SQLITE_COLUMN_INTEGER = 1,
    SS_SQLITE_COLUMN_FLOAT   = 2,
    SS_SQLITE_COLUMN_TEXT    = 3,
    SS_SQLITE_COLUMN_BLOB    = 4,
    SS_SQLITE_COLUMN_NULL    = 5
};

/*
 * Open mode flag bits passed to ss_sqlite_database_open(). At least one of
 * READONLY / READWRITE must be set. CREATE is meaningful only with
 * READWRITE. MEMORY opens an anonymous in-memory database regardless of
 * the path argument and is the recommended mode for unit tests.
 */
enum {
    SS_SQLITE_OPEN_READONLY  = 0x01,
    SS_SQLITE_OPEN_READWRITE = 0x02,
    SS_SQLITE_OPEN_CREATE    = 0x04,
    SS_SQLITE_OPEN_MEMORY    = 0x08
};

int ss_sqlite_database_open(
    const char *filesystem_path,
    int open_flags,
    SSSqliteDatabase **out_database
);

/*
 * Close a database opened by ss_sqlite_database_open(). On success the
 * wrapper the caller holds is freed; on SS_SQLITE_ERR_CLOSE the
 * database remains valid (typically because statements are still
 * unfinalized) and the caller can retry after cleanup.
 */
int ss_sqlite_database_close(SSSqliteDatabase *database);

const char *ss_sqlite_database_errmsg(SSSqliteDatabase *database);
long long   ss_sqlite_database_last_insert_rowid(SSSqliteDatabase *database);
int         ss_sqlite_database_changes(SSSqliteDatabase *database);

/*
 * One-shot execution for SQL that takes no parameters and returns no
 * rows (CREATE TABLE, INSERT ... VALUES (literals), PRAGMA, etc.).
 * For anything with bound parameters or result rows, use the
 * prepare/step/finalize cycle below.
 */
int ss_sqlite_exec(SSSqliteDatabase *database, const char *sql_text);

int ss_sqlite_statement_prepare(
    SSSqliteDatabase *database,
    const char *sql_text,
    SSSqliteStatement **out_statement
);

int ss_sqlite_statement_finalize(SSSqliteStatement *statement);
int ss_sqlite_statement_reset(SSSqliteStatement *statement);
int ss_sqlite_statement_step(SSSqliteStatement *statement);

/*
 * Parameter binding uses 1-based indexing (matching sqlite3_bind_*).
 * Text and blob bindings COPY the input into SQLite's internal buffer
 * via SQLITE_TRANSIENT, so the caller can free or reuse the source
 * memory immediately after the bind call returns. This trades a
 * memcpy per bind for a much simpler caller contract.
 */
int ss_sqlite_statement_bind_int64(SSSqliteStatement *statement, int parameter_index, long long value);
int ss_sqlite_statement_bind_double(SSSqliteStatement *statement, int parameter_index, double value);
int ss_sqlite_statement_bind_text(SSSqliteStatement *statement, int parameter_index, const char *value);
int ss_sqlite_statement_bind_blob(SSSqliteStatement *statement, int parameter_index, const void *value, size_t value_length);
int ss_sqlite_statement_bind_null(SSSqliteStatement *statement, int parameter_index);

/* Column accessors use 0-based indexing (matching sqlite3_column_*). */
int         ss_sqlite_statement_column_count(SSSqliteStatement *statement);
int         ss_sqlite_statement_column_type(SSSqliteStatement *statement, int column_index);
const char *ss_sqlite_statement_column_name(SSSqliteStatement *statement, int column_index);
long long   ss_sqlite_statement_column_int64(SSSqliteStatement *statement, int column_index);
double      ss_sqlite_statement_column_double(SSSqliteStatement *statement, int column_index);
const char *ss_sqlite_statement_column_text(SSSqliteStatement *statement, int column_index);
const void *ss_sqlite_statement_column_blob(SSSqliteStatement *statement, int column_index);
size_t      ss_sqlite_statement_column_bytes(SSSqliteStatement *statement, int column_index);

/*
 * Returns the underlying SQLite version string (e.g. "3.53.1").
 * Used by the smoke demo and as a quick sanity check that the
 * vendored amalgamation actually got linked in.
 */
const char *ss_sqlite_library_version(void);

#ifdef __cplusplus
}
#endif

#endif
