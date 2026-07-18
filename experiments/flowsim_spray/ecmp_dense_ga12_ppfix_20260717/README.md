# FlowSim ECMP: GPT-22B at 256 GPUs

## Configuration

- Workload SHA-256: `29e8082dced64cdabea6e9da8e9506acc02e00898f485142216dbcb769ed746b`
- Shape: world size 256, TP=8, PP=4, EP=1, GA=12
- FlowSim binary SHA-256: `07bf4cb1f172e3b4c7f6650850c5af2c6a28087faaed609970028fb229b56a17`
- Routing: `ecmp`, implemented as per-flow `per_hop_hrw`
- PXN and NVLS: off
- Send latency: 3 ns
- Threads per run: 4
- The corrected DP=8 grouping is enabled.

## Results

| Rank | Topology | ECMP JCT (us) | Relative to best | Exposed communication (us) |
| ---: | --- | ---: | ---: | ---: |
| 1 | Zcube | 2,222,176.511 | 0.000000% | 261,687.488 |
| 2 | HPN | 2,222,220.881 | 0.001997% | 261,731.858 |
| 3 | DeepSeek | 2,233,845.612 | 0.525120% | 273,356.589 |
| 4 | ROFT | 2,233,895.812 | 0.527379% | 273,406.789 |
| 5 | Meta | 2,273,444.385 | 2.307102% | 312,955.362 |
| 6 | RO | 2,417,797.212 | 8.803113% | 457,308.189 |

All six runs exited with status zero. Zcube and HPN differ by only `44.370 us`
(`0.001997%`), so they should be treated as effectively tied.

## How Zcube ECMP Selects a Path

The 256 GPUs form a logical 16 by 16 grid. GPU `g` has row
`floor(g / 16)` and column `g % 16`, and connects to both its row switch and
its column switch. The 16 row switches and 16 column switches form a complete
bipartite graph.

FlowSim ECMP first keeps only next hops that reduce the unweighted shortest
path distance by one. It then computes a highest-random-weight score from the
flow identity, endpoints, current node, and candidate next node, selecting the
candidate with the highest score. A flow keeps that path for its lifetime.

- Same row: one direct two-hop fabric path through the row switch.
- Same column: one direct two-hop fabric path through the column switch.
- Different row and column: two equal three-hop paths. HRW chooses between
  source-row to destination-column and source-column to destination-row.
- Same chassis: the local NVSwitch path is preferred over the fabric.

For this workload, DP groups are `[i, i+32, i+64, ...]`. Adding 32 preserves
`rank % 16`, so every DP peer pair is in the same Zcube column. A corrected
64 MiB DP probe confirms that all 256 unique pairs are same-column pairs and
all 1,792 ECMP transfers use a two-hop path. There is no equal-cost path choice
for these dominant DP transfers.

For example, `0 -> 32` uses the unique shortest route
`GPU 0 -> column switch 304 -> GPU 32`. A cross-dimension pair such as
`0 -> 33` would instead have two equal choices:
`0 -> row switch 288 -> column switch 305 -> 33`, or
`0 -> column switch 304 -> row switch 290 -> 33`.

This mapping affinity, rather than unusually successful ECMP hashing, is the
main reason Zcube ranks well under ECMP. The ECMP DP probe still takes
`2,489.732 us`, versus `1,635.438 us` with Adaptive Spray, because ECMP sends
the whole flow through one 200 Gbps path while Spray can divide it across
multiple paths.

### Why 200 Gbps Can Beat 400 Gbps in the Full Workload

The link itself is not faster. Isolated collectives preserve the expected
ordering:

| Topology | 1.777 GB AllGather | 3.555 GB ReduceScatter |
| --- | ---: | ---: |
| Zcube 200G | 65.232 ms | 130.435 ms |
| DeepSeek 400G | 41.947 ms | 83.864 ms |

The full workload overlaps these two collectives. Zcube finishes their
critical section in `195.667 ms`, equal to the isolated sum. DeepSeek would
need `125.810 ms` from the isolated sum, but contention increases it to
`206.371 ms`.

A bottleneck trace of the minimal overlapping workload explains the reversal:

| Metric | Zcube | DeepSeek |
| --- | ---: | ---: |
| Completed flow records | 3,584 | 3,584 |
| Two-hop records | 3,584 | 1,792 |
| Four-hop records | 0 | 1,792 |
| Mean assigned rate | 25.000 B/ns | 36.265 B/ns |
| Minimum assigned rate | 25.000 B/ns | 8.333 B/ns |
| Maximum active chunks on a bottleneck | 1 | 6 |

Zcube spreads the same-column rings symmetrically over direct links, so every
critical flow receives a stable 200 Gbps. DeepSeek has the higher average
rate, but half of its routes traverse the upper fabric. Overlapping ECMP flows
can share one bottleneck six ways, reducing the slowest flow to about
66.7 Gbps. A collective waits for its slowest rank, so this tail rate controls
JCT and can outweigh the 400 Gbps access-link speed.

## ECMP vs Adaptive Spray

| Topology | ECMP JCT (us) | Adaptive Spray JCT (us) | ECMP penalty |
| --- | ---: | ---: | ---: |
| Zcube | 2,222,176.511 | 2,156,854.173 | +3.028593% |
| HPN | 2,222,220.881 | 2,124,399.237 | +4.604673% |
| DeepSeek | 2,233,845.612 | 2,124,399.237 | +5.151874% |
| ROFT | 2,233,895.812 | 2,124,399.237 | +5.154237% |
| Meta | 2,273,444.385 | 2,124,385.237 | +7.016578% |
| RO | 2,417,797.212 | 2,260,464.495 | +6.960194% |

Adaptive Spray is faster for every topology in this FlowSim workload. ECMP
binds each flow to one equal-cost path, while Adaptive Spray divides it over
up to four selected paths and reacts to predicted path completion time. The
benefit is largest for Meta and RO, where a single ECMP path exposes more
communication on the critical path.

The ECMP ranking also removes the tiny Meta lead seen with Adaptive Spray:
Meta is 2.31% behind the ECMP best. This confirms that the earlier Meta result
was not a general topology advantage. It was an effective tie produced under
the adaptive multi-path abstraction.

These comparisons are FlowSim ECMP versus FlowSim Adaptive Spray. Existing
NS-3 data uses `spray_adaptive`, so it should not be presented as an NS-3 ECMP
cross-check.
