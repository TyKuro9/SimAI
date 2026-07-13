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

## htsim Packet Backend Notes

- htsim packet-level RoCE can deliver callbacks after the backend event queue has drained or while ASTRA is flushing final streams.
- `NcclTreeFlowModel` protects shared flow maps, free-packet counters, QP wait queues, and stream counters with the local `FlowCriticalSection` helper before issuing additional send/recv work.
- Packet release captures per-packet processing flags as arguments instead of relying on mutable object fields that can be changed by a later callback.
- Missing flow-map entries are checked explicitly so late or already-consumed callbacks do not create default map entries that hide stuck-stream bugs.

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
