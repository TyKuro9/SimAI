#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:-$(date +%Y%m%d_%H%M%S)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SIM="${ROOT}/bin/SimAI_simulator"
WL="${WL:-${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp4-ep8-gbs96-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True.txt}"
THREADS="${THREADS:-8}"
ONLY_CASE="${ONLY_CASE:-}"
OUT_ROOT="${OUT_ROOT:-${ROOT}/experiments/ns3_results/topology_sweep_${RUN_ID}}"
STATUS_SUFFIX="${ONLY_CASE:+-${ONLY_CASE}}"
STATUS_FILE="${OUT_ROOT}/status${STATUS_SUFFIX}.tsv"

CASES=(
  "DeepSeek|mytopo/DeepSeek_256g_8gps_p16a0.5_400Gbps_H800|myconfig/DeepSeek256MoE.conf"
  "HPN|mytopo/AlibabaHPN_256g_8gps_DualToR_DualPlane_200Gbps_H100|myconfig/HPN256MoE.conf"
  "Meta|mytopo/Meta_Topo_256g_8gps_400Gbps_A100|myconfig/Meta256MoE.conf"
  "ROFT|mytopo/ROFT_256g_8gps_p16a0.5_400Gbps_H100|myconfig/ROFT256MoE.conf"
)

if [[ ! -x "${SIM}" ]]; then
  echo "missing simulator: ${SIM}" >&2
  exit 1
fi
if [[ ! -f "${WL}" ]]; then
  echo "missing workload: ${WL}" >&2
  exit 1
fi

mkdir -p "${OUT_ROOT}"
printf 'topology\tstarted_at\tfinished_at\texit_status\n' > "${STATUS_FILE}"
matched=0

for entry in "${CASES[@]}"; do
  IFS='|' read -r name topo_rel conf_rel <<< "${entry}"
  if [[ -n "${ONLY_CASE}" && "${name}" != "${ONLY_CASE}" ]]; then
    continue
  fi
  matched=1
  topo="${ROOT}/${topo_rel}"
  conf_src="${ROOT}/${conf_rel}"
  case_dir="${OUT_ROOT}/${name}"
  csv_dir="${case_dir}/csv"
  ns3_dir="${case_dir}/ns3"
  conf="${case_dir}/${name}256MoE.conf"
  log="${case_dir}/run.log"

  if [[ ! -f "${topo}" || ! -f "${conf_src}" ]]; then
    echo "missing topology or config for ${name}" >&2
    exit 1
  fi

  mkdir -p "${csv_dir}" "${ns3_dir}"
  sed \
    -e "s|^FLOW_FILE .*|FLOW_FILE ${ns3_dir}/flow.txt|" \
    -e "s|^TRACE_FILE .*|TRACE_FILE ${ns3_dir}/trace.txt|" \
    -e "s|^TRACE_OUTPUT_FILE .*|TRACE_OUTPUT_FILE ${ns3_dir}/mix.tr|" \
    -e "s|^FCT_OUTPUT_FILE .*|FCT_OUTPUT_FILE ${ns3_dir}/fct.txt|" \
    -e "s|^PFC_OUTPUT_FILE .*|PFC_OUTPUT_FILE ${ns3_dir}/pfc.txt|" \
    "${conf_src}" > "${conf}"

  started_at="$(date --iso-8601=seconds)"
  echo "[topology-sweep] start=${name} time=${started_at}"
  echo "[topology-sweep] topology=${topo}"
  echo "[topology-sweep] output=${case_dir}"

  set +e
  env \
    AS_SEND_LAT=3 \
    AS_NVLS_ENABLE=0 \
    AS_PXN_ENABLE=0 \
    AS_NS3_PROGRESS=1 \
    AS_FCT_OUTPUT=0 \
    AS_NS3_ROUTE_DIAG=1 \
    AS_NS3_ROUTE_TRACE_LIMIT=256 \
    AS_NS3_DROP_TRACE_LIMIT=64 \
    AS_NS3_PFC_FLUSH=1 \
    AS_STREAM_DUMP=1 \
    AS_STREAM_DUMP_LIMIT=12 \
    "${SIM}" \
      -t "${THREADS}" \
      -w "${WL}" \
      -n "${topo}" \
      -c "${conf}" \
      -o "${csv_dir}/" \
      2>&1 | tee "${log}"
  status=${PIPESTATUS[0]}
  set -e

  finished_at="$(date --iso-8601=seconds)"
  printf '%s\t%s\t%s\t%s\n' \
    "${name}" "${started_at}" "${finished_at}" "${status}" >> "${STATUS_FILE}"
  echo "[topology-sweep] finish=${name} time=${finished_at} exit=${status}"

  if [[ "${status}" -ne 0 ]]; then
    exit "${status}"
  fi
done

if [[ "${matched}" -eq 0 ]]; then
  echo "unknown topology: ${ONLY_CASE}" >&2
  exit 2
fi

echo "[topology-sweep] all selected topologies completed"
