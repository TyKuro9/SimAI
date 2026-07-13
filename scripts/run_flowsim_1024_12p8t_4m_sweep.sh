#!/usr/bin/env bash
set -euo pipefail

cd /home/zty/Topo/SimAI_TyKuro9_pxn

python3 scripts/run_flowsim_fault_256_alltoall.py \
  --scale 1024_12p8T \
  --workload my_workloads/synthetic_alltoall_global_world_size1024_4MiB.txt \
  --output-dir experiments/fault_tolerance/flowsim_1024_12p8T_alltoall_4MiB_p01_p15_s10_local_pipeline_d6000 \
  --rates 0.01,0.02,0.03,0.04,0.05,0.06,0.07,0.08,0.09,0.10,0.11,0.12,0.13,0.14,0.15 \
  --samples 10 \
  --seed-base 1 \
  --threads 8 \
  --jobs 2 \
  --run-timeout-seconds 7200 \
  --switch-throughput-limit-gbps 12800 \
  --flowsim-pxn-timing local_pipeline \
  --pxn-local-pipeline-delay-ns 6000 \
  --policy-label local_pipeline_d6000 \
  --resume
