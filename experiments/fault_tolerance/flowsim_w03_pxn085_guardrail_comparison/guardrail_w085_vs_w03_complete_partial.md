# guardrail w0.3 + PXN same-rail w0.85 vs w0.3 FlowSim Policy Sweep Comparison

## Topology Aggregate

| Topology | Rates | Orig factor MAE | Policy factor MAE | Factor delta | Orig JCT MAE | Policy JCT MAE | JCT delta |
| -------- | ----- | --------------- | ----------------- | ------------ | ------------ | -------------- | --------- |
| DeepSeek | 4     | 0.144           | 0.106             | -0.038       | 174.1        | 138.5          | -35.6     |
| RO       | 4     | 1.092           | 1.055             | -0.036       | 22.7         | 6.0            | -16.7     |

## Rate Detail

| Topology | Rate | NS3 factor | Orig factor | Policy factor | NS3 JCT | Orig JCT | Policy JCT | Complete | Success |
| -------- | ---- | ---------- | ----------- | ------------- | ------- | -------- | ---------- | -------- | ------- |
| DeepSeek | 0.01 | 1.151      | 1.215       | 1.207         | 58.7    | 173.7    | 152.1      | True     | 10/10   |
| DeepSeek | 0.05 | 1.518      | 1.721       | 1.694         | 77.4    | 246.1    | 213.5      | True     | 10/10   |
| DeepSeek | 0.10 | 1.892      | 2.069       | 2.009         | 96.5    | 295.9    | 253.1      | True     | 10/10   |
| DeepSeek | 0.15 | 2.112      | 2.245       | 2.188         | 107.7   | 321.1    | 275.7      | True     | 10/10   |
| RO       | 0.01 | 1.093      | 1.520       | 1.535         | 79.8    | 82.1     | 73.7       | True     | 10/10   |
| RO       | 0.05 | 1.410      | 2.228       | 2.219         | 102.9   | 120.3    | 106.5      | True     | 10/10   |
| RO       | 0.10 | 2.040      | 3.356       | 3.306         | 148.9   | 181.2    | 158.7      | True     | 10/10   |
| RO       | 0.15 | 3.084      | 4.889       | 4.788         | 225.1   | 264.0    | 229.8      | True     | 10/10   |

Notes:
- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.
- Negative deltas mean the policy is closer to NS3 than original FlowSim.
- A complete policy row requires at least 10 successful samples.
- Policy summary: `experiments/fault_tolerance/flowsim_256_alltoall_guardrail_w03_pxn085/random_link_failure_summary.csv`
