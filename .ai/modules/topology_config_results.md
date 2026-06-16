# Module: Topology, Config, Workloads, and Results

## Responsibilities

- Store topology definitions.
- Store NS-3 configuration files.
- Store workload descriptions.
- Store experiment outputs.
- Provide experiment matrix inputs for batch scripts.

## Main Directories

- `mytopo/`
- `myconfig/`
- `my_workloads/`
- `simulation_output/`
- `experiments/analytical_results/`
- `experiments/ns3_results/`
- `experiments/flowsim_results/`
- `experiments/flowsim_256/`
- `experiments/flowsim_1024/`
- `experiments/flowsim_4096/`

## Key File Types

- topology files: SimAI topology format with header and link lines.
- config files: NS-3/RDMA parameters, output paths, congestion-control settings.
- workload files: model, world size, TP/PP/EP/GBS/MBS/SEQ encoded in filename and workload contents.
- result CSVs: `EndToEnd.csv`, `detailed_*.csv`.
- FCT files: `fct.txt`, `*_fct.txt`.

## Repro Inputs

- `experiments/ns3_repro/zcube64_csv/` contains a 64-GPU Zcube NS-3 CSV smoke:
  - `Zcube_n8_k2_64g_8gps_200Gbps_H100`
  - `Zcube64_ns3.conf`
  - `dense_64_tiny.txt`
  - `moe_64_tiny.txt`
  - `moe_64_alltoall_ig_tiny.txt`
  - `results_dense_tiny_verify/EndToEnd.csv`
  - `results_moe_alltoall_ig_tiny_verify/EndToEnd.csv`
- These files are for fast CSV/reporting verification only. They are not performance baselines and FCT output is not part of the acceptance signal.

## Inputs

- topology generator scripts under `scripts/` or `astra-sim-alibabacloud/inputs/topo/`
- AICB workload generator outputs
- manually curated config files

## Outputs

- experiment-ready topology/config/workload combinations
- result directories consumed by analysis scripts

## Dependencies

- batch scripts
- NS-3 backend
- FlowSim backend
- Analytical backend for workload stats

## Modification Risk

- Medium: path and naming changes can break scripts.
- High: topology header format changes can break NS-3 and FlowSim parsers.
- Medium: config output paths can silently write to unexpected locations.
