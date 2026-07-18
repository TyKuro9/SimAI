#!/usr/bin/env bash

set -uo pipefail

base=/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2
binary=/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim
workload=${base}/my_workloads/H100-gpt_22B-world_size1024-tp8-pp4-ep1-gbs192-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-True.txt
topology_dir=${base}/mytopo/1024_12p8T
output=${FLOWSIM_OUTPUT:-${base}/experiments/flowsim_spray/adaptive_dense_1024_ga6_gapfix_20260718}
threads=${FLOWSIM_THREADS:-4}
max_parallel=${FLOWSIM_MAX_PARALLEL:-1}

declare -A topologies=(
  [Meta]=Meta_Topo_1024g_8gps_400Gbps_H100_12p8T
  [HPN]=AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100
  [DeepSeek]=DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100
  [Zcube]=Zcube_n32_k2_1024g_8gps_200Gbps_H100
  [RO]=RailOnly_1024g_8gps_s5_400Gbps_H100_12p8T
  [ROFT]=ROFT_1024g_8gps_p32a0.5_400Gbps_H100_12p8T
)

all_names=(ROFT Zcube DeepSeek Meta HPN RO)

run_one() {
  local name=$1
  local topology=${topologies[$name]}
  local result_dir=${output}/${name}
  local rc

  mkdir -p "${result_dir}"
  if [[ -f "${result_dir}/COMPLETE" ]]; then
    printf '[SKIP] %s is already complete\n' "${name}"
    return 0
  fi

  date --iso-8601=seconds > "${result_dir}/started_at.txt"
  printf '[START] %s\n' "${name}"
  env \
    FLOWSIM_ROUTING_POLICY=spray_adaptive \
    FLOWSIM_SPRAY_WIDTH=4 \
    FLOWSIM_ADAPTIVE_PATH_COUNT=64 \
    FLOWSIM_ADAPTIVE_MAX_EXTRA_HOPS=2 \
    FLOWSIM_ADAPTIVE_TRANSPORT_MODEL=ns3_cc \
    FLOWSIM_ADAPTIVE_SINGLE_HOMED_REFERENCE_FANOUT=8 \
    FLOWSIM_ADAPTIVE_SINGLE_HOMED_FANOUT_EXPONENT=0.8 \
    FLOWSIM_ADAPTIVE_DUAL_PLANE_REFERENCE_FANOUT=16 \
    FLOWSIM_ADAPTIVE_DUAL_PLANE_FANOUT_EXPONENT=1.5 \
    FLOWSIM_PACKET_PAYLOAD_BYTES=9000 \
    FLOWSIM_PACKET_HEADER_BYTES=48 \
    AS_SEND_LAT=3 \
    AS_NVLS_ENABLE=0 \
    AS_PXN_ENABLE=0 \
    AS_PXN_POLICY=off \
    FLOWSIM_WRITE_FCT=0 \
    /usr/bin/time \
      -f $'wall_seconds=%e\nmax_rss_kb=%M' \
      -o "${result_dir}/timing.txt" \
      "${binary}" \
      -t "${threads}" \
      -w "${workload}" \
      -n "${topology_dir}/${topology}" \
      -o "${result_dir}" \
      > "${result_dir}/run.log" 2>&1
  rc=$?

  printf '%s\n' "${rc}" > "${result_dir}/exit_code.txt"
  date --iso-8601=seconds > "${result_dir}/finished_at.txt"
  if [[ ${rc} -eq 0 ]] && grep -q 'all passes finished at time:' "${result_dir}/run.log"; then
    touch "${result_dir}/COMPLETE"
    printf '[DONE] %s\n' "${name}"
    return 0
  fi

  printf '[FAIL] %s exit=%s\n' "${name}" "${rc}" >&2
  return 1
}

if [[ ! -x "${binary}" ]]; then
  printf 'FlowSim binary is missing: %s\n' "${binary}" >&2
  exit 1
fi
if [[ ! -f "${workload}" ]]; then
  printf 'Workload is missing: %s\n' "${workload}" >&2
  exit 1
fi
if ! [[ "${max_parallel}" =~ ^[1-6]$ ]]; then
  printf 'FLOWSIM_MAX_PARALLEL must be in [1,6], got %s\n' "${max_parallel}" >&2
  exit 1
fi

filter=${1:-all}
if [[ "${filter}" == all ]]; then
  selected=("${all_names[@]}")
elif [[ -n "${topologies[$filter]+x}" ]]; then
  selected=("${filter}")
else
  printf 'Unknown topology %s. Choose: all %s\n' "${filter}" "${all_names[*]}" >&2
  exit 1
fi

mkdir -p "${output}"
date --iso-8601=seconds > "${output}/last_started_at.txt"

running=0
for name in "${selected[@]}"; do
  run_one "${name}" &
  ((running += 1))
  if ((running == max_parallel)); then
    wait
    running=0
  fi
done
wait

failed=0
for name in "${selected[@]}"; do
  if [[ ! -f "${output}/${name}/COMPLETE" ]]; then
    failed=1
  fi
done
date --iso-8601=seconds > "${output}/last_finished_at.txt"
exit "${failed}"
