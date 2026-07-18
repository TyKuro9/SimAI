# NS3 DP FCT Comparison

Workload: GPT-22B Dense, 1024 GPUs, GA=6. PXN is disabled.
Each logical DP flow groups physical spray stripes by `(flow_id, original_src, original_dst)`; its FCT is the maximum stripe FCT.
The parser validates every logged pair against the simulator's DP grouping rule.

| Policy | Topology | JCT (us) | DP flows | FCT p50 (us) | p90 | p95 | p99 | max | Stripes p50 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| spray_dual_table | Zcube | 1143126.484 | 63488 | 1697.510 | 2262.278 | 2262.278 | 2262.278 | 2262.278 | 4.0 |
| spray_dual_table | DeepSeek | 1142526.543 | 63488 | 1688.408 | 2251.264 | 2251.267 | 2251.273 | 2251.280 | 4.0 |
| spray_dual_table | ROFT | 1142526.541 | 63488 | 1688.408 | 2251.264 | 2251.267 | 2251.273 | 2251.280 | 4.0 |
| spray_adaptive | Zcube | 1143074.296 | 63488 | 1696.671 | 2261.436 | 2261.438 | 2261.440 | 2261.442 | 4.0 |
| spray_adaptive | DeepSeek | 1142527.196 | 63488 | 1688.580 | 2251.266 | 2251.278 | 2251.448 | 2251.630 | 4.0 |
| spray_adaptive | ROFT | 1142527.392 | 63488 | 1688.624 | 2251.266 | 2251.278 | 2251.448 | 2251.627 | 4.0 |
