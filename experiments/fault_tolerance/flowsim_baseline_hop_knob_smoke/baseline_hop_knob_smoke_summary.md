# FlowSim Baseline Hop-Knob Smoke

This smoke uses the rebuilt m4 FlowSim binary:

- Binary: `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim`
- Source changed: `/home/zty/Topo/m4/SimAI/astra-sim-alibabacloud/astra-sim/network_frontend/flowsim/Topology.cc`
- Workload: `my_workloads/synthetic_alltoall_global_world_size256_1MiB.txt`
- Base policy: `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`, `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`, `AS_PXN_POLICY=fallback`, `FLOWSIM_PXN_TIMING=serial`
- CSV: `baseline_hop_knob_smoke_summary.csv`

## Result

| Topology | Case | FlowSim JCT (us) | NS3 baseline (us) | FlowSim / NS3 | Absolute error (us) | Takeaway |
|---|---|---:|---:|---:|---:|---|
| DeepSeek | base | 113.903 | 51.000 | 2.233 | +62.903 | Current policy remains much too slow. |
| DeepSeek | `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.5` | 84.744 | 51.000 | 1.662 | +33.744 | Hop-scoped PXN same-rail weight helps strongly. |
| DeepSeek | `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.4` | 73.063 | 51.000 | 1.433 | +22.063 | Stronger hop-4 weight keeps improving DeepSeek. |
| RO | base | 43.984 | 73.000 | 0.603 | -29.016 | Current RO baseline is already too fast. |
| RO | `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.5` | 43.984 | 73.000 | 0.603 | -29.016 | Hop-4 override does not perturb this RO baseline. |
| ROFT | base | 66.935 | 55.000 | 1.217 | +11.935 | Current direct cross-rail baseline is still too slow. |
| ROFT | `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.25` | 59.410 | 55.000 | 1.080 | +4.410 | Direct-specific cross-rail weight improves ROFT without PXN. |

## Interpretation

- The new hop-scoped PXN knob is a promising DeepSeek baseline lever because it moves DeepSeek sharply while this RO guardrail is unchanged.
- The direct cross-rail knob is a promising ROFT baseline lever because ROFT is direct in both FlowSim and NS3.
- These are still experimental knobs, not a final default policy. The next step is a small grid over DeepSeek hop-4 weights and ROFT direct weights, then a targeted fault-response rerun before considering a full six-topology sweep.
