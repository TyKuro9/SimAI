# Module: AICB

## Responsibilities

- Generate workload descriptions for SimAI simulation.
- Run communication benchmark suites on physical GPU clusters.
- Model training communication patterns for Megatron, DeepSpeed, MoE, and DeepSeek training paths.

## Main Files

- `aicb/README.md`
- `aicb/aicb.py`
- `aicb/run_suites.py`
- `aicb/workload_generator/`
- `aicb/scripts/`
- `aicb/workload/`
- `aicb/visualize/`

## Key Classes and Scripts

- `workload_generator/workload_generator.py`
- `workload_generator/generate_megatron_workload.py`
- `workload_generator/generate_deepspeed_stage1_2_workload.py`
- `workload_generator/generate_deepspeed_stage3_workload.py`
- `workload_generator/SimAI_training_workload_generator.py`

## Inputs

- model size and framework parameters
- TP/PP/DP/EP/SP/Zero settings
- optional profiling/AIOB inputs

## Outputs

- SimAI workload text files
- benchmark logs and visualization data

## Dependencies

- Python runtime.
- PyTorch/CUDA for physical benchmark or profiling modes.
- Consumed downstream by `astra-sim-alibabacloud/astra-sim/workload`.

## Modification Risk

- Medium: workload format changes can break `Workload::initialize_workload()`.
- High if changing generated communication semantics because downstream collective scheduling depends on them.

## Notes

- Vidur-named generator paths are intentionally not analyzed yet.

