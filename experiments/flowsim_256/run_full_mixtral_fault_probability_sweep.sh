#!/usr/bin/env bash
# Full Mixtral 8x7B MoE @ 256 GPU FlowSim error-probability sweep.
#
# Default run:
#   bash experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh
#
# Useful overrides:
#   TOPOS=Meta,Zcube bash experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh
#   MAX_ERROR_PERCENT=5 bash experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh
#   THREADS=32 bash experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh
#   OUTPUT_DIR=results/my_full_run bash experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh
#
# Extra arguments are passed through to run_fault_probability_sweep.py.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
THREADS="${THREADS:-16}"
MAX_ERROR_PERCENT="${MAX_ERROR_PERCENT:-15}"
NUM_SEEDS="${NUM_SEEDS:-1}"
RANDOM_SEED="${RANDOM_SEED:-1}"
SEEDS="${SEEDS:-}"
TOPOS="${TOPOS:-}"
ERROR_MODEL="${ERROR_MODEL:-bandwidth_scale}"
OUTPUT_DIR="${OUTPUT_DIR:-${ROOT}/results/fault_tolerance_256_flowsim_full_mixtral}"
FLOWSIM_BIN="${FLOWSIM_BIN:-/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim}"
MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/matplotlib-cache}"

WORKLOAD="${WORKLOAD:-${ROOT}/my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt}"

if [[ ! -x "${FLOWSIM_BIN}" ]]; then
  echo "Error: FlowSim binary not executable: ${FLOWSIM_BIN}" >&2
  echo "Build with: cd /home/zty/Topo/m4/SimAI && ./scripts/build.sh -c flowsim" >&2
  exit 1
fi

if [[ ! -f "${WORKLOAD}" ]]; then
  echo "Error: workload not found: ${WORKLOAD}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}" "${MPLCONFIGDIR}"

args=(
  experiments/flowsim_256/run_fault_probability_sweep.py
  --workload "${WORKLOAD}"
  --workload-name "Mixtral-8x7B-MoE-256-full"
  --output-dir "${OUTPUT_DIR}"
  --flowsim-bin "${FLOWSIM_BIN}"
  --threads "${THREADS}"
  --max-error-percent "${MAX_ERROR_PERCENT}"
  --num-seeds "${NUM_SEEDS}"
  --random-seed "${RANDOM_SEED}"
  --error-model "${ERROR_MODEL}"
)

if [[ -n "${SEEDS}" ]]; then
  args+=(--seeds "${SEEDS}")
fi

if [[ -n "${TOPOS}" ]]; then
  args+=(--topologies "${TOPOS}")
fi

echo "========== Full Mixtral 256 FlowSim sweep =========="
echo "Workload:       ${WORKLOAD}"
echo "Topologies:     ${TOPOS:-Meta,HPN,DeepSeek,Zcube,RO,ROFT}"
echo "Error percent:  0..${MAX_ERROR_PERCENT}"
echo "Seeds:          ${SEEDS:-${RANDOM_SEED}..$((RANDOM_SEED + NUM_SEEDS - 1))}"
echo "Threads:        ${THREADS}"
echo "Error model:    ${ERROR_MODEL}"
echo "Output:         ${OUTPUT_DIR}"
echo "FlowSim bin:    ${FLOWSIM_BIN}"
echo "===================================================="

export MPLCONFIGDIR
export FLOWSIM_WRITE_FCT=0
export FLOWSIM_PROGRESS="${FLOWSIM_PROGRESS:-0}"

"${PYTHON_BIN}" "${args[@]}" "$@"

echo "Done."
echo "Summary: ${OUTPUT_DIR}/jct_by_error_probability_summary.csv"
echo "Raw:     ${OUTPUT_DIR}/jct_by_error_probability_raw.csv"
echo "Plot:    ${OUTPUT_DIR}/jct_by_error_probability.png"
