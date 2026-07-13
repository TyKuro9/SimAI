# FlowSim w0.3 Full Sweep Status

Updated: 2026-07-03 22:49 +0800

## Completed Job

- tmux session: `flowsim_w03_full`
- Status: completed; the tmux session exited after finishing all samples.
- Command:

```bash
python3 scripts/run_flowsim_fault_256_alltoall.py \
  --output-dir experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full \
  --samples 10 \
  --seed-base 1 \
  --threads 1 \
  --jobs 4 \
  --cross-rail-switch-switch-weight 0.3 \
  --policy-label w0.3-cross-rail-switch-switch
```

## Current Progress

- Total runnable samples: 900
- Completed samples observed: 900/900
- Failed samples observed: 0
- Completed topology/rates:
  - Meta 1%-15%: 10/10 success for each rate
  - HPN 1%-15%: 10/10 success for each rate
  - DeepSeek 1%-15%: 10/10 success for each rate
  - ZCube 1%-15%: 10/10 success for each rate
  - RO 1%-15%: 10/10 success for each rate
  - ROFT 1%-15%: 10/10 success for each rate

## Final Comparison

Report:

- `flowsim_crossrail_w03_full.md`
- `flowsim_crossrail_w03_full_detail.csv`
- `flowsim_crossrail_w03_full_aggregate.csv`
- `plots/flowsim_policy_vs_ns3_full_normalized_jct.png`
- `plots/flowsim_policy_vs_ns3_full_failed_jct.png`
- `plots/flowsim_policy_vs_ns3_full_data.csv`

For all rates:

| Topology | Rates | Original factor MAE | w0.3 factor MAE | Original failed-JCT MAE | w0.3 failed-JCT MAE |
|---|---:|---:|---:|---:|---:|
| ROFT | 15 | 0.098 | 0.141 | 184.9 s | 29.6 s |
| HPN | 15 | 0.364 | 0.260 | 135.2 s | 11.3 s |
| DeepSeek | 15 | 0.142 | 0.142 | 178.8 s | 178.8 s |
| Meta | 15 | 0.845 | 0.529 | 87.4 s | 4.5 s |
| ZCube | 15 | 1.041 | 0.761 | 14.0 s | 5.3 s |
| RO | 15 | 1.103 | 1.103 | 24.0 s | 24.0 s |

Interpretation:

- `w0.3` is consistently closer to NS3 than original FlowSim for Meta and HPN.
- DeepSeek is unchanged by the scoped cross-rail switch-switch policy; this is expected if its bottlenecked traffic is outside that physical cross-rail switch-switch category.
- ZCube improves, especially at high failure rates: at 15%, original FlowSim is 134.4, w0.3 is 103.7, and NS3 is 95.2.
- RO is behaving as a guardrail: all RO rates are unchanged by w0.3, confirming that the scoped policy does not relax PXN-decomposed same-rail/same-server traffic.
- ROFT has the largest absolute failed-JCT improvement, but its normalized factor MAE is worse than original FlowSim. This is the clearest final example where absolute JCT and baseline-normalized factor disagree.
- Across the full sweep, `w0.3` is best understood as a scoped statistical-sharing approximation for physical cross-rail switch-switch traffic, not a global bandwidth change.

## Reproduce Final Outputs

Recreate the final comparison report:

```bash
python3 scripts/compare_flowsim_policy_sweep.py \
  --policy experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_full/random_link_failure_summary.csv \
  --output-dir experiments/fault_tolerance/flowsim_crossrail_w03_full_comparison \
  --output-prefix flowsim_crossrail_w03_full \
  --policy-label 'w0.3 cross-rail full'
```

Recreate the final plots:

```bash
MPLCONFIGDIR=/tmp/matplotlib \
  /home/zty/miniconda3/envs/vidur/bin/python \
  scripts/plot_flowsim_policy_fault_comparison.py \
  --output-dir experiments/fault_tolerance/flowsim_crossrail_w03_full_comparison/plots \
  --prefix flowsim_policy_vs_ns3_full
```

The final full comparison has already been generated.
