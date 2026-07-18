#!/usr/bin/env bash

set -u

base=/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2
binary=/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim
workload=${base}/my_workloads/H100-gpt_22B-world_size256-tp8-pp4-ep1-gbs96-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-True.txt
output=${base}/experiments/flowsim_spray/adaptive_dense_ga12_ppfix_retry_20260717

run_one() {
  local name=$1
  local topology=$2
  local result_dir=${output}/${name}

  mkdir -p "${result_dir}"
  env \
    FLOWSIM_ROUTING_POLICY=spray_adaptive \
    FLOWSIM_SPRAY_WIDTH=4 \
    FLOWSIM_ADAPTIVE_PATH_COUNT=16 \
    FLOWSIM_ADAPTIVE_MAX_EXTRA_HOPS=2 \
    AS_SEND_LAT=3 \
    AS_NVLS_ENABLE=0 \
    AS_PXN_ENABLE=0 \
    AS_PXN_POLICY=off \
    FLOWSIM_WRITE_FCT=0 \
    /usr/bin/time \
      -f $'wall_seconds=%e\nmax_rss_kb=%M' \
      -o "${result_dir}/timing.txt" \
      "${binary}" \
      -t 4 \
      -w "${workload}" \
      -n "${base}/mytopo/${topology}" \
      -o "${result_dir}" \
      > "${result_dir}/run.log" 2>&1
  printf '%s\n' "$?" > "${result_dir}/exit_code.txt"
}

mkdir -p "${output}"
date --iso-8601=seconds > "${output}/started_at.txt"

run_one Meta Meta_Topo_256g_8gps_400Gbps_A100 &
run_one HPN AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100 &
run_one DeepSeek DeepSeek_256g_8gps_p16a0.5_400Gbps_H800 &
run_one Zcube Zcube_n16_k2_256g_8gps_200Gbps_H100 &
run_one RO RailOnly_256g_8gps_p16a0.5_400Gbps_H100 &
run_one ROFT ROFT_256g_8gps_p16a0.5_400Gbps_H100 &

wait
date --iso-8601=seconds > "${output}/finished_at.txt"
touch "${output}/COMPLETE"
