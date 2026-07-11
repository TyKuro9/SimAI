#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

HTSIM_BIN="${HTSIM_BIN:-${ROOT}/bin/SimAI_htsim}"
ROUTE_STRATEGY="${HTSIM_ROUTE_STRATEGY:-spray_plb}"
RUN_STAMP="${HTSIM_RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
OUT_ROOT="${OUT_ROOT:-${ROOT}/experiments/htsim_results/csv/htsim_dense_scale_table_${ROUTE_STRATEGY}_${RUN_STAMP}}"
FLOW_RECLAIM_BATCH="${HTSIM_FLOW_RECLAIM_BATCH:-262144}"
TAIL_RTO="${HTSIM_ROCE_TAIL_RTO:-0}"
MIN_RTO_US="${HTSIM_ROCE_MIN_RTO_US:-20000}"
FINAL_DRAIN_RECOVERY="${HTSIM_FINAL_DRAIN_RECOVERY:-1}"
FINAL_DRAIN_RECOVERY_ROUNDS="${HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS:-65536}"
STALL_CHECK_EVENTS="${HTSIM_STALL_CHECK_EVENTS:-1048576}"
STALL_NO_PROGRESS_CHECKS="${HTSIM_STALL_NO_PROGRESS_CHECKS:-8}"
COMPRESS_FCT="${HTSIM_COMPRESS_FCT:-1}"
RESUME="${HTSIM_RESUME:-1}"
TOPOLOGY_FILTER="${HTSIM_TOPOLOGIES:-}"
CONTINUE_ON_ERROR="${HTSIM_CONTINUE_ON_ERROR:-0}"

WORKLOAD_256="${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-dp4-pp8-gbs384-mbs1-seq2048-interleaved3.txt"
WORKLOAD_1024="${ROOT}/my_workloads/H100-gpt_175B-world_size1024-tp8-dp16-pp8-gbs1536-mbs1-seq4096-interleaved3.txt"

TOPOLOGIES_256=(
  "Meta|${ROOT}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100|${ROOT}/myconfig/Meta256.conf"
  "HPN|${ROOT}/mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100|${ROOT}/myconfig/HPN256.conf"
  "DeepSeek|${ROOT}/mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800|${ROOT}/myconfig/DeepSeek256.conf"
  "Zcube|${ROOT}/mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100|${ROOT}/myconfig/Zcube256.conf"
  "RO|${ROOT}/mytopo/RailOnly_256g_8gps_p16a0.5_400Gbps_H100|${ROOT}/myconfig/RO256.conf"
  "ROFT|${ROOT}/mytopo/ROFT_256g_8gps_p16a0.5_400Gbps_H100|${ROOT}/myconfig/ROFT256.conf"
)

TOPOLOGIES_1024=(
  "Meta|${ROOT}/mytopo/1024/Meta_Topo_1024g_8gps_400Gbps_H100|${ROOT}/myconfig/1024/Meta.conf"
  "HPN|${ROOT}/mytopo/1024/AlibabaHPN_1024g_8gps_DualToR_DualPlane_200Gbps_H100|${ROOT}/myconfig/1024/HPN.conf"
  "DeepSeek|${ROOT}/mytopo/1024/DeepSeek_1024g_8gps_p32a0.5_400Gbps_H100|${ROOT}/myconfig/1024/DeepSeek.conf"
  "Zcube|${ROOT}/mytopo/1024/Zcube_n32_k2_1024g_8gps_200Gbps_H100|${ROOT}/myconfig/1024/Zcube.conf"
  "RO|${ROOT}/mytopo/1024/RailOnly_1024g_8gps_p32a0.5_400Gbps_H100|${ROOT}/myconfig/1024/RO.conf"
  "ROFT|${ROOT}/mytopo/1024/ROFT_1024g_8gps_p32a0.5_400Gbps_H100|${ROOT}/myconfig/1024/ROFT.conf"
)

usage() {
  cat <<'USAGE'
Usage: run_dense_scale_table_spray_plb.sh [all|256|1024 ...]

Runs the six topologies at each selected scale sequentially. The route strategy
defaults to spray_plb and can be changed with HTSIM_ROUTE_STRATEGY.
FCT output is always enabled. Reusing OUT_ROOT skips completed cases.

Environment:
  HTSIM_ROUTE_STRATEGY  HTSim route strategy, default spray_plb.
  HTSIM_TOPOLOGIES      Optional comma-separated topology names to run.
  HTSIM_CONTINUE_ON_ERROR  Continue with later cases after a failure, default 0.
  HTSIM_COMPRESS_FCT  Compress completed fct.txt with gzip, default 1.
  HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS  Consecutive ACK-gated rounds without a
                                    completed flow, default 65536.
  HTSIM_STALL_CHECK_EVENTS  Events between ACK-progress samples, default 1048576.
  HTSIM_STALL_NO_PROGRESS_CHECKS  Samples before handoff, default 8.
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

selected_scales=()
if [[ "$#" -eq 0 ]]; then
  selected_scales=(256 1024)
else
  for arg in "$@"; do
    case "${arg}" in
      all|both)
        selected_scales=(256 1024)
        ;;
      256|1024)
        selected_scales+=("${arg}")
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

case "${ROUTE_STRATEGY}" in
  single|ecmp|ns3_ecmp|spray_rr|spray_incremental|spray_oblivious|spray_plb|plb|spray_reps|reps)
    ;;
  *)
    die "unsupported route strategy: ${ROUTE_STRATEGY}"
    ;;
esac
[[ -x "${HTSIM_BIN}" ]] || die "missing executable: ${HTSIM_BIN}"
require_file "${WORKLOAD_256}" "256 Dense workload"
require_file "${WORKLOAD_1024}" "1024 Dense workload"

mkdir -p "${OUT_ROOT}"
SUMMARY="${OUT_ROOT}/summary.csv"
if [[ ! -f "${SUMMARY}" ]]; then
  echo "scale,model,topology,strategy,status,exit_code,start_epoch,end_epoch,endtoend_lines,fct_lines,finish_time,output_dir,log_file" > "${SUMMARY}"
fi
failed_cases=0

run_case() {
  local scale="$1"
  local model="$2"
  local topology_name="$3"
  local topology="$4"
  local config="$5"
  local workload="$6"
  local case_name="Dense${scale}_${topology_name}"
  local out_dir="${OUT_ROOT}/${case_name}"
  local log_file="${OUT_ROOT}/${case_name}.log"
  local status_file="${out_dir}/status.txt"

  require_file "${topology}" "${scale}/${topology_name} topology"
  require_file "${config}" "${scale}/${topology_name} config"

  if [[ "${RESUME}" == "1" && -f "${status_file}" ]] &&
      grep -qx "status=complete" "${status_file}" &&
      [[ -s "${out_dir}/EndToEnd.csv" ]] &&
      [[ -s "${out_dir}/fct.txt" || -s "${out_dir}/fct.txt.gz" ]]; then
    echo "skip completed ${case_name}: ${out_dir}"
    return
  fi

  mkdir -p "${out_dir}"
  {
    echo "case=${case_name}"
    echo "scale=${scale}"
    echo "model=${model}"
    echo "topology_name=${topology_name}"
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
    echo "compress_fct=${COMPRESS_FCT}"
  } > "${out_dir}/metadata.txt"

  local start_epoch
  start_epoch="$(date +%s)"
  printf 'status=running\nstart_epoch=%s\n' "${start_epoch}" > "${status_file}"
  echo "========== HTSim ${case_name} ${ROUTE_STRATEGY} =========="
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

  if [[ "${status}" == "complete" && "${COMPRESS_FCT}" == "1" ]]; then
    gzip -f "${out_dir}/fct.txt"
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
  echo "${scale},${model},${topology_name},${ROUTE_STRATEGY},${status},${exit_code},${start_epoch},${end_epoch},${e2e_lines},${fct_lines},${finish_time},${out_dir},${log_file}" >> "${SUMMARY}"
  echo "done ${case_name}: status=${status} exit=${exit_code} e2e=${e2e_lines} fct=${fct_lines} finish_time=${finish_time}"

  if [[ "${status}" != "complete" ]]; then
    failed_cases=$((failed_cases + 1))
    if [[ "${CONTINUE_ON_ERROR}" != "1" ]]; then
      die "incomplete case ${case_name}; inspect ${log_file}"
    fi
  fi
}

topology_selected() {
  local topology_name="$1"
  local selected=""
  local selected_topologies=()
  if [[ -z "${TOPOLOGY_FILTER}" ]]; then
    return 0
  fi
  IFS=',' read -ra selected_topologies <<< "${TOPOLOGY_FILTER}"
  for selected in "${selected_topologies[@]}"; do
    if [[ "${selected}" == "${topology_name}" ]]; then
      return 0
    fi
  done
  return 1
}

for scale in "${selected_scales[@]}"; do
  model=""
  workload=""
  topologies=()
  case "${scale}" in
    256)
      model="GPT-22B"
      workload="${WORKLOAD_256}"
      topologies=("${TOPOLOGIES_256[@]}")
      ;;
    1024)
      model="GPT-175B"
      workload="${WORKLOAD_1024}"
      topologies=("${TOPOLOGIES_1024[@]}")
      ;;
  esac

  for entry in "${topologies[@]}"; do
    IFS='|' read -r topology_name topology config <<< "${entry}"
    if ! topology_selected "${topology_name}"; then
      echo "skip filtered ${scale}/${topology_name}"
      continue
    fi
    run_case "${scale}" "${model}" "${topology_name}" "${topology}" "${config}" "${workload}"
  done
done

echo "all selected Dense scale-table HTSim runs completed"
echo "summary: ${SUMMARY}"
if [[ "${failed_cases}" -gt 0 ]]; then
  echo "failed cases: ${failed_cases}" >&2
  exit 1
fi
