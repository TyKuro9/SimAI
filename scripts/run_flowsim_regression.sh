#!/usr/bin/env bash
set -euo pipefail

function PrintUsage() {
  cat <<'EOF'
用法:
  bash scripts/run_flowsim_regression.sh \
    -w <workload_file> -n <topology_file> -o <output_root> \
    [-t "1 2 4 8 16"] [-r repeats] [-b flowsim_bin]

产物:
  - 每次运行: output_root/t{thread}/r{idx}/(fct.txt,runtime.txt,run.log)
  - 汇总基线: output_root/regression_metrics.csv
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

FLOWSIM_BIN="${FLOWSIM_BIN:-/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim}"
THREAD_LIST="${THREAD_LIST:-1 2 4 8 16}"
REPEATS="${REPEATS:-3}"
WORKLOAD=""
TOPOLOGY=""
OUTPUT_ROOT=""

while getopts ":w:n:o:t:r:b:h" opt; do
  case "${opt}" in
    w) WORKLOAD="${OPTARG}" ;;
    n) TOPOLOGY="${OPTARG}" ;;
    o) OUTPUT_ROOT="${OPTARG}" ;;
    t) THREAD_LIST="${OPTARG}" ;;
    r) REPEATS="${OPTARG}" ;;
    b) FLOWSIM_BIN="${OPTARG}" ;;
    h) PrintUsage; exit 0 ;;
    *) PrintUsage; exit 1 ;;
  esac
done

RequireArg "workload(-w)" "${WORKLOAD}"
RequireArg "topology(-n)" "${TOPOLOGY}"
RequireArg "output(-o)" "${OUTPUT_ROOT}"

mkdir -p "${OUTPUT_ROOT}"

for thread in ${THREAD_LIST}; do
  for repeat in $(seq 1 "${REPEATS}"); do
    run_dir="${OUTPUT_ROOT}/t${thread}/r${repeat}"
    mkdir -p "${run_dir}"
    echo "[regression] run thread=${thread} repeat=${repeat}"
    /usr/bin/time -f "%e %M %c" -o "${run_dir}/runtime.txt" \
      "${FLOWSIM_BIN}" -t "${thread}" -w "${WORKLOAD}" -n "${TOPOLOGY}" -o "${run_dir}/" \
      > "${run_dir}/run.log" 2>&1
  done
done

python3 /home/zty/Topo/SimAI_TyKuro9/scripts/flowsim_regression_benchmark.py \
  --input-root "${OUTPUT_ROOT}" \
  --threads ${THREAD_LIST} \
  --repeats "${REPEATS}" \
  --output-csv "${OUTPUT_ROOT}/regression_metrics.csv"

echo "[regression] done: ${OUTPUT_ROOT}/regression_metrics.csv"
