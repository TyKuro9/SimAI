# guardrail w0.3 + PXN same-rail w0.75 FlowSim Policy Sweep Comparison

## Topology Aggregate

| Topology | Rates | Orig factor MAE | Policy factor MAE | Factor delta | Orig JCT MAE | Policy JCT MAE | JCT delta |
| -------- | ----- | --------------- | ----------------- | ------------ | ------------ | -------------- | --------- |
| DeepSeek | 4     | 0.144           | 0.093             | -0.051       | 174.1        | 115.7          | -58.4     |
| RO       | 2     | 0.623           | 0.686             | 0.063        | 9.8          | 6.1            | -3.7      |

## Rate Detail

| Topology | Rate | NS3 factor | Orig factor | Policy factor | NS3 JCT | Orig JCT | Policy JCT | Complete | Success |
| -------- | ---- | ---------- | ----------- | ------------- | ------- | -------- | ---------- | -------- | ------- |
| DeepSeek | 0.01 | 1.151      | 1.215       | 1.212         | 58.7    | 173.7    | 138.2      | True     | 10/10   |
| DeepSeek | 0.05 | 1.518      | 1.721       | 1.689         | 77.4    | 246.1    | 192.6      | True     | 10/10   |
| DeepSeek | 0.10 | 1.892      | 2.069       | 1.998         | 96.5    | 295.9    | 227.8      | True     | 10/10   |
| DeepSeek | 0.15 | 2.112      | 2.245       | 2.146         | 107.7   | 321.1    | 244.6      | True     | 10/10   |
| RO       | 0.01 | 1.093      | 1.520       | 1.593         | 79.8    | 82.1     | 70.1       | True     | 10/10   |
| RO       | 0.05 | 1.410      | 2.228       | 2.282         | 102.9   | 120.3    | 100.4      | True     | 10/10   |

Notes:
- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.
- Negative deltas mean the policy is closer to NS3 than original FlowSim.
- A complete policy row requires at least 10 successful samples.
- Policy summary: `experiments/fault_tolerance/flowsim_256_alltoall_guardrail_w03_pxn075/random_link_failure_summary.csv`
