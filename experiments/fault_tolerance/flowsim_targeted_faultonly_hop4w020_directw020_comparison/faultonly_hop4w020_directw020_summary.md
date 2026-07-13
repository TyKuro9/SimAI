# Targeted FlowSim Fault-Only Correction: Hop4 w0.20 + Direct w0.20

Inputs:

- Fault-only run: `flowsim_256_alltoall_targeted_faultonly_hop4w020_directw020_p01_p05_p10_p15_s3/`
- Baseline-calibrated candidate: `flowsim_256_alltoall_targeted_hop4w025_directw022_p01_p05_p10_p15_s3/`
- Previous policy: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/`
- NS3 reference: `ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix/`

Baseline policy:

- `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25`
- `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22`

Fault-only overrides:

- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.20`
- `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.20`

Scope:

- Topologies: DeepSeek, ROFT, RO
- Rates: 1%, 5%, 10%, 15%
- Samples: 3 per rate
- Result: `36/36` successful samples

## Aggregate Comparison

Negative deltas are improvements relative to the baseline-calibrated candidate.

| Topology | Fault-only failed-JCT MAE | Candidate failed-JCT MAE | Delta vs candidate | Fault-only factor MAE | Candidate factor MAE | Delta vs candidate | Samples |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | 12.59 | 15.51 | -2.92 | 0.110 | 0.128 | -0.018 | 12/12 |
| ROFT | 5.98 | 8.57 | -2.58 | 0.109 | 0.156 | -0.047 | 12/12 |
| RO | 27.93 | 25.43 | +2.50 | 0.622 | 0.679 | -0.057 | 12/12 |

Relative to the previous `w0.3 + pxn0.75` policy:

| Topology | Failed-JCT MAE delta vs previous | Factor MAE delta vs previous |
|---|---:|---:|
| DeepSeek | -103.13 | +0.016 |
| ROFT | -18.37 | +0.032 |
| RO | +19.33 | -0.439 |

## Detail

| Topology | Rate | Fault-only failed JCT | Candidate failed JCT | NS3 failed JCT | Fault-only factor | Candidate factor | NS3 factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | 1% | 60.67 | 65.67 | 58.70 | 1.083 | 1.173 | 1.151 |
| DeepSeek | 5% | 87.33 | 89.00 | 77.40 | 1.560 | 1.589 | 1.518 |
| DeepSeek | 10% | 109.67 | 115.33 | 96.50 | 1.958 | 2.060 | 1.892 |
| DeepSeek | 15% | 133.00 | 132.33 | 107.70 | 2.375 | 2.363 | 2.112 |
| ROFT | 1% | 64.33 | 68.00 | 61.70 | 1.170 | 1.236 | 1.122 |
| ROFT | 5% | 85.00 | 91.00 | 79.30 | 1.545 | 1.655 | 1.442 |
| ROFT | 10% | 106.33 | 106.67 | 101.20 | 1.933 | 1.939 | 1.840 |
| ROFT | 15% | 127.67 | 128.00 | 117.20 | 2.321 | 2.327 | 2.131 |
| RO | 1% | 58.33 | 58.33 | 79.80 | 1.326 | 1.326 | 1.093 |
| RO | 5% | 91.33 | 93.00 | 102.90 | 2.076 | 2.114 | 1.410 |
| RO | 10% | 119.67 | 120.67 | 148.90 | 2.720 | 2.742 | 2.040 |
| RO | 15% | 175.67 | 183.00 | 225.10 | 3.992 | 4.159 | 3.084 |

## Interpretation

- Fault-only correction is directionally useful for DeepSeek and ROFT: it improves both absolute failed JCT and normalized factor versus the baseline-calibrated candidate.
- It does not solve the high-rate tail: DeepSeek 15% and ROFT 15% remain above NS3 in both failed JCT and factor.
- RO remains the guardrail conflict. Fault-only correction lowers RO failed JCT further, which improves factor but worsens absolute JCT.
- A single uniform failed-run speedup is still too blunt. The next correction needs to depend on topology/path class or failure-rate/path-stretch, not only baseline-vs-failed state.

## Next Recommendation

Do not run a full six-topology sweep with `fault hop4=0.20/direct=0.20` yet.

Next useful checks:

1. Add a path-stretch-aware correction, so low-rate and high-rate failed paths can move differently.
2. Keep RO as a hard guardrail: any global failed-run speedup that lowers RO absolute JCT further should be rejected or made topology/path-class-specific.
3. For DeepSeek/ROFT only, test a rate/path-stretch correction on the 1%, 5%, 10%, 15% targeted set before expanding samples.
