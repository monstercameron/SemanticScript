cmake_minimum_required(VERSION 3.20)

project(sem_sqlite_runtime C)

if(CMAKE_C_COMPILER MATCHES "zig(\\.exe)?$" AND CMAKE_C_COMPILER_ARG1 MATCHES "cc")
    set(CMAKE_AR "${CMAKE_C_COMPILER}" CACHE FILEPATH "Zig archiver" FORCE)
    set(CMAKE_RANLIB "${CMAKE_C_COMPILER}" CACHE FILEPATH "Zig ranlib" FORCE)
    set(CMAKE_C_ARCHIVE_CREATE "<CMAKE_AR> ar qc <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_C_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")
endif()

# Path to the vendored amalgamation. third_party/sqlite/ holds the upstream
# single-file distribution and is treated as read-only; see
# third_party/sqlite/README.md for the upgrade procedure.
set(SEM_SQLITE_AMALGAMATION_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/../../../third_party/sqlite")

# The amalgamation is compiled into its own STATIC target so that the
# compile-time defines we apply (the SQLITE_* knobs below) stay scoped to
# the SQLite source and don't leak into adapter code or callers.
add_library(sem_sqlite_amalgamation STATIC
    "${SEM_SQLITE_AMALGAMATION_DIR}/sqlite3.c")
target_include_directories(sem_sqlite_amalgamation
    PUBLIC "${SEM_SQLITE_AMALGAMATION_DIR}")

# Conservative build profile. The reasoning behind each define:
#
#   SQLITE_OMIT_LOAD_EXTENSION
#     We never want a SQL string to be able to side-load a native .so/.dll.
#     This is a hard security posture for embedded-SQL workloads.
#
#   SQLITE_OMIT_DEPRECATED
#     Drops the v1 callback APIs that we have no plans to expose. Saves a
#     small amount of code size and removes attack surface we'd never test.
#
#   SQLITE_DQS=0
#     Forbids double-quoted string literals, a MySQL-ism that SQLite still
#     accepts by default but that quietly turns `WHERE name = "alice"` into
#     a column reference when `alice` doesn't exist as a column. Disabling
#     it removes a class of silent SQL bugs.
#
#   SQLITE_THREADSAFE=2
#     Multi-threaded mode: connections are NOT serialized internally, but
#     SQLite as a whole is safe to use from multiple threads as long as a
#     given SSSqliteDatabase / SSSqliteStatement is only touched by one
#     thread at a time. This is the right default for an async runtime
#     where each task owns its own connection.
#
#   SQLITE_DEFAULT_MEMSTATUS=0
#     Skips per-allocation bookkeeping the runtime adapter never reads.
#     Small but free perf win.
#
#   SQLITE_USE_URI=1
#     Lets callers open `file:foo.db?mode=memory&cache=shared` for shared
#     in-memory databases. Cheap to enable; useful for tests.
target_compile_definitions(sem_sqlite_amalgamation PRIVATE
    SQLITE_OMIT_LOAD_EXTENSION
    SQLITE_OMIT_DEPRECATED
    SQLITE_DQS=0
    SQLITE_THREADSAFE=2
    SQLITE_DEFAULT_MEMSTATUS=0
    SQLITE_USE_URI=1)

# SQLite emits a few legitimate-but-noisy diagnostics under clang's
# -Weverything-style warning sets. Silence them in the amalgamation target
# only so adapter and demo code still get the warnings.
if(CMAKE_C_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(sem_sqlite_amalgamation PRIVATE
        -w)
endif()

# On non-Windows platforms SQLite needs libdl for runtime resolution of
# things like fdatasync detection, libpthread when THREADSAFE != 0, and
# libm for floating-point intrinsics in some date functions.
if(UNIX)
    find_package(Threads REQUIRED)
    target_link_libraries(sem_sqlite_amalgamation PUBLIC Threads::Threads ${CMAKE_DL_LIBS} m)
endif()

# The adapter: thin C wrapper presenting the SS* ABI defined in
# sem_sqlite_runtime.h. This is what generated SemanticScript code links
# against; the amalgamation is a transitive dep behind it.
add_library(sem_sqlite_runtime STATIC sem_sqlite_runtime.c)
target_include_directories(sem_sqlite_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(sem_sqlite_runtime PUBLIC sem_sqlite_amalgamation)

# Build-time sanity check: a tiny demo that opens an in-memory DB and runs
# a round-trip insert + select. Useful for CI smoke and for local
# verification when bumping the vendored amalgamation.
add_executable(sem_sqlite_health_demo health_demo.c)
target_link_libraries(sem_sqlite_health_demo PRIVATE sem_sqlite_runtime)
