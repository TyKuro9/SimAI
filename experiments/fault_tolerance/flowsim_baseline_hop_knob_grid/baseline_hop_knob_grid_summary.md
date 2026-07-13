# FlowSim Baseline Hop-Knob Grid

Combined CSV:

- `baseline_hop_knob_combined_summary.csv`

This grid extends `flowsim_baseline_hop_knob_smoke/` with a few extra baseline-only points. It uses the rebuilt m4 FlowSim binary and does not run fault samples.

## Combined Results

| Topology | Case | FlowSim JCT (us) | NS3 baseline (us) | FlowSim / NS3 | Abs error (us) |
|---|---|---:|---:|---:|---:|
| DeepSeek | base | 113.903 | 51.000 | 2.233 | 62.903 |
| DeepSeek | PXN same-rail hop4 `w=0.50` | 84.744 | 51.000 | 1.662 | 33.744 |
| DeepSeek | PXN same-rail hop4 `w=0.40` | 73.063 | 51.000 | 1.433 | 22.063 |
| DeepSeek | PXN same-rail hop4 `w=0.35` | 67.259 | 51.000 | 1.319 | 16.259 |
| DeepSeek | PXN same-rail hop4 `w=0.30` | 61.424 | 51.000 | 1.204 | 10.424 |
| DeepSeek | PXN same-rail hop4 `w=0.25` | 55.581 | 51.000 | 1.090 | 4.581 |
| RO | base | 43.984 | 73.000 | 0.603 | 29.016 |
| RO | PXN same-rail hop4 `w=0.50` | 43.984 | 73.000 | 0.603 | 29.016 |
| RO | PXN same-rail hop4 `w=0.30` | 43.984 | 73.000 | 0.603 | 29.016 |
| ROFT | base | 66.935 | 55.000 | 1.217 | 11.935 |
| ROFT | direct cross-rail `w=0.25` | 59.410 | 55.000 | 1.080 | 4.410 |
| ROFT | direct cross-rail `w=0.22` | 54.888 | 55.000 | 0.998 | 0.112 |
| ROFT | direct cross-rail `w=0.20` | 51.890 | 55.000 | 0.943 | 3.110 |

## Candidate Values

| Target | Candidate | Why |
|---|---|---|
| DeepSeek baseline | `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25` | Brings baseline from `113.903us` to `55.581us`, within `4.581us` of NS3. |
| ROFT baseline | `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22` | Brings baseline from `66.935us` to `54.888us`, within `0.112us` of NS3. |
| RO guardrail | unchanged by DeepSeek hop4 override | RO stays at `43.984us` for hop4 `w=0.50` and `w=0.30`, so this knob does not worsen the current RO baseline guardrail. |

## Next Test

Run a targeted fault sweep before touching the full six-topology experiment:

- DeepSeek with base `w0.3 + pxn0.75` plus hop4 `0.25`.
- ROFT with base `w0.3 + pxn0.75` plus direct cross-rail `0.22`.
- RO as a guardrail with DeepSeek hop4 `0.25`.

Use the already completed NS3 curves for comparison. If DeepSeek and ROFT baseline alignment improves without making normalized fault response worse, then consider a broader sweep with topology/path-class-specific policy labels.
