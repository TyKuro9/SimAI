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
- `FLOWSIM_ROOT` for permission repair script override, defaulting to `/home/zty/Topo/m4/SimAI`

## Outputs

- `EndToEnd.csv`
- `detailed_*.csv`
- `fct.txt`
- batch logs

## Dependencies

- External `/home/zty/Topo/m4/SimAI`
- `AstraSim::Sys`, `Workload`, `MockNCCL`, `NcclTreeFlowModel`
- `RoutingFramework`

## Difference from NS-3

- NS-3 models RDMA/QP/protocol behavior.
- FlowSim models flow/chunk completion over shared links.
- NS-3 callbacks come from QP send/receive completion.
- FlowSim callbacks come from chunk completion events.
- FlowSim intentionally uses NS-3-like FCT text format.

## Modification Risk

- High if changing callback matching structures because it must stay compatible with MockNCCL flow tags.
- Medium if changing topology parsing or path fallback.
- Medium if changing FCT format.
- High operational risk from external absolute binary path.

## Local Permission Maintenance

- FlowSim compilation and execution should be user-owned and should not require `sudo`.
- If `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim` or `astra-sim-alibabacloud/build/simai_flowsim` becomes owned by `nobody`, `root`, or another user, repair from the main project with `./scripts/fix_local_permissions.sh`.
- The whole `build/simai_flowsim` subtree is included because the FlowSim build wrapper creates/removes both `build/` and `result/`.
- The script uses the external FlowSim root recorded here unless `FLOWSIM_ROOT` is provided.
