# DeepSeek High-Stretch h4=0.05 Fault Policy Comparison

Inputs:
- New: `experiments/fault_tolerance/flowsim_256_alltoall_deepseek_highstretch_hop4w005_threshold103_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
- Fault-only reference: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_targeted_faultonly_hop4w020_directw020_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
- Baseline-calibrated candidate: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_targeted_hop4w025_directw022_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
- Previous w0.3+PXN0.75: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/random_link_failure_summary.csv`
- NS3: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix/random_link_failure_summary.csv`

## Aggregate

| Topology | Rates | New success | New JCT MAE | Fault JCT MAE | Cand JCT MAE | Prev JCT MAE | New factor MAE | Fault factor MAE | Delta vs fault JCT | Delta vs fault factor |
| -------- | ----- | ----------- | ----------- | ------------- | ------------ | ------------ | -------------- | ---------------- | ------------------ | --------------------- |
| DeepSeek | 4     | 12/12       | 12.67       | 12.59         | 15.51        | 115.72       | 0.111          | 0.110            | 0.08               | 0.001                 |

## Detail

| Topology | Rate | Class              | NS3 JCT | New JCT | Fault JCT | Cand JCT | NS3 factor | New factor | Fault factor |
| -------- | ---- | ------------------ | ------- | ------- | --------- | -------- | ---------- | ---------- | ------------ |
| DeepSeek | 1%   | fault_default      | 58.7    | 60.7    | 60.7      | 65.7     | 1.151      | 1.083      | 1.083        |
| DeepSeek | 5%   | fault_default      | 77.4    | 87.3    | 87.3      | 89.0     | 1.518      | 1.560      | 1.560        |
| DeepSeek | 10%  | fault_high_stretch | 96.5    | 112.3   | 109.7     | 115.3    | 1.892      | 2.006      | 1.958        |
| DeepSeek | 15%  | fault_high_stretch | 107.7   | 130.7   | 133.0     | 132.3    | 2.112      | 2.333      | 2.375        |

Notes:
- Lower MAE is better.
- Negative deltas mean the new policy is closer to NS3 than the fault-only reference.
- New rows are collapsed from raw samples, so split `fault_env_class` samples are still averaged at topology/rate level.
