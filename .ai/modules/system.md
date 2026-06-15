# Module: System

## Responsibilities

- Central scheduling and simulation state management.
- Own active streams, ready lists, event queues, logical topologies, and workload.
- Convert workload-issued communication into collective algorithms and stream execution.
- Call backend network APIs through `AstraNetworkAPI`.

## Main Files

- `astra-sim-alibabacloud/astra-sim/system/Sys.hh`
- `astra-sim-alibabacloud/astra-sim/system/Sys.cc`
- `astra-sim-alibabacloud/astra-sim/system/Common.hh`
- `astra-sim-alibabacloud/astra-sim/system/BaseStream.*`
- `astra-sim-alibabacloud/astra-sim/system/StreamBaseline.*`
- `astra-sim-alibabacloud/astra-sim/system/DataSet.*`
- `astra-sim-alibabacloud/astra-sim/system/QueueLevels.*`
- `astra-sim-alibabacloud/astra-sim/system/MemBus.*`
- `astra-sim-alibabacloud/astra-sim/system/SimSendCaller.*`
- `astra-sim-alibabacloud/astra-sim/system/SimRecvCaller.*`

## Key Classes

- `AstraSim::Sys`
- `AstraSim::Sys::SchedulerUnit`
- `AstraSim::BaseStream`
- `AstraSim::StreamBaseline`
- `AstraSim::DataSet`
- `AstraSim::QueueLevels`
- `AstraSim::MemBus`

## Core Interfaces

- `Sys::front_end_sim_send()`
- `Sys::front_end_sim_recv()`
- `Sys::sim_send()`
- `Sys::sim_recv()`
- `Sys::register_event()`
- `Sys::try_register_event()`
- `Sys::schedule()`
- `Sys::get_nccl_Info()`

## Inputs

- backend `AstraNetworkAPI`
- workload path
- physical dimensions
- GPU/NVSwitch metadata

## Outputs

- scheduled backend sends/receives
- stream completion notifications
- workload reports

## Dependencies

- `AstraNetworkAPI`
- `Workload`
- `MockNCCL`
- `LogicalTopology`
- `CollectiveImplementation`

## Modification Risk

- Very high: `Sys` sits between all workload logic and all backends.
- Avoid broad refactors unless explicitly planned.
- Backend-specific behavior should normally live in the backend frontend, not in `Sys`.

