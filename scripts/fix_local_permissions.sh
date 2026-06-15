#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(dirname "$(realpath "$0")")
ROOT_DIR=$(realpath "${SCRIPT_DIR:?}"/..)
FLOWSIM_ROOT=${FLOWSIM_ROOT:-/home/zty/Topo/m4/SimAI}
OWNER=${OWNER:-$(id -un)}
GROUP=${GROUP:-$(id -gn)}

TARGETS=(
    "${ROOT_DIR:?}/bin"
    "${ROOT_DIR:?}/astra-sim-alibabacloud/extern"
    "${ROOT_DIR:?}/astra-sim-alibabacloud/extern/network_backend"
    "${ROOT_DIR:?}/astra-sim-alibabacloud/extern/network_backend/ns3-interface"
    "${ROOT_DIR:?}/astra-sim-alibabacloud/build/astra_ns3/build"
    "${FLOWSIM_ROOT:?}/bin/SimAI_flowsim"
    "${FLOWSIM_ROOT:?}/astra-sim-alibabacloud/build/simai_flowsim"
)

existing_targets=()
for target in "${TARGETS[@]}"; do
    if [ -e "${target:?}" ]; then
        existing_targets+=("${target:?}")
    else
        printf 'skip missing: %s\n' "${target:?}"
    fi
done

if [ "${#existing_targets[@]}" -eq 0 ]; then
    printf 'no permission targets found\n'
    exit 0
fi

printf 'fix owner to %s:%s\n' "${OWNER:?}" "${GROUP:?}"
if [ "$(id -u)" -eq 0 ]; then
    chown -R "${OWNER:?}:${GROUP:?}" "${existing_targets[@]}"
else
    sudo chown -R "${OWNER:?}:${GROUP:?}" "${existing_targets[@]}"
fi

chmod -R u+rwX,g+rwX,o+rX "${existing_targets[@]}"
printf 'done\n'
