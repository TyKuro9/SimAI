#!/usr/bin/env bash
# Mixtral 8x7B MoE @ 256 GPU — NS3 全拓扑批量运行
# 用法: cd /home/zty/Topo/SimAI_TyKuro9 && bash run_mixtral_256moe_ns3.sh [topo名...]
#   无参数则跑全部；例如: bash run_mixtral_256moe_ns3.sh HPN Meta DeepSeek

set -euo pipefail
cd "$(dirname "$0")"

NS3_CSV_BASE="./experiments/ns3_results/csv"
LOG_DIR="./experiments/ns3_results"
mkdir -p "${NS3_CSV_BASE}" "${LOG_DIR}" /home/zty/Topo/SimAI/simulation_output/meta256

# workload 文件名含 * 与空格，必须单引号
WL='./my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt'

SIM="./bin/SimAI_simulator"
FAST_SIM="astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-AstraSimFastNetwork-debug"

run_one() {
  local name="$1"
  shift
  echo "========== ${name} =========="
  "$@"
  echo "========== ${name} done =========="
}

run_HPN() {
  run_one "HPN256" sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
    "${SIM}" -t 32 -w "${WL}" \
    -n ./mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100 \
    -c ./myconfig/HPN256MoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-HPN256H100/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_HPN256H100_ns3.log"
}

run_Meta() {
  run_one "Meta256" sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
    "${SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
    -c ./myconfig/Meta256MoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-Meta256A100/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_Meta256A100_copy_ns3.log"
}

run_MetaFast() {
  run_one "Meta-fast256" sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
    "${FAST_SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
    -c ./myconfig/Meta-fast256MoE.conf \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_Meta-fast256A100_copy_ns3.log"
}

run_DeepSeek() {
  run_one "DeepSeek256" sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
    "${SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800 \
    -c ./myconfig/DeepSeek256MoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-DeepSeek256H800/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_DeepSeek256H800_copy_ns3.log"
}

run_Zcube() {
  run_one "Zcube256" sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
    "${SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100 \
    -c ./myconfig/Zcube256MoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-Zcube256H100/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_Zcube256H100_copy_ns3.log"
}

# MoE 建议关闭 PXN（与 simulaiton_order.sh 注释一致；RO256 段原脚本为 PXN=1，易崩可改 0）
run_RO256() {
  run_one "RO256" sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=0 \
    "${SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
    -c ./myconfig/RO256MoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-RO256H100/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_RO256H100_copy_ns3.log"
}

run_ROFT256() {
  run_one "ROFT256" /usr/bin/time -f 'wall=%e sec  user=%U sec  sys=%S sec' \
    -o "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_ROFT256H100_copy_ns3.time" \
    sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=0 \
    "${SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
    -c ./myconfig/ROFT256MoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-ROFT256H100/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_ROFT256H100_copy_ns3.log"
}

run_ROFT256_woPXN() {
  run_one "ROFT256_woPXN" /usr/bin/time -f 'wall=%e sec  user=%U sec  sys=%S sec' \
    -o "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_ROFT256woPXNH100_copy_ns3.time" \
    sudo env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 AS_PXN_ENABLE=0 \
    "${SIM}" -t 16 -w "${WL}" \
    -n ./mytopo/ROFT_256g_8gps_p64a0.5_400Gbps_H100 \
    -c ./myconfig/ROFT256_woPXNMoE.conf \
    -o "${NS3_CSV_BASE}/Mixtral-ROFT256woPXNH100/" \
    2>&1 | tee "${LOG_DIR}/Update-256gpu_Mixtral8x7B-MoE_ROFT256woPXNH100_copy_ns3.log"
}

ALL_TOPOS=(HPN Meta MetaFast DeepSeek Zcube RO256 ROFT256 ROFT256_woPXN)

if [[ $# -eq 0 ]]; then
  TARGETS=("${ALL_TOPOS[@]}")
else
  TARGETS=("$@")
fi

for t in "${TARGETS[@]}"; do
  case "${t}" in
    HPN|HPN256) run_HPN ;;
    Meta|Meta256) run_Meta ;;
    MetaFast|Meta-fast|Meta-fast256) run_MetaFast ;;
    DeepSeek|DeepSeek256) run_DeepSeek ;;
    Zcube|Zcube256) run_Zcube ;;
    RO256) run_RO256 ;;
    ROFT256) run_ROFT256 ;;
    ROFT256_woPXN|woPXN) run_ROFT256_woPXN ;;
    *)
      echo "未知拓扑: ${t}" >&2
      echo "可选: ${ALL_TOPOS[*]}" >&2
      exit 1
      ;;
  esac
done

echo "全部选定拓扑已完成。"
