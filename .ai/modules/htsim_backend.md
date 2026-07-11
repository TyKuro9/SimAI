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
- `bin/SimAI_htsim -w <workload> -n <topology> -c <config> -o <result-dir> -r single|ecmp|ns3_ecmp|spray_rr|spray_incremental|spray_oblivious|spray_plb|spray_reps`
- `HTSIM_ROUTE_STRATEGY=single|ecmp|ns3_ecmp|spray_rr|spray_incremental|spray_oblivious|spray_plb|spray_reps`
- `HTSIM_LINK_BW_GBPS=<gbps>` for the ASTRA-facing htsim completion estimator.
- `HTSIM_FLOW_LEVEL=1` to force the legacy flow-level completion estimator.
- `HTSIM_MAX_PATHS=<N>` to cap shortest-path route enumeration for packet-level ECMP/Spray; default is 16.
- `HTSIM_FLOW_RECLAIM_BATCH=<N>` to tune completed packet-level RoCE flow owner reclamation. The default is 262144 completed flows of grace before an individual completed flow can be freed.
- `HTSIM_ROCE_VERBOSE=1` to re-enable native htsim RoCE per-flow start/finish stdout.
- `HTSIM_DISABLE_FCT_OUTPUT=1` to skip `fct.txt` creation while preserving htsim flow-completion callbacks and `EndToEnd.csv` reporting.
- `HTSIM_WATCHDOG_EVENTS=<N>` to print htsim flow/event state every N processed htsim events. Pair with `HTSIM_WATCHDOG_DUMP_ASTRA=1`, `HTSIM_WATCHDOG_ASTRA_RANKS=<N>`, and `HTSIM_WATCHDOG_ASTRA_STREAMS=<N>` to dump unfinished ASTRA stream snapshots.
- `HTSIM_ROCE_TAIL_RTO=0|1` to override the default tail-loss RTO recovery setting. The default is enabled only for `ns3_ecmp`.
- `HTSIM_ROCE_MIN_RTO_US=<us>` to override the default minimum RTO used by the `ns3_ecmp` tail recovery path; the current default for `ns3_ecmp` is 100us, but the conservative tail recovery uses adaptive `_rto` lower-bounded by that value.
- `HTSIM_FINAL_DRAIN_RECOVERY=0|1` to disable/enable final-drain-only oldest-unacked recovery; default is enabled.
- `HTSIM_FINAL_DRAIN_RECOVERY_ROUNDS=<N>` to bound consecutive ACK-gated recovery rounds without a complete flow; a flow completion resets this budget and the default is 65536.
- `HTSIM_STALL_CHECK_EVENTS=<N>` to sample post-pass flow-completion and cumulative-ACK progress; default is 1048576 processed events.
- `HTSIM_STALL_NO_PROGRESS_CHECKS=<N>` to choose how many consecutive progress samples trigger Go-Back-N handoff; default is 8.

## Current Implementation Notes

- htsim is a git submodule fixed to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- The Broadcom submodule is kept at the upstream pin. Native htsim RoCE spray changes are stored in `astra-sim-alibabacloud/build/simai_htsim/htsim_roce_spray.patch` and `astra-sim-alibabacloud/build/simai_htsim/build.sh` applies the patch before compiling if the checked-out submodule has not already been patched.
- The ASTRA-facing htsim frontend defaults to packet-level RoCE for SimAI topology files. It parses the full SimAI edge list, creates one htsim FIFO `Queue` and one `Pipe` per directed link, and builds cached shortest-path `Route` sets between GPU pairs.
- Each cached route records its bottleneck link bandwidth. A packet-level `RoceSrc` is paced from its selected route: current same-server routes use 3600 Gbps, Meta scale-out routes use 400 Gbps, and each selected HPN scale-out route uses 200 Gbps.
- The older flow-level estimator remains available only as a fallback or when `HTSIM_FLOW_LEVEL=1` is set. In that mode only the first-link bandwidth/latency summary is used.
- The frontend uses htsim `EventList` for scheduling and preserves the NS-3-style `sentHash`, `recvHash`, `expeRecvHash`, and `receiver_pending_queue` callback matching behavior.
- htsim RoCE `RoceSrc` now supports a vector of routes and selects the next route per data packet for Spray-style transmission.
- For ASTRA sends, `HtsimNetwork` creates a `RoceSrc/RoceSink` pair, installs a completion trigger, and calls the ASTRA send/recv callbacks when the RoCE flow is fully ACKed.
- Completed packet-level RoCE flow owners are not retained until `htsim_destroy()`. Each completed flow records a completion sequence and is eligible for reclamation only after at least `HTSIM_FLOW_RECLAIM_BATCH` later flow completions. This bounds memory for dense workloads while leaving enough grace for delayed duplicate/out-of-order packets that still reference the per-flow route endpoints.
- `RoceSrc` owns the per-flow spray route copies created by `set_paths()` and releases them in its destructor. This is important for long dense runs because `spray_rr` copies up to `HTSIM_MAX_PATHS` routes per flow.
- Route strategies:
  - `single`: first shortest path for each flow.
  - `ecmp`: one deterministic hash-selected shortest path per flow. The complete flow remains pinned to that route, including on HPN's two-path scale-out topology.
  - `ns3_ecmp`: source-routed approximation of NS-3 switch-side ECMP; each flow builds a shortest forward route by hashing the flow key independently at each hop over next hops that move closer to the destination. ACK/NACK return traffic uses a stable reverse shortest path rather than a second independently hashed per-hop path.
  - `spray_rr`: deterministic round-robin over the cached shortest-path set for data packets.
  - `spray_incremental`: explicit alias for deterministic round-robin/incremental packet spraying.
  - `spray_oblivious`: deterministic per-flow RNG chooses a path independently for each data packet.
  - `spray_plb` / `plb`: source-side PLB-style strategy that keeps one active path and reroutes it when NACK or RTT-above-base feedback marks the path congested. It does not transmit concurrently on multiple paths, but it is not flow-pinned.
  - `spray_reps` / `reps`: source-side REPS-inspired strategy that explores paths in the first window, then recycles a bounded FIFO of paths that recently received good ACK/RTT feedback; falls back to random path selection when no good path is cached.
- htsim native `datacenter/htsim_roce` now accepts multi-path strategies such as `-strat perm` for RoCE instead of aborting.
- ACK/NACK packets still use the stable reverse route configured on the sink.
- `RoceSink` maintains a compressed map of received out-of-order byte intervals. It still NACKs a gap, but no longer discards later data; receipt of the missing range advances the cumulative ACK through every now-contiguous buffered interval. This is required by packet-level REPS/Spray on unequal-delay paths and avoids repeated Go-Back-N retransmission of data already delivered.
- `ns3_ecmp` also enables htsim RoCE tail RTO recovery by default. This compensates for htsim RoCE's lack of a real timeout path when a final/tail packet is dropped and no later packet exists to trigger a sink NACK. This is deliberately scoped to `ns3_ecmp` unless overridden by `HTSIM_ROCE_TAIL_RTO`.
- `spray_plb` formal runs keep `HTSIM_ROCE_TAIL_RTO=0`. After the final workload pass, `htsim_run()` samples flow-completion and sink cumulative-ACK progress while events are still executing. If neither changes for the configured window, only the active sources are switched from normal NACK Go-Back-N to final recovery.
- During a final-recovery campaign, newly created sources send their first packet normally and then join ACK-gated recovery. This preserves a nonzero cumulative-ACK starting point without letting each callback-created batch run another expensive Go-Back-N livelock cycle.
- `HtsimAstra` invokes `RoceSrc::recover_oldest_unacked()` once per unfinished flow and drains all resulting packet/ACK events before another recovery round. Recovery never rewinds `_highest_sent`; the consecutive-round budget resets whenever any flow completes.
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
- Set `HTSIM_DISABLE_FCT_OUTPUT=1` to skip creating/writing `fct.txt`; this leaves htsim flow-completion callbacks and ASTRA `EndToEnd.csv` reporting active.
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
- Short cross-simulator Dense256 Meta sanity comparison on 2026-06-26:
  - runner: `experiments/cross_backend_dense256_meta_20260624_114003/run_short_cross_sim_compare.sh 20260626_short10_1mib_r2`
  - workload: `/tmp/htsim_dense256_short10_1mib.txt`; topology/config: `Meta_Topo_256g_8gps_400Gbps_A100`, `myconfig/Meta256MoE.conf`
  - output: `experiments/cross_backend_dense256_meta_20260624_114003/short_cross_sim_20260626_short10_1mib_r2/summary.md`
  - htsim ECMP exited 0, logged `packet_level=1`, wrote 15-line `EndToEnd.csv`, finished at `65367340`, exposed comm `279`, and wrote 144813 FCT rows.
  - htsim `spray_rr` exited 0, logged `packet_level=1`, wrote 15-line `EndToEnd.csv`, finished at `65258013`, exposed comm `170`, and wrote 144865 FCT rows.
  - This is a sanity/trend matrix only; full route isolation still depends on the long htsim ECMP and htsim `spray_rr` runs under `experiments/cross_backend_dense256_meta_20260624_114003/`.
- NS-3-style htsim ECMP smoke on 2026-07-02:
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim` completed.
  - `timeout 180s bin/SimAI_htsim -w /tmp/htsim_dense256_short10_1mib.txt -n mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -c myconfig/Meta256MoE.conf -o experiments/htsim_results/csv/ns3_ecmp_short10_1mib_20260702_codex -r ns3_ecmp`
  - result: exit 0, log contains `route_strategy=ns3_ecmp packet_level=1`, `all passes finished at time: 65339241`, and `SimAI-htsim finished`; `EndToEnd.csv` has 15 lines, total time `65339`, exposed comm `251`, and `fct.txt` has 144721 lines.
- No-FCT htsim output smoke on 2026-07-02:
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim` completed.
  - `timeout 180s env HTSIM_DISABLE_FCT_OUTPUT=1 bin/SimAI_htsim -w /tmp/htsim_dense256_short10_1mib.txt -n mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -c myconfig/Meta256MoE.conf -o experiments/htsim_results/csv/ns3_ecmp_short10_1mib_nofct_20260702_codex -r ns3_ecmp`
  - result: exit 0, log contains `[htsim] fct output disabled by HTSIM_DISABLE_FCT_OUTPUT`, `EndToEnd.csv` has 15 lines, and no `fct.txt` was created.
- Final-drain oldest-unacked recovery verification on 2026-07-10:
  - 256 Meta 64 MiB-tail reproducer completed with tail RTO disabled, exit 0, 12-line `EndToEnd.csv`, 58881-line `fct.txt`, 808 ACK-gated recovery rounds, wall 32.09s, and maximum RSS about 386 MB.
  - 256 and 1024 1 MiB scale-table smokes both exited 0 without invoking recovery. They wrote 28673 and 114689 FCT lines respectively; wall times were 3.59s and 32.03s.
  - The uncapped first-10-layer diagnostic reached final recovery round 1706 and grew from about 122k to 124083 FCT rows during the bounded foreground test. It was intentionally interrupted before full completion; this validates ongoing progress but not a completed large-message result.
  - Formal runner: `experiments/htsim_results/run_dense_scale_table_spray_plb.sh`; output root: `experiments/htsim_results/csv/htsim_dense_scale_table_spray_plb_final_recovery_20260710_191503`.
  - The runner now accepts any supported strategy through `HTSIM_ROUTE_STRATEGY`, an optional comma-separated topology filter through `HTSIM_TOPOLOGIES`, and optional continue-after-failure behavior through `HTSIM_CONTINUE_ON_ERROR=1`. Completed FCT files are gzip-compressed when `HTSIM_COMPRESS_FCT=1`.
- Post-pass Go-Back-N livelock handoff verification on 2026-07-11:
  - 256 Meta 64 MiB core reproducer remained bit-for-bit stable at the result level: exit 0, 58881 FCT lines, 12 EndToEnd lines, JCT `54762.490 us`, 808 recovery rounds, wall 31.90s, and maximum RSS about 386 MB.
  - 256 HPN 256 MiB core-7 reproducer used a deliberately smaller 32768 consecutive-no-completion budget and exited 0. It completed after 22352 total recovery rounds, wrote 58673 FCT lines and 12 EndToEnd lines, reported JCT `207327.981 us`, and took 2:53.75 wall time with about 781 MB maximum RSS.
  - The HPN log shows `no_completion_rounds` repeatedly returning near zero while the total round count keeps increasing, directly verifying that complete-flow progress refreshes the recovery budget.
  - An earlier sender-rate pacing trial was reverted while the callback-order regression was unresolved. After final-recovery handoff and deterministic route-RNG initialization were stabilized, selected-route bottleneck pacing was reintroduced successfully.
  - With route pacing, the Meta 64 MiB reproducer exited 0 with 58881 FCT lines, 12 EndToEnd lines, JCT `54682.702 us`, 809 recovery rounds, and 32.84s wall time. The HPN 256 MiB reproducer exited 0 with 58993 FCT lines, 12 EndToEnd lines, JCT `204440.738 us`, 22368 recovery rounds, and 3:01.99 wall time.
  - One-MiB smokes logged the intended route domains and rates: Meta scale-out 400 Gbps, HPN scale-out 200 Gbps, and scale-up 3600 Gbps. An HPN `ecmp` smoke also exited 0 without final recovery, confirming the fixed-per-flow path mode.
  - HPN still requires substantial recovery under `spray_plb`; correct injection pacing reduces the mismatch but does not remove packet reordering from PLB path changes or add a receiver reorder buffer.
- Receiver reorder-buffer verification on 2026-07-11:
  - The full HPN `spray_reps` run without receiver reordering issued all 1262 layers and reached the two final scale-out streams, then stopped making FCT progress at 36,019,645 rows while consuming one CPU core. It was stopped without JCT.
  - HPN 1 MiB `spray_reps` exited 0 with 15 EndToEnd rows, 144,801 FCT rows, and the expected 3600/200 Gbps scale-up/scale-out pacing logs.
  - HPN 256 MiB core-7 `spray_reps` exited 0 with 12 EndToEnd rows, 58,624 FCT rows, JCT `165421.928 us`, 2:00.36 wall time, and about 519 MB maximum RSS. It required neither event-loop stall handoff nor final recovery.
  - Meta 64 MiB core-7 `spray_plb` remained at the established baseline: exit 0, 12 EndToEnd rows, 58,881 FCT rows, 809 final-recovery rounds, JCT `54682.691 us`, and 32.83s wall time.
- htsim `ns3_ecmp` tail-stall diagnostics on 2026-07-06:
  - Added diagnostic helpers under `experiments/cross_backend_dense256_meta_20260624_114003/`: `make_htsim_repro_workloads.py` and `run_htsim_ns3_ecmp_diagnostics.sh`.
  - `dense256_cap256m_core7` is the compact reproducer: old `ecmp` exits 0 with 12 rows and `all passes finished at time: 54483474`; original `ns3_ecmp` times out after 420s with 0 rows.
  - Reverse-route stabilization alone still timed out, so the final fix adds default-on `ns3_ecmp` tail RTO recovery in htsim RoCE.
  - Fixed `ns3_ecmp` on `dense256_cap256m_core7`: exit 0, 12 rows, `all passes finished at time: 734051676`, wall `2:20.67`, RSS about 789 MB, output `htsim_ns3_ecmp_diag_20260706_cap256m_core7_tail_rto_100us/`.
  - Fixed `ns3_ecmp` on `dense256_fullsize_layernorm_only`: exit 0, 6 rows, `all passes finished at time: 230716551`, wall `2:08.07`, output `htsim_ns3_ecmp_diag_20260706_layernorm_only_tail_rto/`.
  - A fixed 100us tail watchdog variant was tried and stopped because it caused a retransmit storm; keep the conservative adaptive-RTO implementation unless there is a dedicated queue/RTO tuning pass.
- Final-drain fix check on 2026-06-24:
  - The full dense Meta `spray_plb` rerun under `experiments/cross_backend_dense256_meta_20260624_114003/htsim_spray_plb_rerun_20260624_143409/` exited 0 with 36.0M FCT rows but empty `EndToEnd.csv`; the log showed `pass: 0 finished` followed by rank0 waiting for streams 1257/1259 in `Ready` state.
  - `Sys::drain_finished_streams()` was updated to drain exhausted `Ready`, `Executing`, and `Zombie` streams, matching the external FlowSim final-drain behavior.
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim` succeeded after the fix.
  - Short dense Meta `spray_plb` smoke `experiments/htsim_results/csv/final_drain_fix_smoke_20260624_195704/` exited 0, logged `all passes finished at time: 65392354`, wrote 15-line `EndToEnd.csv`, and wrote 144833 FCT rows.
  - The full dense Meta packet PLB rerun output is `experiments/cross_backend_dense256_meta_20260624_114003/htsim_spray_plb_fixed_20260624_195704/`; its historical tmux session is no longer active.
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
