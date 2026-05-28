# Native SQLite Runtime Adapter

This adapter is the SemanticScript-owned boundary between generated code and
the embedded SQL engine. The engine is the upstream **SQLite amalgamation**,
vendored at [`third_party/sqlite/`](../../../third_party/sqlite/README.md);
this adapter is the only thing that includes `sqlite3.h`.

The design mirrors `SemanticScript/runtime/native_http/`:

- A stable C ABI lives in `sem_sqlite_runtime.h`. It deliberately does not
  include `sqlite3.h` so the engine can be replaced or upgraded without
  rippling through callers.
- A thin adapter `sem_sqlite_runtime.c` forwards each entry point to the
  corresponding `sqlite3_*` call, mapping return codes onto the `SS_SQLITE_*`
  enum so a SQLite version bump can't shift our ABI numbering under callers.
- A smoke binary `sem_sqlite_health_demo` exercises the full
  open / exec / prepare / bind / step / column / finalize / close path
  against an in-memory database. It exits non-zero on any failure so it
  drops into CI as-is.

## ABI surface (status)

- Connections: `ss_sqlite_database_open`, `ss_sqlite_database_close`,
  `ss_sqlite_database_errmsg`, `ss_sqlite_database_last_insert_rowid`,
  `ss_sqlite_database_changes`.
- One-shot SQL: `ss_sqlite_exec`; WAL mode:
  `ss_sqlite_database_enable_wal`; scalar Int64 reads:
  `ss_sqlite_query_scalar_int64`; transaction boundaries:
  `ss_sqlite_transaction_begin_immediate`, `ss_sqlite_transaction_commit`,
  `ss_sqlite_transaction_rollback`.
- Prepared statements: `ss_sqlite_statement_prepare / _step / _reset /
  _finalize`.
- Bindings (1-based, TRANSIENT-copied): `_bind_int64`, `_bind_double`,
  `_bind_text`, `_bind_blob`, `_bind_null`.
- Columns (0-based): `_column_count`, `_column_type`, `_column_name`,
  `_column_int64`, `_column_double`, `_column_text`, `_column_blob`,
  `_column_bytes`.
- Version: `ss_sqlite_library_version()` returns the underlying
  `sqlite3_libversion()` string.

## Column pointer lifetime

`ss_sqlite_statement_column_text`, `_column_blob`, and `_column_name` expose
SQLite-owned memory. The pointer belongs to the prepared statement, not to a
process-global scratch buffer: another statement's column reads do not overwrite
it. On the same statement, the next pointer-returning column read,
`ss_sqlite_statement_step`, `ss_sqlite_statement_reset`, or
`ss_sqlite_statement_finalize` can invalidate the older pointer. Generated code
that needs multiple text/blob/name values alive at once must copy or consume
each value before the next same-statement invalidating operation. `semlint`
surfaces this as SS3113.

## Generated ids

New generated-id code should not use
`ss_sqlite_database_last_insert_rowid` / `sqlite.lastInsertRowId` as a normal
dataflow primitive. That value is connection-global state. The native and
webServer-safe pattern is to prepare the INSERT as `INSERT ... RETURNING id`,
step it to `rowSqliteStepResult`, read column 0 with `sqlite.columnInt64`, and
bind that named id into later statements such as an activity-log insert.

When the generated-row insert and activity-log insert must be atomic, wrap them
with `sqlite.beginImmediateTransaction` / `sqlite.commitTransaction`, finalize
or drain the RETURNING statement before COMMIT, and call
`sqlite.rollbackTransaction` on failure paths after BEGIN succeeds. `sem docs
get sqlite.lastInsertRowId --json` exposes the copyable
`target.usage.migration.rows` skeleton, and `semlint` reports SS3639 when code
still depends on `last_insert_rowid()` or `sqlite.lastInsertRowId`.

## Build profile

`CMakeLists.txt` compiles the amalgamation with a conservative set of
defines. The rationale for each is documented inline in the CMake file;
the headline choices are:

- `SQLITE_OMIT_LOAD_EXTENSION` — block runtime loading of native code.
- `SQLITE_DQS=0` — reject the MySQL-style `"double quoted string"` quirk.
- `SQLITE_THREADSAFE=2` — multi-threaded mode, with the invariant that
  any one `SSSqliteDatabase` / `SSSqliteStatement` is owned by one thread
  at a time. The async runtime is expected to enforce this by giving each
  task its own connection.
- `SQLITE_OMIT_DEPRECATED` — drop v1 callback APIs we don't expose.
- `SQLITE_USE_URI=1` — allow `file:foo.db?mode=memory&cache=shared`.

FTS5 and JSON1 are left enabled (they're on by default in the amalgamation
and we want them for app workloads).

## Local compile smoke

On the current Windows toolchain, use Zig's bundled Clang through CMake:

```powershell
$env:CC = "zig cc"
cmake -S SemanticScript/runtime/native_sqlite -B SemanticScript/runtime/native_sqlite/build -G Ninja
cmake --build SemanticScript/runtime/native_sqlite/build
```

Then run the smoke demo:

```powershell
SemanticScript/runtime/native_sqlite/build/sem_sqlite_health_demo.exe
```

Expected output (version may vary with the vendored amalgamation):

```
sem_sqlite_health_demo: sqlite library version=3.53.1
sem_sqlite_health_demo: inserted_rowid=1 changed_rows=1 row_id=1 row_body="hello from sem_sqlite"
sem_sqlite_health_demo: ok
```

## Compiler and Stdlib Integration

This adapter is now wired through the SemanticScript toolchain:

1. `SemanticScript/std/sqlite/main.sem` exposes the public `standard.sqlite`
   import surface for `SqliteDatabase`, `SqliteStatement`, open modes, step
   results, column types, and `sqlite.*` targets.
2. Apps import it with `import sqlite standard.sqlite`; the compiler
   links `sem_sqlite_runtime` for lowered SQLite calls.
3. Feature and app coverage exercise the open / schema / prepare / bind /
   step / column / finalize / close path through generated SemanticScript
   programs, including the curated TaskForge Web application.

Remaining work is product surface, not initial plumbing: broader typed query
helpers, statement-cache abstractions, richer transaction policy, and broader
diagnostics around SQL ownership and lifecycle policy. The first helper,
`sqlite.queryScalarInt64`, covers static no-parameter COUNT/EXISTS-style reads
without exposing a statement handle. WAL is exposed through
`sqlite.enableWalMode` and the build-tape `sqliteJournalMode PROJECT wal`
policy, so apps do not need raw `PRAGMA journal_mode = WAL` SQL constants.
The flat transaction helpers `sqlite.beginImmediateTransaction`,
`sqlite.commitTransaction`, and `sqlite.rollbackTransaction` cover ordinary
explicit transaction boundaries without raw BEGIN/COMMIT/ROLLBACK SQL
constants.
