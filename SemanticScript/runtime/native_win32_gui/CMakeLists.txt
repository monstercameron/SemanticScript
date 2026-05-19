cmake_minimum_required(VERSION 3.20)

project(sem_win32_gui_runtime C)

if(CMAKE_C_COMPILER MATCHES "zig(\\.exe)?$" AND CMAKE_C_COMPILER_ARG1 STREQUAL "cc")
    set(CMAKE_AR "${CMAKE_C_COMPILER}" CACHE FILEPATH "Zig archiver" FORCE)
    set(CMAKE_RANLIB "${CMAKE_C_COMPILER}" CACHE FILEPATH "Zig ranlib" FORCE)
    set(CMAKE_C_ARCHIVE_CREATE "<CMAKE_AR> ar qc <TARGET> <LINK_FLAGS> <OBJECTS>")
    set(CMAKE_C_ARCHIVE_FINISH "<CMAKE_RANLIB> ranlib <TARGET>")
endif()

add_library(sem_win32_gui_runtime STATIC sem_win32_gui_runtime.c)
target_include_directories(sem_win32_gui_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(WIN32)
    target_link_libraries(sem_win32_gui_runtime PUBLIC user32 gdi32)
endif()

add_executable(sem_win32_gui_health_demo health_demo.c)
target_link_libraries(sem_win32_gui_health_demo PRIVATE sem_win32_gui_runtime)
