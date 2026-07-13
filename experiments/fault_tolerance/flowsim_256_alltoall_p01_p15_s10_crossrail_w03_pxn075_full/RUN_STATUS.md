# FlowSim w0.3 + PXN Same-Rail w0.75 Run Status

Command:

```bash
/home/zty/miniconda3/envs/vidur/bin/python scripts/run_flowsim_fault_256_alltoall.py \
  --output-dir experiments/fault_tolerance/flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full \
  --samples 10 \
  --seed-base 1 \
  --threads 1 \
  --jobs 4 \
  --cross-rail-switch-switch-weight 0.3 \
  --pxn-same-rail-switch-switch-weight 0.75 \
  --policy-label crossrail_w0p3_pxn_same_rail_w0p75 \
  --resume
```

Runtime:

- tmux session: `flowsim_w03_pxn075_full` (finished; pane no longer exists)
- Total planned samples: `900`
- Current completed raw rows: `900`
- Current successful rows: `900`
- Resume enabled: yes
- Baselines completed: all six topologies

Baseline JCT:

| Topology | JCT |
|---|---:|
| Meta | 72 |
| HPN | 65 |
| DeepSeek | 114 |
| Zcube | 32 |
| RO | 44 |
| ROFT | 67 |

Completed fault results:

| Topology | Failure probability | Samples | Success | Failed JCT mean |
|---|---:|---:|---:|---:|
| Meta | 0.01 | 10 | 10 | 78.3 |
| Meta | 0.02 | 10 | 10 | 78.5 |
| Meta | 0.03 | 10 | 10 | 79.9 |
| Meta | 0.04 | 10 | 10 | 81.2 |
| Meta | 0.05 | 10 | 10 | 79.7 |
| Meta | 0.06 | 10 | 10 | 86.9 |
| Meta | 0.07 | 10 | 10 | 88.6 |
| Meta | 0.08 | 10 | 10 | 88.0 |
| Meta | 0.09 | 10 | 10 | 99.9 |
| Meta | 0.10 | 10 | 10 | 100.3 |
| Meta | 0.11 | 10 | 10 | 104.6 |
| Meta | 0.12 | 10 | 10 | 107.2 |
| Meta | 0.13 | 10 | 10 | 111.2 |
| Meta | 0.14 | 10 | 10 | 113.3 |
| Meta | 0.15 | 10 | 10 | 118.1 |
| HPN | 0.01 | 10 | 10 | 69.4 |
| HPN | 0.02 | 10 | 10 | 71.0 |
| HPN | 0.03 | 10 | 10 | 73.0 |
| HPN | 0.04 | 10 | 10 | 73.6 |
| HPN | 0.05 | 10 | 10 | 75.3 |
| HPN | 0.06 | 10 | 10 | 76.7 |
| HPN | 0.07 | 10 | 10 | 79.4 |
| HPN | 0.08 | 10 | 10 | 79.8 |
| HPN | 0.09 | 10 | 10 | 82.0 |
| HPN | 0.10 | 10 | 10 | 87.8 |
| HPN | 0.11 | 10 | 10 | 94.4 |
| HPN | 0.12 | 10 | 10 | 96.3 |
| HPN | 0.13 | 10 | 10 | 97.4 |
| HPN | 0.14 | 10 | 10 | 103.5 |
| HPN | 0.15 | 10 | 10 | 105.4 |
| DeepSeek | 0.01 | 10 | 10 | 138.2 |
| DeepSeek | 0.02 | 10 | 10 | 154.9 |
| DeepSeek | 0.03 | 10 | 10 | 168.9 |
| DeepSeek | 0.04 | 10 | 10 | 182.3 |
| DeepSeek | 0.05 | 10 | 10 | 192.6 |
| DeepSeek | 0.06 | 10 | 10 | 200.4 |
| DeepSeek | 0.07 | 10 | 10 | 214.3 |
| DeepSeek | 0.08 | 10 | 10 | 220.5 |
| DeepSeek | 0.09 | 10 | 10 | 221.2 |
| DeepSeek | 0.10 | 10 | 10 | 227.8 |
| DeepSeek | 0.11 | 10 | 10 | 235.7 |
| DeepSeek | 0.12 | 10 | 10 | 231.5 |
| DeepSeek | 0.13 | 10 | 10 | 232.9 |
| DeepSeek | 0.14 | 10 | 10 | 238.2 |
| DeepSeek | 0.15 | 10 | 10 | 244.6 |
| Zcube | 0.01 | 10 | 10 | 49.2 |
| Zcube | 0.02 | 10 | 10 | 50.8 |
| Zcube | 0.03 | 10 | 10 | 55.5 |
| Zcube | 0.04 | 10 | 10 | 58.7 |
| Zcube | 0.05 | 10 | 10 | 60.8 |
| Zcube | 0.06 | 10 | 10 | 62.8 |
| Zcube | 0.07 | 10 | 10 | 69.6 |
| Zcube | 0.08 | 10 | 10 | 70.6 |
| Zcube | 0.09 | 10 | 10 | 76.6 |
| Zcube | 0.10 | 10 | 10 | 86.9 |
| Zcube | 0.11 | 10 | 10 | 91.3 |
| Zcube | 0.12 | 10 | 10 | 90.4 |
| Zcube | 0.13 | 10 | 10 | 91.3 |
| Zcube | 0.14 | 10 | 10 | 101.1 |
| Zcube | 0.15 | 10 | 10 | 103.7 |
| RO | 0.01 | 10 | 10 | 70.1 |
| RO | 0.02 | 10 | 10 | 81.8 |
| RO | 0.03 | 10 | 10 | 91.6 |
| RO | 0.04 | 10 | 10 | 96.4 |
| RO | 0.05 | 10 | 10 | 100.4 |
| RO | 0.06 | 10 | 10 | 106.9 |
| RO | 0.07 | 10 | 10 | 114.0 |
| RO | 0.08 | 10 | 10 | 121.0 |
| RO | 0.09 | 10 | 10 | 127.7 |
| RO | 0.10 | 10 | 10 | 145.1 |
| RO | 0.11 | 10 | 10 | 146.8 |
| RO | 0.12 | 10 | 10 | 168.4 |
| RO | 0.13 | 10 | 10 | 185.1 |
| RO | 0.14 | 10 | 10 | 189.0 |
| RO | 0.15 | 10 | 10 | 206.7 |
| ROFT | 0.01 | 10 | 10 | 83.3 |
| ROFT | 0.02 | 10 | 10 | 90.5 |
| ROFT | 0.03 | 10 | 10 | 94.9 |
| ROFT | 0.04 | 10 | 10 | 100.7 |
| ROFT | 0.05 | 10 | 10 | 107.6 |
| ROFT | 0.06 | 10 | 10 | 114.3 |
| ROFT | 0.07 | 10 | 10 | 119.4 |
| ROFT | 0.08 | 10 | 10 | 120.8 |
| ROFT | 0.09 | 10 | 10 | 121.5 |
| ROFT | 0.10 | 10 | 10 | 123.9 |
| ROFT | 0.11 | 10 | 10 | 128.4 |
| ROFT | 0.12 | 10 | 10 | 128.9 |
| ROFT | 0.13 | 10 | 10 | 129.4 |
| ROFT | 0.14 | 10 | 10 | 137.1 |
| ROFT | 0.15 | 10 | 10 | 142.0 |

Current partial rows:

None. The full sweep completed with `900/900` successful samples.

Complete-only comparison against prior `w0.3`:

| Topology | Rates | Factor MAE delta | Failed JCT MAE delta |
|---|---:|---:|---:|
| Meta | 15 | +0.011 | -0.63 |
| HPN | 15 | +0.002 | -0.15 |
| DeepSeek | 15 | -0.048 | -59.81 |
| Zcube | 15 | +0.000 | +0.00 |
| RO | 15 | -0.017 | -17.39 |
| ROFT | 15 | -0.072 | -5.67 |

Interpretation:

- Across all fifteen Meta rates, the new PXN same-rail weight improves absolute failed JCT versus `w0.3`, but still slightly worsens normalized factor error because it also lowers the baseline.
- HPN is effectively unchanged versus `w0.3` across all fifteen complete rates, which is a useful guardrail: the new PXN-specific weight is not perturbing HPN behavior.
- DeepSeek is complete in the full sweep and matches the targeted guardrail values at `1%`, `5%`, `10%`, and `15%`. The new weight improves DeepSeek versus `w0.3`, but DeepSeek still remains much higher than NS3 in absolute JCT.
- Zcube is complete. The complete `1%..15%` rows are unchanged versus `w0.3` in the policy comparison path.
- RO `1%..15%` is complete. The `5%`, `10%`, and `15%` points match the targeted guardrail results. The full RO aggregate now improves in both views: absolute failed-JCT MAE improves versus `w0.3` (`24.03 -> 6.64`), and normalized factor MAE improves (`1.103 -> 1.086`). RO `15%` still undershoots NS3 in absolute JCT (`206.7` vs `225.1`), but it is much closer than prior `w0.3` (`264.0`).
- ROFT `1%..15%` is complete and improves in both views: normalized factor MAE improves (`0.141 -> 0.069`) and absolute failed-JCT MAE improves (`29.6 -> 23.9`). The `1%`, `5%`, `10%`, and `15%` points match the targeted guardrail values.
- Complete-only figures have been regenerated under `experiments/fault_tolerance/flowsim_w03_pxn075_comparison/plots/`.
- This reinforces that absolute JCT and normalized factor must both be tracked.

Guardrail run:

- tmux session: `flowsim_w03_pxn075_guardrail`
- Topologies: DeepSeek, RO, ROFT, Zcube
- Rates: `1%, 5%, 10%, 15%`
- Samples: `10` each
- Purpose: get key guardrail results before the full sequential sweep reaches those topologies.

First guardrail result:

| Topology | Failure probability | Samples | Success | Failed JCT mean | Baseline | NS3 failed | vs prior w0.3 JCT delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | 0.01 | 10 | 10 | 138.2 | 114 | 58.7 | -35.5 |
| DeepSeek | 0.05 | 10 | 10 | 192.6 | 114 | 77.4 | -53.5 |
| DeepSeek | 0.10 | 10 | 10 | 227.8 | 114 | 96.5 | -68.1 |
| DeepSeek | 0.15 | 10 | 10 | 244.6 | 114 | 107.7 | -76.5 |
| RO | 0.01 | 10 | 10 | 70.1 | 44 | 79.8 | +7.4 |
| RO | 0.05 | 10 | 10 | 100.4 | 44 | 102.9 | -14.9 |
| RO | 0.10 | 10 | 10 | 145.1 | 44 | 148.9 | -36.1 |
| RO | 0.15 | 10 | 10 | 206.7 | 44 | 225.1 | -57.3 |

Interpretation:

- DeepSeek `1%`, `5%`, `10%`, and `15%` all improve versus prior `w0.3`.
- Across these four complete guardrail rates, failed-JCT MAE improves by `58.4`, and factor MAE improves by `0.051`.
- DeepSeek remains far above NS3 in absolute JCT, so this is an improvement but not a full calibration fix.
- DeepSeek 15% also improves in normalized factor: `2.245 -> 2.146`, closer to NS3 `2.112`.
- RO aggregate over `1%`, `5%`, `10%`, and `15%` improves in both views: failed-JCT MAE improves (`22.7 -> 8.6`) and factor MAE improves (`1.092 -> 1.061`). The caveat is that RO `15%` undershoots NS3 in absolute JCT (`206.7` vs `225.1`).

Notes:

- `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`
- Early run logs confirm both weights are visible inside FlowSim.
