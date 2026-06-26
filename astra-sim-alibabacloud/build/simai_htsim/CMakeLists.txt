# CMake requirement
cmake_minimum_required(VERSION 3.15)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)

if (CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    if (CMAKE_CXX_COMPILER_VERSION VERSION_LESS 5.3)
        message(FATAL_ERROR "g++ (GNU) version should be greater than 5.3, but found ${CMAKE_CXX_COMPILER_VERSION}")
    endif()
endif()

project(AstraSim_htsim)

add_definitions(-DHTSIM_BACKEND)

add_subdirectory("${PROJECT_SOURCE_DIR}/../../" AstraSim)
add_subdirectory("${PROJECT_SOURCE_DIR}/../../astra-sim/network_frontend/htsim" simai_htsim)
