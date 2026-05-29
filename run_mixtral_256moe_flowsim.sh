#!/usr/bin/env bash
# Mixtral 8x7B MoE @ 256 GPU — FlowSim 全拓扑批量/单拓扑运行
#
# 用法:
#   cd /home/zty/Topo/SimAI_TyKuro9
#   bash run_mixtral_256moe_flowsim.sh              # 跑全部拓扑
#   bash run_mixtral_256moe_flowsim.sh Meta HPN     # 只跑指定拓扑
#
# 环境变量:
#   FLOWSIM_THREADS  线程数，默认 16
#   FLOWSIM_BIN      FlowSim 可执行文件路径
#
# 可选拓扑: Meta HPN DeepSeek Zcube RO ROFT
# 别名示例: Meta256 HPN256 RO256 ROFT256

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "${ROOT}"

FLOWSIM="${FLOWSIM_BIN:-/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim}"
WL="${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt"
TOPO_DIR="${ROOT}/mytopo"
OUT="${ROOT}/experiments/flowsim_results/256"
THREADS="${FLOWSIM_THREADS:-16}"

# name|topo_file|out_subdir|log_file
ALL_CASES=(
  "Meta|Meta_Topo_256g_8gps_400Gbps_A100|MetaMoE|Update-256gpu_Mixtral8x7B-MoE_Meta256A100_flowsim.log"
  "HPN|AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100|HPNMoE|Update-256gpu_Mixtral8x7B-MoE_HPN256H100_flowsim.log"
  "DeepSeek|DeepSeek_256g_8gps_p16a0.5_400Gbps_H800|DeepSeekMoE|Update-256gpu_Mixtral8x7B-MoE_DeepSeek256H800_flowsim.log"
  "Zcube|Zcube_n16_k2_256g_8gps_200Gbps_H100|ZcubeMoE|Update-256gpu_Mixtral8x7B-MoE_Zcube256H100_flowsim.log"
  "RO|RailOnly_256g_8gps_p64a0.5_400Gbps_H100|ROMoE|Update-256gpu_Mixtral8x7B-MoE_RO256H100_flowsim.log"
  "ROFT|ROFT_256g_8gps_p64a0.5_400Gbps_H100|ROFTMoE|Update-256gpu_Mixtral8x7B-MoE_ROFT256H100_flowsim.log"
)

ALL_TOPOS=(Meta HPN DeepSeek Zcube RO ROFT)

ResolveAlias() {
  case "$1" in
    Meta|Meta256|MetaMoE) echo "Meta" ;;
    HPN|HPN256|HPNMoE) echo "HPN" ;;
    DeepSeek|DeepSeek256|DeepSeekMoE) echo "DeepSeek" ;;
    Zcube|Zcube256|ZcubeMoE) echo "Zcube" ;;
    RO|RO256|ROMoE|RailOnly) echo "RO" ;;
    ROFT|ROFT256|ROFTMoE) echo "ROFT" ;;
    *)
      echo ""
      ;;
  esac
}

LookupCase() {
  local want="$1"
  for entry in "${ALL_CASES[@]}"; do
    IFS='|' read -r name topo_file out_sub log_name <<< "${entry}"
    if [[ "${name}" == "${want}" ]]; then
      echo "${entry}"
      return 0
    fi
  done
  return 1
}

RunOne() {
  local name="$1"
  local topo_file="$2"
  local out_sub="$3"
  local log_name="$4"
  local topo_path="${TOPO_DIR}/${topo_file}"

  if [[ ! -f "${topo_path}" ]]; then
    echo "Error: topology missing: ${topo_path}" >&2
    exit 1
  fi

  mkdir -p "${OUT}/${out_sub}"

  echo "========== FlowSim ${name}MoE 256 =========="
  "${FLOWSIM}" -t "${THREADS}" -w "${WL}" -n "${topo_path}" -o "${OUT}/${out_sub}/" \
    2>&1 | tee "${OUT}/${log_name}"
  echo "Done: ${OUT}/${out_sub}/fct.txt"
  echo "========== FlowSim ${name}MoE 256 finished =========="
}

if [[ ! -x "${FLOWSIM}" ]]; then
  echo "Error: FlowSim binary not found: ${FLOWSIM}" >&2
  echo "Build with: cd /home/zty/Topo/m4/SimAI && ./scripts/build.sh -c flowsim" >&2
  exit 1
fi

if [[ ! -f "${WL}" ]]; then
  echo "Error: workload not found: ${WL}" >&2
  exit 1
fi

bash "${ROOT}/experiments/flowsim_256/mkdir_outputs.sh"
cd /home/zty/Topo/m4/SimAI

if [[ $# -eq 0 ]]; then
  TARGETS=("${ALL_TOPOS[@]}")
else
  TARGETS=()
  for arg in "$@"; do
    resolved="$(ResolveAlias "${arg}")"
    if [[ -z "${resolved}" ]]; then
      echo "未知拓扑: ${arg}" >&2
      echo "可选: ${ALL_TOPOS[*]}" >&2
      exit 1
    fi
    TARGETS+=("${resolved}")
  done
fi

for t in "${TARGETS[@]}"; do
  entry="$(LookupCase "${t}")" || {
    echo "内部错误: 未找到拓扑配置 ${t}" >&2
    exit 1
  }
  IFS='|' read -r name topo_file out_sub log_name <<< "${entry}"
  RunOne "${name}" "${topo_file}" "${out_sub}" "${log_name}"
done

echo "全部选定拓扑 FlowSim 已完成。"
