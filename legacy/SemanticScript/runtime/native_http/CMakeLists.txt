cmake_minimum_required(VERSION 3.20)

project(sem_http_runtime C)

option(SEM_HTTP_WITH_H2O "Build the SemanticScript HTTP adapter with H2O bindings" OFF)

add_library(sem_http_runtime STATIC sem_http_runtime.c)
target_include_directories(sem_http_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})

if(WIN32)
  target_link_libraries(sem_http_runtime PUBLIC ws2_32)
endif()

if(SEM_HTTP_WITH_H2O)
  target_compile_definitions(sem_http_runtime PRIVATE SEM_HTTP_WITH_H2O=1)
  target_include_directories(
    sem_http_runtime
    PRIVATE
      ${CMAKE_CURRENT_SOURCE_DIR}/../../../third_party/h2o/include
  )
endif()

add_executable(sem_http_health_demo health_demo.c)
target_link_libraries(sem_http_health_demo PRIVATE sem_http_runtime)
