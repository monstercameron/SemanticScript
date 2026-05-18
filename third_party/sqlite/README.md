# SQLite (vendored amalgamation)

This is the upstream-blessed single-file distribution of SQLite, dropped in
directly rather than carried as a git submodule. The amalgamation is small
(~9 MB unpacked, ~2.8 MB zipped), public-domain, and self-contained — keeping
it vendored avoids the `git submodule update --init --recursive` step that
`third_party/h2o` requires.

## Pinned version

- Release: **SQLite 3.53.1**
- Upstream archive: `https://sqlite.org/2026/sqlite-amalgamation-3530100.zip`
- `SQLITE_VERSION`: `3.53.1` (see `sqlite3.h` line 149)
- `SQLITE_SOURCE_ID`:
  `2026-05-05 10:34:17 c88b22011a54b4f6fbd149e9f8e4de77658ce58143a1af0e3785e4e6475127e9`

The `SQLITE_SOURCE_ID` hash is the cryptographic fingerprint of the SQLite
source tree at the moment the amalgamation was generated — this is the
identity you pin against, not the outer zip hash. SQLite occasionally
re-archives the same release with different ZIP timestamps, so the zip-level
SHA256 drifts even when the source bytes don't. Verify upgrades by checking
that `SQLITE_SOURCE_ID` matches the value on the SQLite changelog page.

## Files

| File          | Purpose                                                       |
| ------------- | ------------------------------------------------------------- |
| `sqlite3.c`   | The amalgamated SQLite library. This is the only file we compile into `sem_sqlite_runtime`. |
| `sqlite3.h`   | Public API header. Consumed by the runtime adapter and any caller of the C ABI. |
| `sqlite3ext.h`| Loadable-extension API. Kept for completeness, but `SQLITE_OMIT_LOAD_EXTENSION` is set in our build so it is not exercised. |
| `shell.c`     | Source for the standalone `sqlite3` shell. Not built by default; vendored only so we can compile a debug shell on demand. |

## Upgrading

1. Download the next amalgamation from `https://sqlite.org/download.html`.
2. Replace these four files with the contents of the new
   `sqlite-amalgamation-<version>/` directory.
3. Update **both** `SQLITE_VERSION` and `SQLITE_SOURCE_ID` in this file from
   the new `sqlite3.h`.
4. Re-run the `native_sqlite` build and smoke tests
   (`SemanticScript/runtime/native_sqlite/`) to confirm nothing regressed.

## License

SQLite is in the public domain. There is no SemanticScript-side license
obligation introduced by carrying it in-tree.

## Do not edit

Do not patch these files directly. SemanticScript-side adapter code lives in
`SemanticScript/runtime/native_sqlite/`. Patching the amalgamation would
silently diverge from upstream and be lost on the next upgrade.
