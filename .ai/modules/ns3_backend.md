# Module: NS-3 Backend

## Responsibilities

- Provide high-fidelity network simulation.
- Model RDMA, QBB, PFC, ECN, CNP, QP lifecycle, ACK/NACK, congestion control, switches, and NVSwitch.
- Adapt ASTRA-sim `sim_send`/`sim_recv` to NS-3 flow/QP events.

## Main Files

- `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/AstraSimNetwork.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/entry.h`
- `astra-sim-alibabacloud/astra-sim/network_frontend/ns3/common.h`
- `ns-3-alibabacloud/simulation/src/point-to-point/model/*`

## Key Classes

- `ASTRASimNetwork`
- `RdmaHw`
- `RdmaDriver`
- `RdmaQueuePair`
- `QbbNetDevice`
- `SwitchNode`
- `SwitchMmu`
- `NVSwitchNode`

## Core Interfaces

- `ASTRASimNetwork::sim_send()`
- `ASTRASimNetwork::sim_recv()`
- `SendFlow()`
- `qp_finish()`
- `send_finish()`
- `ReadConf()`
- `SetConfig()`
- `SetupNetwork()`

## Inputs

- workload file
- topology file
- network config file
- result directory
- environment variables such as `AS_SEND_LAT`, `AS_NVLS_ENABLE`, `AS_PXN_ENABLE`

## Outputs

- `EndToEnd.csv`
- `detailed_*.csv`
- `fct.txt`
- trace/PFC/monitor files depending on config
- logs

## EndToEnd CSV Notes

- `EndToEnd.csv` is written by upper-level `Workload::report()`, not directly by NS-3 packet/QP completion code.
- A zero-byte `EndToEnd.csv` with a log that lacks `workload stats for the job scheduled` and `all passes finished` means reporting did not run.
- `Unable to create file: <result-dir>` during `CSVWriter::initialize_csv()` means the result directory is missing or not writable. In local runs, existing `experiments/ns3_results/csv` directories owned by `nobody:nogroup` are a known cause.
- Observed Mixtral NS-3 logs could reach the end of pass 0 and then exit without `Workload::report()`, leaving `EndToEnd.csv` empty.
- The NS-3 entrypoint now wraps `Simulator::Run()` in a final-progress loop. After each run it drains finished streams, flushes current-tick ASTRA events, and repeats `Simulator::Run()` if that upper-stack progress schedules more NS-3 events.
- The drain uses the existing `Sys::proceed_to_next_vnet_baseline()` path so dataset notifiers, stream counters, and workload reporting remain on the normal upper-stack route.
- NS-3 `Sys` objects must not self-delete while the entrypoint still owns raw pointers in its `systems` vector. `Sys::call_events()` skips `delete this` for `NS3_MTP`/`NS3_MPI`; otherwise a successful report can be followed by a post-report segfault.
- A reusable 64-GPU Zcube CSV smoke lives in `experiments/ns3_repro/zcube64_csv`. Verified commands use `bin/SimAI_simulator`, `Zcube64_ns3.conf`, and the generated `Zcube_n8_k2_64g_8gps_200Gbps_H100` topology:
  - `dense_64_tiny.txt` -> `results_dense_tiny_verify/EndToEnd.csv` non-empty and log has `workload stats` / `all passes finished`.
  - `moe_64_alltoall_ig_tiny.txt` (`tp8/pp1/ep4`) -> `results_moe_alltoall_ig_tiny_verify/EndToEnd.csv` non-empty and log has `workload stats` / `all passes finished`.
- The MoE smoke covers forward and input-gradient `ALLTOALL_EP`, DP/DP_EP gradient collectives, and zero-byte `REDUCESCATTER`. It is a fast CSV/reporting check, not a full Mixtral 256 performance or FCT baseline.

## Dependencies

- NS-3 simulation framework.
- `AstraSim::Sys`
- MockNCCL flow tags.
- topology/config files.

## Modification Risk

- Very high when changing callback matching, QP completion, or congestion-control logic.
- High if changing config parsing or topology assumptions.
- Medium when changing final drain behavior because it affects when upper-stack stream completion is counted after the NS-3 event queue empties.
- Medium when changing MockNCCL DP/EP sizing because workload header values (`tp`, `pp`, `ep`, `all_gpus`) must stay consistent with topology GPU count; do not use `total_nodes` where NVSwitches are included.
- Keep FCT output format stable unless downstream scripts are updated.
