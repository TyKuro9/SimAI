# FlowSim Fault Tolerance Summary

## Experiment Setup

- Simulator: FlowSim
- Scale: 256 GPUs
- Workload: global all-to-all
- Topologies: Meta, HPN, DeepSeek, Zcube, RO, ROFT
- Fault type: random inter-server link removal
- Fault rates: 1% to 15%, step 1%
- Samples: 10 seeds per fault rate
- Total runs: 6 topologies x 15 rates x 10 seeds = 900
- Result: 900/900 success

Result directory:

`/home/zty/Topo/SimAI_TyKuro9_pxn/experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_chain`

Main CSV files:

- `baseline_jct.csv`
- `random_link_failure_raw.csv`
- `random_link_failure_summary.csv`

## Today Progress

1. Fixed the FlowSim missing-JCT problem under failed topologies.

   Some failed topologies were still connected in a plain graph, but FlowSim does not allow a GPU to be used as an intermediate forwarding node. The previous PXN fallback only supported source-side proxy, so destination-side GPU uplink failures could leave a flow with no valid FlowSim path.

   The FlowSim PXN fallback was extended to support a source/destination proxy chain:

   `src -> src_proxy -> dst_proxy -> dst`

2. Completed the 256-scale FlowSim fault tolerance sweep.

   All 900 samples completed successfully. There were no failed runs, no missing JCT rows, and no empty-route failures after the fix.

3. Produced summary CSVs.

   The key outputs are `baseline_jct.csv`, `random_link_failure_raw.csv`, and `random_link_failure_summary.csv`.

## Baseline JCT

| Topology | Baseline JCT | Eligible inter-server links |
|---|---:|---:|
| Meta | 177 | 512 |
| HPN | 174 | 768 |
| DeepSeek | 143 | 512 |
| Zcube | 32 | 768 |
| RO | 54 | 304 |
| ROFT | 172 | 512 |

## Key JCT Summary

| Topology | Baseline | 1% | 5% | 10% | 15% | 15% degradation |
|---|---:|---:|---:|---:|---:|---:|
| Zcube | 32 | 49.2 | 60.6 | 96.4 | 134.4 | +320.0% |
| RO | 54 | 82.1 | 120.3 | 181.2 | 264.0 | +388.9% |
| DeepSeek | 143 | 173.7 | 246.1 | 295.9 | 321.1 | +124.5% |
| HPN | 174 | 185.4 | 194.5 | 214.3 | 240.6 | +38.3% |
| Meta | 177 | 186.1 | 183.5 | 175.1 | 168.1 | -5.0% |
| ROFT | 172 | 204.8 | 264.5 | 293.8 | 328.3 | +90.9% |

## Main Observations

- Zcube has the lowest absolute JCT across the tested fault rates.
- HPN degrades smoothly as fault rate increases; at 15% fault rate it is about 38.3% slower than baseline.
- Meta is the most unusual result: high fault rates reduce JCT below baseline. This likely reflects FlowSim routing/PXN fallback changing congestion distribution and should be validated against NS3.
- RO and Zcube have low baseline JCT, but large relative degradation under high fault rates.
- ROFT shows poor high-fault-rate behavior in this FlowSim run; at 15% fault rate it reaches the largest JCT among the six topologies.

## Full CSV-Derived Summary

The table below is derived from `random_link_failure_raw.csv`. Each row aggregates 10 successful samples.

| Topology | Fault rate | Samples | Success | JCT mean | JCT std | Degradation mean |
|---|---:|---:|---:|---:|---:|---:|
| Meta | 1% | 10 | 10 | 186.1 | 1.6 | +5.1% |
| Meta | 2% | 10 | 10 | 186.1 | 3.1 | +5.1% |
| Meta | 3% | 10 | 10 | 185.4 | 5.5 | +4.7% |
| Meta | 4% | 10 | 10 | 182.1 | 7.0 | +2.9% |
| Meta | 5% | 10 | 10 | 183.5 | 5.2 | +3.7% |
| Meta | 6% | 10 | 10 | 181.8 | 4.5 | +2.7% |
| Meta | 7% | 10 | 10 | 179.1 | 2.4 | +1.2% |
| Meta | 8% | 10 | 10 | 177.3 | 3.3 | +0.2% |
| Meta | 9% | 10 | 10 | 177.5 | 3.7 | +0.3% |
| Meta | 10% | 10 | 10 | 175.1 | 5.0 | -1.1% |
| Meta | 11% | 10 | 10 | 173.8 | 5.5 | -1.8% |
| Meta | 12% | 10 | 10 | 172.2 | 3.3 | -2.7% |
| Meta | 13% | 10 | 10 | 171.8 | 4.1 | -2.9% |
| Meta | 14% | 10 | 10 | 171.2 | 4.5 | -3.3% |
| Meta | 15% | 10 | 10 | 168.1 | 6.1 | -5.0% |
| HPN | 1% | 10 | 10 | 185.4 | 4.2 | +6.6% |
| HPN | 2% | 10 | 10 | 190.4 | 7.4 | +9.4% |
| HPN | 3% | 10 | 10 | 191.2 | 11.1 | +9.9% |
| HPN | 4% | 10 | 10 | 192.2 | 10.5 | +10.5% |
| HPN | 5% | 10 | 10 | 194.5 | 10.2 | +11.8% |
| HPN | 6% | 10 | 10 | 197.9 | 12.3 | +13.7% |
| HPN | 7% | 10 | 10 | 200.1 | 8.6 | +15.0% |
| HPN | 8% | 10 | 10 | 200.6 | 11.6 | +15.3% |
| HPN | 9% | 10 | 10 | 200.9 | 13.3 | +15.5% |
| HPN | 10% | 10 | 10 | 214.3 | 15.1 | +23.2% |
| HPN | 11% | 10 | 10 | 221.5 | 19.1 | +27.3% |
| HPN | 12% | 10 | 10 | 229.1 | 22.2 | +31.7% |
| HPN | 13% | 10 | 10 | 233.6 | 19.8 | +34.3% |
| HPN | 14% | 10 | 10 | 237.8 | 27.4 | +36.7% |
| HPN | 15% | 10 | 10 | 240.6 | 25.3 | +38.3% |
| DeepSeek | 1% | 10 | 10 | 173.7 | 9.1 | +21.5% |
| DeepSeek | 2% | 10 | 10 | 195.3 | 13.3 | +36.6% |
| DeepSeek | 3% | 10 | 10 | 214.4 | 24.8 | +49.9% |
| DeepSeek | 4% | 10 | 10 | 232.2 | 21.5 | +62.4% |
| DeepSeek | 5% | 10 | 10 | 246.1 | 29.0 | +72.1% |
| DeepSeek | 6% | 10 | 10 | 257.7 | 35.1 | +80.2% |
| DeepSeek | 7% | 10 | 10 | 279.3 | 46.5 | +95.3% |
| DeepSeek | 8% | 10 | 10 | 285.5 | 46.8 | +99.7% |
| DeepSeek | 9% | 10 | 10 | 284.7 | 56.1 | +99.1% |
| DeepSeek | 10% | 10 | 10 | 295.9 | 56.1 | +106.9% |
| DeepSeek | 11% | 10 | 10 | 304.0 | 50.1 | +112.6% |
| DeepSeek | 12% | 10 | 10 | 298.1 | 61.1 | +108.5% |
| DeepSeek | 13% | 10 | 10 | 302.6 | 65.5 | +111.6% |
| DeepSeek | 14% | 10 | 10 | 310.6 | 67.0 | +117.2% |
| DeepSeek | 15% | 10 | 10 | 321.1 | 73.8 | +124.5% |
| Zcube | 1% | 10 | 10 | 49.2 | 0.6 | +53.8% |
| Zcube | 2% | 10 | 10 | 50.8 | 4.1 | +58.7% |
| Zcube | 3% | 10 | 10 | 55.5 | 14.7 | +73.4% |
| Zcube | 4% | 10 | 10 | 58.5 | 14.7 | +82.8% |
| Zcube | 5% | 10 | 10 | 60.6 | 13.7 | +89.4% |
| Zcube | 6% | 10 | 10 | 65.3 | 14.6 | +104.1% |
| Zcube | 7% | 10 | 10 | 74.4 | 15.3 | +132.5% |
| Zcube | 8% | 10 | 10 | 78.5 | 18.4 | +145.3% |
| Zcube | 9% | 10 | 10 | 86.2 | 17.4 | +169.4% |
| Zcube | 10% | 10 | 10 | 96.4 | 16.0 | +201.3% |
| Zcube | 11% | 10 | 10 | 102.8 | 12.8 | +221.2% |
| Zcube | 12% | 10 | 10 | 105.4 | 13.1 | +229.4% |
| Zcube | 13% | 10 | 10 | 110.0 | 16.1 | +243.8% |
| Zcube | 14% | 10 | 10 | 126.1 | 19.3 | +294.1% |
| Zcube | 15% | 10 | 10 | 134.4 | 24.3 | +320.0% |
| RO | 1% | 10 | 10 | 82.1 | 26.9 | +52.0% |
| RO | 2% | 10 | 10 | 99.2 | 28.7 | +83.7% |
| RO | 3% | 10 | 10 | 113.7 | 36.0 | +110.6% |
| RO | 4% | 10 | 10 | 115.8 | 34.2 | +114.4% |
| RO | 5% | 10 | 10 | 120.3 | 29.4 | +122.8% |
| RO | 6% | 10 | 10 | 132.2 | 25.1 | +144.8% |
| RO | 7% | 10 | 10 | 138.8 | 35.2 | +157.0% |
| RO | 8% | 10 | 10 | 145.0 | 34.6 | +168.5% |
| RO | 9% | 10 | 10 | 155.7 | 34.1 | +188.3% |
| RO | 10% | 10 | 10 | 181.2 | 43.2 | +235.6% |
| RO | 11% | 10 | 10 | 182.5 | 49.3 | +238.0% |
| RO | 12% | 10 | 10 | 209.1 | 82.0 | +287.2% |
| RO | 13% | 10 | 10 | 232.3 | 93.5 | +330.2% |
| RO | 14% | 10 | 10 | 236.5 | 95.8 | +338.0% |
| RO | 15% | 10 | 10 | 264.0 | 101.5 | +388.9% |
| ROFT | 1% | 10 | 10 | 204.8 | 14.2 | +19.1% |
| ROFT | 2% | 10 | 10 | 221.4 | 19.6 | +28.7% |
| ROFT | 3% | 10 | 10 | 233.2 | 27.7 | +35.6% |
| ROFT | 4% | 10 | 10 | 245.9 | 43.5 | +43.0% |
| ROFT | 5% | 10 | 10 | 264.5 | 34.4 | +53.8% |
| ROFT | 6% | 10 | 10 | 270.1 | 37.8 | +57.0% |
| ROFT | 7% | 10 | 10 | 283.7 | 46.2 | +64.9% |
| ROFT | 8% | 10 | 10 | 286.1 | 49.5 | +66.3% |
| ROFT | 9% | 10 | 10 | 289.4 | 49.9 | +68.3% |
| ROFT | 10% | 10 | 10 | 293.8 | 46.4 | +70.8% |
| ROFT | 11% | 10 | 10 | 302.6 | 44.1 | +75.9% |
| ROFT | 12% | 10 | 10 | 306.7 | 37.8 | +78.3% |
| ROFT | 13% | 10 | 10 | 307.9 | 40.3 | +79.0% |
| ROFT | 14% | 10 | 10 | 318.8 | 43.3 | +85.3% |
| ROFT | 15% | 10 | 10 | 328.3 | 57.5 | +90.9% |

## Next Steps

1. Investigate why Meta improves at higher fault rates in FlowSim.
2. Compare the same failed-topology samples in NS3.
3. Check whether FlowSim PXN proxy-chain routing changes congestion distribution too aggressively compared with packet-level simulation.
