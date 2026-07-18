# NS3 Dual-Table Spray: 256-GPU Dense GA=3

## Configuration

- Workload: GPT-7B Dense, world size 256, TP=8, PP=4, DP=8, MBS=1, GA=3, GBS=24.
- Routing policy: `spray_dual_table`, spray width 4.
- Dynamic thresholds: 5,000 ns gap, 4,096 bytes, 500 ns hysteresis.
- PXN disabled; NS3 executed with 8 threads.
- One completed sample per topology. Results are not averaged.

## Results

| Topology | JCT (ms) | vs DeepSeek | Exposed comm (ms) | Logical FCT p50 (us) | p95 (us) | p99 (us) | max (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | 452.354475 | 0.000% | 45.468458 | 4.762 | 4.768 | 188.801 | 3.439862 |
| HPN | 477.553253 | +5.571% | 70.667236 | 4.762 | 4.768 | 188.801 | 9.611074 |
| Zcube | 488.823024 | +8.062% | 81.937007 | 4.762 | 4.768 | 188.801 | 6.912390 |

All three final FCT datasets contain 1,906,688 physical QPs and 1,895,936 logical flows. The p50/p95/p99 values are identical because the distribution is dominated by the same short transfers; JCT, exposed communication, and the far tail distinguish the topologies more clearly.

## FCT Files

- DeepSeek: [`DeepSeek/spray_dual_table/fct.txt`](DeepSeek/spray_dual_table/fct.txt)
- HPN: [`HPN/spray_dual_table/fct.txt`](../dual_table_256_dense_ga3_hpn_fct_recheck_20260715/HPN/spray_dual_table/fct.txt)
- Zcube: [`Zcube/spray_dual_table/fct.txt`](Zcube/spray_dual_table/fct.txt)

The original HPN batch file stopped at 1,906,332 rows because the old FCT-only runner terminated three seconds after JCT while FCT output was still growing. The HPN row above uses a same-configuration recheck that waited for the FCT tail, reached 68/68 collectives, produced the full 1,906,688 rows, reported zero pending callbacks, and exited normally. Its JCT was 1.068% above the first HPN run, showing the run-to-run variation of this single-sample, 8-thread dynamic-routing experiment.
