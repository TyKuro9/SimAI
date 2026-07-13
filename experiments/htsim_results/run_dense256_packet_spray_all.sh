#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

HTSIM_BIN="${HTSIM_BIN:-${ROOT}/bin/SimAI_htsim}"
WORKLOAD="${WORKLOAD:-${ROOT}/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt}"
CONFIG="${CONFIG:-${ROOT}/myconfig/Meta256MoE.conf}"
ROUTE_STRATEGY="${ROUTE_STRATEGY:-spray_plb}"
OUT_ROOT="${OUT_ROOT:-${ROOT}/experiments/htsim_results/csv/dense256_packet_spray_20260622_195144}"

mkdir -p "${OUT_ROOT}"
SUMMARY="${OUT_ROOT}/summary.csv"
echo "topology,strategy,exit_code,start_epoch,end_epoch,endtoend_lines,fct_lines,finished,finish_time,output_dir,log_file" > "${SUMMARY}"

CASES=(
  "Meta|${ROOT}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100"
  "HPN|${ROOT}/mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100"
  "DeepSeek|${ROOT}/mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800"
  "Zcube|${ROOT}/mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100"
  "RO|${ROOT}/mytopo/RailOnly_256g_8gps_p16a0.5_400Gbps_H100"
  "ROFT|${ROOT}/mytopo/ROFT_256g_8gps_p16a0.5_400Gbps_H100"
)

if [[ ! -x "${HTSIM_BIN}" ]]; then
  echo "missing executable: ${HTSIM_BIN}" >&2
  exit 1
fi
if [[ ! -f "${WORKLOAD}" ]]; then
  echo "missing workload: ${WORKLOAD}" >&2
  exit 1
fi

for entry in "${CASES[@]}"; do
  IFS='|' read -r name topo <<< "${entry}"
  out_dir="${OUT_ROOT}/${name}"
  log_file="${OUT_ROOT}/${name}.log"
  mkdir -p "${out_dir}"
  start_epoch="$(date +%s)"
  echo "========== htsim packet dense256 ${name} ${ROUTE_STRATEGY} =========="
  echo "start_epoch=${start_epoch} out=${out_dir} log=${log_file}"

  set +e
  "${HTSIM_BIN}" \
    -w "${WORKLOAD}" \
    -n "${topo}" \
    -c "${CONFIG}" \
    -o "${out_dir}" \
    -r "${ROUTE_STRATEGY}" \
    > "${log_file}" 2>&1
  exit_code="$?"
  set -e

  end_epoch="$(date +%s)"
  e2e_lines=0
  fct_lines=0
  finished=0
  finish_time=""
  [[ -f "${out_dir}/EndToEnd.csv" ]] && e2e_lines="$(wc -l < "${out_dir}/EndToEnd.csv")"
  [[ -f "${out_dir}/fct.txt" ]] && fct_lines="$(wc -l < "${out_dir}/fct.txt")"
  if grep -q "all passes finished" "${log_file}"; then
    finished=1
    finish_time="$(grep "all passes finished at time" "${log_file}" | tail -1 | sed -E 's/.*time: ([0-9]+).*/\1/')"
  fi
  echo "${name},${ROUTE_STRATEGY},${exit_code},${start_epoch},${end_epoch},${e2e_lines},${fct_lines},${finished},${finish_time},${out_dir},${log_file}" >> "${SUMMARY}"
  echo "done ${name}: exit=${exit_code} e2e=${e2e_lines} fct=${fct_lines} finished=${finished} finish_time=${finish_time}"

  if [[ "${exit_code}" -ne 0 ]]; then
    echo "stopping after failed topology ${name}; inspect ${log_file}" >&2
    exit "${exit_code}"
  fi
done

echo "all selected htsim dense256 packet-level runs completed"
echo "summary: ${SUMMARY}"
