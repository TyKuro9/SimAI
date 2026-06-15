# Module: Collective and MockNCCL

## Responsibilities

- Represent collective communication algorithms.
- Build NCCL-like communication groups.
- Generate ring/tree/NVLS channels.
- Convert collective operations into dependency-aware point-to-point flow graphs.
- Drive `PacketReceived`, `PacketSentFinshed`, and stream completion events.

## Main Files

- `astra-sim-alibabacloud/astra-sim/system/collective/*.cc`
- `astra-sim-alibabacloud/astra-sim/system/collective/*.hh`
- `astra-sim-alibabacloud/astra-sim/system/collective/NcclTreeFlowModel.*`
- `astra-sim-alibabacloud/astra-sim/system/MockNcclGroup.*`
- `astra-sim-alibabacloud/astra-sim/system/MockNcclChannel.*`
- `astra-sim-alibabacloud/astra-sim/system/MockNccl.h`
- `astra-sim-alibabacloud/astra-sim/system/MockNcclQps.h`

## Key Classes

- `MockNccl::MockNcclGroup`
- `MockNccl::MockNcclComm`
- `AstraSim::NcclTreeFlowModel`
- `AstraSim::CollectiveImplementation`
- `AstraSim::Algorithm`

## Core Interfaces

- `MockNcclComm::get_flow_model()`
- `MockNcclComm::get_rings()`
- `MockNcclComm::get_treechannels()`
- `MockNcclGroup::genringchannels()`
- `NcclTreeFlowModel::run()`
- `NcclTreeFlowModel::insert_packets()`
- `NcclTreeFlowModel::ready()`

## Inputs

- rank id
- TP/DP/PP/EP/DP_EP group settings
- collective type
- data size
- layer/loop state

## Outputs

- flow models
- backend send/recv calls through `Sys`
- stream completion callbacks

## Dependencies

- `Sys`
- `RingTopology` / `GeneralComplexTopology`
- backend callback event data

## Modification Risk

- Very high: small changes can alter every backend result.
- Flow dependency bugs often show up as stuck streams or unmatched send/recv tags.
- Keep FlowSim and NS-3 callback matching behavior aligned when changing flow tags.

