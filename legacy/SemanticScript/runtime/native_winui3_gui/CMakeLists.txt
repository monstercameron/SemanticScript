cmake_minimum_required(VERSION 3.20)

project(sem_winui3_gui_runtime CXX)

add_library(sem_winui3_gui_runtime_contract INTERFACE)
target_include_directories(
    sem_winui3_gui_runtime_contract
    INTERFACE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/../native_win32_gui
)

option(SEM_WINUI3_ENABLE_IMPLEMENTATION "Build the experimental WinUI 3 GUI adapter" OFF)

if(SEM_WINUI3_ENABLE_IMPLEMENTATION)
    message(FATAL_ERROR
        "The WinUI 3 adapter scaffold is present, but the implementation is "
        "not buildable yet. Add Windows App SDK / C++/WinRT package integration "
        "before enabling SEM_WINUI3_ENABLE_IMPLEMENTATION. See README.md.")
endif()
