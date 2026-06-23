# Decisions

## Decision Log

### 2026-06-15: Establish `.ai` Knowledge Base

- Created `.ai/` as the persistent project knowledge base.
- Purpose: future development should start from `.ai/current_context.md` and relevant module docs instead of rescanning the full repository.
- Rationale: this repository is large, multi-backend, and contains external backend dependencies; persistent context reduces repeated expensive exploration.

### 2026-06-15: Treat FlowSim as a First-Class Backend Path

- FlowSim is documented as distinct from NS-3.
- Current project stores FlowSim experiment scripts, topology/workload inputs, and outputs.
- FlowSim implementation and binary are external under `/home/zty/Topo/m4/SimAI`.
- Rationale: user explicitly clarified that FlowSim is a separate backend analysis tool and must be analyzed alongside NS-3.

### 2026-06-15: Keep Vidur Out of Current Analysis

- Vidur-related content is not analyzed in this knowledge base unless explicitly requested.
- Rationale: original project-understanding request asked to skip vidur-related content.

### 2026-06-15: Do Not Modify Business Code During Knowledge-Base Phase

- Only documentation and `.ai` files are created/updated.
- Rationale: current goal is project understanding, not feature development.

### 2026-06-15: Repair Local Build Permissions Without Sudo Builds

- Added `scripts/fix_local_permissions.sh` to repair ownership and write/execute bits on targeted SimAI/FlowSim build and binary paths.
- Added `experiments/ns3_results` to the permission repair targets after NS-3 Mixtral runs failed to create `detailed_288.csv` under a `nobody:nogroup` CSV directory.
- Included the NS-3 `astra-sim-alibabacloud/extern/network_backend` path because `scripts/build.sh -c ns3` removes and recreates `ns3-interface`.
- Included the whole external FlowSim `astra-sim-alibabacloud/build/simai_flowsim` subtree because the FlowSim sub-build script creates/removes both `build/` and `result/`.
- Normal SimAI and FlowSim compilation/execution should run as the current user, not through `sudo`.
- The script uses `sudo chown` only for one-time repair of historical artifacts owned by `nobody`, `root`, or another user.
- Rationale: keeping sudo out of build/run commands avoids creating new root-owned artifacts and keeps experiment scripts reproducible for the regular user.

### 2026-06-15: Precreate and Validate NS-3 Mixtral Output Directories

- Updated `run_mixtral_256moe_ns3.sh` to create all known Mixtral 256 MoE NS-3 output directories before launching a topology.
- The script now checks each output directory for write access and exits early with a `scripts/fix_local_permissions.sh` hint if the directory exists but is not writable.
- Rationale: `CSVWriter::initialize_csv()` reports a fatal `Unable to create file` error when the target directory is missing or not writable; failing before a long NS-3 run makes the issue cheaper and clearer to diagnose.
- Verification: local inspection showed `experiments/ns3_results/csv` and `Mixtral-Meta256A100` were owned by `nobody:nogroup`; an attempted permission repair could not complete in the tool environment because sudo required an interactive password.
- Follow-up: run `bash scripts/fix_local_permissions.sh` in an interactive terminal before rerunning NS-3 if those directories are still owned by `nobody` or `root`.

### 2026-06-15: Drain Finished FlowSim Streams Before Final Reporting

- Added a final FlowSim drain in the external FlowSim implementation under `/home/zty/Topo/m4/SimAI`.
- The drain runs after `FlowSim::Run()` when the FlowSim event queue is empty and completes active `Sys` streams whose `phases_to_go` are already exhausted.
- Rationale: Zcube 256 MoE could reach FlowSim/FCT completion while rank0 still had a few streams not counted as finished, so `Workload::report()` never executed and `EndToEnd.csv` remained empty.
- The drain uses the existing `Sys::proceed_to_next_vnet_baseline()` path so dataset notifiers, stream counters, and report generation stay on the normal system/workload path.
- Verification: FlowSim rebuilt successfully. A temporary Zcube mini workload wrote a non-empty `EndToEnd.csv` and logged `workload stats` / `all passes finished`; the full 1837-layer MoE workload was too slow to complete within the interactive verification window.

### 2026-06-15: Keep FlowSim Drain but Default Verbose Logs Off

- Added a shared `FlowSimVerboseLoggingEnabled()` helper in external FlowSim and gated noisy stdout behind `FLOWSIM_VERBOSE` / `FS_VERBOSE`.
- Default-off logs include per-send/per-callback FlowSim logs, workload parsing/pass logs, layer collective issued/finished logs, chunk-size logs, layer report stdout, and ring-topology initialization logs.
- Key startup, routing, FCT summary, final drain, and finish summaries remain visible by default.
- Rationale: Zcube MoE needs the final drain for correctness, but verbose stdout substantially slows large runs and creates huge logs.
- Verification: a 45-second Zcube 256 MoE smoke run timed out as expected but produced only 8 startup/routing lines and no verbose-log pattern matches.

### 2026-06-15: Cache FlowSim Routes by Source/Destination Pair

- Added a `(src,dst)` path cache in external `RoutingFramework::GetFlowSimPathByNodeIds()`.
- Cache is cleared on topology parse and routing-table precalculation.
- Rationale: FlowSim sends many chunks for repeated GPU pairs; repeated path construction and lookup are avoidable overhead.
- Semantics: unchanged for current FlowSim because `GetFlowSimPathByNodeIds()` always constructs the same fixed UDP `FlowKey` for a given source/destination before calling `GetFlowSimPath()`.

### 2026-06-15: Keep Lightweight FlowSim Layer Progress by Default

- Added default-on FlowSim workload progress lines in the external FlowSim implementation:
  - format: `[LAYER] pass=<pass> state=<state> layer=<current>/<total> name=<layer_name> time=<tick>`
  - emitted once per rank0 `pass/state/layer` transition
  - disabled with `FLOWSIM_PROGRESS=0`
- `FlowsimAstra.cc` now sets `UserParam::mode = ModeType::FLOWSIM` so the progress logging is scoped to FlowSim runs.
- Rationale: after disabling verbose logs, long Zcube MoE runs still need an inexpensive heartbeat showing total layers and current layer, matching the prior rerun log style.
- Verification: FlowSim rebuilt successfully; a 60-second Zcube 256 MoE smoke run printed `[LAYER] pass=0 state=forward layer=1/1837 ...` through layer 13 and had no per-send/per-callback verbose patterns.

### 2026-06-15: Add Optional FlowSim Wall-Clock Profiler

- Added `FLOWSIM_PROFILE=1` profiler instrumentation to the external FlowSim implementation.
- Stages include event queue proceed/schedule/cancel, route lookup/build, send/recv callbacks, topology batching, link-state recalculation, completion scheduling, and chunk callbacks.
- Profiling is default-off and therefore does not affect normal runs.
- Profiling installs SIGTERM/SIGINT handling so `timeout`-interrupted Zcube runs still print accumulated profile data.
- Rationale: layer progress shows simulated time movement, but it cannot identify program wall-clock bottlenecks such as routing lookup versus link sharing.
- Zcube 256 MoE 120s sample:
  - `Topology::update_link_states`: 114123.851 ms over 1926 calls, ~59.254 ms/call.
  - `Topology::process_batch_of_chunks`: 51651.416 ms over 968 calls.
  - `Topology::post_batch_completion_callback`: 63050.848 ms over 958 calls.
  - `FlowSim route lookup`: 16.945 ms over 98214 calls, ~0.173 us/call.
- Decision: current Zcube wall-clock slowness is dominated by max-min link-rate recalculation in `Topology::update_link_states()`, not routing.

### 2026-06-15: Optimize FlowSim Link-State Recalculation Without Changing Sharing Semantics

- Reworked external `Topology::update_link_states()` to maintain per-link `remaining_bandwidth` and `unfixed_chunks` during progressive filling.
- Rationale: the old implementation recomputed each candidate link's fair share by rescanning its active chunks and checking which chunks were already fixed on every iteration. Zcube MoE has many active chunks and links, so that repeated scan dominated wall-clock runtime.
- Semantics: still uses the same progressive max-min filling idea, fixes all unfixed chunks on the current bottleneck link, and subtracts the fixed rate from every link used by each newly fixed chunk.
- Verification:
  - FlowSim rebuilt successfully with `./scripts/build.sh -c flowsim`.
  - A 120s interrupted Zcube 256 MoE profile changed `Topology::update_link_states` from the earlier ~114123.851 ms / 1926 calls / ~59.254 ms per call to 102794.736 ms / 15551 calls / ~6.610 ms per call.
  - The same 120s window processed many more FlowSim events and chunk completions, so the lower average is not from doing less work.
- Risk: equal-rate bottleneck ties may be selected in a different unordered-map order, but max-min rates should remain equivalent because tied bottlenecks have the same fair share.

### 2026-06-15: Coalesce FlowSim Link-State Refresh Through a Dirty Flush

- Added a `link_state_dirty_` state and `schedule_link_state_update()` path in external `Topology`.
- Chunk additions, chunk removals, and batch processing now mark link state dirty instead of directly recomputing rates.
- The post-batch handler now also consumes pending chunks before recomputing rates, then updates remaining sizes, runs `update_link_states()`, and schedules the next completion set once for the accumulated changes.
- Rationale: completion callbacks can trigger new sends at the same simulated time; direct recomputation in both `process_batch_of_chunks()` and `post_batch_completion_callback()` duplicates work around those event-time boundaries.
- Verification:
  - FlowSim rebuilt successfully with `./scripts/build.sh -c flowsim`.
  - A 120s interrupted Zcube 256 MoE profile showed `process_batch_of_chunks` drop to 240.974 ms total over 19638 calls, compared with the previous 120s optimized sample's 47516.382 ms over 7466 calls.
  - In the same 120s window, FlowSim advanced further: sends increased from 419328 to 528704 and chunk completions from 418627 to 527663.
  - `update_link_states` remained the dominant cost at 100272.185 ms total, but its average was ~2.605 ms/call in this sample.
- Risk: this changes when recomputation is dispatched inside the same simulated timestamp, so full-workload result comparison is still useful before treating it as a final performance baseline.

### 2026-06-15: Use Lazy Min-Heap for FlowSim Bottleneck Link Selection

- Reworked external `Topology::update_link_states()` bottleneck selection from scanning all active link states every progressive-filling round to a lazy min-heap keyed by fair share.
- Affected links push a new heap version when a newly fixed chunk reduces their remaining bandwidth or unfixed count; stale heap entries are skipped when popped.
- Rationale: after per-link state and dirty flush, the remaining inner-loop cost was repeatedly finding the current minimum fair-share link.
- Semantics: still fixes the smallest fair-share bottleneck link each round and updates every link traversed by newly fixed chunks. Equal-rate bottleneck tie order may differ, but tied bottlenecks have equivalent fair share.
- Verification:
  - FlowSim rebuilt successfully with `./scripts/build.sh -c flowsim`.
  - A 120s interrupted Zcube 256 MoE profile processed 675664 sends and 674553 chunk completions.
  - `Topology::update_link_states` changed from the dirty/flush sample's 100272.185 ms / 38492 calls / ~2.605 ms per call to 95355.345 ms / 54491 calls / ~1.750 ms per call.
- Risk: the full 1837-layer workload has not yet been run to completion for final output comparison after this heap optimization.

### 2026-06-15: Skip Zero-Byte FlowSim Collectives Before DataSet Creation

- Added no-op handling for non-`None` zero-byte collectives in external FlowSim `Layer` issue paths.
- Affected phases: forward pass, input gradient, and weight gradient.
- Rationale: Zcube MoE workloads contain entries such as `final_column REDUCESCATTER 0`; FlowSim creates no chunk/event for zero bytes, so a `DataSet` created for such a collective waits forever and prevents `Workload::report()` from writing `EndToEnd.csv`.
- Semantics: nonzero collectives keep the same route lookup, chunk scheduling, link sharing, and callback behavior. Zero-byte blocking collectives advance the workload through the existing `workload->call(EventType::General, NULL)` no-op path.
- Verification:
  - `/home/zty/Topo/m4/SimAI` rebuilt successfully with `./scripts/build.sh -c flowsim`.
  - Compact ZcubeMini MoE reproducer now exits 0 and writes `EndToEnd.csv` with 1948 bytes and `fct.txt` with 2208 lines.
  - Full 256 Zcube MoE with `FLOWSIM_PROGRESS=0` timed out after 7200s before workload reporting, so full-run completion still needs a longer run or more acceleration.

### 2026-06-15: Keep FlowSim Sys Lifetime Owned by FlowSim Entry Point

- Changed external FlowSim `Sys::call_events()` behavior so FlowSim backend systems are not self-deleted when workload completion empties rank-local events.
- Rationale: `FlowsimAstra.cc` keeps raw `Sys*` pointers in its `systems` vector and uses them after `FlowSim::Run()` for final drain and finish handling. Self-delete left dangling pointers and caused a post-report segfault in the compact ZcubeMini MoE reproducer.
- Scope: FlowSim backend only; other backend self-delete behavior is unchanged.

### 2026-06-16: Verify Full Zcube 256 MoE FlowSim CSV Generation

- Re-ran the full Zcube 256 MoE FlowSim case after the zero-byte collective fix, FlowSim lifetime guard, final drain, and link-state optimizations.
- Command: `timeout 28800 env FLOWSIM_WRITE_FCT=0 bash run_256moe_flowsim.sh Zcube`.
- Result: exited 0, logged `workload stats for the job scheduled`, `all passes finished`, drained 32 finished streams, and printed `SimAI-FlowSim finished`.
- Output: `/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/256/ZcubeMoE/EndToEnd.csv` is 323759 bytes.
- Decision: the CSV-empty root cause is resolved for the full workload. `FLOWSIM_WRITE_FCT=0` is acceptable for this verification because FCT writing is not required to trigger `Workload::report()`; `[FCT SUMMARY] lines=0` is expected in that mode.

### 2026-06-16: Publish External FlowSim Fork to User GitHub

- Created and used the user-owned remote `git@github.com:TyKuro9/SimAI-FlowSim.git` for the external FlowSim code under `/home/zty/Topo/m4/SimAI`.
- Pushed branch `main` with commit `8cc581238e9e7b06429301746720bef1d2f16ac9` (`fix flowsim zcube moe csv reporting`).
- Rationale: the main `TyKuro9/SimAI` project invokes FlowSim from the external `/home/zty/Topo/m4/SimAI` checkout, so the CSV fix must also live in a remote FlowSim repository to be usable on other machines.
- Scope: only the external FlowSim repository was pushed. Large untracked experiment outputs under `/home/zty/Topo/m4/SimAI/experiments` were intentionally not committed.

### 2026-06-15: Drain Finished NS-3 Streams Before Destroy

- Added `Sys::drain_finished_streams()` to the current SimAI source and invoked it from the NS-3 entrypoint after `Simulator::Run()` and before `Simulator::Destroy()`.
- Kept the `astra-sim` source and the generated `extern/network_backend/ns3-interface` ASTRA-sim copy in sync because NS-3 builds copy/use these files.
- Rationale: Mixtral NS-3 logs could finish the final pass but never print `workload stats` / `all passes finished`, leaving `EndToEnd.csv` at 0 bytes. The missing CSV was therefore not a directory or permission issue; `Workload::report()` did not run because final upper-stack stream completion was not drained after the NS-3 event queue emptied.
- Semantics: the drain calls the existing `Sys::proceed_to_next_vnet_baseline()` path for streams whose `phases_to_go` is already empty, preserving normal dataset notifier and stream-counter behavior.
- Verification:
  - NS-3 rebuilt successfully with `./build.sh -c` from `astra-sim-alibabacloud/build/astra_ns3`.
  - A 30-second smoke run using `bin/SimAI_simulator` started successfully and created `/tmp/simai_ns3_smoke/EndToEnd.csv`; it was timeout-interrupted before workload reporting, so it was not expected to contain end-to-end rows.
- Risk: full Mixtral NS-3 completion has not yet been rerun after the drain, so final output comparison is still recommended.

### 2026-06-15: Add htsim/RoCE as a Parallel Backend

- Added `extern/network_backend/htsim` as a git submodule pinned to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- Added `bin/SimAI_htsim` via `./scripts/build.sh -c htsim`; NS-3 remains available through `bin/SimAI_simulator`.
- The ASTRA-facing htsim frontend reuses existing SimAI workload/topology/config inputs and preserves the upper-stack `EndToEnd.csv` report path.
- htsim route strategy is selected with `-r single|ecmp|spray_rr`, `HTSIM_ROUTE_STRATEGY`, or a `route_strategy` config line.
- Rationale: htsim gives a lighter RoCE/event backend for routing experiments while keeping NS-3 as the high-fidelity protocol backend for comparison and rollback.
- Verification: htsim build succeeded; a SimAI htsim spray smoke wrote `/tmp/simai_htsim_smoke/EndToEnd.csv` with 1813 rows.

### 2026-06-15: Implement Deterministic Per-Packet Spray for htsim RoCE

- Extended htsim `RoceSrc` to own multiple copied routes and select the next route for each data packet.
- Reused htsim's existing route list model instead of adding switch-time dynamic FIB decisions for the first version.
- Kept ACK/NACK on the configured stable reverse path.
- Fixed htsim RoCE datacenter route construction to use `Route(orig, dst)` so transport endpoints are present on forward and reverse routes.
- Rationale: the user wanted RoCE-style Spray routing; per-data-packet deterministic round-robin/permutation is reproducible and matches the chosen first-version policy.
- Verification: native `htsim_roce` tiny topology completed a flow with `-strat perm -paths 2`.

### 2026-06-22: Run htsim as a Real ASTRA Backend and Preserve EndToEnd Reporting

- Changed the htsim ASTRA build to define `HTSIM_BACKEND` without defining `ANALYTI`.
- Excluded physical RDMA/MPI sources for the htsim build while keeping normal ASTRA workload, MockNCCL, stream, dataset, and `Workload::report()` semantics.
- Added htsim `fct.txt` output in the ASTRA-facing frontend so every completed htsim flow records `src dst tag flow_id size_bytes start_ns end_ns fct_ns route_strategy`.
- Rationale: the earlier analytical-style build could exit without exercising real send/recv callbacks, which produced empty `EndToEnd.csv` even when the frontend appeared to run.
- Verification: `./scripts/build.sh -c htsim` succeeds and the 40-layer 256 Meta MoE htsim run writes both non-empty FCT and non-empty `EndToEnd.csv`.

### 2026-06-22: Add htsim Final-Drain and Late-Callback Guards

- Added a htsim final progress loop after `EventList` exhaustion:
  - drain `Zombie` streams through the normal `Sys::proceed_to_next_vnet_baseline()` path;
  - start final uninitialized `Ready` streams whose phase list is exhausted;
  - flush safe ASTRA workload/report events.
- Mark completed streams `Dead` instead of immediately deleting them in `HTSIM_BACKEND` builds.
- Drop late htsim `PacketBundle`, `PacketReceived`, and `PacketSentFinshed` callbacks when their owner stream is `Dead`.
- Rationale: htsim can finish its event queue while ASTRA still has final stream/report work pending; forcing deletion created dangling callbacks during the final drain, while skipping the drain left `EndToEnd.csv` empty.
- Verification: `timeout 300s bin/SimAI_htsim -w /tmp/htsim_meta256_short.txt -n mytopo/Meta_Topo_256g_8gps_400Gbps_A100 -c myconfig/Meta256MoE.conf -o experiments/htsim_results/csv/Meta256MoE_short_retest4 -r spray_rr` exited 0, logged `all passes finished at time: 108372751`, wrote 45 `EndToEnd.csv` lines, and wrote 642561 `fct.txt` lines.
- Risk: htsim `Dead` stream retention intentionally leaks completed stream objects for the process lifetime. This is acceptable for the first htsim backend because it avoids dangling callbacks in a short-lived simulator process; revisit with ownership-safe event cancellation if htsim becomes long-running service code.

### 2026-06-22: Make ASTRA htsim Use Packet-Level RoCE by Default

- Replaced the ASTRA-facing htsim completion estimator as the default path with real htsim packet-level RoCE.
- `HtsimNetwork` now parses SimAI topology edge lists into htsim directed `Queue`/`Pipe` objects, caches GPU-pair shortest-path route sets, creates `RoceSrc/RoceSink` objects per ASTRA send, and completes ASTRA send/recv callbacks from a htsim flow-done trigger.
- `single` uses the first shortest path, `ecmp` uses a deterministic per-flow path choice, and `spray_rr` gives all cached shortest paths to `RoceSrc::set_paths()` so data packets round-robin across paths. ACK/NACK remains on one stable reverse path.
- Kept the old flow-level estimator behind `HTSIM_FLOW_LEVEL=1` for debugging and for cases where packet-level runtime is too high.
- Added startup logging of `packet_level=1/0` so experiment logs make the simulation granularity explicit.
- Suppressed native RoCE per-flow start/finish stdout by default; set `HTSIM_ROCE_VERBOSE=1` for those logs.
- Rationale: topology-sensitive Spray experiments require packet-level path, queue, and ACK behavior; the previous ASTRA-facing estimator could produce non-empty CSV but could not measure topology-dependent packet-level routing behavior.
- Verification:
  - `./scripts/build.sh -c htsim` completed.
  - Meta 256 dense scaled smoke (`/tmp/htsim_dense256_short10_1mib.txt`, `-r spray_rr`) logged `packet_level=1`, `all passes finished at time: 65258013`, wrote 15 `EndToEnd.csv` rows, and wrote 144897 `fct.txt` rows.
  - Six 256 topologies completed with the same scaled workload under both `spray_rr` and `ecmp`, and finish times differ by topology and strategy.
  - The uncapped first-10-layer normal dense workload timed out after 120s on Meta but produced 14224 FCT rows, confirming packet-level work was progressing but full-size dense packet simulation needs long batch/tmux execution.

### 2026-06-22: Use Explicit `/usr/bin` PATH for NS-3 Build Verification

- Verified `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c ns3` after htsim changes.
- Rationale: this environment's default `cmake` can resolve to `/snap/bin/cmake`, whose snap wrapper cannot run in the sandbox and fails before ns-3 configuration. Putting `/usr/bin` first uses the working system CMake.
- Verification: NS-3 configured, built, and linked `ns3.36.1-AstraSimNetwork-debug`.

### 2026-06-16: Keep NS-3 Sys Lifetime Owned by NS-3 Entrypoint

- Changed `Sys::call_events()` so `NS3_MTP`/`NS3_MPI` builds do not `delete this` after local workload/event completion.
- Rationale: the NS-3 entrypoint stores raw `Sys*` objects and iterates them after `Simulator::Run()` for final drain. Self-delete can produce a successful `Workload::report()` followed by a post-report segfault.
- Verification: 64-GPU Zcube dense tiny NS-3 smoke exits 0, logs `workload stats` and `all passes finished`, and writes a non-empty `EndToEnd.csv`.

### 2026-06-16: Continue NS-3 After Final Drain Schedules Upper-Stack Work

- Changed the NS-3 entrypoint from a single `Simulator::Run()` plus one drain loop into a progress loop.
- After each `Simulator::Run()`, the entrypoint drains finished streams and flushes current-tick ASTRA event queues; if that made progress, it calls `Simulator::Run()` again so newly scheduled network events can execute.
- Rationale: a MoE 64-GPU Zcube repro could drain the first finished `ALLTOALL_EP` streams after the NS-3 queue emptied, but the upper-stack event produced by that drain was not processed far enough to reach `Workload::report()`, leaving `EndToEnd.csv` empty despite exit 0.
- Verification: after rebuild with `env PATH=/usr/bin:/bin:$PATH ./build.sh -c`, 64-GPU Zcube `dense_64_tiny.txt` exited 0 and wrote `results_dense_final/EndToEnd.csv` with 1614 bytes; `moe_64_tiny.txt` (`tp8/pp1/ep4`) exited 0 and wrote `results_moe_final/EndToEnd.csv` with 1927 bytes. Both logs contain `workload stats for the job scheduled` and `all passes finished`.

### 2026-06-16: Derive NS-3 MockNCCL DP/EP Sizes from Workload GPU Semantics

- Changed MockNCCL group/comm initialization to use workload `pipeline_model_parallelism` and `all_gpus` when computing DP/EP sizes.
- Rationale: NS-3 topology `total_nodes` can include NVSwitches, so using it in DP sizing corrupts MoE groups and can make small repros crash before reporting.
- Verification: 64-GPU Zcube MoE tiny NS-3 smoke with `tp8/pp1/ep4`, forward `ALLTOALL_EP`, DP/DP_EP gradient collectives, and zero-byte `REDUCESCATTER` exits 0, logs `workload stats` and `all passes finished`, and writes a non-empty `EndToEnd.csv`.

### 2026-06-16: Disable Empty NcclTreeFlowModel Instances

- `NcclTreeFlowModel` now marks itself disabled when the generated flow model is null/empty or has zero channels.
- Rationale: ranks without a usable flow model should not create active streams that can never send or receive packets.
- Scope: shared ASTRA-sim source and generated NS-3 interface copy were kept in sync.
- Verification now includes `moe_64_alltoall_ig_tiny.txt`, so the 64-GPU Zcube MoE CSV smoke covers forward EP all-to-all, input-gradient EP all-to-all, DP/DP_EP gradient collectives, zero-byte collectives, and CSV/report completion.
- Follow-up: full Mixtral 256 NS-3 topology coverage is still a separate long-run verification.

### 2026-06-16: Add 64-GPU NS-3 MoE Backward EP All-to-All Smoke

- Added `experiments/ns3_repro/zcube64_csv/moe_64_alltoall_ig_tiny.txt` as a focused MoE workload with `tp8/pp1/ep4/all_gpus64`.
- Rationale: the earlier passing MoE tiny workload intentionally removed input-gradient `ALLTOALL_EP`; this new smoke keeps the backward EP all-to-all path while preserving a small runtime and valid `DP=8`, `DP_EP=2` grouping.
- Verification:
  - NS-3 rebuilt successfully from `astra-sim-alibabacloud/build/astra_ns3` with `env PATH=/usr/bin:/bin:$PATH ./build.sh -c`.
  - `dense_64_tiny.txt` exited 0 and wrote `experiments/ns3_repro/zcube64_csv/results_dense_tiny_verify/EndToEnd.csv` with 1614 bytes.
  - `moe_64_alltoall_ig_tiny.txt` exited 0 and wrote `experiments/ns3_repro/zcube64_csv/results_moe_alltoall_ig_tiny_verify/EndToEnd.csv` with 1932 bytes.
  - Both logs contain `workload stats for the job scheduled` and `all passes finished`.
- Decision: for NS-3 CSV/reporting regressions, use the dense tiny case first and the MoE backward all-to-all tiny case second before escalating to expensive 256-GPU full-topology runs.

### 2026-06-16: Classify Zcube 256 MoE Expert-Parallel Paths Against RO

- Analyzed the current 256-GPU Mixtral MoE FlowSim inputs for Zcube and RO using the documented FlowSim routing behavior (`GetFlowSimPathByNodeIds`) and MockNCCL EP grouping.
- EP groups for `tp8/pp2/ep8/all_gpus256` are same-local-rank rail groups across 8 consecutive servers, so the expert-parallel `ALLTOALL_EP` traffic contains no same-server GPU-to-GPU pairs.
- Classification convention:
  - same-server non-EP GPU pairs use the local NVSwitch path.
  - Zcube switches `288..303` are treated as local/pair switches.
  - Zcube switches `304..319` are treated as same-rail multi-server switches.
  - RO switches `288..319` are treated as same-rail multi-server switches.
- Result over 1792 directed EP GPU pairs:
  - Zcube: 14.3% local/pair-switch paths, 42.9% single same-rail multi-server-switch paths, 42.9% two ordinary-switch paths.
  - RO: 100% single same-rail multi-server-switch paths.
- Decision: explain Zcube's slower 256 MoE EP behavior relative to RO primarily by the longer and more contended expert-parallel all-to-all paths. Current `EndToEnd.csv` evidence shows Zcube `Expose_EP_comm=190191` versus RO `Expose_EP_comm=79911`; total time is `3158908` versus `3138013`.

### 2026-06-17: Implement Fixed-Probability Fault-Tolerance Driver at Topology Level

- Inspected existing link-failure support before editing. NS-3 already supports a single scheduled `LINK_DOWN` event through `TakeDownLink()`, which disables the bidirectional link, recomputes routes, reinstalls routing tables, and redistributes QPs. The per-link topology `error_rate` and `ERROR_RATE_PER_LINK` config are packet error models, not link removal.
- Added `scripts/fault_tolerance_experiments.py` instead of rewriting topology generation or routing.
- The driver samples failed inter-server links with one fixed `--link-failure-probability` across all seeds, writes failed topology files, and optionally invokes the existing FlowSim binary so startup topology parsing and routing precomputation are reused.
- Random link failure excludes GPU-to-NVSwitch/NVSwitch-to-GPU links so intra-server NVLink/NVSwitch links do not fail.
- Switch failure is emulated by failing all links incident to `--failed-switch-id`; `--failed-switch-role tor` is intentionally unavailable because current topology files do not encode a portable ToR role.
- Outputs use the requested `results/fault_tolerance/` layout with raw/summary CSVs and `metadata.json`.
- Rationale: a topology-level driver is the minimum reviewable implementation that preserves no-failure experiments, avoids changing NS-3/FlowSim routing internals, and still reuses the existing link-down semantics of removing failed links before route computation.
- Verification:
  - `python3 -m py_compile scripts/fault_tolerance_experiments.py`
  - dry-run sanity on `experiments/ns3_repro/zcube64_csv/Zcube_n8_k2_64g_8gps_200Gbps_H100` passed for `p=0`, `p=1`, and switch-id incident-link failure.
  - FlowSim `p=0` smoke with `dense_64_tiny.txt` wrote matching normal/failed JCT values of `11.0`.
  - FlowSim switch-id `72` smoke completed and wrote raw/summary outputs.
  - `p=1` dry-run failed all 192 inter-server links and reduced all-to-all connectivity ratio to `0.1111111111111111`, leaving only same-server NVSwitch connectivity.

### 2026-06-17: Use Bandwidth-Scale Approximation for FlowSim Error-Probability JCT Curves

- Added `experiments/flowsim_256/run_fault_probability_sweep.py` for 256-GPU FlowSim JCT curves with error probability on the x-axis and JCT(s) on the y-axis.
- Current FlowSim parses topology `error_rate` but does not use it in flow completion; NS-3 has the real packet error model. For FlowSim-first experiments, the sweep script therefore generates derived topology files that keep the topology connected, set inter-server link `error_rate` to `p`, and scale inter-server bandwidth by `(1-p)`.
- The original topology files remain unchanged. GPU-to-NVSwitch/NVSwitch-to-GPU intra-server links are not scaled.
- Link-removal mode remains available as `--error-model link_failure`, but it is not the default for error-probability JCT curves. In this session, link-removal generated missing FlowSim `EndToEnd.csv` for nonzero Meta points, so it is not a reliable way to produce the requested curve without deeper backend work.
- Added two 256-GPU MoE sweep workloads:
  - `experiments/flowsim_256/moe_256_fault_tiny.txt` for fast mechanics smoke tests.
  - `experiments/flowsim_256/moe_256_fault_comm.txt` for useful JCT curves with larger communication sizes while keeping only 8 layers.
- Verification:
  - `python3 -m py_compile experiments/flowsim_256/run_fault_probability_sweep.py`
  - Meta smoke with `moe_256_fault_tiny.txt` completed and wrote raw/summary/plot outputs.
  - Meta smoke with `moe_256_fault_comm.txt` completed and showed JCT rising from `0.405045s` at 0% to `0.409079s` at 1%.
  - Full `moe_256_fault_comm.txt` sweep over `Meta`, `HPN`, `DeepSeek`, `Zcube`, `RO`, and `ROFT` for 0..15% completed under `results/fault_tolerance_256_flowsim_comm/` with 96 raw rows, 96 summary rows, no missing JCT values, no empty `EndToEnd.csv`, and `jct_by_error_probability.png`.
- Full 1837-layer Mixtral 256 MoE was not used for the full probability sweep because a single Meta 1% point exceeded 7 minutes before interruption. Treat full Mixtral probability sweeps as separate long batch runs.

### 2026-06-18: Add User-Run Wrapper for Full Mixtral 256 FlowSim Sweep

- Added `experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh`.
- The wrapper runs the full 1837-layer Mixtral 8x7B MoE 256-GPU workload through `run_fault_probability_sweep.py` rather than the 8-layer quick workloads.
- Defaults:
  - output root: `results/fault_tolerance_256_flowsim_full_mixtral/`
  - topologies: `Meta,HPN,DeepSeek,Zcube,RO,ROFT`
  - error probabilities: `0..15%`
  - error model: `bandwidth_scale`
  - `FLOWSIM_WRITE_FCT=0`
  - `FLOWSIM_PROGRESS=0`
- Rationale: full Mixtral points are long enough that the user should launch them as a resumable batch from a terminal. The wrapper avoids requiring a long Python command and makes common overrides explicit through environment variables.
- Verification:
  - `bash -n experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh`
  - `python3 -m py_compile experiments/flowsim_256/run_fault_probability_sweep.py`

### 2026-06-23: Reclaim htsim Packet-Level RoCE Flow Owners With a Grace Window

- Full normal 256 dense Meta htsim `spray_rr` previously failed before completing the first topology: the process retained every completed per-flow `RoceSrc/RoceSink/Route/Trigger` owner until `htsim_destroy()` and was OOM-killed around forward `180/1262`, with RSS about 518 GB.
- Immediate or small-batch reclamation is unsafe for RoCE spray because duplicate/out-of-order packets can remain queued after the cumulative ACK completes a flow. Deleting the per-flow route endpoints too early can leave queued packets with dangling route/sink pointers and crash in `Packet::sendOn()`.
- Decision: reclaim completed flow owners only after a large completion-count grace window. Each completed flow records a completion sequence and is eligible for deletion only after at least `HTSIM_FLOW_RECLAIM_BATCH` later completions. The default is 262144 and can be tuned through the environment.
- Decision: `RoceSrc` owns and frees the route copies created by `set_paths()`, so `spray_rr` route vectors do not leak when a flow owner is eventually reclaimed.
- Rationale: this keeps packet-level RoCE semantics intact, avoids adding packet refcounting to htsim internals, and bounds memory for dense workloads without deleting route endpoints still referenced by delayed packets.
- Verification:
  - `env PATH=/usr/bin:/bin:$PATH ./scripts/build.sh -c htsim`
  - short dense Meta spray smoke with `/tmp/htsim_dense256_short10_1mib.txt`: exit 0, `EndToEnd.csv` 15 lines, `fct.txt` 144897 lines, maximum RSS about 390 MB.
  - full normal dense Meta spray 300s window: timeout 124, no segfault/OOM, forward `9/1262`, `fct.txt` 36840 lines, maximum RSS about 5.0 GB, `EndToEnd.csv` empty because the workload was intentionally interrupted before completion.

## Ongoing Rule

After each future development change, update:

- `.ai/current_context.md`
- `.ai/decisions.md`
- relevant `.ai/modules/*.md`

Each post-change response should include:

- modification summary
- affected modules
- potential risks
- follow-up recommendations
