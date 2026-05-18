#include "sem_sqlite_runtime.h"

#include <stdio.h>
#include <string.h>

/*
 * Smoke demo for the native_sqlite adapter. Exercises the full
 * open/exec/prepare/bind/step/finalize/close cycle against an in-memory
 * database. The purpose is to prove at the binary level that:
 *
 *   1. The vendored amalgamation linked in (we print sqlite3_libversion()).
 *   2. The ABI surface compiles standalone (no leakage of sqlite3.h types).
 *   3. A round-trip insert + read survives prepare/bind/step/column.
 *
 * Exit code is 0 on success, non-zero (the failing SS_SQLITE_ERR_*) on
 * failure, so this is safe to wire into the build-tape regression once we
 * add a SemanticScript-side surface.
 */

static int report(const char *stage, int status, SSSqliteDatabase *database) {
    fprintf(
        stderr,
        "sem_sqlite_health_demo: %s failed status=%d errmsg=\"%s\"\n",
        stage,
        status,
        ss_sqlite_database_errmsg(database)
    );
    return status;
}

int main(void) {
    SSSqliteDatabase *database = NULL;
    SSSqliteStatement *insert_statement = NULL;
    SSSqliteStatement *select_statement = NULL;
    int status = 0;

    printf("sem_sqlite_health_demo: sqlite library version=%s\n", ss_sqlite_library_version());

    status = ss_sqlite_database_open(
        NULL,
        SS_SQLITE_OPEN_READWRITE | SS_SQLITE_OPEN_CREATE | SS_SQLITE_OPEN_MEMORY,
        &database
    );
    if (status != SS_SQLITE_OK) {
        return report("open", status, database);
    }

    status = ss_sqlite_exec(database, "CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT NOT NULL)");
    if (status != SS_SQLITE_OK) {
        report("exec(CREATE)", status, database);
        ss_sqlite_database_close(database);
        return status;
    }

    status = ss_sqlite_statement_prepare(database, "INSERT INTO notes (body) VALUES (?)", &insert_statement);
    if (status != SS_SQLITE_OK) {
        report("prepare(INSERT)", status, database);
        ss_sqlite_database_close(database);
        return status;
    }

    const char *body_text = "hello from sem_sqlite";
    status = ss_sqlite_statement_bind_text(insert_statement, 1, body_text);
    if (status != SS_SQLITE_OK) {
        report("bind_text", status, database);
        ss_sqlite_statement_finalize(insert_statement);
        ss_sqlite_database_close(database);
        return status;
    }

    status = ss_sqlite_statement_step(insert_statement);
    if (status != SS_SQLITE_STEP_DONE) {
        report("step(INSERT)", status, database);
        ss_sqlite_statement_finalize(insert_statement);
        ss_sqlite_database_close(database);
        return status;
    }

    long long inserted_rowid = ss_sqlite_database_last_insert_rowid(database);
    int changed_rows = ss_sqlite_database_changes(database);
    ss_sqlite_statement_finalize(insert_statement);
    insert_statement = NULL;

    status = ss_sqlite_statement_prepare(database, "SELECT id, body FROM notes WHERE id = ?", &select_statement);
    if (status != SS_SQLITE_OK) {
        report("prepare(SELECT)", status, database);
        ss_sqlite_database_close(database);
        return status;
    }

    status = ss_sqlite_statement_bind_int64(select_statement, 1, inserted_rowid);
    if (status != SS_SQLITE_OK) {
        report("bind_int64", status, database);
        ss_sqlite_statement_finalize(select_statement);
        ss_sqlite_database_close(database);
        return status;
    }

    status = ss_sqlite_statement_step(select_statement);
    if (status != SS_SQLITE_STEP_ROW) {
        report("step(SELECT)", status, database);
        ss_sqlite_statement_finalize(select_statement);
        ss_sqlite_database_close(database);
        return status;
    }

    long long row_id = ss_sqlite_statement_column_int64(select_statement, 0);
    const char *row_body = ss_sqlite_statement_column_text(select_statement, 1);

    printf(
        "sem_sqlite_health_demo: inserted_rowid=%lld changed_rows=%d row_id=%lld row_body=\"%s\"\n",
        inserted_rowid,
        changed_rows,
        row_id,
        row_body
    );

    int round_trip_ok = (row_id == inserted_rowid) && (strcmp(row_body, body_text) == 0) && (changed_rows == 1);

    ss_sqlite_statement_finalize(select_statement);
    ss_sqlite_database_close(database);

    if (!round_trip_ok) {
        fprintf(stderr, "sem_sqlite_health_demo: round-trip mismatch\n");
        return 1;
    }

    printf("sem_sqlite_health_demo: ok\n");
    return 0;
}
