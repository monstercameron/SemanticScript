cmake_minimum_required(VERSION 3.20)

project(sem_json_runtime C)

# Zig-cc archiver shim: when the C compiler is `zig cc`, the matching
# `ar` is invoked via `zig ar`. CMake's default archiver discovery does
# not know this, so we override CMAKE_AR / CMAKE_RANLIB to point at the
# same zig binary and rewrite the archive commands accordingly. Mirrors
# the shim in native_sqlite/CMakeLists.txt.
set(_SEM_JSON_C_COMPILER_ARG1 "${CMAKE_C_COMPILER_ARG1}")
string(STRIP "${_SEM_JSON_C_COMPILER_ARG1}" _SEM_JSON_C_COMPILER_ARG1)
if(CMAKE_C_COMPILER MATCHES "zig(\\.exe)?$" AND _SEM_JSON_C_COMPILER_ARG1 STREQUAL "cc")
    set(CMAKE_AR "${CMAKE_C_COMPILER}" CACHE FILEPATH "Zig archiver" FORCE)
    set(CMAKE_RANLIB "${CMAKE_C_COMPILER}" CACHE FILEPATH "Zig ranlib" FORCE)
    set(CMAKE_C_ARCHIVE_CREATE "<CMAKE_AR> ar qc <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_C_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")
endif()

# Adapter target. Pure C; no third-party dependency, so unlike
# native_sqlite there is no separate amalgamation tree to compile.
add_library(sem_json_runtime STATIC sem_json_runtime.c)
target_include_directories(sem_json_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

# Build-time sanity check binary: exercises a small round-trip
# encode + decode cycle. Useful for verifying the adapter compiles
# clean before the semsc dispatch wiring drives any real workload.
add_executable(sem_json_health_demo health_demo.c)
target_link_libraries(sem_json_health_demo PRIVATE sem_json_runtime)
