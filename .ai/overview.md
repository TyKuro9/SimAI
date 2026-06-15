# Project Overview

## Project Goal

`SimAI_TyKuro9` is a simulation-oriented workspace for analyzing large-scale AI training and inference communication behavior. It combines workload generation, collective communication decomposition, system-level scheduling, topology/configuration management, and multiple network backends.

This knowledge base intentionally focuses on the non-vidur paths already analyzed. Vidur-related inference request scheduling is treated as out of scope until explicitly requested.

## Technology Stack

- C++: core simulation engine, ASTRA-sim system layer, network frontend adapters, MockNCCL/collective flow model, NS-3 integration, FlowSim backend, Physical/RDMA backend.
- Python: AICB workload generation, topology generation, analysis scripts, visualization tools.
- Bash: build scripts and batch experiment orchestration.
- CMake: C++ build organization.
- NS-3: packet/RDMA/QBB/PFC/ECN/QP level simulation backend.
- FlowSim: lightweight flow/chunk-level topology simulation backend, currently provided by `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim`.
- MPI/libibverbs: Physical/RDMA mode.
- CUDA/PyTorch: AICB physical benchmark and profiling paths.

## Main Capabilities

- Generate or consume AICB/SimAI workload files.
- Parse workload layers and drive training/inference-like communication phases.
- Decompose collectives into NCCL-like point-to-point flows.
- Run fast analytical estimation.
- Run fine-grained NS-3 simulation.
- Run FlowSim flow/chunk-level topology simulation for large batch topology comparisons.
- Run physical RDMA traffic generation in supported environments.
- Compare topologies, configs, and workload outputs through experiment scripts.

## Key Dependencies

- `astra-sim-alibabacloud`: core system/workload/collective engine and network frontends.
- `ns-3-alibabacloud`: NS-3 backend with RDMA/QBB/PFC/ECN/NVSwitch extensions.
- `aicb`: workload generator and communication benchmark tooling.
- `SimCCL`: collective-to-point-to-point communication concept; basic implementation is integrated through MockNCCL code in astra-sim.
- `/home/zty/Topo/m4/SimAI`: external source and binary provider for FlowSim.

## Directory Structure

- `README.md`, `README_CN.md`, `README.ja.md`: project overview and quick start.
- `scripts/`: top-level build and helper scripts.
- `astra-sim-alibabacloud/`: core simulation library and frontends.
- `ns-3-alibabacloud/`: NS-3 network backend.
- `aicb/`: workload generation and benchmark tools.
- `SimCCL/`: SimCCL documentation and component placeholder.
- `mytopo/`: topology files for 256/1024/4096 GPU experiments and variants.
- `myconfig/`: NS-3 configuration files.
- `my_workloads/`: SimAI/AICB workload files.
- `experiments/`: batch scripts and result directories.
- `simulation_output/`: configured NS-3 output paths.
- `example/`: quick-start examples.
- `bin/`: generated executable symlinks.
- `docs/`: human-facing architecture documents.
- `.ai/`: persistent project knowledge base for future maintenance.

