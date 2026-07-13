#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

HTSIM_BIN="${HTSIM_BIN:-${ROOT}/bin/SimAI_htsim}"
ROUTE_STRATEGY="${ROUTE_STRATEGY:-${HTSIM_ROUTE_STRATEGY:-spray_plb}}"
RUN_STAMP="${HTSIM_RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
OUT_ROOT="${OUT_ROOT:-${ROOT}/experiments/htsim_results/csv/zcube_moe_htsim_${RUN_STAMP}}"
DISABLE_FCT="${HTSIM_DISABLE_FCT_OUTPUT:-1}"
FLOW_RECLAIM_BATCH="${HTSIM_FLOW_RECLAIM_BATCH:-262144}"

WORKLOAD_256="${WORKLOAD_256:-${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt}"
TOPO_256="${TOPO_256:-${ROOT}/mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100}"
CONFIG_256="${CONFIG_256:-${ROOT}/myconfig/Zcube256MoE.conf}"

WORKLOAD_1024="${WORKLOAD_1024:-${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size1024-tp8-pp2-ep8-gbs1024-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt}"
TOPO_1024="${TOPO_1024:-${ROOT}/mytopo/1024/Zcube_n32_k2_1024g_8gps_200Gbps_H100}"
CONFIG_1024="${CONFIG_1024:-${ROOT}/myconfig/1024/ZcubeMoE.conf}"

usage() {
  cat <<'USAGE'
Usage: run_zcube_moe_htsim.sh [all|256|1024 ...]

Environment:
  HTSIM_BIN                  Override htsim binary path.
  HTSIM_ROUTE_STRATEGY       Route strategy, default spray_plb.
  HTSIM_RUN_STAMP            Output stamp, default current timestamp.
  OUT_ROOT                   Output root, default experiments/htsim_results/csv/zcube_moe_htsim_${stamp}.
  HTSIM_DISABLE_FCT_OUTPUT   Default 1; keeps EndToEnd.csv while skipping fct.txt.
  HTSIM_FLOW_RECLAIM_BATCH   Default 262144.
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

case_args=("$@")
if [[ "${#case_args[@]}" -eq 0 ]]; then
  case_args=(all)
fi

targets=()
for arg in "${case_args[@]}"; do
  case "${arg}" in
    all|both)
      targets=(256 1024)
      ;;
    256|1024)
      targets+=("${arg}")
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

[[ -x "${HTSIM_BIN}" ]] || die "missing executable: ${HTSIM_BIN}"
mkdir -p "${OUT_ROOT}"

SUMMARY="${OUT_ROOT}/summary.csv"
echo "case,strategy,exit_code,start_epoch,end_epoch,endtoend_lines,finished,finish_time,output_dir,log_file" > "${SUMMARY}"

run_case() {
  local scale="$1"
  local workload=""
  local topology=""
  local config=""

  case "${scale}" in
    256)
      workload="${WORKLOAD_256}"
      topology="${TOPO_256}"
      config="${CONFIG_256}"
      ;;
    1024)
      workload="${WORKLOAD_1024}"
      topology="${TOPO_1024}"
      config="${CONFIG_1024}"
      ;;
    *)
      die "unsupported scale: ${scale}"
      ;;
  esac

  require_file "${workload}" "workload for ${scale}"
  require_file "${topology}" "topology for ${scale}"
  require_file "${config}" "config for ${scale}"

  local name="Zcube${scale}MoE"
  local out_dir="${OUT_ROOT}/${name}_${ROUTE_STRATEGY}"
  local log_file="${OUT_ROOT}/${name}_${ROUTE_STRATEGY}.log"
  local start_epoch=""
  local end_epoch=""
  local exit_code=0
  local e2e_lines=0
  local finished=0
  local finish_time=""

  mkdir -p "${out_dir}"
  {
    echo "case=${name}"
    echo "strategy=${ROUTE_STRATEGY}"
    echo "workload=${workload}"
    echo "topology=${topology}"
    echo "config=${config}"
    echo "out_dir=${out_dir}"
    echo "disable_fct=${DISABLE_FCT}"
    echo "flow_reclaim_batch=${FLOW_RECLAIM_BATCH}"
  } > "${out_dir}/metadata.txt"

  start_epoch="$(date +%s)"
  echo "========== htsim ${name} ${ROUTE_STRATEGY} =========="
  echo "start_epoch=${start_epoch} out=${out_dir} log=${log_file}"

  set +e
  env \
    HTSIM_DISABLE_FCT_OUTPUT="${DISABLE_FCT}" \
    HTSIM_FLOW_RECLAIM_BATCH="${FLOW_RECLAIM_BATCH}" \
    "${HTSIM_BIN}" \
      -w "${workload}" \
      -n "${topology}" \
      -c "${config}" \
      -o "${out_dir}" \
      -r "${ROUTE_STRATEGY}" \
      > "${log_file}" 2>&1
  exit_code="$?"
  set -e

  end_epoch="$(date +%s)"
  [[ -f "${out_dir}/EndToEnd.csv" ]] && e2e_lines="$(wc -l < "${out_dir}/EndToEnd.csv")"
  if grep -q "all passes finished" "${log_file}"; then
    finished=1
    finish_time="$(grep "all passes finished at time" "${log_file}" | tail -1 | sed -E 's/.*time: ([0-9]+).*/\1/')"
  fi
  echo "${name},${ROUTE_STRATEGY},${exit_code},${start_epoch},${end_epoch},${e2e_lines},${finished},${finish_time},${out_dir},${log_file}" >> "${SUMMARY}"
  echo "done ${name}: exit=${exit_code} e2e_lines=${e2e_lines} finished=${finished} finish_time=${finish_time}"

  if [[ "${exit_code}" -ne 0 ]]; then
    echo "stopping after failed case ${name}; inspect ${log_file}" >&2
    exit "${exit_code}"
  fi
  if [[ "${e2e_lines}" -le 1 ]]; then
    echo "stopping after ${name}; EndToEnd.csv is missing or empty in ${out_dir}" >&2
    exit 1
  fi
}

for target in "${targets[@]}"; do
  run_case "${target}"
done

echo "all selected htsim Zcube MoE runs completed"
echo "summary: ${SUMMARY}"
