# w0.3 + PXN same-rail w0.75 FlowSim Policy Sweep Comparison

## Topology Aggregate

| Topology | Rates | Orig factor MAE | Policy factor MAE | Factor delta | Orig JCT MAE | Policy JCT MAE | JCT delta |
| -------- | ----- | --------------- | ----------------- | ------------ | ------------ | -------------- | --------- |
| HPN      | 5     | 0.220           | 0.201             | -0.019       | 128.9        | 10.6           | -118.3    |
| Meta     | 15    | 0.845           | 0.540             | -0.305       | 87.4         | 3.9            | -83.5     |

## Rate Detail

| Topology | Rate | NS3 factor | Orig factor | Policy factor | NS3 JCT | Orig JCT | Policy JCT | Complete | Success |
| -------- | ---- | ---------- | ----------- | ------------- | ------- | -------- | ---------- | -------- | ------- |
| HPN      | 0.01 | 1.181      | 1.066       | 1.068         | 55.5    | 185.4    | 69.4       | True     | 10/10   |
| HPN      | 0.02 | 1.277      | 1.094       | 1.092         | 60.0    | 190.4    | 71.0       | True     | 10/10   |
| HPN      | 0.03 | 1.370      | 1.099       | 1.123         | 64.4    | 191.2    | 73.0       | True     | 10/10   |
| HPN      | 0.04 | 1.372      | 1.105       | 1.132         | 64.5    | 192.2    | 73.6       | True     | 10/10   |
| HPN      | 0.05 | 1.379      | 1.118       | 1.158         | 64.8    | 194.5    | 75.3       | True     | 10/10   |
| Meta     | 0.01 | 1.231      | 1.051       | 1.087         | 60.3    | 186.1    | 78.3       | True     | 10/10   |
| Meta     | 0.02 | 1.390      | 1.051       | 1.090         | 68.1    | 186.1    | 78.5       | True     | 10/10   |
| Meta     | 0.03 | 1.541      | 1.047       | 1.110         | 75.5    | 185.4    | 79.9       | True     | 10/10   |
| Meta     | 0.04 | 1.614      | 1.029       | 1.128         | 79.1    | 182.1    | 81.2       | True     | 10/10   |
| Meta     | 0.05 | 1.612      | 1.037       | 1.107         | 79.0    | 183.5    | 79.7       | True     | 10/10   |
| Meta     | 0.06 | 1.763      | 1.027       | 1.207         | 86.4    | 181.8    | 86.9       | True     | 10/10   |
| Meta     | 0.07 | 1.814      | 1.012       | 1.231         | 88.9    | 179.1    | 88.6       | True     | 10/10   |
| Meta     | 0.08 | 1.814      | 1.002       | 1.222         | 88.9    | 177.3    | 88.0       | True     | 10/10   |
| Meta     | 0.09 | 1.978      | 1.003       | 1.388         | 96.9    | 177.5    | 99.9       | True     | 10/10   |
| Meta     | 0.10 | 2.006      | 0.989       | 1.393         | 98.3    | 175.1    | 100.3      | True     | 10/10   |
| Meta     | 0.11 | 2.092      | 0.982       | 1.453         | 102.5   | 173.8    | 104.6      | True     | 10/10   |
| Meta     | 0.12 | 2.120      | 0.973       | 1.489         | 103.9   | 172.2    | 107.2      | True     | 10/10   |
| Meta     | 0.13 | 2.216      | 0.971       | 1.544         | 108.6   | 171.8    | 111.2      | True     | 10/10   |
| Meta     | 0.14 | 2.245      | 0.967       | 1.574         | 110.0   | 171.2    | 113.3      | True     | 10/10   |
| Meta     | 0.15 | 2.322      | 0.950       | 1.640         | 113.8   | 168.1    | 118.1      | True     | 10/10   |

Notes:
- Factor is `failed_jct_mean / normal_jct_mean` for each simulator or policy run.
- Negative deltas mean the policy is closer to NS3 than original FlowSim.
- A complete policy row requires at least 10 successful samples.
- Policy summary: `experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/random_link_failure_summary.csv`
