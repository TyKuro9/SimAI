#!/usr/bin/env bash
set -euo pipefail

RUN_ID="${1:-$(date +%Y%m%d_%H%M%S)}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WL="${WL:-${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt}"
TOPO="${ROOT}/mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100"
CONF="${ROOT}/myconfig/Zcube256MoE.conf"
OUT="${ROOT}/experiments/ns3_results/csv/Mixtral-Zcube256H100-fullrun-nogdb-${RUN_ID}"
LOG="${ROOT}/experiments/ns3_results/Update-256gpu_Mixtral8x7B-MoE_Zcube256H100_fullrun_nogdb_${RUN_ID}.log"

mkdir -p "${OUT}" "$(dirname "${LOG}")"

cd "${ROOT}"
export AS_SEND_LAT=3
export AS_NVLS_ENABLE=0
export AS_NS3_PROGRESS=1
export AS_FCT_OUTPUT="${AS_FCT_OUTPUT:-0}"
export AS_NS3_ROUTE_DIAG="${AS_NS3_ROUTE_DIAG:-1}"
export AS_NS3_ROUTE_TRACE_LIMIT="${AS_NS3_ROUTE_TRACE_LIMIT:-256}"
export AS_NS3_DROP_TRACE_LIMIT="${AS_NS3_DROP_TRACE_LIMIT:-64}"
export AS_NS3_PFC_FLUSH="${AS_NS3_PFC_FLUSH:-1}"
export AS_STREAM_DUMP="${AS_STREAM_DUMP:-1}"
export AS_STREAM_DUMP_LIMIT="${AS_STREAM_DUMP_LIMIT:-12}"

echo "[fullrun-nogdb] run_id=${RUN_ID}"
echo "[fullrun-nogdb] output=${OUT}"
echo "[fullrun-nogdb] log=${LOG}"

"${ROOT}/bin/SimAI_simulator" \
  -t 16 \
  -w "${WL}" \
  -n "${TOPO}" \
  -c "${CONF}" \
  -o "${OUT}/" \
  2>&1 | tee "${LOG}"
