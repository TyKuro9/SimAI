#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

HTSIM_BIN="${HTSIM_BIN:-${ROOT}/bin/SimAI_htsim}"
ROUTE_STRATEGY="${HTSIM_ROUTE_STRATEGY:-spray_plb}"
RUN_STAMP="${HTSIM_RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
OUT_ROOT="${OUT_ROOT:-${ROOT}/experiments/htsim_results/csv/htsim256_spray_plb_dense_moe_${RUN_STAMP}}"
FLOW_RECLAIM_BATCH="${HTSIM_FLOW_RECLAIM_BATCH:-262144}"
TAIL_RTO="${HTSIM_ROCE_TAIL_RTO:-0}"
MIN_RTO_US="${HTSIM_ROCE_MIN_RTO_US:-20000}"
FINAL_DRAIN_RECOVERY="${HTSIM_FINAL_DRAIN_RECOVERY:-1}"
FINAL_DRAIN_RECOVERY_ROUNDS="${HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS:-65536}"
STALL_CHECK_EVENTS="${HTSIM_STALL_CHECK_EVENTS:-1048576}"
STALL_NO_PROGRESS_CHECKS="${HTSIM_STALL_NO_PROGRESS_CHECKS:-8}"
RESUME="${HTSIM_RESUME:-1}"

DENSE_WORKLOAD="${DENSE_WORKLOAD:-${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt}"
MOE_WORKLOAD="${MOE_WORKLOAD:-${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt}"

TOPOLOGIES=(
  "Meta|${ROOT}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100"
  "HPN|${ROOT}/mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100"
  "DeepSeek|${ROOT}/mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800"
  "Zcube|${ROOT}/mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100"
  "RO|${ROOT}/mytopo/RailOnly_256g_8gps_p16a0.5_400Gbps_H100"
  "ROFT|${ROOT}/mytopo/ROFT_256g_8gps_p16a0.5_400Gbps_H100"
)

usage() {
  cat <<'USAGE'
Usage: run_256_spray_plb_dense_moe.sh [all|dense|moe ...]

Runs the six 256-GPU topologies sequentially with spray_plb. FCT output is
always enabled. Reusing OUT_ROOT resumes the batch and skips completed cases.

Environment:
  HTSIM_BIN                Override the HTSim binary.
  HTSIM_RUN_STAMP          Output stamp used by the default OUT_ROOT.
  OUT_ROOT                 Override the output root.
  HTSIM_FLOW_RECLAIM_BATCH Flow reclamation batch, default 262144.
  HTSIM_ROCE_TAIL_RTO      Normal-stage tail RTO, default 0.
  HTSIM_ROCE_MIN_RTO_US    Minimum retransmission timeout, default 20000 us.
  HTSIM_FINAL_DRAIN_RECOVERY        Final-drain recovery, default 1.
  HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS Consecutive rounds without a completed flow,
                                    default 65536.
  HTSIM_STALL_CHECK_EVENTS  Events between ACK-progress samples, default 1048576.
  HTSIM_STALL_NO_PROGRESS_CHECKS  Samples before handoff, default 8.
  HTSIM_RESUME             Skip completed cases when 1, default 1.
  DENSE_WORKLOAD           Override the 256-GPU GPT-22B workload.
  MOE_WORKLOAD             Override the 256-GPU Mixtral workload.
USAGE
}

die() {
  echo "error: $*" >&2
  exit 1
}

require_file() {
  local path="$1"
  local label="$2"
  [[ -f "${path}" ]] || die "missing ${label}: ${path}"
}

selected_modes=()
if [[ "$#" -eq 0 ]]; then
  selected_modes=(Dense MoE)
else
  for arg in "$@"; do
    case "${arg,,}" in
      all|both)
        selected_modes=(Dense MoE)
        ;;
      dense)
        selected_modes+=(Dense)
        ;;
      moe)
        selected_modes+=(MoE)
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage >&2
        exit 2
        ;;
    esac
  done
fi

[[ "${ROUTE_STRATEGY}" == "spray_plb" ]] || die "this batch requires spray_plb, got ${ROUTE_STRATEGY}"
[[ -x "${HTSIM_BIN}" ]] || die "missing executable: ${HTSIM_BIN}"
require_file "${DENSE_WORKLOAD}" "Dense workload"
require_file "${MOE_WORKLOAD}" "MoE workload"

mkdir -p "${OUT_ROOT}"
SUMMARY="${OUT_ROOT}/summary.csv"
if [[ ! -f "${SUMMARY}" ]]; then
  echo "model,topology,strategy,status,exit_code,start_epoch,end_epoch,endtoend_lines,fct_lines,finish_time,output_dir,log_file" > "${SUMMARY}"
fi

run_case() {
  local model="$1"
  local name="$2"
  local topology="$3"
  local workload=""
  local config=""

  case "${model}" in
    Dense)
      workload="${DENSE_WORKLOAD}"
      config="${ROOT}/myconfig/${name}256.conf"
      ;;
    MoE)
      workload="${MOE_WORKLOAD}"
      config="${ROOT}/myconfig/${name}256MoE.conf"
      ;;
    *)
      die "unsupported model: ${model}"
      ;;
  esac

  require_file "${topology}" "${name} topology"
  require_file "${config}" "${model}/${name} config"

  local case_name="${model}_${name}"
  local out_dir="${OUT_ROOT}/${case_name}"
  local log_file="${OUT_ROOT}/${case_name}.log"
  local status_file="${out_dir}/status.txt"

  if [[ "${RESUME}" == "1" && -f "${status_file}" ]] &&
      grep -qx "status=complete" "${status_file}" &&
      [[ -s "${out_dir}/EndToEnd.csv" && -s "${out_dir}/fct.txt" ]]; then
    echo "skip completed ${case_name}: ${out_dir}"
    return
  fi

  mkdir -p "${out_dir}"
  {
    echo "case=${case_name}"
    echo "model=${model}"
    echo "topology_name=${name}"
    echo "strategy=${ROUTE_STRATEGY}"
    echo "workload=${workload}"
    echo "topology=${topology}"
    echo "config=${config}"
    echo "out_dir=${out_dir}"
    echo "fct_output=enabled"
    echo "flow_reclaim_batch=${FLOW_RECLAIM_BATCH}"
    echo "tail_rto=${TAIL_RTO}"
    echo "min_rto_us=${MIN_RTO_US}"
    echo "final_drain_recovery=${FINAL_DRAIN_RECOVERY}"
    echo "final_drain_recovery_rounds=${FINAL_DRAIN_RECOVERY_ROUNDS}"
    echo "stall_check_events=${STALL_CHECK_EVENTS}"
    echo "stall_no_progress_checks=${STALL_NO_PROGRESS_CHECKS}"
  } > "${out_dir}/metadata.txt"

  local start_epoch
  start_epoch="$(date +%s)"
  printf 'status=running\nstart_epoch=%s\n' "${start_epoch}" > "${status_file}"
  echo "========== HTSim 256 ${case_name} ${ROUTE_STRATEGY} =========="
  echo "start_epoch=${start_epoch} out=${out_dir} log=${log_file}"

  local exit_code=0
  set +e
  /usr/bin/time -v env \
    HTSIM_DISABLE_FCT_OUTPUT=0 \
    HTSIM_FLOW_RECLAIM_BATCH="${FLOW_RECLAIM_BATCH}" \
    HTSIM_ROCE_TAIL_RTO="${TAIL_RTO}" \
    HTSIM_ROCE_MIN_RTO_US="${MIN_RTO_US}" \
    HTSIM_FINAL_DRAIN_RECOVERY="${FINAL_DRAIN_RECOVERY}" \
    HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS="${FINAL_DRAIN_RECOVERY_ROUNDS}" \
    HTSIM_STALL_CHECK_EVENTS="${STALL_CHECK_EVENTS}" \
    HTSIM_STALL_NO_PROGRESS_CHECKS="${STALL_NO_PROGRESS_CHECKS}" \
    "${HTSIM_BIN}" \
      -w "${workload}" \
      -n "${topology}" \
      -c "${config}" \
      -o "${out_dir}" \
      -r "${ROUTE_STRATEGY}" \
      > "${log_file}" 2>&1
  exit_code="$?"
  set -e

  local end_epoch
  local e2e_lines=0
  local fct_lines=0
  local finish_time=""
  local status="failed"
  end_epoch="$(date +%s)"
  [[ -f "${out_dir}/EndToEnd.csv" ]] && e2e_lines="$(wc -l < "${out_dir}/EndToEnd.csv")"
  [[ -f "${out_dir}/fct.txt" ]] && fct_lines="$(wc -l < "${out_dir}/fct.txt")"
  if [[ "${exit_code}" -eq 0 ]] &&
      grep -q "all passes finished" "${log_file}" &&
      [[ "${e2e_lines}" -gt 1 && "${fct_lines}" -gt 1 ]]; then
    status="complete"
    finish_time="$(grep "all passes finished at time" "${log_file}" | tail -1 | sed -E 's/.*time: ([0-9]+).*/\1/')"
  fi

  {
    echo "status=${status}"
    echo "exit_code=${exit_code}"
    echo "start_epoch=${start_epoch}"
    echo "end_epoch=${end_epoch}"
    echo "endtoend_lines=${e2e_lines}"
    echo "fct_lines=${fct_lines}"
    echo "finish_time=${finish_time}"
  } > "${status_file}"
  echo "${model},${name},${ROUTE_STRATEGY},${status},${exit_code},${start_epoch},${end_epoch},${e2e_lines},${fct_lines},${finish_time},${out_dir},${log_file}" >> "${SUMMARY}"
  echo "done ${case_name}: status=${status} exit=${exit_code} e2e=${e2e_lines} fct=${fct_lines} finish_time=${finish_time}"

  if [[ "${status}" != "complete" ]]; then
    echo "stopping after incomplete case ${case_name}; inspect ${log_file}" >&2
    exit 1
  fi
}

for model in "${selected_modes[@]}"; do
  for entry in "${TOPOLOGIES[@]}"; do
    IFS='|' read -r name topology <<< "${entry}"
    run_case "${model}" "${name}" "${topology}"
  done
done

echo "all selected HTSim 256 spray_plb runs completed"
echo "summary: ${SUMMARY}"
