#!/bin/bash
set -e

SCRIPT_DIR=$(dirname "$(realpath "$0")")
BUILD_DIR="${SCRIPT_DIR:?}"/build/
RESULT_DIR="${SCRIPT_DIR:?}"/result/
HTSIM_DIR="${SCRIPT_DIR:?}"/../../../extern/network_backend/htsim/sim
HTSIM_REPO="${SCRIPT_DIR:?}"/../../../extern/network_backend/htsim
HTSIM_SPRAY_PATCH="${SCRIPT_DIR:?}"/htsim_roce_spray.patch
CMAKE_BIN="${CMAKE_BIN:-/usr/bin/cmake}"

function cleanup_build {
    rm -rf "${BUILD_DIR}"
}

function cleanup_result {
    rm -rf "${RESULT_DIR}"
}

function setup {
    mkdir -p "${BUILD_DIR}"
    mkdir -p "${RESULT_DIR}"
}

function compile {
    if ! grep -q "set_route_strategy" "${HTSIM_DIR:?}"/roce.h; then
        patch -d "${HTSIM_REPO:?}" -p1 -l < "${HTSIM_SPRAY_PATCH:?}"
    fi
    make -C "${HTSIM_DIR:?}" libhtsim.a
    cd "${BUILD_DIR}" || exit
    "${CMAKE_BIN:?}" -DUSE_ANALYTICAL=FALSE -DUSE_HTSIM=TRUE ..
    make
}

case "$1" in
-l|--clean)
    cleanup_build;;
-lr|--clean-result)
    cleanup_build
    cleanup_result;;
-c|--compile)
    setup
    compile;;
-h|--help|*)
    echo "htsim build script."
    echo "Run $0 -c to compile.";;
esac
