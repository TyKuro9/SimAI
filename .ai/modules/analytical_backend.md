# Module: Analytical Backend

## Responsibilities

- Provide fast abstract simulation without packet-level network modeling.
- Implement `AstraNetworkAPI` with a simple event loop.
- Estimate communication using analytical data paths and ratios.

## Main Files

- `astra-sim-alibabacloud/astra-sim/network_frontend/analytical/AnalyticalAstra.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/analytical/AnalyticalNetwork.*`
- `astra-sim-alibabacloud/astra-sim/network_frontend/analytical/AnaSim.*`

## Key Classes

- `AnalyticalNetWork`
- `AnaSim`
- `UserParam`

## Core Interfaces

- `AnalyticalNetWork::sim_get_time()`
- `AnalyticalNetWork::sim_schedule()`
- `AnaSim::Schedule()`
- `AnaSim::Run()`

## Inputs

- workload path
- GPU count
- GPUs per server
- bus bandwidth or NIC/NVLink parameters
- ratio CSV data

## Outputs

- analytical result CSVs
- console logs

## Dependencies

- `AstraSim::Sys`
- `AstraParamParse`
- `AstraNetworkAPI`

## Modification Risk

- Medium: backend is simpler than NS-3/FlowSim but shares upper-stack behavior.
- Be careful with time unit consistency.

