#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

SOURCE_256="${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt"
SOURCE_1024="${ROOT}/my_workloads/H100-gpt_175B-world_size1024-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt"

TARGET_256="${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-dp4-pp8-gbs384-mbs1-seq2048-interleaved3.txt"
TARGET_1024="${ROOT}/my_workloads/H100-gpt_175B-world_size1024-tp8-dp16-pp8-gbs1536-mbs1-seq4096-interleaved3.txt"

generate_workload() {
  local source="$1"
  local target="$2"
  local expected_header="$3"

  [[ -f "${source}" ]] || {
    echo "missing workload template: ${source}" >&2
    exit 1
  }

  sed -E '1 s/vpp: [0-9]+/vpp: 3/' "${source}" > "${target}"
  grep -q "${expected_header}" "${target}" || {
    echo "generated workload header mismatch: ${target}" >&2
    exit 1
  }

  local declared_rows
  local actual_rows
  declared_rows="$(sed -n '2p' "${target}")"
  actual_rows="$(( $(wc -l < "${target}") - 2 ))"
  [[ "${declared_rows}" -eq "${actual_rows}" ]] || {
    echo "generated workload row mismatch: declared=${declared_rows} actual=${actual_rows}" >&2
    exit 1
  }

  echo "generated ${target} (${actual_rows} rows)"
}

generate_workload \
  "${SOURCE_256}" \
  "${TARGET_256}" \
  "model_parallel_NPU_group: 8 ep: 1 pp: 8 vpp: 3 ga: 96 all_gpus: 256"

generate_workload \
  "${SOURCE_1024}" \
  "${TARGET_1024}" \
  "model_parallel_NPU_group: 8 ep: 1 pp: 8 vpp: 3 ga: 96 all_gpus: 1024"

