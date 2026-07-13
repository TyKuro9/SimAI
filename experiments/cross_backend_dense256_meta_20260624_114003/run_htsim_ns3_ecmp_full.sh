#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_ROOT="${ROOT_DIR}/experiments/cross_backend_dense256_meta_20260624_114003"
STAMP="${1:-20260702_ns3_ecmp_nofct}"

WORKLOAD="${ROOT_DIR}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt"
TOPOLOGY="${ROOT_DIR}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100"
CONFIG="${ROOT_DIR}/myconfig/Meta256MoE.conf"
OUT_DIR="${OUT_ROOT}/htsim_ns3_ecmp_full_${STAMP}"

mkdir -p "${OUT_DIR}"

{
  echo "START $(date -Is)"
  echo "strategy=ns3_ecmp"
  echo "disable_fct=1"
  echo "workload=${WORKLOAD}"
  echo "topology=${TOPOLOGY}"
  echo "config=${CONFIG}"
  status=0
  /usr/bin/time -v env HTSIM_FLOW_RECLAIM_BATCH=262144 HTSIM_DISABLE_FCT_OUTPUT=1 \
    "${ROOT_DIR}/bin/SimAI_htsim" \
    -w "${WORKLOAD}" \
    -n "${TOPOLOGY}" \
    -c "${CONFIG}" \
    -o "${OUT_DIR}/" \
    -r ns3_ecmp || status=$?
  echo "EXIT:${status}"
  echo "END $(date -Is)"
  exit "${status}"
} > "${OUT_DIR}/run.log" 2>&1
