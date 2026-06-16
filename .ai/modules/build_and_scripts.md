# Module: Build and Scripts

## Responsibilities

- Build Analytical, NS-3, htsim/RoCE, and Physical/RDMA binaries from the current project.
- Invoke external FlowSim binary for flow/chunk-level experiments.
- Orchestrate batch experiments across workload/topology combinations.
- Create output directories and logs.

## Main Files

- `scripts/build.sh`
- `scripts/fix_local_permissions.sh`
- `astra-sim-alibabacloud/build.sh`
- `astra-sim-alibabacloud/build/simai_htsim/build.sh`
- `run_256dense_flowsim.sh`
- `run_256moe_flowsim.sh`
- `run_mixtral_1024moe_flowsim.sh`
- `run_mixtral_256moe_ns3.sh`
- `experiments/flowsim_*/run*.sh`
- `experiments/flowsim_*/mkdir*.sh`

## Key Interfaces

- `./scripts/build.sh -c analytical`
- `./scripts/build.sh -c ns3`
- `./scripts/build.sh -c htsim`
- `./scripts/build.sh -c phy`
- `./scripts/fix_local_permissions.sh`
- `/home/zty/Topo/m4/SimAI/scripts/build.sh -c flowsim`
- `FLOWSIM_BIN`
- `FLOWSIM_THREADS`
- `HTSIM_ROUTE_STRATEGY`
- `HTSIM_LINK_BW_GBPS`

## Inputs

- workload files under `my_workloads/`
- topology files under `mytopo/`
- config files under `myconfig/`
- environment variables such as `AS_SEND_LAT`, `AS_NVLS_ENABLE`, `AS_PXN_ENABLE`
- htsim-specific route strategy from `-r`, `HTSIM_ROUTE_STRATEGY`, or a `route_strategy` config line.

## Outputs

- binary symlinks under `bin/`
- `bin/SimAI_htsim` for the htsim backend.
- experiment logs under `experiments/*_results`
- CSV and FCT result files.

## Dependencies

- `astra-sim-alibabacloud`
- `ns-3-alibabacloud`
- `extern/network_backend/htsim` submodule pinned to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- external `/home/zty/Topo/m4/SimAI` for FlowSim.

## Modification Risk

- High if changing paths, because many scripts use absolute paths.
- Medium if adding new topology cases, because output directory naming must stay consistent.
- Low for documentation-only changes.

## Local Permission Maintenance

- Normal build and run flows should not require `sudo`.
- If previous sudo/container runs leave build artifacts owned by `nobody`, `root`, or another user, run `./scripts/fix_local_permissions.sh` once from the project root.
- The permission repair script intentionally targets only known build/binary paths:
  - `bin`
  - `experiments/ns3_results`
  - `astra-sim-alibabacloud/extern`
  - `astra-sim-alibabacloud/extern/network_backend`
  - `astra-sim-alibabacloud/extern/network_backend/ns3-interface`
  - `astra-sim-alibabacloud/build/astra_ns3/build`
  - `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim`
  - `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/build/simai_flowsim`
- NS-3 builds need the `extern/network_backend` path to be user-writable because `scripts/build.sh -c ns3` removes and recreates `ns3-interface` before building.
- NS-3 runs need `experiments/ns3_results/csv/<case>/` to be user-writable because `CSVWriter::initialize_csv()` opens `detailed_*.csv` and `EndToEnd.csv` with truncate mode before simulation progresses.
- `run_mixtral_256moe_ns3.sh` creates all known Mixtral 256 MoE NS-3 output directories and fails early with a permission hint if any target is not writable.
- FlowSim builds need the whole external `build/simai_flowsim` path to be user-writable because its sub-build script creates/removes both `build/` and `result/`.
- Use `FLOWSIM_ROOT=/path/to/SimAI ./scripts/fix_local_permissions.sh` if the external FlowSim tree moves.
