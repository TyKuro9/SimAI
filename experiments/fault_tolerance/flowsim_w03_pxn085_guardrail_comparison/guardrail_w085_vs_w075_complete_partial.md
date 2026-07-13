# guardrail w0.85 vs w0.75 FlowSim Policy Sweep Comparison

## Topology Aggregate

| Topology | Rates | Orig factor MAE | Policy factor MAE | Factor delta | Orig JCT MAE | Policy JCT MAE | JCT delta |
| -------- | ----- | --------------- | ----------------- | ------------ | ------------ | -------------- | --------- |
| DeepSeek | 4     | 0.093           | 0.106             | 0.013        | 115.7        | 138.5          | 22.8      |
| RO       | 4     | 1.061           | 1.055             | -0.006       | 8.6          | 6.0            | -2.6      |

## Rate Detail

| Topology | Rate | NS3 factor | Orig factor | Policy factor | NS3 JCT | Orig JCT | Policy JCT | Complete | Success |
| -------- | ---- | ---------- | ----------- | ------------- | ------- | -------- | ---------- | -------- | ------- |
| DeepSeek | 0.01 | 1.151      | 1.212       | 1.207         | 58.7    | 138.2    | 152.1      | True     | 10/10   |
| DeepSeek | 0.05 | 1.518      | 1.689       | 1.694         | 77.4    | 192.6    | 213.5      | True     | 10/10   |
| DeepSeek | 0.10 | 1.892      | 1.998       | 2.009         | 96.5    | 227.8    | 253.1      | True     | 10/10   |
| DeepSeek | 0.15 | 2.112      | 2.146       | 2.188         | 107.7   | 244.6    | 275.7      | True     | 10/10   |
| RO       | 0.01 | 1.093      | 1.593       | 1.535         | 79.8    | 70.1     | 73.7       | True     | 10/10   |
| RO       | 0.05 | 1.410      | 2.282       | 2.219         | 102.9   | 100.4    | 106.5      | True     | 10/10   |
| RO       | 0.10 | 2.040      | 3.298       | 3.306         | 148.9   | 145.1    | 158.7      | True     | 10/10   |
| RO       | 0.15 | 3.084      | 4.698       | 4.788         | 225.1   | 206.7    | 229.8      | True     | 10/10   |

Notes:
- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.
- Negative deltas mean the policy is closer to NS3 than original FlowSim.
- A complete policy row requires at least 10 successful samples.
- Policy summary: `experiments/fault_tolerance/flowsim_256_alltoall_guardrail_w03_pxn085/random_link_failure_summary.csv`
