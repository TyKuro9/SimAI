# Targeted FlowSim Fault Sweep: Hop4 w0.25 + Direct w0.22

Inputs:

- Candidate run: `flowsim_256_alltoall_targeted_hop4w025_directw022_p01_p05_p10_p15_s3/`
- Previous policy: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/`
- NS3 reference: `ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix/`

Candidate policy:

- `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25`
- `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22`

Scope:

- Topologies: DeepSeek, ROFT, RO
- Rates: 1%, 5%, 10%, 15%
- Samples: 3 per rate
- Result: `36/36` successful samples

## Aggregate Comparison

Negative deltas are improvements relative to the previous `w0.3 + pxn0.75` FlowSim policy.

| Topology | Candidate failed-JCT MAE | Previous failed-JCT MAE | Delta | Candidate factor MAE | Previous factor MAE | Delta | Samples |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | 15.51 | 115.73 | -100.22 | 0.128 | 0.093 | +0.035 | 12/12 |
| ROFT | 8.57 | 24.35 | -15.78 | 0.156 | 0.077 | +0.079 | 12/12 |
| RO | 25.43 | 8.60 | +16.83 | 0.679 | 1.061 | -0.382 | 12/12 |

## Detail

| Topology | Rate | Candidate failed JCT | Previous failed JCT | NS3 failed JCT | Candidate factor | Previous factor | NS3 factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | 1% | 65.67 | 138.20 | 58.70 | 1.173 | 1.212 | 1.151 |
| DeepSeek | 5% | 89.00 | 192.60 | 77.40 | 1.589 | 1.689 | 1.518 |
| DeepSeek | 10% | 115.33 | 227.80 | 96.50 | 2.060 | 1.998 | 1.892 |
| DeepSeek | 15% | 132.33 | 244.60 | 107.70 | 2.363 | 2.146 | 2.112 |
| ROFT | 1% | 68.00 | 83.30 | 61.70 | 1.236 | 1.243 | 1.122 |
| ROFT | 5% | 91.00 | 107.60 | 79.30 | 1.655 | 1.606 | 1.442 |
| ROFT | 10% | 106.67 | 123.90 | 101.20 | 1.939 | 1.849 | 1.840 |
| ROFT | 15% | 128.00 | 142.00 | 117.20 | 2.327 | 2.119 | 2.131 |
| RO | 1% | 58.33 | 70.10 | 79.80 | 1.326 | 1.593 | 1.093 |
| RO | 5% | 93.00 | 100.40 | 102.90 | 2.114 | 2.282 | 1.410 |
| RO | 10% | 120.67 | 145.10 | 148.90 | 2.742 | 3.298 | 2.040 |
| RO | 15% | 183.00 | 206.70 | 225.10 | 4.159 | 4.698 | 3.084 |

## Interpretation

- The candidate is excellent for absolute baseline/JCT alignment on DeepSeek and ROFT, but it is not a drop-in replacement for the previous fault policy.
- DeepSeek and ROFT factor curves become worse because the baseline is much lower while failed JCT does not shrink proportionally at higher fault rates.
- RO moves in the opposite direction: its normalized factor improves, but absolute JCT is now too low versus NS3 because the RO baseline remains far below NS3.
- This confirms the baseline and fault-response problems should be separated. Use hop4/direct knobs to study baseline calibration, then add a fault-response correction only if normalized curves remain acceptable.

## Next Recommendation

Do not run a full six-topology 10-sample sweep with this combined candidate yet.

Next, run one of these smaller checks:

1. A 10-sample targeted rerun for DeepSeek and ROFT only, to reduce sample noise on absolute JCT.
2. A two-dimensional correction test: keep the new baseline knobs, then introduce a separate fault-response multiplier that only activates under failed topology conditions.
3. A per-topology reporting split: baseline-calibrated absolute JCT view and original normalized fault-response view, rather than forcing one policy to optimize both.
