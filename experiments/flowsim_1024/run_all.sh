#!/usr/bin/env bash
# 1024 GPU × 175B workload — FlowSim 六种拓扑批量/单拓扑运行
set -euo pipefail

FLOWSIM="/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim"
WL="/home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_175B-world_size1024-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt"
TOPO="/home/zty/Topo/SimAI_TyKuro9/mytopo/1024"
OUT="/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/1024"
THREADS="${FLOWSIM_THREADS:-32}"

if [[ ! -x "${FLOWSIM}" ]]; then
  echo "Error: FlowSim binary not found. Build with:" >&2
  echo "  cd /home/zty/Topo/m4/SimAI && ./scripts/build.sh -c flowsim" >&2
  exit 1
fi

if [[ ! -f "${WL}" ]]; then
  echo "Error: workload not found: ${WL}" >&2
  exit 1
fi

"$(dirname "$0")/mkdir_outputs.sh"
cd /home/zty/Topo/m4/SimAI

RunOne() {
  local name="$1"
  local topo_file="$2"
  local out_sub="$3"
  local log_name="$4"

  if [[ ! -f "${TOPO}/${topo_file}" ]]; then
    echo "Error: topology missing: ${TOPO}/${topo_file}" >&2
    exit 1
  fi

  echo "========== FlowSim ${name} =========="
  "${FLOWSIM}" -t "${THREADS}" -w "${WL}" -n "${TOPO}/${topo_file}" -o "${OUT}/${out_sub}/" \
    2>&1 | tee "${OUT}/${log_name}"
  echo "Done: ${OUT}/${out_sub}/fct.txt"
}

ALL_CASES=(
  "Meta|Meta_Topo_1024g_8gps_400Gbps_H100|Meta|Update-1024gpu_175B_MetaH100_flowsim.log"
  "HPN|AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100|HPN|Update-1024gpu_175B_HPN1024H100_flowsim.log"
  "DeepSeek|DeepSeek_1024g_8gps_p16a0.5_400Gbps_H100|DeepSeek|Update-1024gpu_175B_DeepSeek1024H100_flowsim.log"
  "RO|RailOnly_1024g_8gps_p64a0.5_400Gbps_H100|RO|Update-1024gpu_175B_RO1024H100_flowsim.log"
  "ROFT|ROFT_1024g_8gps_p64a0.5_400Gbps_H100|ROFT|Update-1024gpu_175B_ROFT1024H100_flowsim.log"
  "Zcube|Zcube_n32_k2_1024g_8gps_200Gbps_H100|Zcube|Update-1024gpu_175B_Zcube1024H100_flowsim.log"
)

FILTER="${1:-all}"
for entry in "${ALL_CASES[@]}"; do
  IFS='|' read -r name topo out_sub log_name <<< "${entry}"
  if [[ "${FILTER}" == "all" || "${FILTER}" == "${name}" ]]; then
    RunOne "${name}" "${topo}" "${out_sub}" "${log_name}"
  fi
done

echo "All requested FlowSim runs finished."
