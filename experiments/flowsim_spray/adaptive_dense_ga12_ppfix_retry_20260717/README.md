# FlowSim Adaptive Spray: PP/DP Grouping Fix

## Conclusion

The previous topology ordering was materially biased by an incorrect workload
mapping. FlowSim hard-coded `PP_size=1`, so this world-size 256, TP=8, PP=4
workload used DP=32 instead of DP=8. The corrected grouping changes Ring
AllGather from 31 dependent waves to 7 and removes the false near-best RO
result.

Meta is still first in corrected FlowSim, but it leads HPN, DeepSeek, and ROFT
by only `14 us` (`0.000659%`). That is an effective tie, not evidence that Meta
has higher real throughput.

## Configuration

- Workload SHA-256: `29e8082dced64cdabea6e9da8e9506acc02e00898f485142216dbcb769ed746b`
- Shape: world size 256, TP=8, PP=4, EP=1, GA=12
- FlowSim binary SHA-256: `07bf4cb1f172e3b4c7f6650850c5af2c6a28087faaed609970028fb229b56a17`
- Routing: `spray_adaptive`, width 4, path pool 16, max extra hops 2
- PXN and NVLS: off
- Send latency: 3 ns
- Threads per run: 4
- All topology and workload files came from this spray worktree.

## Corrected Results

| Rank | Topology | FlowSim JCT (us) | Relative to best | Exposed communication (us) |
| ---: | --- | ---: | ---: | ---: |
| 1 | Meta | 2,124,385.237 | 0.000000% | 163,896.214 |
| 2 | HPN | 2,124,399.237 | 0.000659% | 163,910.214 |
| 2 | DeepSeek | 2,124,399.237 | 0.000659% | 163,910.214 |
| 2 | ROFT | 2,124,399.237 | 0.000659% | 163,910.214 |
| 5 | Zcube | 2,156,854.173 | 1.528392% | 196,365.150 |
| 6 | RO | 2,260,464.495 | 6.405583% | 299,975.472 |

All six runs exited with status zero. Compute time is identical at
`1,960,489.023 us`; the differences above come from exposed communication.

## NS-3 Cross-check

| Topology | FlowSim JCT (us) | NS-3 JCT (us) | Difference |
| --- | ---: | ---: | ---: |
| Meta | 2,124,385.237 | 2,141,931.794 | -0.819193% |
| HPN | 2,124,399.237 | 2,151,332.432 | -1.251931% |
| DeepSeek | 2,124,399.237 | 2,124,044.494 | +0.016701% |
| ROFT | 2,124,399.237 | 2,118,948.317 | +0.257246% |
| Zcube | 2,156,854.173 | 2,119,411.632 | +1.766648% |
| RO | 2,260,464.495 | 2,424,428.772 | -6.763007% |

Across the six topologies, the fix improves FlowSim-vs-NS-3 MAE from
`77,386.426 us` to `41,948.706 us` (45.793%) and MAPE from `3.362493%` to
`1.812454%` (46.098%). DeepSeek now matches NS-3 to `0.0167%`.

## Isolation Check

The corrected 64 MiB DP AllGather trace contains exactly 7,168 stripe records
per topology: `256 ranks * 7 Ring steps * 4 stripes`. Before the fix it had
31,744 records: `256 * 31 * 4`.

| Topology | Corrected FlowSim probe JCT (us) | NS-3 probe JCT (us) |
| --- | ---: | ---: |
| Meta | 1,265.971 | n/a |
| HPN | 1,272.971 | n/a |
| DeepSeek | 1,272.971 | 1,233.754 |
| ROFT | 1,272.971 | 1,233.576 |
| Zcube | 1,635.438 | 1,231.981 |
| RO | 2,837.469 | n/a |

## Remaining Mismatch

The workload-group bug explains much of the wrong ordering, but not all of it.
FlowSim still treats Meta, HPN, DeepSeek, and ROFT as effectively equal, while
NS-3 separates them by queueing and packet-level effects. Zcube remains 1.77%
slow and RO remains 6.76% fast versus NS-3. The isolation probe makes the
Zcube discrepancy especially visible, so the next model work should target
parallel-link aggregation and adaptive path contention rather than adding a
ranking correction factor.

The old claim that Meta won because a logical flow waited on a longer-hop
stripe was incorrect. Per-`src,dst` trace grouping found no mixed-hop stripe
groups in the relevant non-Zcube topologies; the old 31-wave pattern came from
the PP/DP grouping bug itself.
