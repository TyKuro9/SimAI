# Targeted High-Stretch Fault Policy Comparison

Inputs:
- New: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_targeted_highstretch_hop4w016_directw018_threshold103_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
- Fault-only reference: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_targeted_faultonly_hop4w020_directw020_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
- Baseline-calibrated candidate: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_targeted_hop4w025_directw022_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
- Previous w0.3+PXN0.75: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/random_link_failure_summary.csv`
- NS3: `/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix/random_link_failure_summary.csv`

## Aggregate

| Topology | Rates | New success | New JCT MAE | Fault JCT MAE | Cand JCT MAE | Prev JCT MAE | New factor MAE | Fault factor MAE | Delta vs fault JCT | Delta vs fault factor |
| -------- | ----- | ----------- | ----------- | ------------- | ------------ | ------------ | -------------- | ---------------- | ------------------ | --------------------- |
| ROFT     | 4     | 12/12       | 6.23        | 5.98          | 8.57         | 24.35        | 0.113          | 0.109            | 0.25               | 0.005                 |
| DeepSeek | 4     | 12/12       | 12.34       | 12.59         | 15.51        | 115.72       | 0.105          | 0.110            | -0.25              | -0.004                |
| RO       | 4     | 12/12       | 27.93       | 27.93         | 25.42        | 8.60         | 0.622          | 0.622            | 0.00               | 0.000                 |

## Detail

| Topology | Rate | Class              | NS3 JCT | New JCT | Fault JCT | Cand JCT | NS3 factor | New factor | Fault factor |
| -------- | ---- | ------------------ | ------- | ------- | --------- | -------- | ---------- | ---------- | ------------ |
| ROFT     | 1%   | fault_default      | 61.7    | 64.3    | 64.3      | 68.0     | 1.122      | 1.170      | 1.170        |
| ROFT     | 5%   | fault_high_stretch | 79.3    | 84.0    | 85.0      | 91.0     | 1.442      | 1.527      | 1.545        |
| ROFT     | 10%  | fault_high_stretch | 101.2   | 105.7   | 106.3     | 106.7    | 1.840      | 1.921      | 1.933        |
| ROFT     | 15%  | fault_high_stretch | 117.2   | 130.3   | 127.7     | 128.0    | 2.131      | 2.370      | 2.321        |
| DeepSeek | 1%   | fault_default      | 58.7    | 60.7    | 60.7      | 65.7     | 1.151      | 1.083      | 1.083        |
| DeepSeek | 5%   | fault_default      | 77.4    | 87.3    | 87.3      | 89.0     | 1.518      | 1.560      | 1.560        |
| DeepSeek | 10%  | fault_high_stretch | 96.5    | 109.7   | 109.7     | 115.3    | 1.892      | 1.958      | 1.958        |
| DeepSeek | 15%  | fault_high_stretch | 107.7   | 132.0   | 133.0     | 132.3    | 2.112      | 2.357      | 2.375        |
| RO       | 1%   | fault_default      | 79.8    | 58.3    | 58.3      | 58.3     | 1.093      | 1.326      | 1.326        |
| RO       | 5%   | fault_default      | 102.9   | 91.3    | 91.3      | 93.0     | 1.410      | 2.076      | 2.076        |
| RO       | 10%  | fault_default      | 148.9   | 119.7   | 119.7     | 120.7    | 2.040      | 2.720      | 2.720        |
| RO       | 15%  | fault_default      | 225.1   | 175.7   | 175.7     | 183.0    | 3.084      | 3.992      | 3.992        |

Notes:
- Lower MAE is better.
- Negative deltas mean the new policy is closer to NS3 than the fault-only reference.
- New rows are collapsed from raw samples, so split `fault_env_class` samples are still averaged at topology/rate level.
