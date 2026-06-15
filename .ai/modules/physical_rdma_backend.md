# Module: Physical/RDMA Backend

## Responsibilities

- Generate NCCL-like RDMA traffic in a physical CPU RDMA cluster environment.
- Use MPI bootstrap and optional ibverbs.
- Poll RDMA completions and feed them back into the shared ASTRA-sim/MockNCCL flow model.

## Main Files

- `astra-sim-alibabacloud/astra-sim/network_frontend/phynet/SimAiMain.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/phynet/SimAiPhyNetwork.*`
- `astra-sim-alibabacloud/astra-sim/network_frontend/phynet/PhySimAi.*`
- `astra-sim-alibabacloud/astra-sim/network_frontend/phynet/SimAiEntry.*`
- `astra-sim-alibabacloud/astra-sim/system/BootStrapnet.*`
- `astra-sim-alibabacloud/astra-sim/system/PhyMultiThread.*`
- `astra-sim-alibabacloud/astra-sim/system/SimAiFlowModelRdma.*`

## Key Classes

- `SimAiPhyNetWork`
- `PhyNetSim`
- `FlowPhyRdma`
- `PhyMultiThread`

## Core Interfaces

- `BootStrapNet()`
- `set_simai_network_callback()`
- `FlowPhyRdma::ibv_init()`
- `PhyNetSim::Run()`
- `notify_all_thread_finished()`

## Inputs

- MPI runtime arguments
- workload path
- GPU count
- optional RDMA GID index

## Outputs

- physical traffic
- logs
- result files under configured path

## Dependencies

- MPI
- libibverbs
- `AstraSim::Sys`
- `NcclTreeFlowModel`

## Modification Risk

- Very high: can affect real network resources and multi-process synchronization.
- Requires appropriate environment to test.
- Avoid speculative changes without a clear test plan.

