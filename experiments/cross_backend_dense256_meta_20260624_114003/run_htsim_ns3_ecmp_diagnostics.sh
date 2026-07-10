#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
EXP_DIR="${ROOT_DIR}/experiments/cross_backend_dense256_meta_20260624_114003"
STAMP="${1:-$(date +%Y%m%d_%H%M%S)}"
OUT_ROOT="${EXP_DIR}/htsim_ns3_ecmp_diag_${STAMP}"

WORKLOAD_NAME="${WORKLOAD_NAME:-dense256_fullsize_core7}"
WORKLOAD_DIR="${EXP_DIR}/diagnostic_workloads"
WORKLOAD="${WORKLOAD_DIR}/${WORKLOAD_NAME}.txt"
TOPOLOGY="${ROOT_DIR}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100"
CONFIG="${ROOT_DIR}/myconfig/Meta256MoE.conf"
STRATEGIES="${STRATEGIES:-ecmp spray_plb ns3_ecmp}"
TIMEOUT_SEC="${TIMEOUT_SEC:-900}"
WATCHDOG_EVENTS="${WATCHDOG_EVENTS:-2000000}"
WATCHDOG_ASTRA_RANKS="${WATCHDOG_ASTRA_RANKS:-4}"
WATCHDOG_ASTRA_STREAMS="${WATCHDOG_ASTRA_STREAMS:-4}"

mkdir -p "${OUT_ROOT}"

python3 "${EXP_DIR}/make_htsim_repro_workloads.py" > "${OUT_ROOT}/generated_workloads.tsv"

if [[ ! -f "${WORKLOAD}" ]]; then
  echo "missing diagnostic workload: ${WORKLOAD}" >&2
  exit 2
fi

{
  echo -e "strategy\tstatus\tend_to_end_rows\tlog"
} > "${OUT_ROOT}/summary.tsv"

run_strategy() {
  local strategy="$1"
  local out_dir="${OUT_ROOT}/${strategy}"
  mkdir -p "${out_dir}"
  (
    echo "START $(date -Is)"
    echo "strategy=${strategy}"
    echo "workload=${WORKLOAD}"
    echo "timeout_sec=${TIMEOUT_SEC}"
    status=0
    /usr/bin/time -v timeout "${TIMEOUT_SEC}s" env \
      HTSIM_DISABLE_FCT_OUTPUT=1 \
      HTSIM_FLOW_RECLAIM_BATCH=262144 \
      HTSIM_WATCHDOG_EVENTS="${WATCHDOG_EVENTS}" \
      HTSIM_WATCHDOG_DUMP_ASTRA=1 \
      HTSIM_WATCHDOG_ASTRA_RANKS="${WATCHDOG_ASTRA_RANKS}" \
      HTSIM_WATCHDOG_ASTRA_STREAMS="${WATCHDOG_ASTRA_STREAMS}" \
      "${ROOT_DIR}/bin/SimAI_htsim" \
      -w "${WORKLOAD}" \
      -n "${TOPOLOGY}" \
      -c "${CONFIG}" \
      -o "${out_dir}/" \
      -r "${strategy}" || status=$?
    echo "EXIT:${status}"
    echo "END $(date -Is)"
    exit "${status}"
  ) > "${out_dir}/run.log" 2>&1
  local status=$?
  local rows=0
  if [[ -f "${out_dir}/EndToEnd.csv" ]]; then
    rows="$(wc -l < "${out_dir}/EndToEnd.csv")"
  fi
  echo -e "${strategy}\t${status}\t${rows}\t${out_dir}/run.log" >> "${OUT_ROOT}/summary.tsv"
  return 0
}

echo "output=${OUT_ROOT}"
for strategy in ${STRATEGIES}; do
  run_strategy "${strategy}"
done

cat "${OUT_ROOT}/summary.tsv"
