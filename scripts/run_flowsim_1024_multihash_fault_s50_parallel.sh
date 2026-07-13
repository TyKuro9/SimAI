#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/zty/Topo/SimAI_TyKuro9_pxn
cd "$ROOT"

BASE=experiments/fault_tolerance/flowsim_1024_tp16dp64_1MiB_multihash4_fault_p01_p15_s50_local_pipeline_d6000_parallel
WORKLOAD=my_workloads/synthetic_alltoall_global_world_size1024_tp16_dp64_1MiB.txt

run_topology() {
    local name="$1"
    local output_dir="$BASE/$name"
    mkdir -p "$output_dir"

    FLOWSIM_ECMP_FLOW_HASH=1 \
    FLOWSIM_ECMP_PATH_COUNT=4 \
    FLOWSIM_ECMP_SEED=srcip \
    FLOWSIM_ECMP_SRC_PORT=10006 \
    python3 scripts/run_flowsim_fault_256_alltoall.py \
        --scale 1024_12p8T \
        --workload "$WORKLOAD" \
        --workload-label all-to-all-global-1024-tp16-dp64-1MiB-multihash4 \
        --output-dir "$output_dir" \
        --rates 0.01,0.02,0.03,0.04,0.05,0.06,0.07,0.08,0.09,0.10,0.11,0.12,0.13,0.14,0.15 \
        --samples 50 \
        --seed-base 1 \
        --threads 8 \
        --jobs 8 \
        --run-timeout-seconds 1800 \
        --flowsim-pxn-timing local_pipeline \
        --pxn-local-pipeline-delay-ns 6000 \
        --topologies "$name" \
        --resume \
        --policy-label multihash4_local_pipeline_d6000 \
        > "$output_dir/runner.log" 2>&1
    printf '%s 0\n' "$name" > "$output_dir/exit_status"
}

names=(Meta HPN DeepSeek Zcube ROFT)
pids=()
for name in "${names[@]}"; do
    run_topology "$name" &
    pids+=("$!")
done

status=0
for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        status=1
    fi
done
exit "$status"
