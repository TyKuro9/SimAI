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

## Zcube 256 MoE Expert-Parallel Path Classification

- Workload: `my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt`.
- Topologies compared:
  - Zcube: `mytopo/Zcube_n16_k2_256g_8gps_200Gbps_H100`.
  - RO: `mytopo/RailOnly_256g_8gps_p16a0.5_400Gbps_H100`.
- Node numbering in these 256-GPU topology files:
  - GPU hosts: `0..255`.
  - NVSwitch nodes: `256..287`, one per 8-GPU server.
  - ordinary switch nodes: `288..319`.
- MockNCCL EP groups for `tp8/pp2/ep8/all_gpus256` are same-local-rank rail groups across 8 consecutive servers, for example `[0,8,16,24,32,40,48,56]`. Therefore the `ALLTOALL_EP` traffic has no same-server GPU pair; all EP pairs are cross-server same-rail GPU pairs.
- Same-server non-EP GPU pairs prefer the local NVSwitch path, e.g. `gpu0 -> nvswitch256 -> gpu1`.
- Zcube switch role interpretation for this analysis:
  - `288..303`: local/pair switches connecting all rails of a small server pair; these are the single-rail/local switches in the user's classification language.
  - `304..319`: same-rail multi-server switches.
- RO switch role interpretation:
  - `288..319`: same-rail multi-server switches.
- FlowSim/NS-3-style routing gives the following directed EP pair classes over the 32 unique EP groups, 1792 directed GPU pairs total:
  - Zcube: 256 pairs (14.3%) use `GPU -> local/pair switch -> GPU`.
  - Zcube: 768 pairs (42.9%) use `GPU -> same-rail multi-server switch -> GPU`.
  - Zcube: 396 pairs (22.1%) use `GPU -> same-rail multi-server switch -> local/pair switch -> GPU`.
  - Zcube: 372 pairs (20.8%) use `GPU -> local/pair switch -> same-rail multi-server switch -> GPU`.
  - RO: 1792 pairs (100%) use `GPU -> same-rail multi-server switch -> GPU`.
- Zcube therefore sends 42.9% of EP directed pairs through two ordinary switches, while RO sends all EP directed pairs through a single rail switch.
- Observed 256 MoE FlowSim result:
  - Zcube `Expose_EP_comm`: `190191`, total time `3158908`.
  - RO `Expose_EP_comm`: `79911`, total time `3138013`.
  - Zcube is slower than RO mainly because EP all-to-all has longer/more contended ordinary-switch paths in Zcube, despite Zcube having lower exposed DP communication in this result.

## Inputs

- topology generator scripts under `scripts/` or `astra-sim-alibabacloud/inputs/topo/`
- AICB workload generator outputs
- manually curated config files

## Outputs

- experiment-ready topology/config/workload combinations
- result directories consumed by analysis scripts

## Fault-Tolerance Experiments

- `scripts/fault_tolerance_experiments.py` runs fixed-probability startup fault-tolerance experiments without modifying original topology files.
- The script reuses the existing link-failure/routing semantics by writing a failed topology under `results/fault_tolerance/generated_topologies/` and then, when `--run-simulator` is set, invoking the existing FlowSim binary so routing is rebuilt from that topology at startup.
- Random link failure supports:
  - `--link-failure-probability <p>`: one fixed probability configured once per experiment.
  - `--num-seeds <n>` / `--random-seed <seed>` / `--seeds a,b,c`: multiple independent seeds using the same fixed probability.
  - `--failure-target inter_server_links`: only inter-server links are eligible. GPU-to-NVSwitch/NVSwitch-to-GPU links are excluded so intra-server NVLink/NVSwitch connectivity does not fail in random-link experiments.
- Switch failure emulation supports `--failed-switch-id <id>` by failing all topology links incident to that switch. This is equivalent to setting those incident links' failure probability to `1.0` and all other links to `0.0`.
- `--failed-switch-role tor` is intentionally unavailable because current topology files distinguish GPU, NVSwitch, and ordinary switch nodes, but do not carry a generic ToR role label.
- Outputs are written under `results/fault_tolerance/` by default:
  - `random_link_failure_raw.csv`
  - `random_link_failure_summary.csv`
  - `switch_failure_raw.csv`
  - `switch_failure_summary.csv`
  - `metadata.json`
- Available metrics:
  - JCT/degradation when `--run-simulator` is used and `EndToEnd.csv` contains `Total time`.
  - failed link count/ratio.
  - all-to-all disconnected ordered GPU-pair count/ratio.
  - connectivity ratio.
  - average path length after failure.
  - path stretch versus no-failure topology.
- Missing/limited metrics:
  - max link utilization is marked `missing`; existing EndToEnd/FCT outputs do not provide per-link utilization.
  - exact failed-flow counts for arbitrary workload files are marked `missing`; all-to-all uses ordered GPU-pair disconnection as the failed-flow definition.

## 256 FlowSim Error-Probability Sweep

- `experiments/flowsim_256/run_fault_probability_sweep.py` runs a 256-GPU FlowSim JCT sweep over error probability and writes:
  - `jct_by_error_probability_raw.csv`
  - `jct_by_error_probability_summary.csv`
  - `jct_by_error_probability.png`
  - per-point FlowSim run directories under `runs/<topology>/pXX/seedY/`
  - generated topologies under `generated_topologies/<topology>/`
- Current common 256 topologies available in `mytopo/` are:
  - `Meta`
  - `HPN`
  - `DeepSeek`
  - `Zcube`
  - `RO`
  - `ROFT`
- The default FlowSim error model is `bandwidth_scale`, not link removal:
  - Original topology files are never modified.
  - Generated topology files keep the same link count and connectivity.
  - Inter-server links have bandwidth scaled by `(1 - error_probability)`.
  - The topology `error_rate` column is set to the configured probability for those inter-server links.
  - GPU-to-NVSwitch/NVSwitch-to-GPU intra-server links are left unchanged.
- Rationale: current FlowSim parses the topology `error_rate` column but does not use it in flow completion. Scaling inter-server bandwidth is the smallest FlowSim-compatible approximation for JCT sensitivity to error probability without changing the backend core.
- Added quick 256 workloads:
  - `experiments/flowsim_256/moe_256_fault_tiny.txt`: 8-layer tiny MoE smoke; verifies sweep mechanics but messages are too small for a useful JCT curve.
  - `experiments/flowsim_256/moe_256_fault_comm.txt`: 8-layer communication-enhanced MoE sweep workload with `all_gpus=256`, `tp8/pp2/ep8`, EP all-to-all, DP/DP_EP collectives, and larger message sizes.
- Verified output on 2026-06-17:
  - command used `moe_256_fault_comm.txt`, error probabilities `0..15%`, one seed, six common topologies.
  - output root: `results/fault_tolerance_256_flowsim_comm/`.
  - `jct_by_error_probability_raw.csv`: 96 rows.
  - `jct_by_error_probability_summary.csv`: 96 rows.
  - no missing JCT values and no empty `EndToEnd.csv` files.
  - generated plot: `results/fault_tolerance_256_flowsim_comm/jct_by_error_probability.png`.
- Full 1837-layer Mixtral 256 MoE can be used with the same script, but a single Meta 1% point exceeded 7 minutes in the interactive session before being interrupted. Treat full-workload sweeps as longer batch jobs.
- Full-workload wrapper:
  - `experiments/flowsim_256/run_full_mixtral_fault_probability_sweep.sh`
  - Default workload: `my_workloads/H100-Mixtral_8*7B-world_size256-tp8-pp2-ep8-gbs256-mbs1-seq2048-MOE-True-GEMM-True-flash_attn-True copy.txt`.
  - Default output root: `results/fault_tolerance_256_flowsim_full_mixtral/`.
  - Default topologies: `Meta,HPN,DeepSeek,Zcube,RO,ROFT`.
  - Default error probabilities: `0..15%`.
  - Runtime overrides are environment variables: `TOPOS`, `MAX_ERROR_PERCENT`, `THREADS`, `OUTPUT_DIR`, `SEEDS`, `NUM_SEEDS`, `RANDOM_SEED`, `ERROR_MODEL`, `FLOWSIM_BIN`, and `WORKLOAD`.
  - The wrapper passes any extra command-line arguments through to `run_fault_probability_sweep.py`.

## Dependencies

- batch scripts
- NS-3 backend
- FlowSim backend
- Analytical backend for workload stats

## Modification Risk

- Medium: path and naming changes can break scripts.
- High: topology header format changes can break NS-3 and FlowSim parsers.
- Medium: config output paths can silently write to unexpected locations.
