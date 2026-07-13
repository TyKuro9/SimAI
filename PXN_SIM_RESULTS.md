# PXN Simulation Results

## Context

Worktree: `/home/zty/Topo/SimAI_TyKuro9_pxn`

Branch: `pxn-routing`

Target scale: 256 GPUs, 8 GPUs per server.

Topologies:

- RO: `mytopo/RailOnly_256g_8gps_p16a0.5_400Gbps_H100`
- Zcube: `mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100`

Workloads:

- Smoke all-to-all EP: `my_workloads/synthetic_alltoall_ep_world_size256_tp2_ep16_64KiB.txt`
- Global all-to-all: `my_workloads/synthetic_alltoall_global_world_size256_1MiB.txt`

PXN switch:

- Enable: `AS_PXN_ENABLE=1`
- Disable: `AS_PXN_ENABLE=0`
- Policy override: `AS_PXN_POLICY=off|force|fallback|aggregate`
- Compatibility: if `AS_PXN_POLICY` is unset, `AS_PXN_ENABLE=1` keeps the old force-PXN behavior.

## Implemented Changes

FlowSim path:

- Added PXN split in the FlowSim network frontend.
- Verified implementation path: `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/FlowsimNetwork.cc`.
- Note: this PXN worktree does not currently contain the FlowSim frontend source file; the FlowSim runs below used the m4 tree binary.
- Added `AS_PXN_POLICY` support:
  - `off`: never split.
  - `force`: split all cross-host, cross-rail logical flows.
  - `fallback`: split only when the direct route is unavailable.
  - `aggregate`: currently equivalent to force at the frontend split layer.
- A logical cross-host, cross-rail flow `src -> dst` is physically sent as `src -> proxy -> dst`.
- The proxy is selected as the GPU on the source server with the destination rail:
  `proxy = src_server * gpus_per_server + dst_rail`.
- Upper layers still observe the original logical flow completion.
- PXN remote leg now pays the same `AS_SEND_LAT` startup delay as the first leg when `AS_SEND_LAT` is set.
- Added PXN summary counters printed at finish:
  `policy`, `split`, and `direct_cross_rail`.

NS3 path:

- Added PXN split in `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h`.
- Added the same `AS_PXN_POLICY` support as FlowSim.
- For PXN local leg `src -> proxy`, the code does not increment the upper-layer completion wait counters.
- When the local leg finishes, NS3 schedules the remote leg `proxy -> dst`.
- The remote leg completion is translated back to the original logical pair `src -> dst` before notifying AstraSim.
- `GLOBAL_T` is now respected from the config instead of being forced back to `1`.
- Added PXN summary counters printed at simulator teardown.

Tree flow tag fix:

- Updated `NcclTreeFlowModel.cc` to include `chunk_id` in non-ring tag calculation and to handle `PXN_REMOTE` initial receive readiness.

## Validation Results

### Smoke workload

| Simulator | Topology | PXN | Result | Total time |
|---|---:|---:|---|---:|
| FlowSim | RO | off | expected fail | missing direct cross-rail link |
| FlowSim | RO | on | pass | 2.661 |
| FlowSim | Zcube | off | pass | 4.830 |
| FlowSim | Zcube | on | pass | 4.814 |
| NS3 | RO | off | expected fail | `We assume at least one NIC is alive` |
| NS3 | RO | on | pass | 9.406 |
| NS3 | Zcube | off | pass | 7.443 |
| NS3 | Zcube | on | pass | 10.584 |

### Global all-to-all workload

| Simulator | Topology | PXN | Result | Total time | BusBW |
|---|---:|---:|---|---:|---:|
| FlowSim | RO | on | pass | 22.749 | 42.769 |
| FlowSim | Zcube | off | pass | 28.838 | 33.737 |
| FlowSim | Zcube | on | pass | 43.311 | 22.462 |
| NS3 | RO | on | pass | 57.872 | 16.810 |
| NS3 | Zcube | off | pass | 46.508 | 20.918 |
| NS3 | Zcube | on | pass | 47.981 | 20.276 |

RO direct is not included in global performance comparison because the smoke workload already proves that RO without PXN cannot carry cross-host cross-rail traffic.

## Policy Validation

Policy runs used:

- `AS_PXN_ENABLE=1`
- `AS_PXN_POLICY=fallback` or `AS_PXN_POLICY=aggregate`
- `AS_SEND_LAT=3`

`AS_PXN_ENABLE=1` is kept in these runs so the existing collective-layer PXN branches remain comparable with earlier PXN runs; `AS_PXN_POLICY` controls the network-frontend direct/proxy decision.

### Smoke policy behavior

| Simulator | Topology | Policy | Split | Direct cross-rail | Total time |
|---|---|---|---:|---:|---:|
| FlowSim | RO | fallback | 2304 | 0 | 5.661 |
| FlowSim | Zcube | fallback | 0 | 2304 | 7.830 |
| FlowSim | RO | aggregate | 2304 | 0 | 5.661 |
| FlowSim | Zcube | aggregate | 2304 | 0 | 7.814 |
| NS3 | RO | fallback | 2304 | 0 | 9.406 |
| NS3 | Zcube | fallback | 0 | 2304 | 7.937 |
| NS3 | RO | aggregate | 2304 | 0 | 9.406 |
| NS3 | Zcube | aggregate | 2304 | 0 | 10.584 |

This confirms the intended behavior:

- RO fallback uses PXN because direct cross-rail routing is unavailable.
- Zcube fallback keeps direct cross-rail routing.
- Aggregate keeps the old force-PXN frontend behavior.

### Global all-to-all policy behavior

| Simulator | Topology | Policy | Split | Direct cross-rail | Total time | BusBW |
|---|---|---|---:|---:|---:|---:|
| FlowSim | RO | fallback | 55552 | 0 | 49.213 | 19.768 |
| FlowSim | RO | aggregate | 55552 | 0 | 49.213 | 19.768 |
| FlowSim | Zcube | fallback | 0 | 55552 | 31.838 | 30.558 |
| FlowSim | Zcube | aggregate | 55552 | 0 | 46.311 | 21.007 |
| NS3 | RO | fallback | verified by FCT | 0 physical cross-rail | 57.872 | 16.810 |
| NS3 | Zcube | fallback | verified by FCT | 55552 physical cross-rail | 46.508 | 20.918 |
| NS3 | Zcube | aggregate | verified by FCT | 0 physical cross-rail | 47.981 | 20.276 |

NS3 global runs wrote `EndToEnd.csv` and FCT successfully. The processes were interrupted after result generation because the NS3 event loop can continue draining residual events for a long time on the global workload.

### NS3 policy FCT row check

| Case | FCT rows | Expected interpretation |
|---|---:|---|
| RO smoke fallback/aggregate | 6144 | 3840 logical rows + 2304 local proxy legs |
| Zcube smoke fallback | 3840 | direct logical rows only |
| Zcube smoke aggregate | 6144 | 3840 logical rows + 2304 local proxy legs |
| RO global fallback | 120832 | 65280 logical rows + 55552 local proxy legs |
| Zcube global fallback | 65280 | direct logical rows only |
| Zcube global aggregate | 120832 | 65280 logical rows + 55552 local proxy legs |

Note: FlowSim global RO policy results in this run are slower than the earlier FlowSim RO+PXN baseline in this file. The policy counters and NS3 results are internally consistent, but FlowSim should be re-baselined once its collective-layer PXN setting and `AS_SEND_LAT` convention are finalized.

## FCT Notes

FlowSim FCT records logical flows:

- Global all-to-all: 65280 rows for each completed run.
- PXN is applied inside the FlowSim network frontend, but the FCT row remains the logical `src -> dst` pair.
- Therefore FlowSim FCT still shows logical cross-host cross-rail pairs under PXN.

NS3 FCT records physical network segments:

- Zcube direct global: 65280 rows.
- RO+PXN global: 120832 rows.
- Zcube+PXN global: 120832 rows.

The increase from 65280 to 120832 is expected:

- Logical all-to-all pairs: `256 * 255 = 65280`
- Cross-host, cross-rail logical pairs: `55552`
- PXN adds one local proxy segment for those pairs.
- Physical segments: `65280 + 55552 = 120832`

Therefore, NS3 FCT under PXN is useful for verifying physical split behavior, but `EndToEnd.csv` should be used for logical workload performance comparison.

### NS3 physical FCT classification

| Case | FCT rows | same host | cross-host same rail | cross-host cross rail |
|---|---:|---:|---:|---:|
| RO smoke PXN | 6144 | 3072 | 3072 | 0 |
| Zcube smoke direct | 3840 | 768 | 768 | 2304 |
| Zcube smoke PXN | 6144 | 3072 | 3072 | 0 |
| RO global PXN | 120832 | 57344 | 63488 | 0 |
| Zcube global direct | 65280 | 1792 | 7936 | 55552 |
| Zcube global PXN | 120832 | 57344 | 63488 | 0 |

This confirms that NS3 PXN removes physical cross-rail traffic by converting every cross-host cross-rail logical flow into:

1. local leg: `src -> proxy` inside the source host;
2. remote leg: `proxy -> dst` on the destination rail.

## Interpretation

RO:

- Without PXN, RO cannot carry cross-host cross-rail traffic.
- With PXN, both FlowSim and NS3 run through.
- This matches the expected role of PXN for rail-only topology.
- The RO comparison here is RO+PXN, not RO direct.

Zcube:

- Zcube can route cross-rail traffic directly without PXN.
- With current implementation, enabling PXN forces cross-host cross-rail flows through the proxy path.
- This can hurt performance when direct Zcube paths already exist.
- In NS3 global all-to-all, Zcube+PXN is only slightly slower than Zcube direct.
- In FlowSim global all-to-all, Zcube+PXN is significantly slower than Zcube direct, which likely reflects FlowSim's simplified path/bandwidth model.

### Why FlowSim and NS3 Differ

The FlowSim and NS3 numbers should not be expected to match exactly.

FlowSim is a flow-level fluid model:

- It allocates bandwidth by max-min fair sharing on active links.
- It uses static link bandwidth and latency from the topology file.
- It does not model packet-by-packet RDMA dynamics, ACK/CNP feedback, ECN marking, PFC pause, queue occupancy evolution, or DCQCN/HPCC rate convergence.
- Under PXN, FlowSim keeps FCT as the original logical `src -> dst` flow, even though the physical send is split internally.

NS3 is a packet/RDMA model:

- It creates RDMA QPs and sends MTU-sized packets.
- It models QCN/DCQCN-style rate control, windows, ACK/CNP feedback, queueing, PFC, and packet headers.
- With PXN, NS3 FCT records physical segments, so PXN runs have more FCT rows than logical all-to-all flow count.
- The NS3 config parser currently forces `GLOBAL_T` to `1` after reading the config, so QPs use global max RTT/BDP values rather than the literal `GLOBAL_T 0` setting.

For logical workload performance, use `EndToEnd.csv`. For PXN split verification, use NS3 FCT row counts and physical src/dst classification.

### FlowSim vs NS3 gap diagnostics

The gap is not uniform across all cases. With the current policy runs:

| Case | FlowSim total time | NS3 total time | NS3 / FlowSim |
|---|---:|---:|---:|
| Zcube global fallback/direct | 31.838 | 46.508 | 1.46x |
| Zcube global aggregate/PXN | 46.311 | 47.981 | 1.04x |
| RO global fallback/PXN | 49.213 | 57.872 | 1.18x |
| Zcube smoke fallback/direct | 7.830 | 7.937 | 1.01x |
| Zcube smoke aggregate/PXN | 7.814 | 10.584 | 1.35x |
| RO smoke fallback/PXN | 5.661 | 9.406 | 1.66x |

This suggests three separate effects:

1. Zcube direct/fallback exposes the largest global-model gap.
   - FlowSim and NS3 both find direct cross-rail routes.
   - FlowSim finishes the global all-to-all at 31.838, while NS3 finishes at 46.508.
   - The smoke case is almost identical, so the gap appears only when many flows contend concurrently.

2. Zcube aggregate/PXN is already close at the workload level.
   - FlowSim: 46.311.
   - NS3: 47.981.
   - This means the PXN split itself is not the only source of mismatch.

3. RO+PXN still has a moderate gap.
   - FlowSim: 49.213.
   - NS3: 57.872.
   - This is consistent with NS3 charging packet/RDMA behavior and PXN remote-leg startup costs more explicitly.

FCT distribution also points to a tail-dynamics issue rather than a basic bandwidth/header mismatch:

| Case | Rows | FCT p50 | FCT p95 | FCT p99 | FCT max | Note |
|---|---:|---:|---:|---:|---:|---|
| FlowSim Zcube fallback | 65280 | 28.723 | 28.723 | 28.723 | 28.723 | highly synchronized max-min completion |
| NS3 Zcube fallback | 65280 | 29.109 | 38.883 | 41.251 | 49.372 | packet/RDMA queueing creates a long tail |
| FlowSim Zcube aggregate | 65280 | 38.215 | 43.196 | 43.196 | 43.196 | logical FCT only |
| NS3 Zcube aggregate | 120832 | 5.154 | 34.786 | 39.594 | 42.455 | physical FCT segments |
| FlowSim RO fallback | 65280 | 46.098 | 46.098 | 46.098 | 46.098 | logical FCT only |
| NS3 RO fallback | 120832 | 6.407 | 51.079 | 54.740 | 58.533 | physical FCT segments |

Code-level mismatch status after fixes:

- Fixed: NS3 used to read `GLOBAL_T` from config and then force `global_t = 1` in `network_frontend/ns3/common.h`. Configs with `GLOBAL_T 0` now use pair-specific RTT/BDP in `RdmaClientHelper`.
- Fixed: NS3 applies `AS_SEND_LAT` in every physical `SendFlowPhysical` call, including PXN remote legs. FlowSim now also schedules the PXN remote leg with the same `AS_SEND_LAT` delay before calling `FlowSim::Send(proxy, dst, ...)`.
- FlowSim uses max-min fair sharing over active chunks and recalculates at completion events. It does not model queue buildup, PFC pause, CNP/ECN feedback, or RDMA rate convergence.
- Remaining check: current NS3 PXN configs set `PACKET_PAYLOAD_SIZE 9000`, while FlowSim's serialization helper currently uses a fixed 1000B payload plus 48B header. This is separate from the two fixed mismatches and should be isolated in the next comparison.

Post-fix smoke verification:

| Case | FlowSim before | FlowSim after | NS3 after | Notes |
|---|---:|---:|---:|---|
| Zcube smoke fallback/direct | 7.830 | 7.830 | 7.443 | no PXN split; FlowSim unchanged, NS3 reflects real `GLOBAL_T 0` |
| Zcube smoke aggregate/PXN | 7.814 | 10.281 | 10.584 | PXN remote-leg startup is now charged in FlowSim |
| RO smoke fallback/PXN | 5.661 | 8.061 | 9.406 | PXN remote-leg startup is now charged in FlowSim |

Recommended next diagnostic runs:

1. Re-run the global all-to-all matrix after the two fixes.
   - Zcube fallback/direct will show how much the NS3 `GLOBAL_T` fix reduces the 1.46x gap.
   - Zcube aggregate/PXN and RO fallback/PXN will show the effect of FlowSim charging the second PXN startup delay.

2. Add optional FlowSim physical segment FCT logging.
   - Keep existing logical FCT for workload comparison.
   - Add physical rows for `src -> proxy` and `proxy -> dst`.
   - This makes PXN FCT comparable to NS3 physical FCT.

3. Align or parameterize FlowSim packet payload size.
   - Current NS3 smoke/global configs use `PACKET_PAYLOAD_SIZE 9000`.
   - FlowSim currently uses a fixed 1000B payload in its serialization-overhead helper.
   - Make this configurable before interpreting smaller residual gaps.

4. Create a direct-cross-rail-only Zcube workload.
   - Exclude same-host and same-rail flows.
   - If the gap grows, the main mismatch is direct cross-rail contention and packet/RDMA tail behavior.

5. Compare route/link utilization at the route level.
   - NS3 dimension utilization is near 100%, so the next useful signal is which links are hot and how flow paths are distributed.
   - Add FlowSim per-link active-flow/utilization dump for the same window.

### Why FlowSim RO+PXN Can Be Faster Than Zcube

In the current comparison, RO+PXN and Zcube direct are not equal-bandwidth alternatives:

- RO topology file: 304 network links at `400Gbps`, plus 256 local NVSwitch links at `3600Gbps`.
- Zcube topology file: 768 network links at `200Gbps`, plus 256 local NVSwitch links at `3600Gbps`.

With PXN, RO converts cross-host cross-rail logical traffic into:

1. a local `src -> proxy` leg through high-bandwidth NVSwitch/NVLink;
2. a remote `proxy -> dst` leg on the destination rail.

So in FlowSim, most RO+PXN remote bottlenecks are modeled on 400Gbps rail links, while Zcube direct cross-rail traffic uses 200Gbps network links. Since FlowSim is mostly a bandwidth-sharing model, this can make RO+PXN appear faster than Zcube direct even though Zcube has direct cross-rail reachability.

This does not mean RO direct is better than Zcube. RO direct still fails for cross-host cross-rail flows; the passing RO result depends on PXN.

## Next Steps

1. Add physical PXN segment logging for FlowSim:
   - Keep logical FCT for workload comparison.
   - Add optional physical segment FCT/log for direct/proxy verification.

2. Extend direct-vs-proxy route classification:
   - The frontend now counts split and direct cross-rail flows.
   - Add optional local proxy and remote rail segment counters separately.

3. Run fault experiments after path policy is stable:
   - Link fault should exclude NVSwitch/NVLink scale-up domain.
   - ToR fault should be single-ToR only under the current assumption.
   - Compare RO fallback behavior under link/ToR failures.

4. Clean worktree before commit:
   - Decide whether to keep generated `myconfig/pxn/` configs.
   - Decide whether to keep the copied `ns-3-alibabacloud` source in the worktree or initialize it as a real submodule checkout.
