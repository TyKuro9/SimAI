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
- `bin/SimAI_htsim -w <workload> -n <topology> -c <config> -o <result-dir> -r single|ecmp|spray_rr|spray_incremental|spray_oblivious|spray_plb|spray_reps`
- `HTSIM_ROUTE_STRATEGY=single|ecmp|spray_rr|spray_incremental|spray_oblivious|spray_plb|spray_reps`
- `HTSIM_LINK_BW_GBPS=<gbps>` for the ASTRA-facing htsim completion estimator.
- `HTSIM_FLOW_LEVEL=1` to force the legacy flow-level completion estimator.
- `HTSIM_MAX_PATHS=<N>` to cap shortest-path route enumeration for packet-level ECMP/Spray; default is 16.
- `HTSIM_FLOW_RECLAIM_BATCH=<N>` to tune completed packet-level RoCE flow owner reclamation. The default is 262144 completed flows of grace before an individual completed flow can be freed.
- `HTSIM_ROCE_VERBOSE=1` to re-enable native htsim RoCE per-flow start/finish stdout.

## Current Implementation Notes

- htsim is a git submodule fixed to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- The Broadcom submodule is kept at the upstream pin. Native htsim RoCE spray changes are stored in `astra-sim-alibabacloud/build/simai_htsim/htsim_roce_spray.patch` and `astra-sim-alibabacloud/build/simai_htsim/build.sh` applies the patch before compiling if the checked-out submodule has not already been patched.
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
  - `spray_incremental`: explicit alias for deterministic round-robin/incremental packet spraying.
  - `spray_oblivious`: deterministic per-flow RNG chooses a path independently for each data packet.
  - `spray_plb` / `plb`: source-side PLB-style strategy that keeps one active path and reroutes it when NACK or RTT-above-base feedback marks the path congested.
  - `spray_reps` / `reps`: source-side REPS-inspired strategy that explores paths in the first window, then recycles a bounded FIFO of paths that recently received good ACK/RTT feedback; falls back to random path selection when no good path is cached.
- htsim native `datacenter/htsim_roce` now accepts multi-path strategies such as `-strat perm` for RoCE instead of aborting.
- ACK/NACK packets still use the stable reverse route configured on the sink.
- These PLB/REPS strategies borrow the entropy/path-selection shape from the REPS EuroSys artifact but are implemented on the existing htsim RoCE source-route model. They are source-side approximations, not Tomahawk5 switch-port DLB.

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
  - drain final-phase `Ready`, `Executing`, and `Zombie` streams whose `phases_to_go` is empty through `Sys::proceed_to_next_vnet_baseline()`;
  - start final `Ready` streams that have no remaining phases and were not initialized because the htsim event queue emptied;
  - flush safe ASTRA workload/report events.
- Full dense workloads can end with the backend event queue empty while the final rank0 streams are still `Ready` or `Executing`, not `Zombie`. Draining only `Zombie` streams can let htsim exit 0 after `pass: 0 finished` but before `Workload::report()`, leaving `EndToEnd.csv` empty even with millions of FCT rows. The drain intentionally uses the existing `proceed_to_next_vnet_baseline()` path so DataSet notifiers and workload reporting stay normal.
- htsim marks completed streams `Dead` instead of deleting them immediately. Late htsim `PacketReceived`, `PacketSentFinshed`, or `PacketBundle` callbacks check `Dead` and drop themselves. This avoids dangling callbacks during final drain without changing NS-3 behavior.
- `HtsimNetwork::pass_front_end_report()` stops the htsim event loop once ASTRA has produced `EndToEnd.csv`. This avoids spending unbounded wall-clock time draining late duplicate/out-of-order packet events after the workload-level report, especially for random/adaptive packet-spray strategies.

## Verification

- `./scripts/build.sh -c htsim` builds `bin/SimAI_htsim`.
- A fresh checkout must initialize `extern/network_backend/htsim`; the htsim build script then applies the repo-owned RoCE spray patch to the submodule worktree before building `libhtsim.a`.
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
- htsim load-balancing strategy verification on 2026-06-23:
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim` completed.
  - Short dense Meta smoke with `/tmp/htsim_dense256_short10_1mib.txt` and `Meta_Topo_256g_8gps_400Gbps_A100` completed with non-empty `EndToEnd.csv` for `spray_incremental`, `spray_oblivious`, `spray_plb`, and `spray_reps`.
  - Final observed outputs after report-stop changes: `spray_oblivious` exited 0, wrote `EndToEnd.csv` with 15 lines and `fct.txt` with 144855 lines, and logged `SimAI-htsim finished`. Earlier same-run verification showed `spray_incremental`, `spray_plb`, and `spray_reps` also exited 0 with 15 `EndToEnd.csv` lines.
  - Pure random `spray_oblivious` produced more late packet tail before the report-stop fix; it should be treated as a stress/baseline strategy rather than the preferred large-run strategy.
- 256-scale short dense load-balancing comparison on 2026-06-24:
  - workload: `/tmp/htsim_dense256_short10_1mib.txt`
  - topology/config: `mytopo/Meta_Topo_256g_8gps_400Gbps_A100`, `myconfig/Meta256MoE.conf`
  - output: `experiments/htsim_results/csv/lb256_short_20260624_103219/summary.csv`
  - all tested strategies exited 0, logged `packet_level=1`, printed `SimAI-htsim finished`, and wrote 15-line `EndToEnd.csv` files.
  - finish times: `single=65392354`, `ecmp=65367340`, `spray_rr=65258013`, `spray_incremental=65258013`, `spray_plb=65392354`, `spray_reps=65804407`, `spray_oblivious=66622492`.
  - interpretation: deterministic round-robin was fastest in this small smoke; pure random `spray_oblivious` was slowest and remains best treated as a stress baseline.
- 256-scale first-100-layer dense load-balancing comparison on 2026-06-24:
  - workload: `/tmp/htsim_dense256_short100_1mib.txt`, generated from the normal dense workload by keeping the first 100 layers and capping communication sizes at 1 MiB.
  - topology/config: `mytopo/Meta_Topo_256g_8gps_400Gbps_A100`, `myconfig/Meta256MoE.conf`
  - output: `experiments/htsim_results/csv/lb256_short100_20260624_103638/summary.csv`
  - all 7 strategies exited 0, logged `packet_level=1`, printed `SimAI-htsim finished`, and wrote 105-line `EndToEnd.csv` files.
  - finish times: `single=622924125`, `ecmp=625586320`, `spray_rr=624261144`, `spray_incremental=624261144`, `spray_plb=622924125`, `spray_reps=625216793`, `spray_oblivious=626701375`.
  - interpretation: `single` and `spray_plb` tied fastest in this 100-layer smoke; `spray_rr`/`spray_incremental` matched exactly as intended; pure random `spray_oblivious` was slowest.
- Final-drain fix check on 2026-06-24:
  - The full dense Meta `spray_plb` rerun under `experiments/cross_backend_dense256_meta_20260624_114003/htsim_spray_plb_rerun_20260624_143409/` exited 0 with 36.0M FCT rows but empty `EndToEnd.csv`; the log showed `pass: 0 finished` followed by rank0 waiting for streams 1257/1259 in `Ready` state.
  - `Sys::drain_finished_streams()` was updated to drain exhausted `Ready`, `Executing`, and `Zombie` streams, matching the external FlowSim final-drain behavior.
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim` succeeded after the fix.
  - Short dense Meta `spray_plb` smoke `experiments/htsim_results/csv/final_drain_fix_smoke_20260624_195704/` exited 0, logged `all passes finished at time: 65392354`, wrote 15-line `EndToEnd.csv`, and wrote 144833 FCT rows.
  - A new full dense Meta packet PLB rerun is active in tmux session `dense256_meta_htsim_plb_fixed_20260624_195704`, output `experiments/cross_backend_dense256_meta_20260624_114003/htsim_spray_plb_fixed_20260624_195704/`.
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
- Low to medium for adding additional htsim route strategies when they only change `RoceSrc::choose_route()` and source-side feedback handling. Random/adaptive strategies can create more out-of-order packets and late ACK/NACK tail than deterministic round-robin.
