# guardrail w0.3 + PXN same-rail w0.75 vs w0.3 FlowSim Policy Sweep Comparison

## Topology Aggregate

| Topology | Rates | Orig factor MAE | Policy factor MAE | Factor delta | Orig JCT MAE | Policy JCT MAE | JCT delta |
| -------- | ----- | --------------- | ----------------- | ------------ | ------------ | -------------- | --------- |
| ROFT     | 4     | 0.145           | 0.077             | -0.068       | 29.3         | 24.3           | -4.9      |
| DeepSeek | 4     | 0.144           | 0.093             | -0.051       | 174.1        | 115.7          | -58.4     |
| Zcube    | 4     | 0.779           | 0.779             | 0.000        | 5.6          | 5.6            | 0.0       |
| RO       | 4     | 1.092           | 1.061             | -0.031       | 22.7         | 8.6            | -14.1     |

## Rate Detail

| Topology | Rate | NS3 factor | Orig factor | Policy factor | NS3 JCT | Orig JCT | Policy JCT | Complete | Success |
| -------- | ---- | ---------- | ----------- | ------------- | ------- | -------- | ---------- | -------- | ------- |
| ROFT     | 0.01 | 1.122      | 1.249       | 1.243         | 61.7    | 83.7     | 83.3       | True     | 10/10   |
| ROFT     | 0.05 | 1.442      | 1.699       | 1.606         | 79.3    | 113.8    | 107.6      | True     | 10/10   |
| ROFT     | 0.10 | 1.840      | 1.934       | 1.849         | 101.2   | 129.6    | 123.9      | True     | 10/10   |
| ROFT     | 0.15 | 2.131      | 2.231       | 2.119         | 117.2   | 149.5    | 142.0      | True     | 10/10   |
| DeepSeek | 0.01 | 1.151      | 1.215       | 1.212         | 58.7    | 173.7    | 138.2      | True     | 10/10   |
| DeepSeek | 0.05 | 1.518      | 1.721       | 1.689         | 77.4    | 246.1    | 192.6      | True     | 10/10   |
| DeepSeek | 0.10 | 1.892      | 2.069       | 1.998         | 96.5    | 295.9    | 227.8      | True     | 10/10   |
| DeepSeek | 0.15 | 2.112      | 2.245       | 2.146         | 107.7   | 321.1    | 244.6      | True     | 10/10   |
| Zcube    | 0.01 | 1.145      | 1.538       | 1.538         | 53.8    | 49.2     | 49.2       | True     | 10/10   |
| Zcube    | 0.05 | 1.377      | 1.900       | 1.900         | 64.7    | 60.8     | 60.8       | True     | 10/10   |
| Zcube    | 0.10 | 1.732      | 2.716       | 2.716         | 81.4    | 86.9     | 86.9       | True     | 10/10   |
| Zcube    | 0.15 | 2.026      | 3.241       | 3.241         | 95.2    | 103.7    | 103.7      | True     | 10/10   |
| RO       | 0.01 | 1.093      | 1.520       | 1.593         | 79.8    | 82.1     | 70.1       | True     | 10/10   |
| RO       | 0.05 | 1.410      | 2.228       | 2.282         | 102.9   | 120.3    | 100.4      | True     | 10/10   |
| RO       | 0.10 | 2.040      | 3.356       | 3.298         | 148.9   | 181.2    | 145.1      | True     | 10/10   |
| RO       | 0.15 | 3.084      | 4.889       | 4.698         | 225.1   | 264.0    | 206.7      | True     | 10/10   |

Notes:
- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.
- Negative deltas mean the policy is closer to NS3 than original FlowSim.
- A complete policy row requires at least 10 successful samples.
- Policy summary: `experiments/fault_tolerance/flowsim_256_alltoall_guardrail_w03_pxn075/random_link_failure_summary.csv`
