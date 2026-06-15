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

## Dependencies

- NS-3 simulation framework.
- `AstraSim::Sys`
- MockNCCL flow tags.
- topology/config files.

## Modification Risk

- Very high when changing callback matching, QP completion, or congestion-control logic.
- High if changing config parsing or topology assumptions.
- Keep FCT output format stable unless downstream scripts are updated.

