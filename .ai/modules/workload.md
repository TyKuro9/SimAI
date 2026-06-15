# Module: Workload

## Responsibilities

- Parse workload files.
- Create and own `Layer` objects.
- Drive model execution state machines.
- Trigger layer compute and communication phases.
- Produce end-to-end and per-layer statistics.

## Main Files

- `astra-sim-alibabacloud/astra-sim/workload/Workload.hh`
- `astra-sim-alibabacloud/astra-sim/workload/Workload.cc`
- `astra-sim-alibabacloud/astra-sim/workload/Layer.hh`
- `astra-sim-alibabacloud/astra-sim/workload/Layer.cc`
- `astra-sim-alibabacloud/astra-sim/workload/CSVWriter.hh`
- `astra-sim-alibabacloud/astra-sim/workload/CSVWriter.cc`

## Key Classes

- `AstraSim::Workload`
- `AstraSim::Layer`
- `AstraSim::CSVWriter`

## Core Interfaces

- `Workload::fire()`
- `Workload::call(EventType, CallData*)`
- `Workload::initialize_workload(std::string)`
- `Workload::report()`
- `Layer::call(EventType, CallData*)`
- `Layer::issue_*_comm()`

## Inputs

- workload text file path
- `Sys` pointer
- number of passes
- result path

## Outputs

- calls into `Sys` to schedule communication
- `EndToEnd.csv`
- `detailed_<nodes>.csv`
- dimension utilization CSV

## Dependencies

- `AstraSim::Sys`
- `Layer`
- `CSVWriter`
- `AstraSimDataAPI`

## Modification Risk

- High: workload state machine changes can affect every backend.
- High: workload parser changes can invalidate existing AICB-generated workloads.
- Medium: reporting changes may affect downstream analysis scripts.

