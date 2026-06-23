# Module: htsim Backend

## Responsibilities

- Provide a parallel htsim-based backend without replacing NS-3.
- Reuse existing SimAI workload/topology/config inputs at the frontend level.
- Drive ASTRA-sim callbacks through htsim `EventList` so `Workload::report()` can still produce `EndToEnd.csv`.
- Support RoCE route-strategy experiments, especially deterministic per-packet Spray.

## Main Files

- `extern/network_backend/htsim`
- `astra-sim-alibabacloud/astra-sim/network_frontend/htsim/HtsimAstra.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/htsim/HtsimNetwork.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/htsim/HtsimNetwork.h`
- `astra-sim-alibabacloud/build/simai_htsim/*`

## Key Interfaces

- `./scripts/build.sh -c htsim`
- `bin/SimAI_htsim`
- `bin/SimAI_htsim -w <workload> -n <topology> -c <config> -o <result-dir> -r single|ecmp|spray_rr`
- `HTSIM_ROUTE_STRATEGY=single|ecmp|spray_rr`
- `HTSIM_LINK_BW_GBPS=<gbps>` for the ASTRA-facing htsim completion estimator.
- `HTSIM_FLOW_LEVEL=1` to force the legacy flow-level completion estimator.
- `HTSIM_MAX_PATHS=<N>` to cap shortest-path route enumeration for packet-level ECMP/Spray; default is 16.
- `HTSIM_FLOW_RECLAIM_BATCH=<N>` to tune completed packet-level RoCE flow owner reclamation. The default is 262144 completed flows of grace before an individual completed flow can be freed.
- `HTSIM_ROCE_VERBOSE=1` to re-enable native htsim RoCE per-flow start/finish stdout.

## Current Implementation Notes

- htsim is a git submodule fixed to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- The ASTRA-facing htsim frontend defaults to packet-level RoCE for SimAI topology files. It parses the full SimAI edge list, creates one htsim FIFO `Queue` and one `Pipe` per directed link, and builds cached shortest-path `Route` sets between GPU pairs.
- The older flow-level estimator remains available only as a fallback or when `HTSIM_FLOW_LEVEL=1` is set. In that mode only the first-link bandwidth/latency summary is used.
- The frontend uses htsim `EventList` for scheduling and preserves the NS-3-style `sentHash`, `recvHash`, `expeRecvHash`, and `receiver_pending_queue` callback matching behavior.
- htsim RoCE `RoceSrc` now supports a vector of routes and selects the next route per data packet for Spray-style transmission.
- For ASTRA sends, `HtsimNetwork` creates a `RoceSrc/RoceSink` pair, installs a completion trigger, and calls the ASTRA send/recv callbacks when the RoCE flow is fully ACKed.
- Completed packet-level RoCE flow owners are not retained until `htsim_destroy()`. Each completed flow records a completion sequence and is eligible for reclamation only after at least `HTSIM_FLOW_RECLAIM_BATCH` later flow completions. This bounds memory for dense workloads while leaving enough grace for delayed duplicate/out-of-order packets that still reference the per-flow route endpoints.
- `RoceSrc` owns the per-flow spray route copies created by `set_paths()` and releases them in its destructor. This is important for long dense runs because `spray_rr` copies up to `HTSIM_MAX_PATHS` routes per flow.
- Route strategies:
  - `single`: first shortest path for each flow.
  - `ecmp`: one deterministic hash-selected shortest path per flow.
  - `spray_rr`: deterministic round-robin over the cached shortest-path set for data packets.
- htsim native `datacenter/htsim_roce` now accepts multi-path strategies such as `-strat perm` for RoCE instead of aborting.
- ACK/NACK packets still use the stable reverse route configured on the sink.

## Inputs

- workload file under `my_workloads/`
- SimAI topology file under `mytopo/`
- optional config file under `myconfig/`
- result directory for `EndToEnd.csv`

## Outputs

- `EndToEnd.csv` from ASTRA `Workload::report()`
- `fct.txt` from the htsim frontend, with columns:
  - `src dst tag flow_id size_bytes start_ns end_ns fct_ns route_strategy`
- htsim native logs when running `extern/network_backend/htsim/sim/datacenter/htsim_roce`
- `bin/SimAI_htsim` symlink after `./scripts/build.sh -c htsim`

## ASTRA Completion Semantics

- The htsim frontend builds as `HTSIM_BACKEND`, not `ANALYTI`; it excludes physical RDMA/MPI sources while keeping the normal ASTRA workload/report path active.
- htsim flow completion writes one `fct.txt` row and then triggers ASTRA receive/send callbacks.
- After the htsim `EventList` becomes empty, `HtsimAstra.cc` runs a progress loop:
  - drain `Zombie` streams through `Sys::proceed_to_next_vnet_baseline()`;
  - start final `Ready` streams that have no remaining phases and were not initialized because the htsim event queue emptied;
  - flush safe ASTRA workload/report events.
- htsim marks completed streams `Dead` instead of deleting them immediately. Late htsim `PacketReceived`, `PacketSentFinshed`, or `PacketBundle` callbacks check `Dead` and drop themselves. This avoids dangling callbacks during final drain without changing NS-3 behavior.

## Verification

- `./scripts/build.sh -c htsim` builds `bin/SimAI_htsim`.
- `make -C extern/network_backend/htsim/sim/datacenter htsim_roce` builds the native htsim RoCE datacenter binary.
- Native htsim smoke:
  - `extern/network_backend/htsim/sim/datacenter/htsim_roce -nodes 16 -topo extern/network_backend/htsim/sim/datacenter/topologies/leaf_spine_tiny.topo -tm extern/network_backend/htsim/sim/datacenter/connection_matrices/one.cm -strat perm -paths 2 -end 1000 -o /tmp/htsim_roce_smoke.log`
  - verified one RoCE flow completed.
- SimAI htsim smoke:
  - `bin/SimAI_htsim ... -r spray_rr -o /tmp/simai_htsim_smoke`
  - verified `/tmp/simai_htsim_smoke/EndToEnd.csv` had 1813 rows.
- 256 Meta MoE short verification on 2026-06-22:
  - workload: first 40 layers from `my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt`
  - command shape: `timeout 300s bin/SimAI_htsim -w /tmp/htsim_meta256_short.txt -n mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -c myconfig/Meta256MoE.conf -o experiments/htsim_results/csv/Meta256MoE_short_retest4 -r spray_rr`
  - result: exit 0, log contains `all passes finished at time: 108372751`, `EndToEnd.csv` has 45 lines, and `fct.txt` has 642561 lines.
  - current rerun output: `experiments/htsim_results/csv/Meta256MoE_verify_current` with the same completion marker and line counts.
- 256 dense packet-level smoke on 2026-06-22:
  - workload: `/tmp/htsim_dense256_short10_1mib.txt`, generated from the normal dense workload used by `run_256dense_flowsim.sh` with the first 10 layers and communication sizes capped at 1 MiB.
  - command shape: `timeout 180s bin/SimAI_htsim -w /tmp/htsim_dense256_short10_1mib.txt -n <topology> -c myconfig/Meta256MoE.conf -o experiments/htsim_results/csv/packet_dense256_short10_1mib_<topo>_<strategy> -r spray_rr|ecmp`
  - `spray_rr` all six 256 topologies completed with `EndToEnd.csv` 15 lines and `fct.txt` 144897 lines. Finish times: Meta `65258013`, HPN `65725585`, DeepSeek `65175141`, Zcube `65378481`, RO `65343242`, ROFT `65175141`.
  - `ecmp` all six 256 topologies completed with `EndToEnd.csv` 15 lines and `fct.txt` 144897 lines. Finish times: Meta `65367340`, HPN `65203996`, DeepSeek `65207842`, Zcube `65446799`, RO `65343242`, ROFT `65207842`.
  - Recheck output `experiments/htsim_results/csv/packet_dense256_short10_1mib_meta_spray_recheck` logged `SimAI begin run htsim route_strategy=spray_rr packet_level=1` and completed.
- Uncapped normal dense first-10-layer packet-level smoke on Meta timed out at 120s with no `EndToEnd.csv` rows yet but 14224 FCT rows. Treat uncapped/full dense packet-level 256 runs as long tmux jobs.
- htsim dense memory fix verification on 2026-06-23:
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim` completed.
  - Short dense Meta spray smoke with `/tmp/htsim_dense256_short10_1mib.txt` exited 0, logged `all passes finished at time: 65258013`, wrote `EndToEnd.csv` with 15 lines and `fct.txt` with 144897 lines, and reported maximum RSS about 390 MB.
  - Full normal dense Meta spray 300s window exited by timeout 124, did not segfault or OOM, reached forward `9/1262`, wrote `fct.txt` with 36840 lines, left `EndToEnd.csv` empty as expected for an incomplete workload, and reported maximum RSS about 5.0 GB.
  - Earlier unbounded retention attempt hit OOM at Meta forward about `180/1262` with RSS around 518 GB; immediate/small-batch reclamation caused dangling packet route references. The current design uses a large completion-count grace window to balance memory and route lifetime safety.
- NS-3 comparison build on 2026-06-22:
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c ns3`
  - result: build completed and linked `ns3.36.1-AstraSimNetwork-debug`.
  - plain `./scripts/build.sh -c ns3` may pick `/snap/bin/cmake` in this environment and fail before configuration; prefer the PATH override above if snap cmake appears.

## Modification Risk

- High if changing callback matching because upper-stack stream completion depends on send/recv handler ordering and `ncclFlowTag` propagation.
- Medium if changing topology parsing because existing SimAI topology files encode GPU/NVSwitch/switch counts in the first two lines.
- Medium if changing htsim RoCE route ownership because native htsim routes are pointer-heavy and route copies must append transport endpoints with `Route(orig, dst)`.
- Medium if increasing `HTSIM_MAX_PATHS` or uncapping dense workload sizes because packet-level event counts grow quickly.
- Medium if lowering `HTSIM_FLOW_RECLAIM_BATCH`: RoCE spray can leave delayed duplicate/out-of-order packets in queues after the cumulative ACK completes a flow, so reclaiming flow-owned route endpoints too early can crash in `Packet::sendOn()`.
- Medium if changing htsim final-drain behavior because late ASTRA callbacks can target streams that have already completed.
- Low for adding additional htsim route strategies when they only change `RoceSrc::choose_route()`.
