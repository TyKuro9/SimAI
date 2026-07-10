#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_ROOT="${ROOT_DIR}/experiments/cross_backend_dense256_meta_20260624_114003/short_cross_sim_${1:-20260626_short10_1mib}"

WORKLOAD="${SHORT_WORKLOAD:-/tmp/htsim_dense256_short10_1mib.txt}"
TOPOLOGY="${ROOT_DIR}/mytopo/Meta_Topo_256g_8gps_400Gbps_A100"
HTSIM_CONFIG="${ROOT_DIR}/myconfig/Meta256MoE.conf"
NS3_TEMPLATE="${ROOT_DIR}/experiments/cross_backend_dense256_meta_20260624_114003/ns3_rerun_20260624_143409/retry_fixed_conf/Meta256_run.conf"
FLOWSIM="${FLOWSIM_BIN:-/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim}"
THREADS="${THREADS:-16}"
NS3_TIMEOUT_SEC="${NS3_TIMEOUT_SEC:-3600}"

mkdir -p "${OUT_ROOT}"

write_meta() {
  local out_dir="$1"
  {
    echo "workload=${WORKLOAD}"
    echo "topology=${TOPOLOGY}"
    echo "threads=${THREADS}"
    echo "date=$(date -Is)"
  } > "${out_dir}/meta.txt"
}

run_htsim() {
  local strategy="$1"
  local out_dir="${OUT_ROOT}/htsim_${strategy}"
  mkdir -p "${out_dir}"
  write_meta "${out_dir}"
  (
    echo "START $(date -Is)"
    echo "backend=htsim"
    echo "strategy=${strategy}"
    /usr/bin/time -v env HTSIM_FLOW_RECLAIM_BATCH=262144 \
      "${ROOT_DIR}/bin/SimAI_htsim" \
      -t "${THREADS}" \
      -w "${WORKLOAD}" \
      -n "${TOPOLOGY}" \
      -c "${HTSIM_CONFIG}" \
      -o "${out_dir}/" \
      -r "${strategy}"
    status=$?
    echo "EXIT:${status}"
    echo "END $(date -Is)"
    exit "${status}"
  ) > "${out_dir}/run.log" 2>&1
}

run_flowsim() {
  local out_dir="${OUT_ROOT}/flowsim"
  mkdir -p "${out_dir}"
  write_meta "${out_dir}"
  (
    echo "START $(date -Is)"
    echo "backend=flowsim"
    cd /home/zty/Topo/m4/SimAI || exit 2
    /usr/bin/time -v env FLOWSIM_PROGRESS=0 \
      "${FLOWSIM}" \
      -t "${THREADS}" \
      -w "${WORKLOAD}" \
      -n "${TOPOLOGY}" \
      -o "${out_dir}/"
    status=$?
    echo "EXIT:${status}"
    echo "END $(date -Is)"
    exit "${status}"
  ) > "${out_dir}/run.log" 2>&1
}

write_ns3_config() {
  local out_dir="$1"
  local aux_dir="${out_dir}/ns3_aux"
  local conf_dir="${out_dir}/conf"
  mkdir -p "${aux_dir}" "${conf_dir}"
  awk -v aux="${aux_dir}" '
    /^FLOW_FILE / { print "FLOW_FILE " aux "/short_flow.txt"; next }
    /^TRACE_FILE / { print "TRACE_FILE " aux "/short_trace.txt"; next }
    /^TRACE_OUTPUT_FILE / { print "TRACE_OUTPUT_FILE " aux "/short_mix.tr"; next }
    /^FCT_OUTPUT_FILE / { print "FCT_OUTPUT_FILE " aux "/short_fct.txt"; next }
    /^PFC_OUTPUT_FILE / { print "PFC_OUTPUT_FILE " aux "/short_pfc.txt"; next }
    /^ENABLE_TRACE / { print "ENABLE_TRACE 0"; next }
    { print }
  ' "${NS3_TEMPLATE}" > "${conf_dir}/Meta256_short.conf"
}

run_ns3() {
  local out_dir="${OUT_ROOT}/ns3_ecmp"
  mkdir -p "${out_dir}"
  write_meta "${out_dir}"
  write_ns3_config "${out_dir}"
  (
    echo "START $(date -Is)"
    echo "backend=ns3"
    echo "strategy=ecmp"
    if [[ "${NS3_TIMEOUT_SEC}" == "0" ]]; then
      /usr/bin/time -v env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
        "${ROOT_DIR}/bin/SimAI_simulator" \
        -t "${THREADS}" \
        -w "${WORKLOAD}" \
        -n "${TOPOLOGY}" \
        -c "${out_dir}/conf/Meta256_short.conf" \
        -o "${out_dir}/"
    else
      /usr/bin/time -v timeout "${NS3_TIMEOUT_SEC}s" env AS_SEND_LAT=3 AS_NVLS_ENABLE=0 \
        "${ROOT_DIR}/bin/SimAI_simulator" \
        -t "${THREADS}" \
        -w "${WORKLOAD}" \
        -n "${TOPOLOGY}" \
        -c "${out_dir}/conf/Meta256_short.conf" \
        -o "${out_dir}/"
    fi
    status=$?
    echo "EXIT:${status}"
    echo "END $(date -Is)"
    exit "${status}"
  ) > "${out_dir}/run.log" 2>&1
}

for required in "${WORKLOAD}" "${TOPOLOGY}" "${HTSIM_CONFIG}" "${NS3_TEMPLATE}"; do
  if [[ ! -f "${required}" ]]; then
    echo "missing required file: ${required}" >&2
    exit 2
  fi
done

if [[ ! -x "${ROOT_DIR}/bin/SimAI_htsim" || ! -x "${ROOT_DIR}/bin/SimAI_simulator" || ! -x "${FLOWSIM}" ]]; then
  echo "missing one or more backend binaries" >&2
  exit 2
fi

echo "output=${OUT_ROOT}"
run_flowsim
run_htsim ecmp
run_htsim spray_rr
run_ns3

"${ROOT_DIR}/experiments/cross_backend_dense256_meta_20260624_114003/summarize_short_cross_sim_compare.py" "${OUT_ROOT}"
