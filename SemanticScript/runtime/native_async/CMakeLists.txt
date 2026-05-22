cmake_minimum_required(VERSION 3.20)

project(sem_async_runtime C)

option(SEM_ASYNC_WITH_LIBUV "Build SemanticScript async runtime with libuv" OFF)
option(SEM_ASYNC_FETCH_LIBUV "Fetch and build libuv when SEM_ASYNC_WITH_LIBUV is ON and no system libuv is found" ON)

add_library(sem_async_runtime STATIC sem_async_runtime.c)
target_include_directories(sem_async_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(SEM_ASYNC_WITH_LIBUV)
  find_package(PkgConfig QUIET)
  if(PkgConfig_FOUND)
    pkg_check_modules(LIBUV QUIET libuv)
  endif()

  set(_SEM_LIBUV_INCLUDE_HINTS)
  set(_SEM_LIBUV_LIBRARY_HINTS)
  if(DEFINED ENV{SEM_LIBUV_ROOT})
    list(APPEND _SEM_LIBUV_INCLUDE_HINTS "$ENV{SEM_LIBUV_ROOT}/include")
    list(APPEND _SEM_LIBUV_LIBRARY_HINTS "$ENV{SEM_LIBUV_ROOT}/lib" "$ENV{SEM_LIBUV_ROOT}/lib64")
  endif()
  if(DEFINED ENV{SEM_LIBUV_INCLUDE_DIR})
    list(APPEND _SEM_LIBUV_INCLUDE_HINTS "$ENV{SEM_LIBUV_INCLUDE_DIR}")
  endif()
  if(DEFINED ENV{SEM_LIBUV_LIB_DIR})
    list(APPEND _SEM_LIBUV_LIBRARY_HINTS "$ENV{SEM_LIBUV_LIB_DIR}")
  endif()

  find_path(LIBUV_INCLUDE_DIR uv.h HINTS ${LIBUV_INCLUDE_DIRS} ${_SEM_LIBUV_INCLUDE_HINTS})
  if(DEFINED ENV{SEM_LIBUV_LIB} AND EXISTS "$ENV{SEM_LIBUV_LIB}")
    set(LIBUV_LIBRARY "$ENV{SEM_LIBUV_LIB}")
  elseif(DEFINED ENV{SEM_LIBUV_LIBRARY} AND EXISTS "$ENV{SEM_LIBUV_LIBRARY}")
    set(LIBUV_LIBRARY "$ENV{SEM_LIBUV_LIBRARY}")
  else()
    find_library(LIBUV_LIBRARY NAMES uv libuv HINTS ${LIBUV_LIBRARY_DIRS} ${_SEM_LIBUV_LIBRARY_HINTS})
  endif()

  target_compile_definitions(sem_async_runtime PUBLIC SEM_ASYNC_WITH_LIBUV=1)

  if(LIBUV_INCLUDE_DIR AND LIBUV_LIBRARY)
    target_include_directories(sem_async_runtime PUBLIC ${LIBUV_INCLUDE_DIR})
    target_link_libraries(sem_async_runtime PUBLIC ${LIBUV_LIBRARY})
  elseif(SEM_ASYNC_FETCH_LIBUV)
    include(FetchContent)
    set(LIBUV_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(LIBUV_BUILD_BENCH OFF CACHE BOOL "" FORCE)
    FetchContent_Declare(
      sem_libuv
      GIT_REPOSITORY https://github.com/libuv/libuv.git
      GIT_TAG v1.48.0
      GIT_SHALLOW TRUE
    )
    FetchContent_MakeAvailable(sem_libuv)
    if(TARGET uv_a)
      target_link_libraries(sem_async_runtime PUBLIC uv_a)
    elseif(TARGET uv)
      target_link_libraries(sem_async_runtime PUBLIC uv)
    else()
      message(FATAL_ERROR "Fetched libuv did not define an expected uv_a or uv target")
    endif()
    target_include_directories(sem_async_runtime PUBLIC ${sem_libuv_SOURCE_DIR}/include)
  else()
    message(FATAL_ERROR "SEM_ASYNC_WITH_LIBUV=ON requires libuv headers/library or SEM_ASYNC_FETCH_LIBUV=ON")
  endif()

  if(WIN32)
    target_link_libraries(sem_async_runtime PUBLIC ws2_32 iphlpapi userenv psapi)
  endif()
endif()

add_executable(sem_async_health_demo health_demo.c)
target_link_libraries(sem_async_health_demo PRIVATE sem_async_runtime)
