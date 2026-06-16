# Current Context

## Current Project State

- Project understanding phase is complete for README/config/build/entry/core modules.
- Non-vidur architecture has been documented in `docs/Architecture.md`, `docs/Modules.md`, and `docs/Flow.md`.
- `.ai/` now serves as the persistent maintenance knowledge base.
- There are pre-existing uncommitted changes in the worktree outside this knowledge-base work. Treat them as user-owned unless explicitly told otherwise.
- FlowSim is an important backend path, but its source and binary live in `/home/zty/Topo/m4/SimAI`; this project invokes it through scripts. The user-owned remote for this external FlowSim fork is `git@github.com:TyKuro9/SimAI-FlowSim.git`.
- Local SimAI/FlowSim build and run paths should not require `sudo`; if historical artifacts are owned by `nobody`/`root`, use `scripts/fix_local_permissions.sh` once to repair targeted build, binary, NS-3 `extern/network_backend`, and external FlowSim `build/simai_flowsim` paths.
- Zcube 256 MoE FlowSim `EndToEnd.csv` being empty is not a file-permission issue. The full Zcube log can finish FlowSim/FCT while missing `workload stats`/`all passes finished`, which means `Workload::report()` did not run.
- External FlowSim now has a final drain after `FlowSim::Run()` to complete rank streams whose phases are already exhausted when the FlowSim event queue becomes empty. This lets `DataSet` notifiers and `Workload::report()` run and write `EndToEnd.csv`.
- External FlowSim verbose stdout is now default-off. Set `FLOWSIM_VERBOSE=1` or `FS_VERBOSE=1` to restore per-send/per-callback, workload/layer, chunk-size, and ring-topology diagnostic logs.
- External FlowSim lightweight layer progress is default-on and prints `[LAYER] pass=... state=... layer=current/total name=... time=...`; set `FLOWSIM_PROGRESS=0` to disable it for the quietest batch runs.
- External FlowSim route lookup now caches `RoutingFramework::GetFlowSimPathByNodeIds(src,dst)` by `(src,dst)` and clears that cache when topology/routing tables are rebuilt. This does not change route selection for current FlowSim because the uncached call constructs the same fixed `FlowKey` for a given source/destination pair.
- External FlowSim has optional wall-clock profiling via `FLOWSIM_PROFILE=1`. A 120s interrupted Zcube 256 MoE profile showed runtime is dominated by `Topology::update_link_states()` inside batch/completion processing; route lookup was only ~17 ms across ~98k sends in that sample.
- External FlowSim `Topology::update_link_states()` now keeps per-link remaining bandwidth and unfixed chunk counts during progressive filling. This preserves max-min link sharing semantics while avoiding repeated scans of every active chunk on every link; a 120s Zcube profile reduced `update_link_states` average time from ~59.254 ms/call to ~6.610 ms/call.
- External FlowSim now uses a dirty/flush path for link-state refresh: chunk add/remove and batch processing mark link state dirty, while a single post handler processes pending chunks, updates remaining sizes, recalculates rates, and reschedules completions for that event time.
- External FlowSim `Topology::update_link_states()` now uses a lazy min-heap for bottleneck-link selection. A 120s Zcube profile reduced `update_link_states` average time from the dirty/flush sample's ~2.605 ms/call to ~1.750 ms/call and processed 675664 sends in the same window.
- External FlowSim now treats non-`None` zero-byte collectives as no-ops in `Layer` before creating a `DataSet`. This fixes the Zcube MoE CSV-empty root cause where `final_column REDUCESCATTER 0` input-gradient created an outstanding dataset but no FlowSim chunks/events, so no completion callback could ever arrive.
- Actual `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim` was rebuilt after the zero-byte collective fix and later link-state micro-optimizations. These external FlowSim changes are committed as `8cc581238e9e7b06429301746720bef1d2f16ac9` and pushed to `TyKuro9/SimAI-FlowSim` on `main`. The compact ZcubeMini MoE reproducer in `/home/zty/Topo/worktrees/SimAI_TyKuro9-flowsim-csv-debug/experiments/flowsim_repro/zcube_moe_csv_missing` exits 0, logs `workload stats` / `all passes finished`, writes `EndToEnd.csv` with 1948 bytes, and writes `fct.txt` with 2208 lines.
- Full 256 Zcube MoE FlowSim completion is now verified. `timeout 28800 env FLOWSIM_WRITE_FCT=0 bash run_256moe_flowsim.sh Zcube` exited 0, logged `workload stats` / `all passes finished` / `SimAI-FlowSim finished`, and wrote `/home/zty/Topo/SimAI_TyKuro9/experiments/flowsim_results/256/ZcubeMoE/EndToEnd.csv` with 323759 bytes. FCT writing was disabled for this verification, so `[FCT SUMMARY] lines=0` is expected and any old large `fct.txt` in that directory may be stale.
- NS-3 Mixtral runs can create an empty `EndToEnd.csv` when the NS-3 event queue becomes empty after the final pass but before upper-stack stream completion has been counted, so `Workload::report()` is never reached. The NS-3 path now drains finished streams after `Simulator::Run()` and before `Simulator::Destroy()`, mirroring the FlowSim final-drain fix.
- NS-3 `Sys` lifetime is now kept by the NS-3 entrypoint instead of self-deleting when workload completion empties local events. This prevents post-report segfaults when the entrypoint still iterates the `systems` vector for final drain/destroy handling.
- NS-3 MockNCCL group initialization now derives `PP_size` from the workload header and computes `DP_size` from `all_gpus`, not `total_nodes`, so NVSwitch/extra topology nodes do not corrupt DP/EP sizing for MoE runs.
- `NcclTreeFlowModel` now disables empty/null flow models instead of constructing an active algorithm with no usable flows/channels.
- Verified 64-GPU Zcube NS-3 smoke runs on 2026-06-16 using `experiments/ns3_repro/zcube64_csv`: `dense_64_tiny.txt` exited 0 and wrote `results_dense_tiny_verify/EndToEnd.csv` with 1614 bytes; `moe_64_alltoall_ig_tiny.txt` (`tp8/pp1/ep4`) exited 0 and wrote `results_moe_alltoall_ig_tiny_verify/EndToEnd.csv` with 1932 bytes. Both logs contain `workload stats for the job scheduled` and `all passes finished`.
- The current 64-GPU MoE smoke covers forward and input-gradient `ALLTOALL_EP`, DP/DP_EP gradient collectives, and zero-byte `REDUCESCATTER`. It is a CSV/reporting correctness smoke only; full Mixtral 256 NS-3 topology coverage is still a separate, longer verification.
- NS-3 `Unable to create file: ./experiments/ns3_results/csv/...` can also be a local permission issue: existing result directories/files may be owned by `nobody:nogroup` from earlier sudo/container runs. `run_mixtral_256moe_ns3.sh` now creates/checks all output directories up front, and `scripts/fix_local_permissions.sh` includes `experiments/ns3_results`.
- htsim/RoCE is now added as a parallel backend, not a replacement for NS-3. The submodule lives at `extern/network_backend/htsim` and is pinned to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- `./scripts/build.sh -c htsim` builds `bin/SimAI_htsim`; the build wrapper uses `/usr/bin/cmake` by default because this environment's `cmake` resolves to a snap wrapper that cannot run under the sandbox.
- `bin/SimAI_htsim` accepts existing SimAI workload/topology/config inputs plus `-r single|ecmp|spray_rr`. `HTSIM_ROUTE_STRATEGY` can override the route strategy, and `HTSIM_LINK_BW_GBPS` can override the ASTRA-facing htsim completion estimator bandwidth.
- htsim native RoCE now supports multi-path packet spraying by extending `RoceSrc` with per-data-packet route selection. `datacenter/htsim_roce -strat perm -paths <N>` no longer aborts for RoCE.
- Verified htsim smoke runs on 2026-06-15: `./scripts/build.sh -c htsim`, native `htsim_roce` tiny topology with `-strat perm -paths 2`, and `bin/SimAI_htsim` spray smoke writing `/tmp/simai_htsim_smoke/EndToEnd.csv` with 1813 rows.

## Current Focus Modules

- `build_and_scripts`: because project execution is script-driven and contains absolute paths.
- `flowsim_backend`: because it is easy to confuse with NS-3 but is a distinct backend.
- `ns3_backend`: high-fidelity simulation path.
- `htsim_backend`: RoCE/event backend for route-strategy experiments such as deterministic per-packet Spray.
- `system` and `collective_mocknccl`: shared upper-stack logic.

## Later Development Direction

- Keep `.ai/` updated before and after changes.
- When modifying a backend, verify whether the change affects common `Sys`/MockNCCL semantics or only backend callback behavior.
- For FlowSim `EndToEnd.csv` failures, first check whether logs contain `workload stats for the job scheduled` and `all passes finished`. `SimAI-FlowSim finished` alone only means the FlowSim event queue exited.
- For Zcube MoE FlowSim specifically, also check for zero-byte non-`None` collectives such as `final_column REDUCESCATTER 0`; these must be skipped as no-ops before `DataSet` creation.
- For NS-3 `EndToEnd.csv` failures, first check whether the log contains `workload stats for the job scheduled` and `all passes finished`. If absent but the final pass completed, suspect that stream completion callbacks were not drained after the NS-3 event queue emptied.
- For NS-3 small repros, start with `experiments/ns3_repro/zcube64_csv`. Use `dense_64_tiny.txt` first, then `moe_64_alltoall_ig_tiny.txt`; both are intended to verify CSV/reporting, not FCT fidelity. Final verified outputs from this turn are `results_dense_tiny_verify/EndToEnd.csv` and `results_moe_alltoall_ig_tiny_verify/EndToEnd.csv`.
- For NS-3 MoE work, keep workload `tp/pp/ep/all_gpus` internally consistent. For 64 GPUs, `tp8/pp1/ep4` gives `DP=8` and `DP_EP=2`; copying 256-GPU `tp8/pp2/ep8` makes `DP/EP` zero and can fail before the network path is exercised.
- For NS-3 CSV open failures before simulation starts, check `ls -ld experiments/ns3_results/csv*`; if owner is `root` or `nobody`, run `bash scripts/fix_local_permissions.sh` from an interactive terminal and avoid `sudo ./bin/SimAI_simulator` runs.
- For htsim backend work, start from `.ai/modules/htsim_backend.md`. Keep NS-3 intact and treat htsim as an additional backend unless the user explicitly asks to remove/replace NS-3.
- For htsim RoCE route bugs, inspect route ownership carefully: htsim `Route(orig, dst)` appends the transport endpoint, while `Route::add_endpoints()` currently only updates reverse routes.
- For FlowSim performance regressions, first separate simulation work from stdout cost. Default logs include FlowSim/ROUTING startup summaries, lightweight `[LAYER]` progress, and final FCT/drain/report summaries; detailed per-flow/per-collective logs require `FLOWSIM_VERBOSE=1`.
- For Zcube FlowSim slowness, inspect `FLOWSIM_PROFILE=1` output before changing routing. Current evidence points at max-min link-rate recalculation (`Topology::update_link_states`) rather than route lookup.
- If further Zcube acceleration is needed, start from the remaining `update_link_states` cost and completion scheduling; route lookup, FCT writing, and batch processing are not currently material for the verified full run.
- When changing experiment scripts, preserve topology/workload/output conventions and document any absolute path changes.
- When adding support for new topology/workload variants, update `topology_config_results.md` and related backend docs.

## Current Open Questions

- Should FlowSim eventually be vendored or submoduled into `SimAI_TyKuro9`, or remain an external dependency on `/home/zty/Topo/m4/SimAI` with remote `TyKuro9/SimAI-FlowSim`?
- Should absolute paths in scripts be parameterized for portability?
- Should `scripts/fix_local_permissions.sh` eventually cover additional backend build directories if analytical/physical builds hit the same ownership issue?
- Should the external FlowSim final-drain fix be upstreamed to the original `liecn/SimAI`, vendored, or kept in the user-owned `TyKuro9/SimAI-FlowSim` fork?
- Should full 256-GPU Mixtral NS-3 verification be batched topology-by-topology with FCT disabled or reduced, now that the 64-GPU CSV/reporting smoke covers backward EP all-to-all?
- Should vidur-related paths remain excluded from this knowledge base until a dedicated analysis request?

## Development Rule Reminder

For future development requests:

1. Read `.ai/current_context.md`.
2. Read relevant `.ai/modules/*.md`.
3. Check source only if needed.
4. Propose/choose implementation plan.
5. Implement.
6. Update `.ai/current_context.md`, `.ai/decisions.md`, and relevant module docs.
