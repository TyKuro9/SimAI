#!/usr/bin/env bash
# 1024 GPU × 175B workload — FlowSim 六种拓扑批量/单拓扑运行
set -euo pipefail

FLOWSIM="/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim"
WL="/home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_175B-world_size1024-tp8-pp8-ep1-gbs1536-mbs1-seq4096-MOE-False-GEMM-False-flash_attn-False.txt"
TOPO="/home/zty/Topo/SimAI_TyKuro9/mytopo/1024"
OUT="/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/1024"
THREADS="${FLOWSIM_THREADS:-8}"
SEND_EMAIL="${HOME}/.cursor/scripts/SendEmail.py"
EMAIL_CONFIG="${HOME}/.cursor/email.env"

NOTIFY_ON_RUN_FINISH="${NOTIFY_ON_RUN_FINISH:-0}"
if [[ "${1:-}" == "--notify" ]]; then
  NOTIFY_ON_RUN_FINISH=1
  shift
fi

SCRIPT_START_EPOCH="$(date +%s)"
SCRIPT_START_HUMAN="$(date '+%Y-%m-%d %H:%M:%S')"
COMPLETED_CASES=()
REQUESTED_FILTER=""

SendRunReport() {
  local exit_code="$1"
  [[ "${NOTIFY_ON_RUN_FINISH}" == "1" ]] || return 0

  if [[ ! -f "${EMAIL_CONFIG}" ]]; then
    echo "Warning: 邮件通知已启用但未找到配置文件: ${EMAIL_CONFIG}" >&2
    return 0
  fi
  if [[ ! -f "${SEND_EMAIL}" ]]; then
    echo "Warning: 邮件通知已启用但未找到 SendEmail.py: ${SEND_EMAIL}" >&2
    return 0
  fi

  local end_human duration status_text subject
  end_human="$(date '+%Y-%m-%d %H:%M:%S')"
  duration="$(( $(date +%s) - SCRIPT_START_EPOCH ))"
  if [[ "${exit_code}" -eq 0 ]]; then
    status_text="成功 — 所有请求的运行已完整完成"
    subject="[FlowSim 1024] 运行成功"
  else
    status_text="失败 — 未完整完成 (exit code ${exit_code})"
    subject="[FlowSim 1024] 运行失败 (code ${exit_code})"
  fi

  local completed_text="${COMPLETED_CASES[*]}"
  [[ -n "${completed_text}" ]] || completed_text="无"

  local body
  body="FlowSim 1024 批量运行报告

状态: ${status_text}
开始时间: ${SCRIPT_START_HUMAN}
结束时间: ${end_human}
耗时: ${duration} 秒
运行参数: ${REQUESTED_FILTER:-all}
已完成拓扑: ${completed_text}
输出目录: ${OUT}

脚本: $(realpath "$0")"

  python3 "${SEND_EMAIL}" \
    --config "${EMAIL_CONFIG}" \
    --subject "${subject}" \
    --body "${body}" \
    || echo "Warning: 运行结束邮件发送失败。" >&2
}

OnExit() {
  SendRunReport "$?"
}

trap OnExit EXIT

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
  COMPLETED_CASES+=("${name}")
}

ALL_CASES=(
  "Meta|Meta_Topo_1024g_8gps_400Gbps_H100|Meta|Update-1024gpu_175B_MetaH100_flowsim.log"
  "HPN|AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100|HPN|Update-1024gpu_175B_HPN1024H100_flowsim.log"
  "DeepSeek|DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100|DeepSeek|Update-1024gpu_175B_DeepSeek1024H100_flowsim.log"
  "RO|RailOnly_1024g_8gps_p32a0.5_400Gbps_H100|RO|Update-1024gpu_175B_RO1024H100_flowsim.log"
  "ROFT|ROFT_1024g_8gps_p32a0.5_400Gbps_H100|ROFT|Update-1024gpu_175B_ROFT1024H100_flowsim.log"
  "Zcube|Zcube_n32_k2_1024g_8gps_200Gbps_H100|Zcube|Update-1024gpu_175B_Zcube1024H100_flowsim.log"
)

FILTER="${1:-all}"
REQUESTED_FILTER="${FILTER}"
for entry in "${ALL_CASES[@]}"; do
  IFS='|' read -r name topo out_sub log_name <<< "${entry}"
  if [[ "${FILTER}" == "all" || "${FILTER}" == "${name}" ]]; then
    RunOne "${name}" "${topo}" "${out_sub}" "${log_name}"
  fi
done

echo "All requested FlowSim runs finished."
