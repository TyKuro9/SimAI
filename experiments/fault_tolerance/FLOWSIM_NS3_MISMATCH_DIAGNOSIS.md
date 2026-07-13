# FlowSim vs NS3 Fault-Tolerance Mismatch Diagnosis

Date: 2026-07-03

Scope:
- Workload: 256-GPU synthetic all-to-all, 1 MiB.
- Fault model: random inter-server link failure, 1%-15%, 10 seeds per rate.
- NS3 result source: `ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix`.
- FlowSim result source: `flowsim_256_alltoall_p01_p15_s10_chain`.

## Current Evidence

- Joined samples: 900/900.
- FlowSim and NS3 failed link sets match exactly for every topology/rate/seed.
- The previous graph-level `path_stretch` metric allowed GPUs as transit nodes. This is useful for PXN-capable reachability, but it is not the same as direct network routing.
- A new direct-route estimator disallows intermediate GPU transit, matching `RoutingFramework::FindPath`.
- The estimator reproduces FlowSim log PXN split ratios exactly:
  - `max_abs_estimated_pxn_split_ratio_error = 0.0`.

## Main Pattern

At 15% link failure:

| Topology | FlowSim factor | NS3 factor | NS3 - FlowSim |
|---|---:|---:|---:|
| RO | 4.889 | 3.084 | -1.805 |
| ZCube | 4.200 | 2.026 | -2.174 |
| Meta | 0.950 | 2.322 | +1.373 |

Mean over all 1%-15% samples:

| Topology | FlowSim factor | NS3 factor | NS3 - FlowSim |
|---|---:|---:|---:|
| RO | 2.973 | 1.870 | -1.103 |
| ZCube | 2.613 | 1.571 | -1.041 |
| Meta | 1.006 | 1.851 | +0.845 |

## Direct Route / PXN Evidence

At selected rates:

| Topology | Rate | PXN split ratio | Direct-route connectivity | FlowSim factor | NS3 factor |
|---|---:|---:|---:|---:|---:|
| RO | 1% | 1.000 | 0.146 | 1.520 | 1.093 |
| RO | 15% | 1.000 | 0.113 | 4.889 | 3.084 |
| ZCube | 1% | 0.000 | 1.000 | 1.538 | 1.145 |
| ZCube | 15% | 0.052 | 0.949 | 4.200 | 2.026 |
| Meta | 1% | 0.021 | 0.980 | 1.051 | 1.231 |
| Meta | 15% | 0.290 | 0.718 | 0.950 | 2.322 |

Correlations with estimated PXN split ratio:

| Topology | Corr(FlowSim factor, split ratio) | Corr(NS3 factor, split ratio) | Corr(delta, split ratio) |
|---|---:|---:|---:|
| ZCube | +0.823 | +0.633 | -0.751 |
| Meta | -0.725 | +0.873 | +0.886 |

Interpretation:
- For RO, direct cross-rail routing is unavailable by construction, so fallback PXN is always used for cross-rail traffic.
- For ZCube, only a small fraction of cross-rail pairs lose direct routes at 15%, but FlowSim slowdown grows sharply. FlowSim appears highly sensitive to a small number of PXN-split routes and route/path-stretch changes.
- For Meta, many cross-rail pairs lose direct routes and switch to PXN under fault, but FlowSim does not slow down. NS3 does. This is the strongest mismatch and likely points to FlowSim underpricing packet-level congestion/PFC effects for Meta rerouting.

## Code Path Notes

FlowSim:
- `FlowSimNetWork::sim_send` builds a PXN plan when `AS_PXN_POLICY=fallback` and `flowsim_has_direct_route(src, dst)` is false.
- `flowsim_has_direct_route` checks `RoutingFramework::GetPairBandwidth(src, dst) > 0`.
- `RoutingFramework::FindPath` disallows intermediate host/GPU nodes, so direct route availability differs from the earlier generic graph BFS metric.
- `FlowSim::Send` uses `RoutingFramework::GetFlowSimPathByNodeIds(src, dst)` to obtain one path per GPU pair and then applies max-min link sharing in `Topology::update_link_states`.

NS3:
- NS3 includes packet queues, PFC pause/resume, and dynamic transmission behavior.
- The repaired NS3 PFC resume path now completes all 900 samples.

## Current Hypotheses

1. RO/ZCube: FlowSim is more pessimistic because PXN split and route loss are modeled as serial chained legs with max-min sharing over active chunks. NS3 still overlaps packet-level progress and may distribute congestion differently.
2. Meta: FlowSim is too optimistic because its fixed-path max-min model does not capture queue/PFC amplification from rerouting. The effect is especially visible when direct-route connectivity drops from ~0.98 to ~0.72 and PXN split ratio rises to ~0.29.
3. The old `path_stretch` metric alone is insufficient because it allowed intermediate GPU transit and therefore mixed PXN reachability with direct network reachability.

## Static Route-Load Evidence

A static route-load estimator was added after the direct-route diagnosis. It:

- Routes every all-to-all pair through direct routes when available.
- Falls back to the same generic PXN proxy search used by FlowSim when the direct route is unavailable.
- Counts all PXN legs as traffic on their underlying links.
- Computes both raw load and pressure, where pressure is `load / link_Gbps`.
- Normalizes failed-topology pressure against the no-fault baseline for the same topology.

The estimator preserves the previous PXN validation:

- Joined samples: 900/900.
- Failed link sets match for all samples.
- Estimated PXN split ratio still matches FlowSim logs exactly:
  `max_abs_estimated_pxn_split_ratio_error = 0.0`.

Selected rate-level results:

| Topology | Rate | Inter-server max pressure / baseline | Local NVSwitch max pressure / baseline | Avg legs / baseline | FlowSim factor | NS3 factor |
|---|---:|---:|---:|---:|---:|---:|
| RO | 1% | 1.634 | 2.013 | 1.011 | 1.520 | 1.093 |
| RO | 15% | 5.473 | 4.522 | 1.156 | 4.889 | 3.084 |
| ZCube | 1% | 1.043 | 1.000 | 1.000 | 1.538 | 1.145 |
| ZCube | 15% | 3.194 | 47.057 | 1.052 | 4.200 | 2.026 |
| Meta | 1% | 1.000 | 36.429 | 1.021 | 1.051 | 1.231 |
| Meta | 15% | 0.884 | 132.086 | 1.306 | 0.950 | 2.322 |

Topology-level correlations:

| Topology | Corr(FlowSim factor, inter pressure) | Corr(NS3 factor, inter pressure) | Corr(delta, inter pressure) | Corr(FlowSim factor, local pressure) | Corr(NS3 factor, local pressure) | Corr(delta, local pressure) |
|---|---:|---:|---:|---:|---:|---:|
| RO | +0.990 | +0.955 | -0.885 | +0.662 | +0.630 | -0.603 |
| ZCube | +0.947 | +0.651 | -0.905 | +0.633 | +0.563 | -0.538 |
| Meta | +0.913 | -0.739 | -0.782 | -0.665 | +0.968 | +0.968 |

Interpretation:

- RO and ZCube mismatch is strongly tied to inter-server hotspot pressure. As the static inter-server pressure rises, both simulators slow down, but FlowSim slows down more. This supports the hypothesis that FlowSim's max-min sharing over fixed routes is more pessimistic than NS3's packet-level dynamics for these topologies.
- Meta is qualitatively different. Inter-server max pressure is below baseline at high fault rates, while local NVSwitch pressure grows by over 100x and NS3 slowdown rises with it. This makes local PXN conversion volume / in-server traffic the strongest current proxy for Meta's NS3 slowdown.
- FlowSim sees the same PXN split volume, but the local high-bandwidth legs are cheap in its model. NS3 appears to expose additional overhead or queueing interaction that is not captured by FlowSim's current local-leg accounting.

## Targeted FCT Evidence

A targeted FCT rerun was added for three high-mismatch samples. This rerun does not change the sweep JCT data; it enables `fct.txt` output for representative cases. A follow-up monitor rerun also enabled `send.txt`, BW, queue, rate, and PFC outputs; the table below uses that more complete rerun.

Targeted samples:

| Topology | Rate | Seed | FlowSim JCT | NS3 JCT | FlowSim FCT rows | NS3 FCT rows | NS3 / FlowSim rows |
|---|---:|---:|---:|---:|---:|---:|---:|
| Meta | 15% | 3 | 166 | 135 | 65,280 | 82,144 | 1.258 |
| ZCube | 15% | 7 | 166 | 64 | 65,280 | 69,248 | 1.061 |
| RO | 15% | 6 | 464 | 428 | 65,280 | 143,968 | 2.205 |

Important logging-grain difference:

- FlowSim writes one FCT row per original all-to-all flow: `256 * 255 = 65,280`.
- NS3 writes FCT rows for physical QP legs. When PXN decomposes an original cross-rail transfer, extra same-server and same-rail rows appear.
- Therefore raw FCT-row distributions are not an apples-to-apples original-flow comparison. They are still useful because they show how much physical PXN work NS3 exposes.

Selected category-level p95 FCT values from `fct.txt` column 7:

| Topology | Simulator | Same-server p95 | Cross-server same-rail p95 | Cross-server cross-rail p95 |
|---|---|---:|---:|---:|
| Meta | FlowSim | 2,507 | 163,206 | 163,206 |
| Meta | NS3 | 4,906 | 117,480 | 72,291 |
| ZCube | FlowSim | 2,507 | 96,510 | 111,421 |
| ZCube | NS3 | 2,089 | 52,743 | 53,770 |
| RO | FlowSim | 5,183 | 461,256 | 461,120 |
| RO | NS3 | 3,839 | 419,672 | n/a |

Interpretation:

- RO NS3 has no physical `cross_server_cross_rail` FCT rows in this sample. Cross-rail original traffic is decomposed into same-server local legs plus cross-server same-rail legs, confirming PXN behavior in the packet simulator.
- RO has the largest NS3 line inflation: +78,688 rows, or 2.205x FlowSim. Even with many extra physical legs, NS3's failed-sample JCT is still lower than FlowSim's. This reinforces that FlowSim's fixed-path max-min model is more pessimistic for RO tails.
- ZCube has only modest NS3 line inflation: +3,968 rows, or 1.061x FlowSim. FlowSim's p95 tail remains roughly 2x NS3 for same-rail/cross-rail traffic, so the ZCube mismatch is not caused simply by NS3 doing less PXN work.
- Meta has meaningful physical-leg inflation: +16,864 rows, or 1.258x FlowSim, including a much larger same-server share in NS3. Meta's raw failed JCT is lower in NS3 than FlowSim, but NS3's normalized slowdown is worse because its no-fault baseline is much faster. This keeps the current Meta hypothesis focused on local PXN / queueing / PFC effects relative to NS3's baseline.

## Targeted Monitor Evidence

The targeted monitor rerun enabled NS3 `send.txt`, queue length, bandwidth, QP rate, trace, and PFC logs. `detailed_288.csv` is still empty, but `send.txt` now matches `fct.txt` line counts exactly, so NS3 physical-leg accounting can be inspected from both files.

Monitor rows captured:

| Topology | Queue rows | BW rows | QP-rate rows | PFC events |
|---|---:|---:|---:|---:|
| Meta | 16,249 | 9,273 | 64,018 | 0 |
| ZCube | 22,905 | 7,974 | 62,552 | 0 |
| RO | 9,377 | 14,470 | 63,396 | 116 |

NS3 physical `send.txt` legs by source/destination category:

| Topology | Same-server legs | Cross-server same-rail legs | Cross-server cross-rail legs |
|---|---:|---:|---:|
| Meta | 18,656 | 9,016 | 54,472 |
| ZCube | 5,760 | 7,964 | 55,524 |
| RO | 80,480 | 63,488 | 0 |

Peak monitor values by reconstructed output link category:

| Topology | Max local-NVSwitch BW | Max GPU-switch BW | Max switch-switch BW | Max local-NVSwitch queue | Max GPU-switch queue | Max switch-switch queue |
|---|---:|---:|---:|---:|---:|---:|
| Meta | 67,217 | 130,310 | 131,798 | 1.97 MB | 4.57 MB | 1.32 MB |
| ZCube | 25,443 | 137,099 | 71,860 | 0.00 MB | 0.93 MB | 0.50 MB |
| RO | 168,010 | 109,181 | 27,852 | 0.74 MB | 1.01 MB | 14.89 MB |

Interpretation:

- RO confirms the PXN decomposition most directly: NS3 records no physical cross-server cross-rail legs. Original cross-rail traffic is split into same-server legs plus cross-server same-rail legs. RO is also the only targeted sample with PFC events, and its switch-switch queue peak is much larger than Meta/ZCube.
- ZCube still records most sends as cross-server cross-rail physical legs. Its queues are low, QP rates are higher than Meta/RO, and NS3 finishes much faster than FlowSim. This supports the earlier view that FlowSim's fixed-route max-min sharing is pessimistic for ZCube under these failures.
- Meta has substantial cross-server cross-rail physical traffic plus nontrivial same-server PXN legs. It has no PFC events in this targeted sample, so the normalized Meta mismatch is more likely from queueing/local-leg overhead relative to NS3's very fast baseline than from explicit PFC pause/resume.
- The monitor evidence refines the static pressure result: local NVSwitch traffic is very high in RO and Meta, but only RO converts that into very large switch-switch queues and PFC events in this sample.

## Baseline-Normalized Monitor Evidence

The same monitor pass was also run on no-fault baseline samples for Meta, ZCube, and RO. This converts the failed-sample monitor values into fault/baseline ratios.

| Topology | NS3 JCT ratio | NS3 QP-leg ratio | Local NVSwitch queue ratio | GPU-switch queue ratio | Switch-switch queue ratio | PFC events |
|---|---:|---:|---:|---:|---:|---:|
| Meta | 2.755 | 1.258 | n/a | 6.974 | 1.272 | 0 -> 0 |
| ZCube | 1.362 | 1.061 | n/a | 1.955 | 1.248 | 0 -> 0 |
| RO | 5.863 | 1.191 | 6.582 | 1.621 | 8.345 | 0 -> 116 |

Interpretation:

- RO is now the clearest NS3 congestion case: JCT increases by 5.86x, switch-switch queue increases by 8.35x, local NVSwitch queue increases by 6.58x, and PFC appears only under fault. Extra QP legs increase by only 1.19x, so the slowdown is not just line inflation; it is where those legs concentrate.
- ZCube remains mild in NS3: JCT increases by only 1.36x and queue ratios stay below 2x. This further supports that FlowSim is over-pessimistic for ZCube's failed fixed-route sharing.
- Meta's failed sample has a 2.76x NS3 JCT ratio and a 6.97x GPU-switch queue ratio, but switch-switch queue only grows 1.27x and PFC stays at 0. This suggests Meta's normalized mismatch is more about endpoint/GPU-switch pressure and baseline sensitivity than deep fabric PFC collapse.
- Across the three samples, QP-leg ratio alone is not a sufficient predictor of NS3 slowdown. Queue amplification by link class is the stronger signal.

## Original-Flow Reconstruction Evidence

NS3 `send.txt` and `fct.txt` were extended with six trailing metadata fields:

`original_src original_dst pxn_leg_kind pxn_leg_index pxn_leg_count flow_id`

This preserves the old prefix fields while making physical PXN legs groupable back to their original all-to-all flow. New logs have 13 columns in `send.txt` and 14 columns in `fct.txt`; older parsers that use only the prefix fields still work.

The three targeted 15% fault samples were rerun with this format. NS3 JCTs stayed the same as before: Meta `135`, ZCube `64`, RO `428`.

Fault-sample original-flow grouping from `send.txt`:

| Topology | Original flows | Physical rows | Avg rows/original | Split original flows | Cross-rail original flows | Cross-rail split flows | Cross-rail originals with physical cross-rail leg | Physical cross-rail rows |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Meta | 65,280 | 82,144 | 1.258 | 15,782 | 55,552 | 13,812 | 52,640 | 54,472 |
| ZCube | 65,280 | 69,248 | 1.061 | 3,912 | 55,552 | 3,420 | 55,036 | 55,524 |
| RO | 65,280 | 143,968 | 2.205 | 58,444 | 55,552 | 55,552 | 0 | 0 |

Fault vs no-fault baseline comparison:

| Topology | Physical row ratio | Split flows baseline -> fault | Cross-rail split baseline -> fault | Physical cross-rail rows baseline -> fault |
|---|---:|---:|---:|---:|
| Meta | 1.258 | 0 -> 15,782 | 0 -> 13,812 | 55,552 -> 54,472 |
| ZCube | 1.061 | 0 -> 3,912 | 0 -> 3,420 | 55,552 -> 55,524 |
| RO | 1.191 | 55,552 -> 58,444 | 55,552 -> 55,552 | 0 -> 0 |

Interpretation:

- RO baseline already splits every cross-rail original flow through PXN, so fault does not change cross-rail split count. Fault adds 2,892 split same-rail original flows and increases physical rows from 120,832 to 143,968. This explains why RO has heavy physical-leg inflation even before considering queue/PFC.
- Meta and ZCube baseline have no split original flows. Under 15% fault, Meta splits 13,812 cross-rail originals, while ZCube splits only 3,420. This exactly matches the FlowSim PXN summary scale and proves both simulators are using the same logical fallback condition at the original-flow level.
- Meta/ZCube still retain most cross-rail originals as physical cross-rail traffic under fault. RO retains none. This is the cleanest evidence that RO's cross-rail traffic is fully decomposed into PXN legs, while Meta/ZCube mostly remain direct with a smaller fallback subset.
- The remaining FlowSim/NS3 mismatch is therefore not because NS3 is losing original-flow identity or silently skipping flows. NS3 completes all 65,280 original flows; the mismatch is how physical legs and congestion are priced.

Same-grain original-flow FCT comparison:

For NS3, each original flow is assigned the max FCT of its physical legs. This compares FlowSim original-flow FCT with NS3 grouped original-flow FCT instead of raw physical-leg rows.

| Topology | Original category | FlowSim p95 FCT | NS3 grouped p95 FCT | NS3 / FlowSim |
|---|---|---:|---:|---:|
| Meta | Cross-server cross-rail | 163,206 | 79,306 | 0.486 |
| Meta | Cross-server same-rail | 163,206 | 78,406 | 0.480 |
| ZCube | Cross-server cross-rail | 111,421 | 53,767 | 0.483 |
| ZCube | Cross-server same-rail | 96,510 | 52,753 | 0.547 |
| RO | Cross-server cross-rail | 461,120 | 419,672 | 0.910 |
| RO | Cross-server same-rail | 461,256 | 419,673 | 0.910 |

Interpretation:

- The same-grain comparison confirms that raw FCT logging grain was not the main cause of the FlowSim/NS3 gap. Even after grouping NS3 physical legs back to original flows, NS3 p95 remains much lower than FlowSim for Meta/ZCube and moderately lower for RO.
- RO is the closest among the three: grouped NS3 original-flow p95 is about 91% of FlowSim for both cross-rail and same-rail categories. This points to FlowSim being directionally close on RO tail timing, while still more pessimistic.
- Meta/ZCube are the strongest evidence for a FlowSim sharing/timing mismatch: NS3 grouped original-flow p95 is roughly half of FlowSim, despite completing the same original flow set.

## Mechanism-Level Summary

A compact summary script now joins three evidence sources:

- Same-grain FlowSim vs NS3 original-flow FCT.
- NS3 original-flow to physical-leg reconstruction.
- NS3 monitor ratios normalized against the no-fault baseline.

Representative targeted samples:

| Topology | FlowSim JCT ratio | NS3 JCT ratio | FlowSim / NS3 p95 same-rail | FlowSim / NS3 p95 cross-rail | NS3 physical row ratio | Fault split originals | Fault cross-rail split | GPU-switch queue ratio | Switch-switch queue ratio | PFC events |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Meta | 0.938 | 2.755 | 2.082 | 2.058 | 1.258 | 15,782 | 13,812 | 6.974 | 1.272 | 0 -> 0 |
| RO | 8.593 | 5.863 | 1.099 | 1.099 | 1.191 | 58,444 | 55,552 | 1.621 | 8.345 | 0 -> 116 |
| ZCube | 5.188 | 1.362 | 1.829 | 2.072 | 1.061 | 3,912 | 3,420 | 1.955 | 1.248 | 0 -> 0 |

Interpretation:

- Meta and ZCube have the largest same-grain FCT gap: FlowSim p95 is about 1.8x-2.1x NS3 grouped original-flow p95. This points to a FlowSim timing/sharing model mismatch, not a logging-grain mismatch.
- RO is much closer at the same original-flow grain: FlowSim p95 is about 1.10x NS3. RO's remaining mismatch is likely a smaller tail-timing conservatism plus different queue/PFC treatment.
- Meta's NS3 normalized slowdown is high even though FlowSim does not slow down in the targeted sample. The strongest monitor signal is GPU-switch queue amplification, not PFC.
- ZCube's NS3 queues stay mild and physical-leg inflation is small, yet FlowSim slows down strongly. This is the cleanest case for fixed-route max-min over-pessimism.
- RO shows true NS3 congestion symptoms: switch-switch queue ratio is 8.345 and PFC appears under fault.

## FlowSim Code-Path Findings

The next code inspection focused on the FlowSim source currently used by the binary under `/home/zty/Topo/m4/SimAI`.

Confirmed behavior:

- `FlowSimNetWork::sim_send` schedules the original request after `AS_SEND_LAT`, then builds a PXN plan and either calls `FlowSim::Send` directly or enters `flowsim_pxn_send_next`.
- `flowsim_pxn_send_next` serializes PXN legs. A non-last leg must complete before `flowsim_pxn_local_completion_callback` schedules the next leg; when `AS_SEND_LAT > 0`, that latency is also inserted between PXN legs.
- `Topology::update_link_states` uses global max-min progressive filling over all currently active chunks and all links in each chunk's path.
- `Topology::schedule_next_min_completion_set` schedules only the earliest completion set, then `post_batch_completion_callback` updates all remaining active chunks and recomputes rates.
- NS3, by contrast, starts an `RdmaClient` application for each physical send and then lets packet queues, QP state, rate control, and PFC determine progress.

Implication:

- FlowSim models each chunk as a continuous full-path flow with one instantaneous bottleneck rate at a time.
- PXN in FlowSim is currently store-and-forward at the leg level, not packet-pipelined across local and remote legs.
- This explains why FlowSim can overestimate tails for ZCube/Meta after failures: a small number of changed routes or PXN splits can hold bottleneck shares for whole chunks, while NS3 can expose packet-level overlap and queue dynamics.
- It also explains why FlowSim can underrepresent Meta's normalized NS3 slowdown: local/GPU-switch queue amplification appears in NS3 monitor data, but FlowSim prices local legs mainly through high static bandwidth and does not model endpoint queue buildup.

## FlowSim PXN Timing Smoke

An experimental FlowSim switch was added in the `/home/zty/Topo/m4/SimAI` FlowSim source:

- Default: `serial`, preserving the existing store-and-forward PXN leg chain.
- Experimental: `FLOWSIM_PXN_TIMING=overlap` or `AS_PXN_TIMING=overlap`, which launches all PXN physical legs together and completes the original flow after the slowest leg.

This is not intended as the final correctness model. It is a diagnostic switch to test whether PXN leg serialization is the dominant cause of the FlowSim/NS3 gap.

Targeted 15% fault smoke results:

| Topology | Serial JCT | Overlap JCT | Reduction | NS3 JCT | Serial p95 cross-rail | Overlap p95 cross-rail | NS3 grouped p95 cross-rail |
|---|---:|---:|---:|---:|---:|---:|---:|
| Meta | 166 | 155 | 6.627% | 135 | 163,206 | 152,060 | 79,306 |
| ZCube | 166 | 164 | 1.205% | 64 | 111,421 | 110,356 | 53,767 |
| RO | 464 | 445 | 4.095% | 428 | 461,120 | 444,323 | 419,672 |

Interpretation:

- The overlap approximation moves FlowSim in the expected direction, but only modestly.
- It nearly closes the RO JCT gap, but RO was already the closest same-grain case.
- It does not explain Meta/ZCube. Meta cross-rail p95 remains 1.92x NS3 grouped p95; ZCube cross-rail p95 remains 2.05x NS3 grouped p95.
- Therefore PXN leg serialization is a secondary contributor, not the primary mismatch mechanism for Meta/ZCube.
- The next useful target is FlowSim bottleneck attribution: identify which links/categories fix the p95 chunks' max-min rate.

## FlowSim Bottleneck Trace

A second FlowSim diagnostic switch was added:

- `FLOWSIM_BOTTLENECK_TRACE=1`
- Optional output path: `FLOWSIM_BOTTLENECK_TRACE_FILE=/path/bottleneck_trace.csv`

When enabled, FlowSim writes one row per completed physical chunk/leg with:

`time_ns, src, dst, chunk_size, remaining_size, rate, bottleneck_src, bottleneck_dst, bottleneck_rate, bottleneck_category, path_hops`

The trace records the link that fixed the chunk's max-min rate in `Topology::update_link_states`. It is disabled by default.

Targeted serial-mode trace results:

| Topology | Scope | Rows | Local NVSwitch | GPU-switch | Switch-switch | Physical cross-rail |
|---|---|---:|---:|---:|---:|---:|
| DeepSeek | all | 137,120 | 53.699% | 11.867% | 34.434% | 0.000% |
| DeepSeek | tail p95 time | 7,305 | 46.667% | 0.000% | 53.333% | 0.000% |
| DeepSeek | tail p99 time | 1,757 | 100.000% | 0.000% | 0.000% | 0.000% |
| Meta | all | 82,144 | 22.711% | 10.353% | 66.936% | 66.313% |
| Meta | tail p95 time | 8,344 | 17.162% | 82.838% | 0.000% | 64.070% |
| Meta | tail p99 time | 1,432 | 100.000% | 0.000% | 0.000% | 0.000% |
| RO | all | 143,968 | 55.901% | 11.875% | 32.224% | 0.000% |
| RO | tail p95 time | 7,260 | 62.094% | 0.000% | 37.906% | 0.000% |
| RO | tail p99 time | 1,603 | 100.000% | 0.000% | 0.000% | 0.000% |
| ZCube | all | 69,248 | 8.318% | 55.609% | 36.073% | 80.181% |
| ZCube | tail p95 time | 3,510 | 2.137% | 0.000% | 97.863% | 88.775% |
| ZCube | tail p99 time | 829 | 1.689% | 0.000% | 98.311% | 91.797% |

Interpretation:

- ZCube is now the clearest fixed-route max-min mismatch. FlowSim's tail is almost entirely `switch_switch` bottlenecked, but NS3's ZCube switch-switch queue ratio is only 1.248 and has no PFC. This strongly supports FlowSim overpricing static fabric hotspots for ZCube.
- Meta's p95 tail is mostly `gpu_switch` bottlenecked, which aligns with the NS3 monitor signal that GPU-switch queue grows by 6.974x under fault. However, FlowSim's same-grain p95 is still about 2x NS3, so the issue is not missing the bottleneck class; it is how FlowSim prices sustained fair-share pressure relative to NS3 packet dynamics and baseline timing.
- DeepSeek behaves like a fully PXN-decomposed case in this targeted sample: FlowSim reports `split=55552` and `direct_cross_rail=0`, and the trace has `0%` physical cross-rail rows. Therefore the cross-rail switch-switch weight cannot affect it. Its remaining mismatch is mainly absolute-time calibration: at 15%, FlowSim factor is close to NS3 (`2.245` vs `2.112`), but FlowSim baseline is much larger (`143` vs `51`).
- RO's p95 tail is mixed local NVSwitch and switch-switch, and NS3 also shows the strongest switch-switch queue/PFC behavior for RO. This explains why RO is the closest same-grain match and why the overlap timing switch helps but does not fully remove the gap.
- The p99 local-NVSwitch dominance in Meta/RO comes from late local PXN legs in serial mode. Since overlap only modestly changes JCT/FCT, these local legs are visible but not the main explanation for Meta/ZCube's large p95 mismatch.

## PXN-Leg Calibration

A targeted sensitivity script was added for fully PXN-decomposed cases:

- `scripts/run_flowsim_pxn_leg_calibration.py`
- Output: `flowsim_pxn_leg_calibration_smoke/pxn_leg_calibration_summary.csv`

The script runs baseline and 15%-fault seed1 FlowSim for DeepSeek and RO while changing only diagnostic link-category multipliers. Both targeted fault samples report `split=55552` and `direct_cross_rail=0`, so these are PXN same-server/same-rail leg tests rather than physical cross-rail tests.

| Topology | Variant | Local multiplier | Switch-switch multiplier | FlowSim baseline | FlowSim failed | NS3 failed | FlowSim factor | NS3 factor | Failed JCT error | Factor error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | default | 1.0 | 1.0 | 143 | 336 | 105 | 2.350 | 2.059 | 231 | 0.291 |
| DeepSeek | localx2 | 2.0 | 1.0 | 142 | 330 | 105 | 2.324 | 2.059 | 225 | 0.265 |
| DeepSeek | switchx2 | 1.0 | 2.0 | 76 | 176 | 105 | 2.316 | 2.059 | 71 | 0.257 |
| DeepSeek | localx2_switchx2 | 2.0 | 2.0 | 76 | 176 | 105 | 2.316 | 2.059 | 71 | 0.257 |
| RO | default | 1.0 | 1.0 | 54 | 281 | 253 | 5.204 | 3.466 | 28 | 1.738 |
| RO | localx2 | 2.0 | 1.0 | 53 | 284 | 253 | 5.358 | 3.466 | 31 | 1.893 |
| RO | switchx2 | 1.0 | 2.0 | 33 | 151 | 253 | 4.576 | 3.466 | 102 | 1.110 |
| RO | localx2_switchx2 | 2.0 | 2.0 | 32 | 152 | 253 | 4.750 | 3.466 | 101 | 1.284 |

Interpretation:

- Local NVSwitch capacity is not the main knob for these two PXN-decomposed samples. `localx2` barely changes DeepSeek (`336 -> 330`) and does not help RO (`281 -> 284`).
- Switch-switch capacity dominates DeepSeek's absolute time: `switchx2` cuts failed JCT from `336` to `176` and baseline from `143` to `76`. This supports the idea that DeepSeek's absolute mismatch is mostly same-rail fabric fair-share pricing after PXN decomposition.
- The same `switchx2` knob breaks RO's absolute JCT: failed JCT drops from `281` to `151`, below NS3's `253`. This confirms that a global same-rail switch-switch multiplier is too blunt, just like the earlier global fabric multiplier.
- DeepSeek and RO both have `direct_cross_rail=0`, but they should not share a single simple fabric scaling rule. RO has explicit NS3 congestion/PFC evidence in the targeted monitor runs, while the DeepSeek monitor check below shows no comparable PFC or switch-switch queue amplification.

### PXN Timing Endpoint Check

The calibration script was extended with a `pxn_timing` dimension:

- CLI form: `--variant overlap:timing=overlap`
- FlowSim env: `FLOWSIM_PXN_TIMING=serial|overlap`
- Output: `flowsim_pxn_timing_endpoint/pxn_leg_calibration_summary.csv`

This isolates whether FlowSim's serial accounting of PXN legs is the main source of the DeepSeek/RO mismatch.

| Topology | Timing | FlowSim baseline | FlowSim failed | NS3 baseline | NS3 failed | FlowSim factor | NS3 factor | Failed JCT error | Factor error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | serial | 143 | 336 | 51 | 105 | 2.350 | 2.059 | 231 | 0.291 |
| DeepSeek | overlap | 138 | 317 | 51 | 105 | 2.297 | 2.059 | 212 | 0.238 |
| RO | serial | 54 | 281 | 73 | 253 | 5.204 | 3.466 | 28 | 1.738 |
| RO | overlap | 49 | 263 | 73 | 253 | 5.367 | 3.466 | 10 | 1.902 |

Interpretation:

- Full PXN-leg overlap only modestly changes DeepSeek (`336 -> 317`) and leaves a large absolute error (`212`). Therefore DeepSeek's large absolute mismatch is not mainly caused by FlowSim simply adding all PXN legs serially.
- For RO, overlap improves failed absolute JCT (`281 -> 263`, closer to NS3 `253`), but it also lowers baseline (`54 -> 49`) and worsens normalized factor error (`1.738 -> 1.902`). It is useful diagnostically but not a global fix.
- The next model target should not be a global same-rail bandwidth multiplier or a blanket full-overlap timing mode. The remaining mismatch points to FlowSim's sustained fair-share approximation for same-rail PXN traffic versus NS3's packet-level endpoint/queue dynamics and statistical sharing.

### PXN Same-Rail Weight Smoke

A more targeted diagnostic knob was added in FlowSim:

- Chunk metadata: PXN-generated legs are marked when they are emitted by `FlowsimNetwork`.
- Env: `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=<w>`
- Scope: only PXN-generated, cross-server same-rail chunks on switch-switch links.
- Non-goal: this does not change physical link bandwidth, direct same-rail traffic, or physical cross-rail traffic.

The calibration script now accepts `pxn_same_rail=<w>` in `--variant`.
The main FlowSim fault runner now accepts `--pxn-same-rail-switch-switch-weight <w>` and records it in both raw and summary CSVs.

Smoke results in the same endpoint output directory:

| Topology | Variant | PXN same-rail weight | FlowSim baseline | FlowSim failed | NS3 failed | FlowSim factor | NS3 factor | Failed JCT error | Factor error |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | serial | 1.00 | 143 | 336 | 105 | 2.350 | 2.059 | 231 | 0.291 |
| DeepSeek | pxn_w0p75 | 0.75 | 114 | 259 | 105 | 2.272 | 2.059 | 154 | 0.213 |
| DeepSeek | pxn_w0p5 | 0.50 | 85 | 186 | 105 | 2.188 | 2.059 | 81 | 0.129 |
| RO | serial | 1.00 | 54 | 281 | 253 | 5.204 | 3.466 | 28 | 1.738 |
| RO | pxn_w0p75 | 0.75 | 44 | 225 | 253 | 5.114 | 3.466 | 28 | 1.648 |
| RO | pxn_w0p5 | 0.50 | 34 | 162 | 253 | 4.765 | 3.466 | 91 | 1.299 |

Interpretation:

- The PXN-only same-rail weight is a better diagnostic than full overlap for DeepSeek: `w=0.75` cuts failed JCT by `77` without changing physical cross-rail accounting, and `w=0.5` cuts by `150`.
- The RO guardrail rules out aggressive weights. `w=0.5` overshoots RO failed JCT to `162`, far below NS3 `253`.
- `w=0.75` is the first candidate worth broader testing: it improves DeepSeek and leaves RO failed absolute error unchanged (`28`), but it still does not solve DeepSeek's absolute gap (`259` vs `105`). It should be treated as a bounded statistical-sharing knob, not a completed model fix.

### Full Sweep Launch

The six-topology FlowSim validation for the combined policy is now running:

- Policy: `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3` plus `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`
- Output: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/`
- Status file: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/RUN_STATUS.md`
- tmux session: `flowsim_w03_pxn075_full`
- Planned samples: six topologies, `1%..15%`, `10` seeds each, `900` fault samples total

Current verified state:

- All six baselines completed.
- Current progress snapshot: `276/900` successful rows.
- Complete fault summary rows:
  - Meta at `1%`, `10/10` success, failed JCT mean `78.3` versus baseline `72`.
  - Meta at `2%`, `10/10` success, failed JCT mean `78.5` versus baseline `72`.
- Meta at `3%`, `10/10` success, failed JCT mean `79.9` versus baseline `72`.
- Meta at `4%`, `10/10` success, failed JCT mean `81.2` versus baseline `72`.
- Meta at `5%`, `10/10` success, failed JCT mean `79.7` versus baseline `72`.
- Meta at `6%`, `10/10` success, failed JCT mean `86.9` versus baseline `72`.
- Meta at `7%`, `10/10` success, failed JCT mean `88.6` versus baseline `72`.
- Meta at `8%`, `10/10` success, failed JCT mean `88.0` versus baseline `72`.
- Meta at `9%`, `10/10` success, failed JCT mean `99.9` versus baseline `72`.
- Meta at `10%`, `10/10` success, failed JCT mean `100.3` versus baseline `72`.
- Meta at `11%`, `10/10` success, failed JCT mean `104.6` versus baseline `72`.
- Meta at `12%`, `10/10` success, failed JCT mean `107.2` versus baseline `72`.
- Meta at `13%`, `10/10` success, failed JCT mean `111.2` versus baseline `72`.
- Meta at `14%`, `10/10` success, failed JCT mean `113.3` versus baseline `72`.
- Meta at `15%`, `10/10` success, failed JCT mean `118.1` versus baseline `72`.
- HPN at `1%`, `10/10` success, failed JCT mean `69.4` versus baseline `65`.
- HPN at `2%`, `10/10` success, failed JCT mean `71.0` versus baseline `65`.
- HPN at `3%`, `10/10` success, failed JCT mean `73.0` versus baseline `65`.
- HPN at `4%`, `10/10` success, failed JCT mean `73.6` versus baseline `65`.
- HPN at `5%`, `10/10` success, failed JCT mean `75.3` versus baseline `65`.
- HPN at `6%`, `10/10` success, failed JCT mean `76.7` versus baseline `65`.
- HPN at `7%`, `10/10` success, failed JCT mean `79.4` versus baseline `65`.
- HPN at `8%`, `10/10` success, failed JCT mean `79.8` versus baseline `65`.
- HPN at `9%`, `10/10` success, failed JCT mean `82.0` versus baseline `65`.
- HPN at `10%`, `10/10` success, failed JCT mean `87.8` versus baseline `65`.
- HPN at `11%`, `10/10` success, failed JCT mean `94.4` versus baseline `65`.
- HPN at `12%`, `10/10` success, failed JCT mean `96.3` versus baseline `65`.
- HPN at `13%` is partial: `6/10` success, failed JCT mean `96.67` versus baseline `65`.
- The runner now supports `--resume` and has been smoke-tested: a completed sample is skipped on rerun, and existing `EndToEnd.csv` files are reused.

Early comparison against prior `w0.3` using the complete rates available so far:

| Topology | Rates | w0.3 factor MAE | w0.3 + PXN factor MAE | Factor delta | w0.3 failed JCT MAE | w0.3 + PXN failed JCT MAE | JCT delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| HPN | 12 | 0.243 | 0.245 | +0.002 | 10.80 | 10.70 | -0.10 |
| Meta | 15 | 0.529 | 0.540 | +0.011 | 4.49 | 3.86 | -0.63 |

Interpretation:

- The new PXN same-rail weight improves Meta's absolute failed-JCT error slightly versus `w0.3`, but worsens normalized factor error.
- HPN is effectively unchanged across all fifteen complete rates, so this PXN-specific weight is not perturbing HPN behavior.
- This is not enough evidence to accept or reject the candidate; it confirms the need to keep both views and wait for DeepSeek/RO/ROFT/Zcube guardrails.

Update:

- Full sweep is complete: `900/900` successful fault samples. All six topologies have `1%..15%`, `10/10` samples per rate.
- The complete-rate comparison against prior `w0.3` is: Meta factor MAE delta `+0.011`, Meta failed-JCT MAE delta `-0.6`; HPN factor MAE delta `+0.002`, HPN failed-JCT MAE delta `-0.2`; DeepSeek factor MAE delta `-0.048`, DeepSeek failed-JCT MAE delta `-59.8`; Zcube factor/JCT deltas remain exactly `0.000/0.0` over all fifteen rates.
- RO `1%` matches the targeted guardrail result: `w=0.75` gives failed JCT `70.1` versus NS3 `79.8` and original `w0.3` `82.1`. This first RO point is worse than original in both absolute JCT and normalized factor because `w=0.75` lowers the RO baseline to `44`; the earlier guardrail improvement for RO only appears when considering `1%`, `5%`, `10%`, and `15%` together.
- With RO `1%..15%` complete, the RO aggregate now improves in both views: absolute failed-JCT MAE improves from `24.03` to `6.64`, and normalized factor MAE improves from `1.103` to `1.086`. The RO `15%` point still undershoots NS3 in absolute JCT (`206.7` vs NS3 `225.1`), but it is much closer than prior `w0.3` (`264.0`). This confirms the targeted guardrail result in the full sweep.
- With ROFT `1%..15%` complete, the new policy also improves both views: normalized factor MAE improves from `0.141` to `0.069`, and absolute failed-JCT MAE improves from `29.6` to `23.9`. The ROFT absolute gain is smaller than RO/DeepSeek, but all guardrail checkpoints (`1%`, `5%`, `10%`, `15%`) match the full sweep.
- Current complete-only plots were regenerated:
  - `flowsim_w03_pxn075_comparison/plots/flowsim_w03_pxn075_vs_ns3_complete_partial_normalized_jct.png`
  - `flowsim_w03_pxn075_comparison/plots/flowsim_w03_pxn075_vs_ns3_complete_partial_failed_jct.png`
  - `flowsim_w03_pxn075_comparison/plots/flowsim_w03_pxn075_vs_ns3_complete_partial_data.csv`
- A targeted guardrail sweep has been launched in tmux session `flowsim_w03_pxn075_guardrail` for DeepSeek, RO, ROFT, and Zcube at `1%, 5%, 10%, 15%`, `10` seeds each.
- Guardrail DeepSeek baseline completed with JCT `114`; run log confirms `split=55552`, `direct_cross_rail=0`, and both weights (`cross_rail=0.3`, `pxn_same_rail=0.75`) are active.
- Complete guardrail rows:
  - DeepSeek at `1%`, `10/10` success, failed JCT mean `138.2` versus baseline `114` and NS3 failed `58.7`.
  - DeepSeek at `5%`, `10/10` success, failed JCT mean `192.6` versus baseline `114` and NS3 failed `77.4`.
  - DeepSeek at `10%`, `10/10` success, failed JCT mean `227.8` versus baseline `114` and NS3 failed `96.5`.
- DeepSeek at `15%`, `10/10` success, failed JCT mean `244.6` versus baseline `114` and NS3 failed `107.7`.
- RO at `1%`, `10/10` success, failed JCT mean `70.1` versus baseline `44` and NS3 failed `79.8`.
- RO at `5%`, `10/10` success, failed JCT mean `100.4` versus baseline `44` and NS3 failed `102.9`.
- RO at `10%`, `10/10` success, failed JCT mean `145.1` versus baseline `44` and NS3 failed `148.9`.
- RO at `15%`, `10/10` success, failed JCT mean `206.7` versus baseline `44` and NS3 failed `225.1`.
- Compared with prior `w0.3`, DeepSeek improves in both views over these four rates: failed-JCT MAE improves by `58.4`, and factor MAE improves by `0.051`.
- At `15%`, the new DeepSeek factor is `2.146`, closer to NS3 `2.112` than prior `w0.3` factor `2.245`, while absolute failed JCT still remains much higher than NS3 (`244.6` vs `107.7`).
- RO aggregate over `1%`, `5%`, `10%`, and `15%` also improves under `w=0.75`: failed-JCT MAE improves from `22.7` to `8.6`, and factor MAE improves from `1.092` to `1.061`.
- The caution is the RO `15%` single point: `w=0.75` undershoots absolute JCT (`206.7` vs NS3 `225.1`) even though it improves normalized factor (`4.698` vs prior `4.889`, NS3 `3.084`).
- Therefore `w=0.75` is viable as a strong absolute-JCT candidate, not rejected by RO aggregate. The lighter-weight calibration should decide whether `0.85/0.90/0.95` preserve enough DeepSeek benefit while avoiding the RO `15%` undershoot.
- ROFT is complete in the `w=0.75` guardrail and also improves: factor MAE `0.145 -> 0.077`, failed-JCT MAE `29.3 -> 24.3`.
- Zcube is complete in the `w=0.75` guardrail and is unchanged at all four guardrail rates (`1%`, `5%`, `10%`, `15%`): factor MAE stays `0.779` and failed-JCT MAE stays `5.6`. This confirms the PXN same-rail weight does not affect the sampled Zcube path mix.

Follow-up calibration launched:

- tmux session: `flowsim_pxn_weight_balance`
- Output: `flowsim_pxn_same_rail_weight_balance/`
- Topologies: DeepSeek and RO
- Target: 15% link-failure seed1, plus baseline
- Variants: `w=1.0`, `0.95`, `0.90`, `0.85`, `0.75`
- Purpose: find whether a weaker uniform PXN same-rail weight can preserve most of the DeepSeek gain without worsening RO, before spending time on another multi-sample guardrail.

First calibration result:

- DeepSeek default (`w=1.0`): baseline `143`, failed `336`, factor `2.350`, NS3 failed `105`, NS3 factor `2.059`.
- DeepSeek `w=0.95`: baseline `137`, failed `322`, factor `2.350`.
- DeepSeek `w=0.90`: baseline `131`, failed `302`, factor `2.305`.
- DeepSeek `w=0.85`: baseline `126`, failed `288`, factor `2.286`.
- DeepSeek `w=0.75`: baseline `114`, failed `259`, factor `2.272`.
- Interpretation: `w=0.95` modestly improves DeepSeek absolute JCT (`336 -> 322`) but does not improve normalized factor. `w=0.90`, `w=0.85`, and `w=0.75` improve both DeepSeek absolute JCT and factor error, with `w=0.75` still strongest for DeepSeek and `w=0.85` the gentler compromise candidate. RO-side calibration is now the deciding evidence before launching another guardrail.
- RO default (`w=1.0`): baseline `54`, failed `281`, factor `5.204`, NS3 failed `253`, NS3 factor `3.466`.
- RO `w=0.95`: baseline `52`, failed `270`, factor `5.192`.
- RO `w=0.90`: baseline `50`, failed `258`, factor `5.160`.
- RO `w=0.85`: baseline `48`, failed `247`, factor `5.146`.
- RO `w=0.75`: baseline `44`, failed `225`, factor `5.114`.
- Interpretation: `w=0.85` is the best compromise point from the seed1 calibration. It gives stronger DeepSeek improvement than `w=0.90` (`336 -> 288`) while keeping RO failed JCT close to NS3 (`247` vs `253`) and avoiding the stronger `w=0.75` absolute undershoot (`225` vs `253`). `w=0.75` remains best for DeepSeek and RO factor error, but not for RO absolute JCT. The next multi-sample guardrail should test `w=0.85` on DeepSeek and RO before trying to make it a broader policy.

`w=0.85` guardrail launched:

- tmux session: `flowsim_w03_pxn085_guardrail`
- Output: `flowsim_256_alltoall_guardrail_w03_pxn085/`
- Topologies: DeepSeek and RO
- Rates: `1%`, `5%`, `10%`, `15%`
- Samples: `10` each
- Purpose: compare `w=0.85` against the completed `w=0.75` guardrail and prior `w0.3`.

First `w=0.85` guardrail row:

- DeepSeek `1%`, `10/10` success: baseline `126`, failed JCT `152.1`.
- Versus prior `w0.3`, this improves both views: failed-JCT error improves by `21.6`, factor error improves by `0.008`.
- Versus `w=0.75`, this is the expected compromise: absolute JCT is worse (`138.2 -> 152.1`), but factor is slightly closer to NS3 (`1.212 -> 1.207`, NS3 `1.151`).

Second `w=0.85` guardrail row:

- DeepSeek `5%`, `10/10` success: failed JCT `213.5`.
- Across DeepSeek `1%` and `5%`, `w=0.85` improves over prior `w0.3`: failed-JCT MAE `141.8 -> 114.8`, factor MAE `0.134 -> 0.116`.
- Compared with `w=0.75`, `w=0.85` has nearly identical DeepSeek factor MAE (`0.117 -> 0.116`) but worse absolute failed-JCT MAE (`97.3 -> 114.8`). Therefore the case for `w=0.85` depends on whether it improves RO enough to offset the DeepSeek absolute-JCT loss.

Third `w=0.85` guardrail row:

- DeepSeek `10%`, `10/10` success: failed JCT `253.1`.
- Across DeepSeek `1%`, `5%`, and `10%`, `w=0.85` still improves over prior `w0.3`: failed-JCT MAE `161.0 -> 128.7`, factor MAE `0.148 -> 0.117`.
- Compared with `w=0.75`, `w=0.85` is worse in both views over these three DeepSeek rates: failed-JCT MAE `108.7 -> 128.7`, factor MAE `0.113 -> 0.117`.
- This makes the decision hinge on RO: `w=0.85` must materially reduce RO's `w=0.75` high-rate undershoot to compensate for weaker DeepSeek absolute-JCT calibration.

DeepSeek `w=0.85` guardrail complete:

- Four rates complete: `1%`, `5%`, `10%`, `15%`.
- Versus prior `w0.3`, `w=0.85` improves factor MAE `0.144 -> 0.106` and failed-JCT MAE `174.1 -> 138.5`.
- Versus `w=0.75`, `w=0.85` is worse in both views: factor MAE `0.093 -> 0.106`, failed-JCT MAE `115.7 -> 138.5`.
- Therefore `w=0.85` is no longer a DeepSeek-improvement candidate over `w=0.75`; it is only worth keeping if RO gains are large enough.

First RO `w=0.85` guardrail row:

- RO `1%`, `10/10` success: baseline `48`, failed JCT `73.7`.
- Versus `w=0.75`, this improves both views for RO `1%`: failed-JCT error `9.7 -> 6.1`, factor error `0.500 -> 0.442`.
- This confirms the intended tradeoff: `w=0.85` weakens DeepSeek calibration but can reduce RO undershoot. The decision still needs RO `5%`, `10%`, and `15%`.

Second RO `w=0.85` guardrail row:

- RO `5%`, `10/10` success: baseline `48`, failed JCT `106.5`.
- Versus prior `w0.3`, this improves absolute failed-JCT MAE over RO `1%+5%` from `9.8` to `4.8`, while factor MAE is essentially unchanged (`0.623 -> 0.626`).
- Versus `w=0.75`, the two-rate RO aggregate improves in both views: failed-JCT MAE `6.1 -> 4.8`, factor MAE `0.686 -> 0.626`.
- The single `5%` point is mixed: `w=0.75` is closer in absolute JCT (`100.4` vs NS3 `102.9`, while `w=0.85` is `106.5`), but `w=0.85` is closer in normalized factor (`2.219` vs `2.282`, NS3 `1.410`).
- Therefore `w=0.85` is still a RO tradeoff candidate, but it has not displaced `w=0.75`; the deciding evidence remains RO `10%` and `15%`.

Third RO `w=0.85` guardrail row:

- RO `10%`, `10/10` success: baseline `48`, failed JCT `158.7`.
- Versus prior `w0.3`, the three-rate RO aggregate improves in both views: factor MAE `0.854 -> 0.839`, failed-JCT MAE `17.3 -> 6.5`.
- Versus `w=0.75`, the three-rate RO aggregate is mixed: factor MAE improves `0.877 -> 0.839`, but failed-JCT MAE worsens `5.3 -> 6.5`.
- The single `10%` point is also mixed: `w=0.75` is closer in absolute JCT (`145.1` vs NS3 `148.9`, while `w=0.85` is `158.7`), but `w=0.85` is very slightly closer in factor (`3.306` vs `3.298`, NS3 `2.040`).
- Current implication: `w=0.85` is a normalized-factor tradeoff, not a clear replacement for `w=0.75`. RO `15%` remains the decisive point because that is where `w=0.75` had the largest absolute undershoot.

RO `w=0.85` guardrail complete:

- RO `15%`, `10/10` success: baseline `48`, failed JCT `229.8`.
- Versus prior `w0.3`, the four-rate RO aggregate improves in both views: factor MAE `1.092 -> 1.055`, failed-JCT MAE `22.7 -> 6.0`.
- Versus `w=0.75`, RO improves slightly in both views: factor MAE `1.061 -> 1.055`, failed-JCT MAE `8.6 -> 6.0`.
- The reason is mostly the `15%` point: `w=0.85` lands much closer to NS3 in absolute JCT (`229.8` vs NS3 `225.1`) than `w=0.75` (`206.7`), although its normalized factor is worse at that point (`4.788` vs `4.698`, NS3 `3.084`).
- This RO gain is not enough to make `w=0.85` the uniform default: DeepSeek gets worse versus `w=0.75` by `+22.8` failed-JCT MAE and `+0.013` factor MAE, while RO only gains `-2.6` failed-JCT MAE and `-0.006` factor MAE.
- Weighted over the completed DeepSeek+RO guardrail rates, `w=0.85` is slightly worse than `w=0.75`: factor MAE `0.577 -> 0.581`, failed-JCT MAE `62.2 -> 72.3`.
- Current recommendation: keep `w=0.75` as the uniform PXN same-rail candidate for the full six-topology run, and keep `w=0.85` as evidence that a future topology-aware policy could treat RO differently.

## DeepSeek NS3 Monitor Check

DeepSeek was rerun with the same detailed NS3 monitors as the previous Meta/ZCube/RO targeted cases:

- Fault target: `DeepSeek`, `15%`, `seed1`.
- Baseline target: `DeepSeek`, no failure.
- Output:
  - `targeted_deepseek_monitor/targeted_monitor_overview.csv`
  - `targeted_deepseek_monitor_baseline/targeted_monitor_overview.csv`
  - `targeted_deepseek_monitor_comparison/targeted_monitor_fault_vs_baseline.csv`
  - `targeted_deepseek_original_flow/ns3_original_flow_category_summary.csv`
  - `targeted_deepseek_original_flow_baseline/ns3_original_flow_category_summary.csv`

Fault-vs-baseline monitor summary:

| Metric | Baseline | Fault | Fault / baseline |
|---|---:|---:|---:|
| FlowSim JCT | 143 | 336 | 2.350 |
| NS3 JCT | 51 | 105 | 2.059 |
| NS3 physical rows | 120,832 | 137,120 | 1.135 |
| PFC events | 0 | 0 | n/a |
| Same-server send rows | 57,344 | 73,632 | 1.284 |
| Same-rail send rows | 63,488 | 63,488 | 1.000 |
| Cross-rail send rows | 0 | 0 | n/a |
| Max local-NVSwitch queue | 16,712 | 472,872 | 28.295 |
| Max GPU-switch queue | 716,096 | 2,919,440 | 4.077 |
| Max switch-switch queue | 568,276 | 710,088 | 1.250 |
| Max local-NVSwitch BW | 156,869 | 127,560 | 0.813 |
| Max GPU-switch BW | 160,386 | 145,811 | 0.909 |
| Max switch-switch BW | 147,745 | 117,784 | 0.797 |

Original-flow reconstruction:

| Original category | Baseline physical rows | Fault physical rows | Baseline split originals | Fault split originals |
|---|---:|---:|---:|---:|
| Same-server | 1,792 | 1,792 | 0 | 0 |
| Cross-server same-rail | 7,936 | 12,008 | 0 | 2,036 |
| Cross-server cross-rail | 111,104 | 123,320 | 55,552 | 55,552 |

Interpretation:

- DeepSeek is not an RO-style PFC/fabric-collapse case. Fault and baseline both have `0` PFC events, and switch-switch queue grows only `1.25x`, while RO's earlier switch-switch queue ratio was `8.35x` with `116` PFC events.
- DeepSeek's fault adds physical work mostly by splitting `2,036` same-rail originals and adding local same-server legs to some cross-rail originals. Total physical rows grow `1.135x`.
- The same-rail QP `p95_curr_rate` is unchanged between fault and baseline (`568041472` in both monitor summaries), so NS3's slowdown is not from ECN/PFC rate collapse.
- The largest monitor amplifications are local-NVSwitch queue spikes and GPU-switch queue growth. The local-NVSwitch max is sparse (`4` monitored queue rows and `2` active ports in the fault summary), so it should not be overread as a global local bandwidth problem.
- This refines the FlowSim-side calibration result: switch-switch capacity controls DeepSeek's FlowSim absolute time, but NS3 monitor data does not show matching switch-switch congestion. Since full leg overlap only modestly helps, the mismatch is more likely FlowSim's sustained fair-share approximation for PXN same-rail traffic versus NS3's packet-level endpoint/queue dynamics and statistical sharing, not a physical same-rail bandwidth shortage.

## FlowSim ECMP / Sharing Experiments

Two more FlowSim experiment knobs were added:

- `FLOWSIM_ECMP_SEED=node` and `FLOWSIM_ECMP_SRC_PORT=10000` make FlowSim use a more NS3-like ECMP hash seed and first source port. Defaults remain `srcip` and `10006`.
- `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=<w>` changes the weighted max-min accounting only for physical cross-rail chunks on switch-switch links. Default is `1.0`.
- Existing diagnostic knobs `FLOWSIM_SWITCH_SWITCH_BW_MULTIPLIER` and `FLOWSIM_FABRIC_BW_MULTIPLIER` globally scale switch-switch capacity, but this proved too blunt.

Targeted results:

| Topology | Variant | JCT | JCT / serial | JCT / NS3 | p95 cross-rail | p95 cross-rail / NS3 | p95 same-rail / NS3 |
|---|---|---:|---:|---:|---:|---:|---:|
| Meta | serial | 166 | 1.000 | 1.230 | 163,206 | 2.058 | 2.082 |
| Meta | crossrail_switch_w0.5 | 149 | 0.898 | 1.104 | 103,640 | 1.307 | 1.322 |
| ZCube | serial | 166 | 1.000 | 2.594 | 111,421 | 2.072 | 1.829 |
| ZCube | ecmp_ns3ish | 165 | 0.994 | 2.578 | 111,511 | 2.074 | 1.798 |
| ZCube | switch_switch_x2 | 85 | 0.512 | 1.328 | 66,795 | 1.242 | 1.266 |
| ZCube | crossrail_switch_w0.5 | 90 | 0.542 | 1.406 | 73,356 | 1.364 | 1.391 |
| RO | serial | 464 | 1.000 | 1.084 | 461,120 | 1.099 | 1.099 |
| RO | switch_switch_x2 | 240 | 0.517 | 0.561 | 236,458 | 0.563 | 0.564 |
| RO | crossrail_switch_w0.5 | 464 | 1.000 | 1.084 | 461,120 | 1.099 | 1.099 |

Interpretation:

- ECMP seed/port mismatch is not the main issue. `ecmp_ns3ish` changes ZCube JCT only from 166 to 165.
- Global switch-switch scaling is too blunt. It helps ZCube but destroys the RO guardrail by reducing RO JCT from 464 to 240, far below NS3's 428.
- The cross-rail switch-switch weighted sharing knob is much better aligned:
  - ZCube improves from 166 to 90 and cross-rail p95 / NS3 improves from 2.072 to 1.364.
  - Meta improves from 166 to 149 and cross-rail p95 / NS3 improves from 2.058 to 1.307.
  - RO is unchanged because RO has no physical cross-server cross-rail legs after PXN decomposition.
- This supports a more specific model change: FlowSim should not globally relax fabric links; it should account for multipath/statistical sharing primarily for physical cross-rail switch-switch traffic, while preserving RO's PXN-induced same-rail/same-server bottlenecks.

### Cross-Rail Sharing Weight Grid

A targeted grid was then run for `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT` on the same 15% fault samples. The first pass used `0.4, 0.5, 0.6, 0.75, 1.0`; a second low-weight pass added `0.25, 0.3, 0.35, 0.45`.

Detailed outputs:

- `flowsim_sharing_weight_grid/flowsim_sharing_weight_grid_summary.csv`
- `flowsim_sharing_weight_grid/flowsim_sharing_weight_grid_detailed_summary.csv`
- `flowsim_sharing_weight_grid/flowsim_sharing_weight_grid_detailed_summary.md`

Summary:

| Topology | Weight | JCT | JCT / serial | JCT / NS3 | p95 cross-rail / NS3 | p95 same-rail / NS3 |
|---|---:|---:|---:|---:|---:|---:|
| Meta | 0.25 | 149 | 0.898 | 1.104 | 1.230 | 1.244 |
| Meta | 0.3 | 149 | 0.898 | 1.104 | 1.245 | 1.259 |
| Meta | 0.35 | 149 | 0.898 | 1.104 | 1.248 | 1.262 |
| Meta | 0.4 | 149 | 0.898 | 1.104 | 1.263 | 1.277 |
| Meta | 0.45 | 149 | 0.898 | 1.104 | 1.247 | 1.262 |
| Meta | 0.5 | 149 | 0.898 | 1.104 | 1.307 | 1.322 |
| Meta | 0.6 | 149 | 0.898 | 1.104 | 1.454 | 1.471 |
| Meta | 0.75 | 149 | 0.898 | 1.104 | 1.672 | 1.692 |
| Meta | 1.0 | 166 | 1.000 | 1.230 | 2.058 | 2.082 |
| ZCube | 0.25 | 74 | 0.446 | 1.156 | 1.309 | 1.335 |
| ZCube | 0.3 | 72 | 0.434 | 1.125 | 1.285 | 1.310 |
| ZCube | 0.35 | 76 | 0.458 | 1.188 | 1.346 | 1.372 |
| ZCube | 0.4 | 75 | 0.452 | 1.172 | 1.281 | 1.306 |
| ZCube | 0.45 | 83 | 0.500 | 1.297 | 1.328 | 1.353 |
| ZCube | 0.5 | 90 | 0.542 | 1.406 | 1.364 | 1.391 |
| ZCube | 0.6 | 106 | 0.639 | 1.656 | 1.530 | 1.334 |
| ZCube | 0.75 | 129 | 0.777 | 2.016 | 1.831 | 1.460 |
| ZCube | 1.0 | 166 | 1.000 | 2.594 | 2.072 | 1.829 |
| RO | 0.25 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.3 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.35 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.4 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.45 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.5 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.6 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 0.75 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |
| RO | 1.0 | 464 | 1.000 | 1.084 | 1.099 | 1.099 |

Interpretation:

- The best targeted candidate is now a small range, not a single weight. `0.3` gives the best ZCube JCT match (`72` vs NS3 `64`, JCT/NS3 `1.125`), while `0.4` gives the best ZCube cross-rail p95 match (`1.281x` NS3).
- Meta is less sensitive at the low end. JCT stays at `149` for `0.25-0.75`, and the best cross-rail p95/NS3 is `1.230` at `0.25`. The remaining Meta gap is likely not removable by this switch-switch-only weight because same-server and GPU-switch effects still dominate part of the tail.
- RO is unchanged across the whole tested range, including `0.25`. This is the desired guardrail behavior and confirms that the scoped physical-cross-rail switch-switch weight does not accidentally relax RO's PXN-decomposed same-rail/same-server bottlenecks.
- For the next reduced multi-rate sweep, the defensible candidates are `0.3` and `0.4`. `0.3` prioritizes JCT matching for ZCube; `0.4` is slightly more conservative and better on ZCube cross-rail p95.

### Reduced Multi-Rate Weight Sweep

A reduced multi-rate FlowSim sweep was then run for the two candidate weights:

- Topologies: Meta, ZCube, RO.
- Rates: `1%, 5%, 10%, 15%`.
- Samples: 10 seeds per rate.
- Workload: same 256-GPU all-to-all.

Outputs:

- `flowsim_256_alltoall_p01_p05_p10_p15_s10_crossrail_w03/random_link_failure_summary.csv`
- `flowsim_256_alltoall_p01_p05_p10_p15_s10_crossrail_w04/random_link_failure_summary.csv`
- `flowsim_crossrail_weight_reduced_comparison/flowsim_crossrail_weight_reduced_comparison.csv`
- `flowsim_crossrail_weight_reduced_comparison/flowsim_crossrail_weight_reduced_comparison.md`

Comparison:

| Topology | Rate | NS3 factor | Orig factor | w0.3 factor | w0.4 factor | NS3 JCT | Orig JCT | w0.3 JCT | w0.4 JCT |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Meta | 0.01 | 1.231 | 1.051 | 1.133 | 1.107 | 60.3 | 186.1 | 81.6 | 96.3 |
| Meta | 0.05 | 1.612 | 1.037 | 1.124 | 1.097 | 79.0 | 183.5 | 80.9 | 95.4 |
| Meta | 0.10 | 2.006 | 0.989 | 1.382 | 1.197 | 98.3 | 175.1 | 99.5 | 104.1 |
| Meta | 0.15 | 2.322 | 0.950 | 1.638 | 1.368 | 113.8 | 168.1 | 117.9 | 119.0 |
| ZCube | 0.01 | 1.145 | 1.538 | 1.538 | 1.538 | 53.8 | 49.2 | 49.2 | 49.2 |
| ZCube | 0.05 | 1.377 | 1.894 | 1.900 | 1.900 | 64.7 | 60.6 | 60.8 | 60.8 |
| ZCube | 0.10 | 1.732 | 3.013 | 2.716 | 2.712 | 81.4 | 96.4 | 86.9 | 86.8 |
| ZCube | 0.15 | 2.026 | 4.200 | 3.241 | 3.256 | 95.2 | 134.4 | 103.7 | 104.2 |
| RO | 0.01 | 1.093 | 1.520 | 1.520 | 1.520 | 79.8 | 82.1 | 82.1 | 82.1 |
| RO | 0.05 | 1.410 | 2.228 | 2.228 | 2.228 | 102.9 | 120.3 | 120.3 | 120.3 |
| RO | 0.10 | 2.040 | 3.356 | 3.356 | 3.356 | 148.9 | 181.2 | 181.2 | 181.2 |
| RO | 0.15 | 3.084 | 4.889 | 4.889 | 4.889 | 225.1 | 264.0 | 264.0 | 264.0 |

Interpretation:

- `w0.3` is the better reduced-sweep candidate. For Meta it is closer to NS3 than `w0.4` in both normalized factor and absolute JCT at all tested rates.
- ZCube is almost identical for `w0.3` and `w0.4` in the reduced sweep. Both reduce high-rate absolute JCT substantially: at 15%, original FlowSim is `134.4`, `w0.3` is `103.7`, and NS3 is `95.2`.
- ZCube normalized factors remain above NS3 because FlowSim's no-fault baseline is still much faster (`32`) than NS3's (`47`). The weight improves failed JCT but does not fix baseline normalization.
- RO is exactly unchanged, preserving the guardrail and confirming that the scoped weight does not affect RO's PXN-decomposed physical traffic.
- The best next candidate for a broader FlowSim-only fault-tolerance run is therefore `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`.

### Full w0.3 Sweep Result

A full FlowSim-only sweep finished with the selected candidate:

- Topologies: Meta, HPN, DeepSeek, ZCube, RO, ROFT.
- Rates: `1%-15%`.
- Samples: 10 seeds per rate.
- FlowSim policy: `--cross-rail-switch-switch-weight 0.3`
  (`FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`).
- Output: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full/random_link_failure_summary.csv`.
- Status/report: `flowsim_crossrail_w03_full_comparison/RUN_STATUS.md`.

All `900/900` samples completed, with no failed samples observed. The final comparison against NS3 is:

| Topology | Rates | Orig factor MAE | w0.3 factor MAE | Orig failed-JCT MAE | w0.3 failed-JCT MAE |
|---|---:|---:|---:|---:|---:|
| ROFT | 15 | 0.098 | 0.141 | 184.9 | 29.6 |
| HPN | 15 | 0.364 | 0.260 | 135.2 | 11.3 |
| DeepSeek | 15 | 0.142 | 0.142 | 178.8 | 178.8 |
| Meta | 15 | 0.845 | 0.529 | 87.4 | 4.5 |
| ZCube | 15 | 1.041 | 0.761 | 14.0 | 5.3 |
| RO | 15 | 1.103 | 1.103 | 24.0 | 24.0 |

Interpretation:

- Meta and HPN are consistent with the reduced sweep: `w0.3` is much closer to NS3 in absolute failed JCT and improves normalized factor MAE.
- DeepSeek is unchanged by the scoped cross-rail switch-switch policy because the targeted trace shows `0%` physical cross-rail rows; it is dominated by PXN same-server/same-rail legs and baseline absolute-time calibration.
- ZCube's low-rate absolute JCT was already close to NS3, but improvement grows in the higher rates; at 15%, original FlowSim is `134.4`, `w0.3` is `103.7`, and NS3 is `95.2`.
- RO is acting as the intended guardrail: all RO rates are unchanged by `w0.3`, confirming that the scoped physical cross-rail switch-switch policy does not relax RO's PXN-decomposed same-rail/same-server traffic.
- ROFT is the main caveat: `w0.3` greatly improves absolute failed JCT (`184.9` to `29.6` MAE), but normalized factor remains worse than original (`0.098` to `0.141` MAE). This confirms that absolute JCT and baseline-normalized factor can disagree when simulator baselines differ.
- The policy is therefore useful as a scoped statistical-sharing approximation for physical cross-rail switch-switch traffic, but it is not a complete model of NS3 normalized slowdown across all topologies.

## Artifacts

- Sample-level joined data:
  `diagnose_flowsim_ns3_mismatch/sample_level_joined.csv`
- Topology-level summary:
  `diagnose_flowsim_ns3_mismatch/topology_mismatch_summary.csv`
- Rate-level summary:
  `diagnose_flowsim_ns3_mismatch/rate_mismatch_summary.csv`
- Top mismatch samples:
  `diagnose_flowsim_ns3_mismatch/top_mismatch_samples.csv`
- Figures:
  `diagnose_flowsim_ns3_mismatch/path_stretch_vs_simulator_delta.png`
  `diagnose_flowsim_ns3_mismatch/simulator_delta_by_fault_rate.png`
  `diagnose_flowsim_ns3_mismatch/flowsim_pxn_split_vs_flowsim_factor.png`
  `diagnose_flowsim_ns3_mismatch/inter_server_pressure_vs_simulator_delta.png`
  `diagnose_flowsim_ns3_mismatch/local_nvswitch_pressure_vs_simulator_delta.png`
- Targeted FCT rerun script:
  `scripts/rerun_targeted_fct_mismatch.py`
- Targeted FCT analysis script:
  `scripts/analyze_targeted_fct_mismatch.py`
- Targeted FCT summaries:
  `targeted_fct_mismatch/targeted_fct_summary.csv`
  `targeted_fct_mismatch/targeted_fct_distribution_summary.csv`
  `targeted_fct_mismatch/targeted_fct_category_summary.csv`
  `targeted_fct_mismatch/targeted_fct_line_inflation_summary.csv`
  `targeted_fct_mismatch/targeted_fct_sample_rows.csv`
- Targeted FCT figures:
  `targeted_fct_mismatch/plots/targeted_fct_line_counts.png`
  `targeted_fct_mismatch/plots/targeted_fct_p95_by_category.png`
- Targeted monitor analysis script:
  `scripts/analyze_targeted_monitor_mismatch.py`
- Targeted monitor rerun:
  `targeted_monitor_mismatch_retry/targeted_fct_summary.csv`
  `targeted_monitor_mismatch_retry/targeted_monitor_overview.csv`
  `targeted_monitor_mismatch_retry/targeted_monitor_bw_summary.csv`
  `targeted_monitor_mismatch_retry/targeted_monitor_qlen_summary.csv`
  `targeted_monitor_mismatch_retry/targeted_monitor_rate_summary.csv`
  `targeted_monitor_mismatch_retry/targeted_monitor_send_summary.csv`
  `targeted_monitor_mismatch_retry/targeted_monitor_pfc_summary.csv`
- Targeted monitor figures:
  `targeted_monitor_mismatch_retry/targeted_monitor_peak_bw_by_link_category.png`
  `targeted_monitor_mismatch_retry/targeted_monitor_peak_queue_by_link_category.png`
- Targeted monitor FCT reanalysis:
  `targeted_monitor_mismatch_retry/fct_analysis/targeted_fct_line_inflation_summary.csv`
  `targeted_monitor_mismatch_retry/fct_analysis/targeted_fct_category_summary.csv`
- Baseline monitor runner:
  `scripts/rerun_baseline_monitor_mismatch.py`
- Baseline monitor results:
  `targeted_monitor_baseline/targeted_fct_summary.csv`
  `targeted_monitor_baseline/targeted_monitor_overview.csv`
  `targeted_monitor_baseline/targeted_monitor_bw_summary.csv`
  `targeted_monitor_baseline/targeted_monitor_qlen_summary.csv`
- Fault-vs-baseline comparison:
  `scripts/compare_targeted_monitor_baseline.py`
  `targeted_monitor_fault_vs_baseline.csv`
  `targeted_monitor_fault_vs_baseline_ratios.png`
- NS3 original-flow log metadata:
  `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h`
- NS3 original-flow analysis:
  `scripts/analyze_ns3_original_flows.py`
  `scripts/compare_ns3_original_flow_baseline.py`
  `scripts/compare_flowsim_ns3_original_fct.py`
  `scripts/summarize_flowsim_ns3_mechanisms.py`
  `scripts/summarize_flowsim_pxn_timing.py`
  `targeted_original_flow_mismatch/ns3_original_flow_line_summary.csv`
  `targeted_original_flow_mismatch/ns3_original_flow_category_summary.csv`
  `targeted_original_flow_mismatch/ns3_original_flow_pattern_summary.csv`
  `targeted_original_flow_mismatch/flowsim_ns3_original_fct_comparison.csv`
  `baseline_original_flow/ns3_original_flow_line_summary.csv`
  `baseline_original_flow/ns3_original_flow_category_summary.csv`
  `baseline_original_flow/ns3_original_flow_pattern_summary.csv`
  `ns3_original_flow_fault_vs_baseline.csv`
  `flowsim_ns3_mechanism_summary.csv`
  `flowsim_ns3_mechanism_summary.md`
- FlowSim PXN timing smoke:
  `flowsim_pxn_timing_smoke/flowsim_pxn_timing_summary.csv`
  `flowsim_pxn_timing_smoke/flowsim_pxn_timing_summary.md`
- FlowSim bottleneck tracing:
  `scripts/analyze_flowsim_bottleneck_trace.py`
  `flowsim_bottleneck_trace/deepseek/bottleneck_trace.csv`
  `flowsim_bottleneck_trace/meta/bottleneck_trace.csv`
  `flowsim_bottleneck_trace/ro/bottleneck_trace.csv`
  `flowsim_bottleneck_trace/zcube/bottleneck_trace.csv`
  `flowsim_bottleneck_trace/flowsim_bottleneck_trace_summary.csv`
  `flowsim_bottleneck_trace/flowsim_bottleneck_trace_summary.md`
- FlowSim PXN-leg calibration:
  `scripts/run_flowsim_pxn_leg_calibration.py`
  `flowsim_pxn_leg_calibration_smoke/pxn_leg_calibration_summary.csv`
  `flowsim_pxn_leg_calibration_smoke/pxn_leg_calibration_summary.md`
- DeepSeek NS3 monitor/original-flow check:
  `targeted_deepseek_monitor/targeted_fct_summary.csv`
  `targeted_deepseek_monitor/targeted_monitor_overview.csv`
  `targeted_deepseek_monitor/targeted_monitor_bw_summary.csv`
  `targeted_deepseek_monitor/targeted_monitor_qlen_summary.csv`
  `targeted_deepseek_monitor/targeted_monitor_rate_summary.csv`
  `targeted_deepseek_monitor/targeted_monitor_send_summary.csv`
  `targeted_deepseek_monitor_baseline/targeted_fct_summary.csv`
  `targeted_deepseek_monitor_baseline/targeted_monitor_overview.csv`
  `targeted_deepseek_monitor_comparison/targeted_monitor_fault_vs_baseline.csv`
  `targeted_deepseek_original_flow/ns3_original_flow_category_summary.csv`
  `targeted_deepseek_original_flow_baseline/ns3_original_flow_category_summary.csv`
- DeepSeek/ROFT baseline original-flow FCT comparison:
  `baseline_deepseek_roft_fct_w03_pxn075/targeted_fct_summary.csv`
  `baseline_deepseek_roft_fct_w03_pxn075/ns3_original_flow_category_summary.csv`
  `baseline_deepseek_roft_fct_w03_pxn075/flowsim_ns3_original_fct_comparison.csv`
- FlowSim baseline hop-knob smoke:
  `flowsim_baseline_hop_knob_smoke/baseline_hop_knob_smoke_summary.csv`
  `flowsim_baseline_hop_knob_smoke/baseline_hop_knob_smoke_summary.md`
  `flowsim_baseline_hop_knob_grid/baseline_hop_knob_combined_summary.csv`
  `flowsim_baseline_hop_knob_grid/baseline_hop_knob_grid_summary.md`
  `flowsim_targeted_hop4w025_directw022_comparison/targeted_hop4w025_directw022_vs_previous_ns3_detail.csv`
  `flowsim_targeted_hop4w025_directw022_comparison/targeted_hop4w025_directw022_vs_previous_ns3_aggregate.csv`
  `flowsim_targeted_hop4w025_directw022_comparison/targeted_hop4w025_directw022_summary.md`
  `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_hop4w020_directw020_vs_candidate_previous_ns3_detail.csv`
  `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_hop4w020_directw020_vs_candidate_previous_ns3_aggregate.csv`
  `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_hop4w020_directw020_summary.md`
  `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_error_by_path_stretch.csv`
  `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_error_by_path_stretch.md`
- FlowSim sharing experiments:
  `scripts/summarize_flowsim_sharing_experiments.py`
  `scripts/run_flowsim_sharing_weight_grid.py`
  `scripts/summarize_flowsim_sharing_weight_grid.py`
  `scripts/compare_flowsim_weight_reduced_sweeps.py`
  `flowsim_sharing_smoke/flowsim_sharing_experiment_summary.csv`
  `flowsim_sharing_smoke/flowsim_sharing_experiment_summary.md`
  `flowsim_sharing_weight_grid_smoke/flowsim_sharing_weight_grid_summary.csv`
  `flowsim_sharing_weight_grid/flowsim_sharing_weight_grid_summary.csv`
  `flowsim_sharing_weight_grid/flowsim_sharing_weight_grid_detailed_summary.csv`
  `flowsim_sharing_weight_grid/flowsim_sharing_weight_grid_detailed_summary.md`
  `flowsim_256_alltoall_p01_p05_p10_p15_s10_crossrail_w03/random_link_failure_summary.csv`
  `flowsim_256_alltoall_p01_p05_p10_p15_s10_crossrail_w04/random_link_failure_summary.csv`
  `flowsim_crossrail_weight_reduced_comparison/flowsim_crossrail_weight_reduced_comparison.csv`
  `flowsim_crossrail_weight_reduced_comparison/flowsim_crossrail_weight_reduced_comparison.md`
  `scripts/plot_flowsim_policy_fault_comparison.py`
  `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full/random_link_failure_summary.csv`
  `flowsim_crossrail_w03_full_comparison/RUN_STATUS.md`
  `flowsim_crossrail_w03_full_comparison/flowsim_crossrail_w03_full.md`
  `flowsim_crossrail_w03_full_comparison/flowsim_crossrail_w03_full_detail.csv`
  `flowsim_crossrail_w03_full_comparison/flowsim_crossrail_w03_full_aggregate.csv`
  `flowsim_crossrail_w03_full_comparison/plots/flowsim_policy_vs_ns3_full_normalized_jct.png`
  `flowsim_crossrail_w03_full_comparison/plots/flowsim_policy_vs_ns3_full_failed_jct.png`
  `flowsim_crossrail_w03_full_comparison/plots/flowsim_policy_vs_ns3_full_data.csv`

## Current Follow-Up State

1. Treat `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3` as the current best experimental FlowSim policy.
2. `w0.3` is now exposed in the fault-tolerance runner as `--cross-rail-switch-switch-weight 0.3`, with a CSV `flowsim_policy` label.
3. Keep reporting both normalized factors and absolute failed JCT, because ZCube and ROFT show that these two views can disagree when baselines differ.
4. Treat DeepSeek as a separate PXN-leg/baseline calibration case, not a cross-rail switch-switch sharing case.
5. Do not use a global same-rail switch-switch multiplier as the fix: it helps DeepSeek absolute JCT but overshoots RO badly.
6. DeepSeek NS3 monitor/original-flow reconstruction is complete; it shows no PFC and only mild switch-switch queue growth, unlike RO.
7. Full PXN-leg overlap was tested and is not sufficient: it leaves DeepSeek far above NS3 and worsens RO's normalized factor even though RO's failed JCT gets closer.
8. A PXN-only same-rail switch-switch weight was implemented as `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT`. The smoke test makes `w=0.75` a candidate for broader validation, while `w=0.5` is too aggressive for RO.
9. The main FlowSim fault runner now exposes this knob as `--pxn-same-rail-switch-switch-weight` and supports `--resume`.
10. The six-topology `w0.3 + pxn_same_rail_w0.75` full sweep is complete: `900/900` successful fault samples.
11. Meta, HPN, DeepSeek, Zcube, RO, and ROFT are all complete for `1%..15%`, `10/10` samples per rate.
12. RO aggregate over the four guardrail rates improves under `w=0.75`, but RO `15%` undershoots NS3 in absolute JCT; this makes lighter weights worth checking before another multi-sample run.
13. The lighter DeepSeek/RO calibration for `w=0.95/0.90/0.85/0.75` is complete. It made `w=0.85` the gentlest plausible compromise, and the DeepSeek/RO guardrail sweep for `w=0.85` is also complete.
14. Current `w=0.85` evidence: DeepSeek is worse than `w=0.75` in both absolute JCT and factor over all four guardrail rates; RO is slightly better than `w=0.75` over its four guardrail rates. The combined DeepSeek+RO guardrail still favors `w=0.75`, so keep the full six-topology run on `w=0.75`.
15. Keep documenting the model as a statistical-sharing approximation, not a claim that physical link bandwidth changed.
16. The plotting script now supports `--policy-series-label`, and the current complete-only `w0.75` figures are in `flowsim_w03_pxn075_comparison/plots/`.
17. In the current full sweep comparison, RO `1%..15%` improves in both views: absolute failed-JCT MAE improves (`24.03 -> 6.64`) and normalized factor MAE improves (`1.103 -> 1.086`). RO `15%` still undershoots NS3 in absolute JCT (`206.7` vs `225.1`), so `w=0.75` remains a strong uniform candidate but not a perfect RO high-rate calibration.
18. ROFT `1%..15%` also improves in both views: normalized factor MAE improves (`0.141 -> 0.069`) and absolute failed-JCT MAE improves (`29.6 -> 23.9`). The absolute gain is modest, but all targeted guardrail checkpoints match the full sweep.
19. The residual mismatch is now split into baseline and fault-response tracks in `FLOWSIM_W03_PXN075_RESIDUAL_DIAGNOSIS.md`: DeepSeek/ROFT are mostly baseline-dominated, while Meta/Zcube/RO still need normalized fault-response analysis.
20. A ROFT no-fault NS3 monitor rerun was added under `targeted_roft_monitor_baseline_pxn075/`. It confirms ROFT baseline is direct cross-rail (`split_original_flows=0`, `physical_cross_rail_rows=55552`) with no PFC, so ROFT's remaining baseline gap is not a PXN-decomposition issue.
21. DeepSeek/ROFT baseline original-flow FCT comparison was added under `baseline_deepseek_roft_fct_w03_pxn075/`. DeepSeek remains much slower in FlowSim after grouping NS3 physical PXN legs back to original flows (`106-111us` FlowSim p95 vs about `40.5us` NS3 grouped p95), while ROFT's remaining direct-fabric p95 gap is smaller (`63.8us` FlowSim vs `47-48us` NS3). This makes the next baseline fix topology/path-class specific: PXN same-rail sharing for DeepSeek, direct cross-rail sharing for ROFT.
22. The m4 FlowSim backend now exposes experimental path-class controls: `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT` and hop-scoped overrides such as `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4`. Baseline smoke shows DeepSeek improves from `113.903us` to `73.063us` with PXN same-rail hop4 `w=0.4`, while the RO guardrail stays at `43.984us`; ROFT improves from `66.935us` to `59.410us` with direct cross-rail `w=0.25`.
23. Baseline grid selects the next targeted candidates: DeepSeek hop4 `w=0.25` gives `55.581us` vs NS3 `51us`, and ROFT direct cross-rail `w=0.22` gives `54.888us` vs NS3 `55us`. RO remains unchanged at `43.984us` under hop4 `w=0.30`, so the next step should be a targeted FlowSim fault sweep for DeepSeek/ROFT plus RO guardrail before any full six-topology rerun.
24. The targeted fault sweep for DeepSeek/ROFT/RO at `1%`, `5%`, `10%`, and `15%` completed `36/36` samples. The candidate improves absolute failed-JCT MAE for DeepSeek (`115.73 -> 15.51`) and ROFT (`24.35 -> 8.57`), but worsens their normalized factor MAE. RO does the opposite: factor MAE improves (`1.061 -> 0.679`), but absolute failed-JCT MAE worsens (`8.60 -> 25.43`). This confirms baseline calibration and fault-response calibration should stay separate.
25. The FlowSim fault runner now supports separate failed-run overrides through `--fault-*` parameters. The first fault-only correction (`fault hop4=0.20`, `fault direct=0.20`) completed another `36/36` targeted samples and improves DeepSeek and ROFT versus the baseline-calibrated candidate in both absolute failed-JCT MAE and factor MAE. RO remains the guardrail conflict: factor improves, but absolute failed-JCT MAE worsens further. This points to a topology/path-class- or path-stretch-aware correction rather than a global failed-run speedup.
26. Path-stretch diagnosis confirms that DeepSeek and ROFT residual errors grow with path stretch after fault-only correction (`corr=+0.973/+0.879` for failed-JCT error), while RO has the opposite absolute-JCT direction (`corr=-0.851`) despite high factor error. The next correction should target DeepSeek/ROFT high-stretch failures first and should not be applied globally to RO.
27. The runner now supports conditional high-stretch failed-run overrides using `fault_env_class`. The first high-stretch sweep (`threshold=1.03`, DeepSeek/ROFT only, high-stretch `hop4=0.16/direct=0.18`) completed `36/36` samples. It barely changes DeepSeek (`failed-JCT MAE 12.59 -> 12.34`, factor MAE `0.110 -> 0.105`), slightly worsens ROFT (`5.98 -> 6.23`, factor `0.109 -> 0.113`), and leaves RO unchanged. Therefore ROFT should stay on the fault-only policy for now.
28. A DeepSeek-only sensitivity sweep shows the hop4 control is non-monotonic under faulted high-stretch conditions: `hop4=0.05` improves DeepSeek `15%` (`133.0us -> 130.7us`) but worsens `10%` (`109.7us -> 112.3us`). The best current composite is therefore a stricter DeepSeek threshold (`path_stretch >= 1.04`) that applies `hop4=0.05` only to DeepSeek `15%`-like samples and leaves DeepSeek `10%`, ROFT, and RO on fault-only. This composite improves DeepSeek failed-JCT MAE `12.59 -> 12.01` and factor MAE `0.110 -> 0.099`, while ROFT/RO remain unchanged.
29. The bottleneck trace now records PXN/class/weight fields. A DeepSeek `10%` seed `1` trace comparing fault-only `hop4=0.20` against `hop4=0.05` confirms the non-monotonic mechanism: switch-switch bottleneck rows fall (`30.3% -> 21.0%`), but GPU-switch bottleneck rows rise (`17.1% -> 26.4%`), and the p99 tail is already entirely local NVSwitch/GPU-switch in both runs. This means further lowering same-rail switch-switch weight is the wrong next lever; the remaining model mismatch is in PXN leg overlap/local-leg contention.
30. FlowSim now has an experimental middle PXN timing mode, `FLOWSIM_PXN_TIMING=local_pipeline`, with `FLOWSIM_PXN_LOCAL_PIPELINE_DELAY_NS` controlling staggered leg launch. DeepSeek seed `1` full 256 all-to-all confirms the direction: at `delay=6000ns`, `10%` improves from `107us` to `100us` versus NS3 `93us`, and `15%` improves from `123us` to `105us`, exactly matching NS3 `105us`. A too-small delay (`3000ns`) timed out in the 64KiB smoke, so this should be treated as a calibrated timing model, not unconditional full overlap.
31. The calibrated `local_pipeline d6000` guardrail sweep completed `36/36` samples for DeepSeek, ROFT, and RO at `1%/5%/10%/15%`, seeds `1..3`. Failed-JCT MAE improves versus serial fault-only on all three tested topologies: DeepSeek `12.59 -> 4.39`, ROFT `5.98 -> 2.35`, and RO `18.65 -> 12.32`. Factor MAE also improves slightly for all three, but RO remains poor (`0.749 -> 0.698`) because its FlowSim baseline is still too low (`49us` vs NS3 `73us`). Therefore `local_pipeline d6000` is a strong PXN timing candidate, but not a complete RO factor fix.
32. The remaining-topology `local_pipeline d6000` sweep also completed `36/36` samples for Meta, HPN, and Zcube at the same four rates and seeds. The combined six-topology `s3` comparison improves overall failed-JCT MAE from `28.72` to `4.68` and factor MAE from `0.479` to `0.351` versus the previous complete `w0.3 + pxn_same_rail_w0.75` policy. Remaining weaknesses are concentrated in RO and Zcube normalization: Zcube failed JCT is close but baseline is too low, while RO absolute MAE is slightly worse than the previous full policy even though factor improves.
33. The full six-topology `local_pipeline d6000` sweep under `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/` completed `900/900` successful samples. A reusable comparison script was added as `scripts/compare_flowsim_partial_full_sweep.py`. On all `90` topology-rate groups, local-pipeline improves combined failed-JCT MAE (`28.34 -> 6.40`) and combined factor MAE (`0.487 -> 0.320`) versus the previous complete `w0.3 + pxn_same_rail_w0.75` policy. The main remaining conflict is RO: factor MAE improves (`1.197 -> 0.498`) but absolute failed-JCT MAE worsens (`6.86 -> 17.82`) with a systematic fast bias. DeepSeek, HPN, ROFT, and Zcube absolute JCT all improve materially; Meta is a smaller metric tradeoff where absolute JCT is slightly worse but factor is better.
34. New comparison artifacts:
  - `scripts/compare_targeted_fault_policies.py`
  - `scripts/compare_flowsim_partial_full_sweep.py`
  - `flowsim_targeted_highstretch_hop4w016_directw018_comparison/targeted_highstretch_fault_comparison.md`
  - `flowsim_deepseek_highstretch_hop4w005_comparison/deepseek_highstretch_hop4w005_comparison.md`
  - `flowsim_deepseek_highstretch_hop4w005_threshold104_composite/deepseek_highstretch_hop4w005_threshold104_composite_comparison.md`
  - `flowsim_targeted_composite_deepseek_h005_t104_roft_ro_faultonly/targeted_composite_deepseek_h005_t104_roft_ro_faultonly_comparison.md`
  - `flowsim_bottleneck_trace_deepseek_p10_seed1_h020_vs_h005/flowsim_bottleneck_trace_summary.md`
  - `flowsim_pxn_local_pipeline_smoke_64k/`
  - `flowsim_256_alltoall_local_pipeline_d6000_deepseek_seed1_p10_p15/random_link_failure_raw.csv`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_deepseek_roft_ro_p01_p05_p10_p15_s3/local_pipeline_d6000_vs_serial_ns3.md`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_deepseek_roft_ro_p01_p05_p10_p15_s3/local_pipeline_d6000_vs_serial_ns3_detail.csv`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_deepseek_roft_ro_p01_p05_p10_p15_s3/local_pipeline_d6000_vs_serial_ns3_aggregate.csv`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_meta_hpn_zcube_p01_p05_p10_p15_s3/random_link_failure_raw.csv`
  - `flowsim_local_pipeline_d6000_six_topology_p01_p05_p10_p15_s3_comparison/six_topology_local_pipeline_d6000_comparison.md`
  - `flowsim_local_pipeline_d6000_six_topology_p01_p05_p10_p15_s3_comparison/six_topology_local_pipeline_d6000_detail.csv`
  - `flowsim_local_pipeline_d6000_six_topology_p01_p05_p10_p15_s3_comparison/six_topology_local_pipeline_d6000_aggregate.csv`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/RUN_STATUS.md`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/PARTIAL_COMPARISON.md`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/partial_comparison_completed_groups.csv`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/FULL_COMPARISON.md`
  - `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/full_comparison_completed_groups.csv`
