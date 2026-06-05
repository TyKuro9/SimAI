#!/usr/bin/env bash
set -euo pipefail

function PrintUsage() {
  cat <<'EOF'
用法:
  FS_PROFILE_ENABLE=1 bash scripts/flowsim_hotspot_profile.sh \
    -w <workload_file> -n <topology_file> -o <output_dir> [-t threads] [-b flowsim_bin]

说明:
  1) 自动执行一次 FlowSim，并开启内置热点剖析输出
  2) 尝试用 perf 采样（如果系统可用）
  3) 输出 profile_summary.txt / perf.data / perf_report.txt
EOF
}

function RequireArg() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    echo "缺少参数: ${name}" >&2
    PrintUsage
    exit 1
  fi
}

THREADS="${FLOWSIM_THREADS:-16}"
FLOWSIM_BIN="${FLOWSIM_BIN:-/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim}"
WORKLOAD=""
TOPOLOGY=""
OUTPUT_DIR=""

while getopts ":t:b:w:n:o:h" opt; do
  case "${opt}" in
    t) THREADS="${OPTARG}" ;;
    b) FLOWSIM_BIN="${OPTARG}" ;;
    w) WORKLOAD="${OPTARG}" ;;
    n) TOPOLOGY="${OPTARG}" ;;
    o) OUTPUT_DIR="${OPTARG}" ;;
    h) PrintUsage; exit 0 ;;
    *) PrintUsage; exit 1 ;;
  esac
done

RequireArg "workload(-w)" "${WORKLOAD}"
RequireArg "topology(-n)" "${TOPOLOGY}"
RequireArg "output(-o)" "${OUTPUT_DIR}"

mkdir -p "${OUTPUT_DIR}"
LOG_FILE="${OUTPUT_DIR}/profile_summary.txt"
PERF_DATA="${OUTPUT_DIR}/perf.data"
PERF_REPORT="${OUTPUT_DIR}/perf_report.txt"

echo "[profile] running flowsim with profiler..." | tee "${LOG_FILE}"
FS_PROFILE_ENABLE=1 "${FLOWSIM_BIN}" -t "${THREADS}" -w "${WORKLOAD}" -n "${TOPOLOGY}" -o "${OUTPUT_DIR}/run/" \
  2>&1 | tee -a "${LOG_FILE}"

if command -v perf >/dev/null 2>&1; then
  echo "[profile] collecting perf samples..." | tee -a "${LOG_FILE}"
  perf record -F 99 -g -o "${PERF_DATA}" -- \
    "${FLOWSIM_BIN}" -t "${THREADS}" -w "${WORKLOAD}" -n "${TOPOLOGY}" -o "${OUTPUT_DIR}/perf_run/" \
    >> "${LOG_FILE}" 2>&1 || true
  perf report -i "${PERF_DATA}" --stdio > "${PERF_REPORT}" 2>/dev/null || true
else
  echo "[profile] perf 不可用，已跳过采样" | tee -a "${LOG_FILE}"
fi

echo "[profile] done: ${OUTPUT_DIR}" | tee -a "${LOG_FILE}"
