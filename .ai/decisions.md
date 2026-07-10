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

### 2026-07-10: Restrict HTSim Spray Tail Recovery to Final Drain

- Kept `HTSIM_ROCE_TAIL_RTO=0` for formal `spray_plb` runs because adaptive tail RTO can rewind and retransmit the full unacknowledged suffix while normal congestion is still active.
- Added `RoceSrc::recover_oldest_unacked()` and a final-drain recovery loop in `HtsimAstra.cc`. Recovery starts only when ASTRA cannot drain, schedule, start, or flush any more work and the HTSim event queue is empty.
- Each round sends one retransmission from every unfinished flow's cumulative ACK position, drains all resulting HTSim events, and then reassesses progress. It does not change the normal `_highest_sent` cursor.
- Default recovery is enabled with a 32768-round cap. Progress logging is sparse: first round, every 256 rounds, and whenever the unfinished-flow count changes.
- Verification: the 256 Meta 64 MiB-tail reproducer exited 0 in 32.09s with 58881 FCT lines after 808 recovery rounds; independent 256/1024 1 MiB smokes exited 0 without recovery.
- The formal 12-case 256/1024 Dense `spray_plb` FCT batch runs sequentially in tmux session `htsim_dense_scale_plb_fct_final_20260710`, output root `experiments/htsim_results/csv/htsim_dense_scale_table_spray_plb_final_recovery_20260710_191503`.

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
