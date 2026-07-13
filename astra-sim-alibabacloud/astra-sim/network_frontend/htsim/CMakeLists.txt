# CMake requirement
cmake_minimum_required(VERSION 3.15)

project(SimAI_htsim)

set(HTSIM_ROOT
    "${PROJECT_SOURCE_DIR}/../../../../extern/network_backend/htsim/sim")

include_directories("${PROJECT_SOURCE_DIR}/../../../")
include_directories("${HTSIM_ROOT}")

add_executable(
  SimAI_htsim
  HtsimAstra.cc
  HtsimNetwork.cc)

target_link_libraries(
  SimAI_htsim
  AstraSim
  "${HTSIM_ROOT}/libhtsim.a")

set_property(TARGET SimAI_htsim PROPERTY CXX_STANDARD 17)
