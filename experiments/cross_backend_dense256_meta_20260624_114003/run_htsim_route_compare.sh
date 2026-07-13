#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_ROOT="${ROOT_DIR}/experiments/cross_backend_dense256_meta_20260624_114003"
STAMP="${1:-$(date +%Y%m%d_%H%M%S)}"

WORKLOAD="${ROOT_DIR}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt"
TOPOLOGY="${ROOT_DIR}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100"
CONFIG="${ROOT_DIR}/myconfig/Meta256MoE.conf"

run_case() {
  local strategy="$1"
  local out_dir="${OUT_ROOT}/htsim_${strategy}_full_${STAMP}"
  mkdir -p "${out_dir}"
  {
    echo "START $(date -Is)"
    echo "strategy=${strategy}"
    echo "workload=${WORKLOAD}"
    echo "topology=${TOPOLOGY}"
    echo "config=${CONFIG}"
    status=0
    /usr/bin/time -v env HTSIM_FLOW_RECLAIM_BATCH=262144 \
      "${ROOT_DIR}/bin/SimAI_htsim" \
      -w "${WORKLOAD}" \
      -n "${TOPOLOGY}" \
      -c "${CONFIG}" \
      -o "${out_dir}/" \
      -r "${strategy}" || status=$?
    echo "EXIT:${status}"
    echo "END $(date -Is)"
    return "${status}"
  } > "${out_dir}/run.log" 2>&1
}

run_case ecmp
run_case spray_rr
