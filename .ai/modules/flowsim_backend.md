# Module: FlowSim Backend

## Responsibilities

- Provide a lightweight alternative to NS-3 for topology-aware flow/chunk simulation.
- Use precomputed routes and link-sharing calculations instead of packet/QP protocol simulation.
- Support fast batch topology comparisons.
- Emit NS-3-like `fct.txt` output for downstream analysis compatibility.

## Main Files

Current project invocation:

- `run_256moe_flowsim.sh`
- `run_256dense_flowsim.sh`
- `run_mixtral_1024moe_flowsim.sh`
- `experiments/flowsim_*/*.sh`

External implementation:

- `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim`
- `/home/zty/Topo/m4/SimAI/scripts/build.sh`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/FlowsimAstra.cc`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/FlowsimNetwork.*`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/FlowSim.*`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/EventQueue.*`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/Topology.*`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/TopologyBuilder.*`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/Chunk.*`
- `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/Link.h`

## Key Classes

- `FlowSimNetWork`
- `FlowSim`
- `EventQueue`
- `Topology`
- `Chunk`
- `Link`
- `Device`
- `RoutingFramework`

## Core Interfaces

- `FlowSimNetWork::sim_send()`
- `FlowSimNetWork::sim_recv()`
- `FlowSim::Send()`
- `FlowSim::Schedule()`
- `FlowSim::Run()`
- `Topology::send_with_batching()`
- `Topology::update_link_states()`
- `Topology::schedule_next_min_completion_set()`
- `WriteFlowFct()`

## Inputs

- workload from `SimAI_TyKuro9/my_workloads`
- topology from `SimAI_TyKuro9/mytopo`
- output directory under `SimAI_TyKuro9/experiments/flowsim_results`
- environment variables: `FLOWSIM_BIN`, `FLOWSIM_THREADS`, `AS_SEND_LAT`, `AS_NVLS_ENABLE`
- verbose logging override: `FLOWSIM_VERBOSE=1` or `FS_VERBOSE=1`
- progress logging override: `FLOWSIM_PROGRESS=0` disables default `[LAYER]` progress lines
- wall-clock profiling: `FLOWSIM_PROFILE=1`
- `FLOWSIM_ROOT` for permission repair script override, defaulting to `/home/zty/Topo/m4/SimAI`

## Outputs

- `EndToEnd.csv`
- `detailed_*.csv`
- `fct.txt`
- batch logs
- 256 error-probability sweep summaries and plots under `results/fault_tolerance_256_flowsim_*` when using `experiments/flowsim_256/run_fault_probability_sweep.py`

## Dependencies

- External `/home/zty/Topo/m4/SimAI`
- User-owned remote: `git@github.com:TyKuro9/SimAI-FlowSim.git`
- `AstraSim::Sys`, `Workload`, `MockNCCL`, `NcclTreeFlowModel`
- `RoutingFramework`

## Difference from NS-3

- NS-3 models RDMA/QP/protocol behavior.
- FlowSim models flow/chunk completion over shared links.
- NS-3 callbacks come from QP send/receive completion.
- FlowSim callbacks come from chunk completion events.
- FlowSim intentionally uses NS-3-like FCT text format.
- `EndToEnd.csv` is written by upper-level `Workload::report()`, not by the FlowSim FCT writer. A FlowSim log ending with `SimAI-FlowSim finished` can still have an empty `EndToEnd.csv` if remaining streams never trigger workload reporting.

## Zcube 256 MoE EndToEnd Note

- Observed symptom: `/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/256/ZcubeMoE/EndToEnd.csv` stayed empty while other topology outputs were non-empty.
- Root cause found from logs: Zcube reached FlowSim/FCT completion but lacked `workload stats` and `all passes finished`; rank0 still had a small number of streams not counted as finished after the FlowSim event queue became empty.
- Additional root cause found from a compact ZcubeMini MoE reproducer: the workload can issue non-`None` zero-byte collectives such as `final_column REDUCESCATTER 0` during input-gradient. FlowSim creates no chunks/events for size 0, so a `DataSet` created for that collective can never receive a completion callback.
- External fix location:
  - `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/system/Sys.hh`
  - `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/system/Sys.cc`
  - `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/FlowsimAstra.cc`
- Fix behavior: after `FlowSim::Run()`, FlowSim drains active streams whose `phases_to_go` are exhausted by calling the existing `Sys::proceed_to_next_vnet_baseline()` path. This preserves normal dataset notifier and `Workload::report()` behavior.
- Zero-byte collective fix behavior: `Layer` skips non-`None` zero-byte forward/input-gradient/weight-gradient collectives before creating a `DataSet`. This preserves all nonzero route, scheduling, and callback behavior.
- Diagnostic rule: if `EndToEnd.csv` is empty, grep the FlowSim log for `workload stats for the job scheduled` and `all passes finished`; if absent, the upper workload report did not execute.
- Compact reproducer:
  - main-project worktree: `/home/zty/Topo/worktrees/SimAI_TyKuro9-flowsim-csv-debug`
  - command: `bash experiments/flowsim_repro/zcube_moe_csv_missing/run.sh`
  - fixed binary result: exits 0, `EndToEnd.csv` is 1948 bytes, `fct.txt` has 2208 lines.
- Full 256 verification:
  - command: `timeout 28800 env FLOWSIM_WRITE_FCT=0 bash run_256moe_flowsim.sh Zcube`
  - result: exits 0, logs `workload stats`, `all passes finished`, and `SimAI-FlowSim finished`
  - output: `/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/256/ZcubeMoE/EndToEnd.csv` is 323759 bytes
  - note: `FLOWSIM_WRITE_FCT=0` intentionally disables FCT writes for faster verification, so `[FCT SUMMARY] lines=0` is expected and any existing `fct.txt` may be stale from an earlier interrupted run.
- Remote publication:
  - repository: `TyKuro9/SimAI-FlowSim`
  - branch: `main`
  - commit: `8cc581238e9e7b06429301746720bef1d2f16ac9`
  - local remote name: `tykuro9`

## Current External FlowSim Local Patches

- Final drain after `FlowSim::Run()`:
  - `Sys::drain_finished_streams()` completes active streams whose `phases_to_go` is empty through the existing `proceed_to_next_vnet_baseline()` path.
  - `FlowsimAstra.cc` repeatedly drains all systems until no more finished streams are found.
- Zero-byte collective no-op handling:
  - `Layer::issue_forward_pass_comm()`, `Layer::issue_input_grad_comm()`, and `Layer::issue_weight_grad_comm()` return early for non-`None` collectives with size `0`.
  - Blocking zero-byte collectives notify the workload immediately through the existing `workload->call(EventType::General, NULL)` path.
- FlowSim lifecycle guard:
  - `Sys::call_events()` no longer self-deletes FlowSim backend systems at workload completion. `FlowsimAstra.cc` still holds those pointers for final drain and finish handling, so self-delete caused a post-report segfault in the compact reproducer.
- Quiet-by-default logging:
  - `Common.hh` provides `FlowSimVerboseLoggingEnabled()`.
  - `FlowsimNetwork.cc`, `Workload.cc`, `Layer.cc`, `Sys.cc`, and `RingTopology.cc` gate high-volume stdout behind `FLOWSIM_VERBOSE` / `FS_VERBOSE`.
  - Default logs keep startup/routing/FCT/drain/final summaries and suppress per-flow/per-collective diagnostics.
- Lightweight progress:
  - `Workload::maybe_report_progress()` prints rank0 layer progress once per `pass/state/layer` transition.
  - Format: `[LAYER] pass=<pass> state=<state> layer=<current>/<total> name=<layer_name> time=<tick>`.
  - `FLOWSIM_PROGRESS=0` disables these progress lines without enabling verbose logs.
  - `FlowsimAstra.cc` sets `UserParam::mode = ModeType::FLOWSIM` so progress is scoped to FlowSim.
- Route lookup cache:
  - `RoutingFramework::GetFlowSimPathByNodeIds()` caches paths by `(src,dst)`.
  - Cache invalidates on `ParseTopology()` and `PrecalculateRoutingTables()`.
  - This preserves current FlowSim route semantics because the uncached function uses a fixed flow key for each source/destination pair.
- Wall-clock profiler:
  - `FlowSimProfiler.*` records stage totals when `FLOWSIM_PROFILE=1`.
  - `FlowsimAstra.cc` prints accumulated profile data on normal completion and on SIGTERM/SIGINT, which makes `timeout`-based profiling useful.
  - Profiling stages cover routing lookup/build, event queue operations, topology batching, `update_link_states`, completion scheduling, and FlowSim callback paths.
- Link-state recalculation optimization:
  - `Topology::update_link_states()` now builds per-active-link state with remaining bandwidth and unfixed chunk count.
  - When a bottleneck link fixes chunks, the implementation updates only the links those newly fixed chunks traverse.
  - This avoids repeatedly rescanning each active link's full chunk set while preserving progressive max-min filling behavior.
  - Bottleneck-link selection uses a lazy min-heap keyed by fair share, so affected links update their heap entries while unaffected links are not rescanned each progressive-filling round.
  - Chunks cache active `Link*` pointers and use an epoch marker for fixed-rate state, reducing repeated map lookups and temporary fixed-set allocations inside each recalculation.
- Dirty link-state flush:
  - Chunk add/remove and batch processing call a dirty path instead of directly recomputing link rates.
  - `post_batch_completion_callback()` consumes any pending chunks, updates active chunk remaining sizes, runs link-state recomputation once for accumulated changes, then reschedules the next completion set.
  - This primarily removes duplicated recomputation between batch processing and completion post-processing at the same simulated timestamp.

## Performance Notes

- FlowSim runtime can be dominated by stdout when per-flow/per-collective verbose logs are enabled on large MoE workloads. Keep verbose disabled for normal batch runs; leave `[LAYER]` progress enabled for observability or set `FLOWSIM_PROGRESS=0` for maximum quiet.
- Current FlowSim parses topology `error_rate` but does not use it in link-sharing or completion-time calculations. For FlowSim JCT-versus-error-probability experiments, `experiments/flowsim_256/run_fault_probability_sweep.py` uses a generated-topology approximation that scales inter-server bandwidth by `(1-p)` and records `p` in the topology error-rate column.
- The final drain adds a small end-of-run cleanup step but is required to trigger `Workload::report()` for Zcube MoE cases where the FlowSim event queue empties before upper streams are counted finished.
- The `(src,dst)` routing cache is the first low-risk acceleration point because it avoids repeated path lookup without changing link sharing, chunk scheduling, callbacks, or workload ordering.
- Current Zcube profiling evidence says route lookup is no longer material: the pre-optimization 120s sample spent ~114s in `Topology::update_link_states()` versus ~17ms in route lookup.
- After the per-link-state optimization, a 120s Zcube profile showed `Topology::update_link_states` average cost drop from ~59.254 ms/call to ~6.610 ms/call while processing many more events in the same wall-clock window.
- After the dirty/flush path, a 120s Zcube profile processed 528704 sends and 527663 chunk completions; `process_batch_of_chunks` became negligible at ~241 ms total, while `update_link_states` remained dominant at ~100272 ms total.
- After lazy min-heap bottleneck selection, a 120s Zcube profile processed 675664 sends and 674553 chunk completions; `Topology::update_link_states` averaged ~1.750 ms/call.
- Future acceleration should focus on reducing the remaining `update_link_states` data-structure churn, completion scheduling, and possibly event-time ordering; route lookup and batch processing are no longer material.
- Full 256 Zcube MoE completion remains expensive but is now proven to finish. A previous `FLOWSIM_PROGRESS=0 timeout 7200 bash run_256moe_flowsim.sh Zcube` timed out before workload reporting; a later 28800s timeout run with FCT writes disabled completed normally and wrote the non-empty `EndToEnd.csv`.
- Full 1837-layer Mixtral 256 MoE error-probability sweeps are too expensive for quick interactive runs. A Meta 1% bandwidth-scale point ran for more than 7 minutes before interruption. For quick curve generation, use `experiments/flowsim_256/moe_256_fault_comm.txt`, which keeps 256-GPU MoE communication structure but reduces the layer count to 8.

## Modification Risk

- High if changing callback matching structures because it must stay compatible with MockNCCL flow tags.
- High if changing final stream drain semantics because it touches shared `Sys` stream lifecycle behavior.
- Medium if changing topology parsing or path fallback.
- Medium if changing FCT format.
- High operational risk from external absolute binary path.

## Local Permission Maintenance

- FlowSim compilation and execution should be user-owned and should not require `sudo`.
- If `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim` or `astra-sim-alibabacloud/build/simai_flowsim` becomes owned by `nobody`, `root`, or another user, repair from the main project with `./scripts/fix_local_permissions.sh`.
- The whole `build/simai_flowsim` subtree is included because the FlowSim build wrapper creates/removes both `build/` and `result/`.
- The script uses the external FlowSim root recorded here unless `FLOWSIM_ROOT` is provided.
- On a new machine, clone the external FlowSim fork from `git@github.com:TyKuro9/SimAI-FlowSim.git` when reproducing the verified Zcube MoE CSV behavior.
