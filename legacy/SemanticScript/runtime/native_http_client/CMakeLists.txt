cmake_minimum_required(VERSION 3.20)

project(sem_http_client_runtime C)

option(SEM_HTTP_CLIENT_WITH_CURL "Build SemanticScript HTTP client runtime with libcurl" OFF)
option(SEM_HTTP_CLIENT_FETCH_CURL "Fetch and build libcurl when SEM_HTTP_CLIENT_WITH_CURL is ON and no system libcurl is found" ON)

add_subdirectory(
  ${CMAKE_CURRENT_SOURCE_DIR}/../native_async
  ${CMAKE_CURRENT_BINARY_DIR}/native_async
)

add_library(sem_http_client_runtime STATIC sem_http_client_runtime.c)
target_include_directories(
  sem_http_client_runtime
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/../native_async
)
target_link_libraries(sem_http_client_runtime PUBLIC sem_async_runtime)

if(SEM_HTTP_CLIENT_WITH_CURL)
  set(_SEM_CURL_INCLUDE_HINTS)
  set(_SEM_CURL_LIBRARY_HINTS)
  set(_SEM_CURL_MANUAL_HINT OFF)
  if(DEFINED ENV{SEM_CURL_ROOT})
    set(_SEM_CURL_MANUAL_HINT ON)
    list(APPEND _SEM_CURL_INCLUDE_HINTS "$ENV{SEM_CURL_ROOT}/include")
    list(APPEND _SEM_CURL_LIBRARY_HINTS "$ENV{SEM_CURL_ROOT}/lib" "$ENV{SEM_CURL_ROOT}/lib64")
  endif()
  if(DEFINED ENV{SEM_CURL_INCLUDE_DIR})
    set(_SEM_CURL_MANUAL_HINT ON)
    list(APPEND _SEM_CURL_INCLUDE_HINTS "$ENV{SEM_CURL_INCLUDE_DIR}")
  endif()
  if(DEFINED ENV{SEM_CURL_LIB_DIR})
    set(_SEM_CURL_MANUAL_HINT ON)
    list(APPEND _SEM_CURL_LIBRARY_HINTS "$ENV{SEM_CURL_LIB_DIR}")
  endif()
  if((DEFINED ENV{SEM_CURL_LIB} AND EXISTS "$ENV{SEM_CURL_LIB}") OR
     (DEFINED ENV{SEM_CURL_LIBRARY} AND EXISTS "$ENV{SEM_CURL_LIBRARY}"))
    set(_SEM_CURL_MANUAL_HINT ON)
  endif()

  if(NOT _SEM_CURL_MANUAL_HINT)
    find_package(CURL QUIET)
  endif()
  if(CURL_FOUND AND NOT _SEM_CURL_MANUAL_HINT)
    target_link_libraries(sem_http_client_runtime PUBLIC CURL::libcurl)
  else()
    find_path(CURL_INCLUDE_DIR curl/curl.h HINTS ${_SEM_CURL_INCLUDE_HINTS})
    if(DEFINED ENV{SEM_CURL_LIB} AND EXISTS "$ENV{SEM_CURL_LIB}")
      set(CURL_LIBRARY "$ENV{SEM_CURL_LIB}")
    elseif(DEFINED ENV{SEM_CURL_LIBRARY} AND EXISTS "$ENV{SEM_CURL_LIBRARY}")
      set(CURL_LIBRARY "$ENV{SEM_CURL_LIBRARY}")
    else()
      find_library(CURL_LIBRARY NAMES curl libcurl HINTS ${_SEM_CURL_LIBRARY_HINTS})
    endif()
    if(CURL_INCLUDE_DIR AND CURL_LIBRARY)
      target_include_directories(sem_http_client_runtime PUBLIC ${CURL_INCLUDE_DIR})
      target_link_libraries(sem_http_client_runtime PUBLIC ${CURL_LIBRARY})
    elseif(SEM_HTTP_CLIENT_FETCH_CURL)
      include(FetchContent)
      set(BUILD_CURL_EXE OFF CACHE BOOL "" FORCE)
      set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
      set(BUILD_LIBCURL_DOCS OFF CACHE BOOL "" FORCE)
      set(BUILD_MISC_DOCS OFF CACHE BOOL "" FORCE)
      set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
      set(BUILD_STATIC_LIBS ON CACHE BOOL "" FORCE)
      set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
      set(CURL_DISABLE_INSTALL ON CACHE BOOL "" FORCE)
      set(CURL_USE_LIBPSL OFF CACHE BOOL "" FORCE)
      set(ENABLE_CURL_MANUAL OFF CACHE BOOL "" FORCE)
      set(HTTP_ONLY ON CACHE BOOL "" FORCE)
      if(WIN32)
        set(CURL_USE_SCHANNEL ON CACHE BOOL "" FORCE)
        set(CURL_USE_OPENSSL OFF CACHE BOOL "" FORCE)
      endif()
      FetchContent_Declare(
        sem_curl
        GIT_REPOSITORY https://github.com/curl/curl.git
        GIT_TAG curl-8_8_0
        GIT_SHALLOW TRUE
      )
      FetchContent_MakeAvailable(sem_curl)
      if(TARGET CURL::libcurl)
        target_link_libraries(sem_http_client_runtime PUBLIC CURL::libcurl)
      elseif(TARGET libcurl_static)
        target_link_libraries(sem_http_client_runtime PUBLIC libcurl_static)
        target_compile_definitions(sem_http_client_runtime PUBLIC CURL_STATICLIB=1)
      elseif(TARGET libcurl)
        target_link_libraries(sem_http_client_runtime PUBLIC libcurl)
      else()
        message(FATAL_ERROR "Fetched libcurl did not define an expected CURL::libcurl, libcurl_static, or libcurl target")
      endif()
      target_include_directories(sem_http_client_runtime PUBLIC ${sem_curl_SOURCE_DIR}/include)
    else()
      message(FATAL_ERROR "SEM_HTTP_CLIENT_WITH_CURL=ON requires libcurl headers and library")
    endif()
  endif()
  target_compile_definitions(sem_http_client_runtime PUBLIC SEM_HTTP_CLIENT_WITH_CURL=1)
endif()

add_executable(sem_http_client_health_demo health_demo.c)
target_link_libraries(sem_http_client_health_demo PRIVATE sem_http_client_runtime)

add_executable(sem_http_client_bench_demo bench_demo.c)
target_link_libraries(sem_http_client_bench_demo PRIVATE sem_http_client_runtime)
