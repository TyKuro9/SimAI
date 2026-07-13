#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "usage: $0 CASE_NAME [RUN_TAG]" >&2
  exit 2
fi

CASE="$1"
RUN_TAG="${2:-$(date +%Y%m%d_%H%M%S)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIAG="${ROOT}/diagnostics/zcube_moe_final_drain"
WL="${DIAG}/workloads/zcube_moe_${CASE}.txt"
TOPO="${ROOT}/mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100"
OUT="${DIAG}/runs/${CASE}_${RUN_TAG}"
CONF="${OUT}/Zcube256MoE.conf"

if [[ ! -f "${WL}" ]]; then
  echo "missing workload: ${WL}" >&2
  exit 1
fi

mkdir -p "${OUT}/ns3" "${OUT}/csv"
sed \
  -e "s|^FLOW_FILE .*|FLOW_FILE ${OUT}/ns3/flow.txt|" \
  -e "s|^TRACE_FILE .*|TRACE_FILE ${OUT}/ns3/trace.txt|" \
  -e "s|^TRACE_OUTPUT_FILE .*|TRACE_OUTPUT_FILE ${OUT}/ns3/mix.tr|" \
  -e "s|^FCT_OUTPUT_FILE .*|FCT_OUTPUT_FILE ${OUT}/ns3/fct.txt|" \
  -e "s|^PFC_OUTPUT_FILE .*|PFC_OUTPUT_FILE ${OUT}/ns3/pfc.txt|" \
  "${ROOT}/myconfig/Zcube256MoE.conf" > "${CONF}"

export AS_SEND_LAT=3
export AS_NVLS_ENABLE=0
export AS_NS3_PROGRESS=1
export AS_FCT_OUTPUT="${AS_FCT_OUTPUT:-0}"
export AS_NS3_ROUTE_DIAG="${AS_NS3_ROUTE_DIAG:-0}"
export AS_NS3_ROUTE_TRACE_LIMIT="${AS_NS3_ROUTE_TRACE_LIMIT:-0}"
export AS_NS3_DROP_TRACE_LIMIT="${AS_NS3_DROP_TRACE_LIMIT:-64}"

cd "${ROOT}"
printf 'started_at=%s\ncase=%s\ncommit=%s\n' \
  "$(date --iso-8601=seconds)" "${CASE}" "$(git rev-parse HEAD)" \
  > "${OUT}/metadata.txt"

set +e
/usr/bin/time -v "${ROOT}/bin/SimAI_simulator" \
  -t "${THREADS:-16}" -w "${WL}" -n "${TOPO}" -c "${CONF}" \
  -o "${OUT}/csv/" > "${OUT}/run.log" 2>&1
status=$?
set -e
printf 'finished_at=%s\nexit_status=%s\n' \
  "$(date --iso-8601=seconds)" "${status}" >> "${OUT}/metadata.txt"
exit "${status}"
