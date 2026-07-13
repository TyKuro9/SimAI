# w0.3 cross-rail full partial FlowSim Policy Sweep Comparison

## Topology Aggregate

| Topology | Rates | Orig factor MAE | Policy factor MAE | Factor delta | Orig JCT MAE | Policy JCT MAE | JCT delta |
| -------- | ----- | --------------- | ----------------- | ------------ | ------------ | -------------- | --------- |
| Meta     | 4     | 0.399           | 0.307             | -0.092       | 114.2        | 11.1           | -103.1    |

## Rate Detail

| Topology | Rate | NS3 factor | Orig factor | Policy factor | NS3 JCT | Orig JCT | Policy JCT | Success |
| -------- | ---- | ---------- | ----------- | ------------- | ------- | -------- | ---------- | ------- |
| Meta     | 0.01 | 1.231      | 1.051       | 1.133         | 60.3    | 186.1    | 81.6       | 10/10   |
| Meta     | 0.02 | 1.390      | 1.051       | 1.133         | 68.1    | 186.1    | 81.6       | 10/10   |
| Meta     | 0.03 | 1.541      | 1.047       | 1.139         | 75.5    | 185.4    | 82.0       | 10/10   |
| Meta     | 0.04 | 1.614      | 1.029       | 1.141         | 79.1    | 182.1    | 82.2       | 6/6     |

Notes:
- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.
- Negative deltas mean the policy is closer to NS3 than original FlowSim.
- Policy summary: `experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full/random_link_failure_summary.csv`
