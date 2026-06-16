# Architecture

## System Architecture

The project is organized around a shared upper simulation stack and multiple interchangeable backend implementations.

```text
AICB / my_workloads
        |
        v
Workload + Layer
        |
        v
AstraSim::Sys
        |
        +--> LogicalTopology / CollectiveImplementation
        |
        +--> MockNCCL group/channel/flow model
        |
        +--> SchedulerUnit / StreamBaseline / DataSet
        |
        v
AstraNetworkAPI
        |
        +--> AnalyticalNetWork + AnaSim
        |
        +--> ASTRASimNetwork + NS-3 RDMA/QBB backend
        |
        +--> FlowSimNetWork + FlowSim EventQueue/Topology/Chunk backend
        |
        +--> HtsimNetwork + htsim EventList/RoCE backend
        |
        +--> SimAiPhyNetWork + Physical RDMA backend
```

## Module Relationships

- AICB produces workload descriptions.
- `Workload` parses workload descriptions into `Layer` objects.
- `Layer` issues compute and collective communication phases.
- `Sys` owns scheduling, stream lifecycle, event registration, logical topologies, and network API calls.
- MockNCCL builds TP/DP/EP/DP_EP communication groups and converts collective operations into flow models.
- `NcclTreeFlowModel` executes dependency-aware point-to-point flow graphs.
- Network frontends implement `AstraNetworkAPI` and connect the common upper stack to a backend.

## Core Data Structures

- `AstraSim::Sys`: central system layer object per rank/node.
- `AstraSim::Workload`: workload state machine and report owner.
- `AstraSim::Layer`: per-layer compute and communication model.
- `AstraSim::DataSet`: collective payload and stream grouping.
- `AstraSim::BaseStream` / `StreamBaseline`: stream execution objects.
- `MockNccl::MockNcclGroup`: global NCCL-like communication groups.
- `MockNccl::MockNcclComm`: rank-local NCCL-like communicator.
- `MockNccl::FlowModels`: map of channel/flow id to point-to-point flow metadata.
- `AstraSim::ncclFlowTag`: flow context propagated through send/recv callbacks.
- `recvHash`, `expeRecvHash`, `sentHash`, `receiver_pending_queue`: backend callback matching structures.
- FlowSim-specific `EventQueue`, `Topology`, `Chunk`, `Link`, `Device`.
- NS-3-specific `RdmaHw`, `RdmaDriver`, `QbbNetDevice`, `SwitchNode`, `SwitchMmu`, `RdmaQueuePair`.
- htsim-specific `EventList`, `RoceSrc`, `RoceSink`, `Route`, and FatTree topology/connection-matrix utilities.

## Core Design Ideas

- Keep the model semantics in ASTRA-sim and MockNCCL, while letting backends differ in network fidelity.
- Use `AstraNetworkAPI` as the seam between common simulation logic and backend-specific network behavior.
- Model workloads as layered compute/communication phases, not arbitrary executable model code.
- Represent collective operations as flow graphs with explicit dependency and callback propagation.
- Use NS-3 when protocol fidelity matters.
- Use htsim/RoCE when a faster packet/event backend with RoCE-style routing experiments such as per-packet Spray is needed.
- Use FlowSim when fast topology-scale flow completion approximation matters.
- Keep batch experiments scriptable through topology/config/workload files.

## Backend Comparison

| Backend | Granularity | Strength | Main Entry |
| --- | --- | --- | --- |
| Analytical | abstract timing | very fast estimation | `bin/SimAI_analytical` |
| NS-3 | packet/QP/protocol | high-fidelity network behavior | `bin/SimAI_simulator` |
| htsim/RoCE | event/packet RoCE model | fast RoCE route-strategy experiments | `bin/SimAI_htsim` |
| FlowSim | flow/chunk/link sharing | large-scale fast topology comparison | `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim` |
| Physical/RDMA | real RDMA traffic | physical cluster traffic generation | `bin/SimAI_phynet` |
