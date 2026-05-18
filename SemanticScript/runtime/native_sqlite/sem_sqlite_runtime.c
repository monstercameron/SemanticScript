#include "sem_sqlite_runtime.h"

#include "sqlite3.h"

#include <ctype.h>
#include <limits.h>
#include <stdlib.h>

/*
 * Opaque wrappers around the upstream handles. We deliberately keep these
 * as distinct allocated structs (rather than typedef'ing
 * `SSSqliteDatabase = sqlite3`) so that:
 *
 *   1. The public header in sem_sqlite_runtime.h does not need to forward-
 *      declare or reference any upstream SQLite type.
 *   2. We have a stable place to attach adapter-side state in the future
 *      (e.g. a per-connection journal-mode cache, a logging hook, or a
 *      reference back to the owning database from a prepared statement).
 *   3. The adapter owns the lifetime boundary, so future state can be
 *      invalidated in one place before the upstream handle is released.
 */
struct SSSqliteDatabase {
    sqlite3 *handle;
};

struct SSSqliteStatement {
    sqlite3_stmt *handle;
    SSSqliteDatabase *owning_database;
};

static int translate_sqlite_open_flags(int open_flags, int *out_sqlite_flags) {
    int translated = 0;

    if (out_sqlite_flags == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    /* The caller must pick exactly one access mode. SQLite would otherwise
     * silently default to READONLY for an unspecified combination, which
     * tends to surface much later as a confusing "attempt to write a
     * readonly database" — easier to reject up front. */
    int wants_readonly  = (open_flags & SS_SQLITE_OPEN_READONLY)  != 0;
    int wants_readwrite = (open_flags & SS_SQLITE_OPEN_READWRITE) != 0;

    if (wants_readonly == wants_readwrite) {
        return SS_SQLITE_ERR_CONFIG;
    }

    translated |= wants_readonly ? SQLITE_OPEN_READONLY : SQLITE_OPEN_READWRITE;

    if ((open_flags & SS_SQLITE_OPEN_CREATE) != 0) {
        if (wants_readonly) {
            return SS_SQLITE_ERR_CONFIG;
        }
        translated |= SQLITE_OPEN_CREATE;
    }

    if ((open_flags & SS_SQLITE_OPEN_MEMORY) != 0) {
        translated |= SQLITE_OPEN_MEMORY;
    }

    *out_sqlite_flags = translated;
    return SS_SQLITE_OK;
}

int ss_sqlite_database_open(
    const char *filesystem_path,
    int open_flags,
    SSSqliteDatabase **out_database
) {
    int sqlite_flags = 0;
    int translation_status = 0;
    int open_status = 0;
    SSSqliteDatabase *database = NULL;

    if (out_database == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    *out_database = NULL;

    /* SQLite treats a NULL path as ":memory:" only when SQLITE_OPEN_MEMORY
     * is also set. Pre-validate to give callers a clear ERR_CONFIG instead
     * of letting sqlite3_open_v2 surface a generic error. */
    int memory_mode = (open_flags & SS_SQLITE_OPEN_MEMORY) != 0;
    if (filesystem_path == NULL && !memory_mode) {
        return SS_SQLITE_ERR_CONFIG;
    }

    translation_status = translate_sqlite_open_flags(open_flags, &sqlite_flags);
    if (translation_status != SS_SQLITE_OK) {
        return translation_status;
    }

    database = (SSSqliteDatabase *)calloc(1, sizeof(*database));
    if (database == NULL) {
        return SS_SQLITE_ERR_OPEN;
    }

    const char *effective_path = memory_mode ? ":memory:" : filesystem_path;
    open_status = sqlite3_open_v2(effective_path, &database->handle, sqlite_flags, NULL);
    if (open_status != SQLITE_OK) {
        /* sqlite3_open_v2 still allocates the handle on most error paths so
         * the caller can retrieve the failure message; we have to close it
         * here because we're about to discard our wrapper. */
        if (database->handle != NULL) {
            sqlite3_close(database->handle);
        }
        free(database);
        return SS_SQLITE_ERR_OPEN;
    }

    *out_database = database;
    return SS_SQLITE_OK;
}

int ss_sqlite_database_close(SSSqliteDatabase *database) {
    int close_status = 0;

    if (database == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    /* sqlite3_close returns SQLITE_BUSY if statements are still alive.
     * We surface that to the caller rather than leaking or force-finalizing,
     * so a "you forgot to finalize" bug stays visible. */
    close_status = sqlite3_close(database->handle);
    if (close_status != SQLITE_OK) {
        return SS_SQLITE_ERR_CLOSE;
    }

    free(database);
    return SS_SQLITE_OK;
}

const char *ss_sqlite_database_errmsg(SSSqliteDatabase *database) {
    if (database == NULL || database->handle == NULL) {
        return "";
    }
    return sqlite3_errmsg(database->handle);
}

long long ss_sqlite_database_last_insert_rowid(SSSqliteDatabase *database) {
    if (database == NULL || database->handle == NULL) {
        return 0;
    }
    return (long long)sqlite3_last_insert_rowid(database->handle);
}

int ss_sqlite_database_changes(SSSqliteDatabase *database) {
    if (database == NULL || database->handle == NULL) {
        return 0;
    }
    return sqlite3_changes(database->handle);
}

int ss_sqlite_exec(SSSqliteDatabase *database, const char *sql_text) {
    int exec_status = 0;

    if (database == NULL || database->handle == NULL || sql_text == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    /* We pass NULL for the error message out-pointer because the per-
     * connection message is already reachable via sqlite3_errmsg() and we
     * don't want to bear the malloc/free cost of the duplicate string. */
    exec_status = sqlite3_exec(database->handle, sql_text, NULL, NULL, NULL);
    if (exec_status != SQLITE_OK) {
        return SS_SQLITE_ERR_EXEC;
    }

    return SS_SQLITE_OK;
}

int ss_sqlite_statement_prepare(
    SSSqliteDatabase *database,
    const char *sql_text,
    SSSqliteStatement **out_statement
) {
    int prepare_status = 0;
    SSSqliteStatement *statement = NULL;
    const char *trailing_sql = NULL;

    if (out_statement == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    *out_statement = NULL;

    if (database == NULL || database->handle == NULL || sql_text == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    statement = (SSSqliteStatement *)calloc(1, sizeof(*statement));
    if (statement == NULL) {
        return SS_SQLITE_ERR_PREPARE;
    }
    statement->owning_database = database;

    /* Treat any SQL past the first statement as caller error.
     * Multi-statement scripts should go through ss_sqlite_exec() instead. */
    prepare_status = sqlite3_prepare_v2(
        database->handle,
        sql_text,
        -1,
        &statement->handle,
        &trailing_sql
    );
    if (prepare_status != SQLITE_OK) {
        if (statement->handle != NULL) {
            sqlite3_finalize(statement->handle);
        }
        free(statement);
        return SS_SQLITE_ERR_PREPARE;
    }
    if (statement->handle == NULL) {
        free(statement);
        return SS_SQLITE_ERR_PREPARE;
    }
    while (trailing_sql != NULL && *trailing_sql != '\0') {
        if (!isspace((unsigned char)*trailing_sql)) {
            sqlite3_finalize(statement->handle);
            free(statement);
            return SS_SQLITE_ERR_PREPARE;
        }
        trailing_sql++;
    }

    *out_statement = statement;
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_finalize(SSSqliteStatement *statement) {
    int finalize_status = 0;

    if (statement == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    finalize_status = sqlite3_finalize(statement->handle);
    free(statement);
    if (finalize_status != SQLITE_OK) {
        return SS_SQLITE_ERR_FINALIZE;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_reset(SSSqliteStatement *statement) {
    int reset_status = 0;

    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    reset_status = sqlite3_reset(statement->handle);
    if (reset_status != SQLITE_OK) {
        return SS_SQLITE_ERR_RESET;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_step(SSSqliteStatement *statement) {
    int step_status = 0;

    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }

    step_status = sqlite3_step(statement->handle);
    if (step_status == SQLITE_ROW) {
        return SS_SQLITE_STEP_ROW;
    }
    if (step_status == SQLITE_DONE) {
        return SS_SQLITE_STEP_DONE;
    }
    return SS_SQLITE_ERR_STEP;
}

int ss_sqlite_statement_bind_int64(SSSqliteStatement *statement, int parameter_index, long long value) {
    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    if (sqlite3_bind_int64(statement->handle, parameter_index, (sqlite3_int64)value) != SQLITE_OK) {
        return SS_SQLITE_ERR_BIND;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_bind_double(SSSqliteStatement *statement, int parameter_index, double value) {
    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    if (sqlite3_bind_double(statement->handle, parameter_index, value) != SQLITE_OK) {
        return SS_SQLITE_ERR_BIND;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_bind_text(SSSqliteStatement *statement, int parameter_index, const char *value) {
    if (statement == NULL || statement->handle == NULL || value == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    /* SQLITE_TRANSIENT makes SQLite copy the bytes immediately, so the
     * caller is free to mutate or free `value` the instant bind returns. */
    if (sqlite3_bind_text(statement->handle, parameter_index, value, -1, SQLITE_TRANSIENT) != SQLITE_OK) {
        return SS_SQLITE_ERR_BIND;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_bind_blob(SSSqliteStatement *statement, int parameter_index, const void *value, size_t value_length) {
    static const unsigned char empty_blob = 0;
    const void *blob_value = value;

    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    /* A NULL value with length 0 is a legitimate zero-length blob; pass a
     * stable non-NULL address so SQLite does not reinterpret it as SQL NULL.
     * Bind_null is the right call for SQL NULL. */
    if (value == NULL) {
        if (value_length != 0) {
            return SS_SQLITE_ERR_CONFIG;
        }
        blob_value = &empty_blob;
    }
    /* sqlite3_bind_blob takes an int length, so reject any blob whose
     * size would overflow. Real SQLite blobs are also capped by
     * SQLITE_MAX_LENGTH (1 GiB by default), but the int boundary is the
     * narrower one on platforms where size_t is 64-bit. */
    if (value_length > (size_t)INT_MAX) {
        return SS_SQLITE_ERR_BIND;
    }
    if (sqlite3_bind_blob(statement->handle, parameter_index, blob_value, (int)value_length, SQLITE_TRANSIENT) != SQLITE_OK) {
        return SS_SQLITE_ERR_BIND;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_bind_null(SSSqliteStatement *statement, int parameter_index) {
    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_ERR_CONFIG;
    }
    if (sqlite3_bind_null(statement->handle, parameter_index) != SQLITE_OK) {
        return SS_SQLITE_ERR_BIND;
    }
    return SS_SQLITE_OK;
}

int ss_sqlite_statement_column_count(SSSqliteStatement *statement) {
    if (statement == NULL || statement->handle == NULL) {
        return 0;
    }
    return sqlite3_column_count(statement->handle);
}

int ss_sqlite_statement_column_type(SSSqliteStatement *statement, int column_index) {
    if (statement == NULL || statement->handle == NULL) {
        return SS_SQLITE_COLUMN_NULL;
    }
    /* SQLITE_INTEGER..SQLITE_NULL are numerically 1..5 and our enum was
     * declared to match. Forwarding the cast is safe across all SQLite
     * versions we vendor. */
    return sqlite3_column_type(statement->handle, column_index);
}

const char *ss_sqlite_statement_column_name(SSSqliteStatement *statement, int column_index) {
    if (statement == NULL || statement->handle == NULL) {
        return "";
    }
    const char *name = sqlite3_column_name(statement->handle, column_index);
    return (name != NULL) ? name : "";
}

long long ss_sqlite_statement_column_int64(SSSqliteStatement *statement, int column_index) {
    if (statement == NULL || statement->handle == NULL) {
        return 0;
    }
    return (long long)sqlite3_column_int64(statement->handle, column_index);
}

double ss_sqlite_statement_column_double(SSSqliteStatement *statement, int column_index) {
    if (statement == NULL || statement->handle == NULL) {
        return 0.0;
    }
    return sqlite3_column_double(statement->handle, column_index);
}

const char *ss_sqlite_statement_column_text(SSSqliteStatement *statement, int column_index) {
    if (statement == NULL || statement->handle == NULL) {
        return "";
    }
    const unsigned char *text = sqlite3_column_text(statement->handle, column_index);
    return (text != NULL) ? (const char *)text : "";
}

const void *ss_sqlite_statement_column_blob(SSSqliteStatement *statement, int column_index) {
    if (statement == NULL || statement->handle == NULL) {
        return NULL;
    }
    return sqlite3_column_blob(statement->handle, column_index);
}

size_t ss_sqlite_statement_column_bytes(SSSqliteStatement *statement, int column_index) {
    int byte_count = 0;

    if (statement == NULL || statement->handle == NULL) {
        return 0;
    }
    byte_count = sqlite3_column_bytes(statement->handle, column_index);
    if (byte_count < 0) {
        return 0;
    }
    return (size_t)byte_count;
}

const char *ss_sqlite_library_version(void) {
    return sqlite3_libversion();
}
