# FlowSim w0.3 + PXNw0.75 Residual Diagnosis

Source comparison:

- Policy summary: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/random_link_failure_summary.csv`
- Comparison detail: `flowsim_w03_pxn075_comparison/flowsim_w03_vs_w03_pxn075_complete_partial_detail.csv`
- Comparison aggregate: `flowsim_w03_pxn075_comparison/flowsim_w03_vs_w03_pxn075_complete_partial_aggregate.csv`
- Figures:
  - `flowsim_w03_pxn075_comparison/plots/flowsim_w03_pxn075_vs_ns3_complete_partial_normalized_jct.png`
  - `flowsim_w03_pxn075_comparison/plots/flowsim_w03_pxn075_vs_ns3_complete_partial_failed_jct.png`

The full sweep completed with `900/900` successful samples.

## Final Aggregate

| Topology | Policy vs w0.3 factor MAE delta | Policy vs w0.3 failed-JCT MAE delta | Main outcome |
|---|---:|---:|---|
| DeepSeek | -0.048 | -59.81 | Strong improvement, but absolute JCT remains far above NS3. |
| RO | -0.017 | -17.39 | Improves both views; 15% still undershoots NS3 absolute JCT. |
| ROFT | -0.072 | -5.67 | Improves both views; absolute gain is modest. |
| Meta | +0.011 | -0.63 | Absolute JCT slightly improves, normalized factor worsens. |
| HPN | +0.002 | -0.15 | Essentially unchanged. |
| Zcube | +0.000 | +0.00 | Unchanged by the PXN same-rail weight. |

## Residual Error Classification

`baseline-adjusted failed MAE` means: use the policy normalized factor curve, but multiply it by the NS3 no-fault baseline. If this number is low, the remaining absolute-JCT mismatch is mostly a baseline calibration problem. If it is high, the fault response curve itself still differs from NS3.

| Topology | NS3 baseline | Policy baseline | Policy / NS3 baseline | Policy failed-JCT MAE | Policy failed-JCT bias | Policy factor MAE | Baseline-adjusted failed MAE | Residual class |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| DeepSeek | 51.0 | 114.0 | 2.235 | 119.03 | +119.03 | 0.094 | 4.80 | Baseline-dominated absolute mismatch. |
| ROFT | 55.0 | 67.0 | 1.218 | 23.90 | +23.90 | 0.069 | 3.77 | Mostly baseline-dominated; factor curve is close. |
| Meta | 49.0 | 72.0 | 1.469 | 3.86 | +3.70 | 0.540 | 26.45 | Absolute match is partly cancellation; slowdown is under-modeled. |
| RO | 73.0 | 44.0 | 0.603 | 6.64 | -6.47 | 1.086 | 79.26 | Absolute curve improved, but normalized curve remains too steep. |
| Zcube | 47.0 | 32.0 | 0.681 | 5.31 | +0.77 | 0.761 | 35.74 | Absolute match is cancellation; normalized curve remains too steep. |
| HPN | 47.0 | 65.0 | 1.383 | 11.10 | +11.10 | 0.262 | 12.32 | Small policy effect; separate calibration problem. |

## Interpretation

1. `w0.3 + PXNw0.75` is a good current FlowSim fault policy, not a final physical model.

   It improves DeepSeek, RO, and ROFT without perturbing Zcube. HPN and Meta move only slightly. This makes it a reasonable default for the next FlowSim-side comparisons.

2. DeepSeek and ROFT should not be fixed by more fault-rate tuning first.

   Their policy factor curves are already close to NS3 after the new PXN same-rail weight. DeepSeek's remaining absolute error is dominated by no-fault baseline mismatch (`114` vs `51`). ROFT shows the same pattern at smaller scale (`67` vs `55`). The next useful work is baseline/no-fault modeling, not another link-failure weight.

3. Meta, Zcube, and RO are not just baseline problems.

   For these topologies, replacing the FlowSim baseline with the NS3 baseline would make the failed-JCT curve much worse. Their residual mismatch is in the normalized fault response: Meta under-models degradation, while Zcube and RO still have too-steep normalized curves.

4. Zcube is confirmed as unaffected by the PXN same-rail knob.

   The policy and original rows are identical at all fifteen rates. Any Zcube mismatch should be handled through direct cross-rail/fixed-route/packet-sharing modeling, not PXN same-rail calibration.

## Baseline Track Evidence

### Original-flow FCT Comparison

New comparison input/output:

- Input summary: `baseline_deepseek_roft_fct_w03_pxn075/targeted_fct_summary.csv`
- NS3 grouped original-flow summary: `baseline_deepseek_roft_fct_w03_pxn075/ns3_original_flow_category_summary.csv`
- Comparison output: `baseline_deepseek_roft_fct_w03_pxn075/flowsim_ns3_original_fct_comparison.csv`
- Baseline hop-knob smoke: `flowsim_baseline_hop_knob_smoke/baseline_hop_knob_smoke_summary.md`
- Baseline hop-knob grid: `flowsim_baseline_hop_knob_grid/baseline_hop_knob_grid_summary.md`
- Targeted fault sweep: `flowsim_targeted_hop4w025_directw022_comparison/targeted_hop4w025_directw022_summary.md`
- Targeted fault-only correction: `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_hop4w020_directw020_summary.md`
- Fault-only path-stretch diagnosis: `flowsim_targeted_faultonly_hop4w020_directw020_comparison/faultonly_error_by_path_stretch.md`

`fct.txt` column 7 is real FCT, not finish timestamp. NS3 writes physical PXN legs and original-flow metadata; the comparison below groups NS3 physical legs back to the original logical src/dst flow before comparing with FlowSim logical FCT.

| Topology | Original category | FlowSim p95 FCT (us) | NS3 grouped p95 FCT (us) | NS3 / FlowSim p95 | FlowSim max FCT (us) | NS3 grouped max FCT (us) | NS3 / FlowSim max | NS3 physical rows | NS3 split original flows |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | cross_server_cross_rail | 110.788 | 40.540 | 0.366 | 110.788 | 46.576 | 0.420 | 111,104 | 55,552 |
| DeepSeek | cross_server_same_rail | 106.120 | 40.554 | 0.382 | 106.120 | 46.665 | 0.440 | 7,936 | 0 |
| DeepSeek | same_server | 0.117 | 0.217 | 1.855 | 0.117 | 0.226 | 1.932 | 1,792 | 0 |
| ROFT | cross_server_cross_rail | 63.820 | 48.249 | 0.756 | 63.820 | 54.595 | 0.855 | 55,552 | 0 |
| ROFT | cross_server_same_rail | 63.820 | 47.243 | 0.740 | 63.820 | 53.823 | 0.843 | 7,936 | 0 |
| ROFT | same_server | 0.117 | 0.217 | 1.855 | 0.117 | 0.226 | 1.932 | 1,792 | 0 |

Implications:

- DeepSeek is not failing because NS3 refuses to use PXN. Both simulators are PXN-decomposed at baseline, but FlowSim's logical same-rail/cross-rail original flows are about `2.6x-2.7x` slower at p95 after grouping NS3 legs back to original flows.
- DeepSeek's cross-server same-rail and cross-server cross-rail p95 are almost the same in FlowSim (`106.120us` vs `110.788us`). That points at shared endpoint/same-rail scheduling in FlowSim, not simply extra cross-rail switch-switch distance.
- ROFT is direct in both simulators. FlowSim remains slower on direct cross-server traffic by about `15-17us` at p95 after the `w0.3` cross-rail policy, but the residual is much smaller than DeepSeek.
- Same-server FCT is slower in NS3 than FlowSim, but it is only `1,792 / 65,280` flows and does not explain the baseline JCT gap.

### Baseline Hop-Knob Smoke

The m4 FlowSim backend now has two additional experimental controls:

- `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT`: direct non-PXN cross-rail switch-switch weight; defaults to `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT`.
- `FLOWSIM_*_SWITCH_SWITCH_WEIGHT_HOPS<N>`: hop-scoped override for the corresponding switch-switch weight, for example `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4`.

Smoke results:

| Topology | Case | FlowSim JCT (us) | NS3 baseline (us) | FlowSim / NS3 | Takeaway |
|---|---|---:|---:|---:|---|
| DeepSeek | base | 113.903 | 51.000 | 2.233 | Current policy remains too slow. |
| DeepSeek | PXN same-rail hop4 `w=0.5` | 84.744 | 51.000 | 1.662 | Strong improvement. |
| DeepSeek | PXN same-rail hop4 `w=0.4` | 73.063 | 51.000 | 1.433 | Stronger improvement; still above NS3. |
| RO | base | 43.984 | 73.000 | 0.603 | Current RO baseline is already too fast. |
| RO | PXN same-rail hop4 `w=0.5` | 43.984 | 73.000 | 0.603 | This RO guardrail is unchanged. |
| ROFT | base | 66.935 | 55.000 | 1.217 | Direct cross-rail baseline still too slow. |
| ROFT | direct cross-rail `w=0.25` | 59.410 | 55.000 | 1.080 | Direct-specific weight improves ROFT. |

Interpretation:

- Hop-scoped PXN same-rail weight is a better DeepSeek baseline lever than lowering the global PXN same-rail weight.
- Direct-specific cross-rail weight is a better ROFT baseline lever than treating ROFT as a PXN case.
- These knobs should be calibrated on targeted grids before any full six-topology rerun.

### Baseline Hop-Knob Grid

The baseline-only grid gives two candidate values for the next targeted fault sweep:

| Target | Candidate | Baseline result |
|---|---|---|
| DeepSeek | `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25` | `113.903us -> 55.581us`, NS3 baseline `51.000us`. |
| ROFT | `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22` | `66.935us -> 54.888us`, NS3 baseline `55.000us`. |
| RO guardrail | DeepSeek hop4 override | RO remains `43.984us` for hop4 `w=0.50` and `w=0.30`; this guardrail was not perturbed in the baseline smoke/grid. |

Interpretation:

- DeepSeek hop4 `0.25` is much more targeted than lowering the global PXN same-rail weight.
- ROFT direct `0.22` almost exactly aligns the no-fault baseline, confirming ROFT should be treated as direct cross-rail, not PXN.
- The next experiment should be a targeted fault sweep over DeepSeek, ROFT, and RO before any full six-topology rerun.

### Targeted Fault Sweep

The targeted sweep used:

- `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`
- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25`
- `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22`

Scope: DeepSeek, ROFT, and RO at 1%, 5%, 10%, and 15%, with 3 samples per rate. All `36/36` samples succeeded.

Aggregate result versus NS3 and the previous `w0.3 + pxn0.75` policy:

| Topology | Failed-JCT MAE delta | Factor MAE delta | Interpretation |
|---|---:|---:|---|
| DeepSeek | -100.22 | +0.035 | Absolute JCT greatly improves, but normalized factor is slightly worse. |
| ROFT | -15.78 | +0.079 | Absolute JCT improves, but normalized factor gets worse. |
| RO | +16.83 | -0.382 | Normalized factor improves, but absolute JCT becomes too low. |

Interpretation:

- The new hop4/direct knobs are useful baseline calibration tools.
- They should not replace the previous fault policy as a single universal policy.
- Baseline alignment and fault-response alignment are now clearly separate problems.
- Do not launch a full six-topology 10-sample sweep with this combined candidate until a separate fault-response correction is designed.

### Targeted Fault-Only Correction

The runner now supports separate baseline and failed-run environments through `--fault-*` parameters. The first fault-only test kept the baseline-calibrated candidate for baseline runs, then used these failed-run overrides:

- `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.20`
- `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.20`

Scope: DeepSeek, ROFT, and RO at 1%, 5%, 10%, and 15%, with 3 samples per rate. All `36/36` samples succeeded.

Aggregate result versus the baseline-calibrated candidate:

| Topology | Failed-JCT MAE delta | Factor MAE delta | Interpretation |
|---|---:|---:|---|
| DeepSeek | -2.92 | -0.018 | Directionally improves both absolute JCT and factor. |
| ROFT | -2.58 | -0.047 | Directionally improves both absolute JCT and factor. |
| RO | +2.50 | -0.057 | Factor improves, but absolute JCT moves farther below NS3. |

Interpretation:

- Fault-only correction is useful, but the uniform failed-run speedup is still too blunt.
- DeepSeek and ROFT benefit, while RO remains a guardrail conflict.
- The next candidate should be topology/path-class- or path-stretch-aware, not a single global failed-run override.

Path-stretch evidence:

| Topology | Corr(path stretch, failed-JCT error) | Corr(path stretch, factor error) | Meaning |
|---|---:|---:|---|
| DeepSeek | +0.973 | +0.949 | High-stretch failures remain too slow in FlowSim. |
| ROFT | +0.879 | +0.879 | High-stretch failures remain too slow in FlowSim. |
| RO | -0.851 | +0.921 | High-stretch factor is too high, but absolute JCT is already too low. |

This means the next failed-run correction should be tested on DeepSeek/ROFT first and should not be applied globally to RO.

### DeepSeek

Current full-sweep FlowSim baseline:

- FlowSim baseline JCT under `w0.3 + PXNw0.75`: `114`
- NS3 baseline JCT: `51`
- FlowSim baseline log: `split=55552`, `direct_cross_rail=0`

Existing NS3 baseline monitor/original-flow evidence:

- NS3 physical rows: `120832`
- Original flows: `65280`
- Split original flows: `55552`
- Physical same-server rows: `57344`
- Physical same-rail rows: `63488`
- Physical cross-rail rows: `0`
- PFC events: `0`

Interpretation:

- DeepSeek baseline is a PXN-decomposed baseline in both simulators.
- The policy factor curve is already close to NS3, but FlowSim's no-fault absolute time remains high.
- The grouped original-flow comparison shows the baseline gap is already visible within cross-server flow FCT: FlowSim p95 is `106-111us`, while NS3 grouped p95 is about `40.5us`.
- Existing timing and bandwidth smokes show that full PXN overlap and global switch scaling are not good final fixes. The likely remaining issue is FlowSim's sustained fair-share accounting for PXN same-rail work versus NS3's packet-level sharing/endpoint behavior.

### ROFT

New ROFT no-fault monitor rerun:

- Script: `scripts/rerun_baseline_monitor_mismatch.py`
- Output: `targeted_roft_monitor_baseline_pxn075/`
- FlowSim baseline CSV: `flowsim_256_alltoall_p01_p15_s10_crossrail_w03_pxn075_full/baseline_jct.csv`
- NS3 monitor summary: `targeted_roft_monitor_baseline_pxn075/targeted_monitor_overview.csv`
- Original-flow summary: `targeted_roft_monitor_baseline_pxn075/original_flow/ns3_original_flow_line_summary.csv`

ROFT no-fault evidence:

| Metric | Value |
|---|---:|
| Original FlowSim baseline JCT | 172 |
| FlowSim baseline JCT with cross-rail `w0.3` | 67 |
| FlowSim baseline JCT | 67 |
| NS3 baseline JCT | 55 |
| NS3 / FlowSim JCT | 0.821 |
| NS3 send rows | 65,280 |
| NS3 FCT rows | 65,280 |
| Split original flows | 0 |
| Direct original flows | 65,280 |
| Original cross-rail flows | 55,552 |
| Original cross-rail split flows | 0 |
| Physical same-server rows | 1,792 |
| Physical same-rail rows | 7,936 |
| Physical cross-rail rows | 55,552 |
| PFC events | 0 |

Interpretation:

- ROFT baseline is not a PXN baseline. It is direct cross-rail in NS3 and direct cross-rail in FlowSim (`split=0`, `direct_cross_rail=55552` in the FlowSim baseline log).
- The scoped cross-rail weight already moved FlowSim baseline from `172` to `67`. The remaining ROFT absolute baseline gap is therefore a direct-fabric FlowSim/NS3 timing gap after the cross-rail correction, not a PXN decomposition issue.
- The grouped original-flow comparison puts the remaining direct-fabric tail gap at about `15-17us` p95 for cross-server flows.
- This explains why ROFT factor calibration is good after the policy, while absolute failed JCT remains above NS3 by about `23.9` on average.

## Next Iteration

1. Freeze the current combined policy for fault-tolerance reporting:

   - `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`
   - `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT=0.75`

2. Split the remaining work into two tracks:

   - Baseline track: DeepSeek and ROFT no-fault absolute timing.
   - Fault-response track: Meta, Zcube, and RO normalized degradation.

3. For the baseline track, do not continue lowering the uniform PXN same-rail weight. DeepSeek needs a hop-scoped PXN same-rail correction, while ROFT needs a direct cross-rail correction. The targeted candidate was:

   - DeepSeek: `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25`.
   - ROFT: `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22`.
   - RO: guardrail check, since its baseline remains too low relative to NS3.

   The targeted fault sweep confirms this candidate improves absolute JCT for DeepSeek and ROFT, but worsens normalized fault response. Treat it as baseline calibration evidence, not the final fault-tolerance policy.

4. For the fault-response track, the first failed-run-only correction (`fault hop4=0.20`, `fault direct=0.20`) improves DeepSeek and ROFT but worsens RO absolute JCT. Do not use it for a full six-topology sweep. The next model should make the failed-run correction conditional on topology/path class or path stretch.

5. For the broader fault-response track, avoid a global weight. Meta, Zcube, and RO require topology/path-class-specific explanations:

   - Meta: likely missing local/PFC/queue amplification relative to the very fast NS3 baseline.
   - Zcube: physical direct cross-rail sharing/fixed-route pessimism remains the active mismatch.
   - RO: absolute JCT is now close, but the normalized curve is still steep because the FlowSim baseline is much lower than NS3.

## High-Stretch Fault Follow-Up

New runner support:

- `scripts/run_flowsim_fault_256_alltoall.py` can now choose a separate high-stretch failed-run environment per sample using `--high-stretch-fault-topologies`, `--high-stretch-threshold`, and `--high-stretch-fault-*` knobs.
- Rows record `fault_env_class` so summary/comparison scripts do not mix default fault and high-stretch fault samples silently.
- `scripts/compare_targeted_fault_policies.py` compares raw or summary CSVs after collapsing them back to topology/rate.

Completed checks:

| Policy | Scope | Result |
|---|---|---|
| `threshold=1.03`, high-stretch `hop4=0.16/direct=0.18` | DeepSeek/ROFT high-stretch; RO guardrail | `36/36` success. DeepSeek improves slightly (`12.59 -> 12.34` failed-JCT MAE), ROFT slightly worsens (`5.98 -> 6.23`), RO unchanged. |
| DeepSeek `threshold=1.03`, high-stretch `hop4=0.05` | DeepSeek only | `12/12` success. Improves DeepSeek `15%` but worsens `10%`, so the aggregate is slightly worse than fault-only (`12.59 -> 12.67`). |
| Composite DeepSeek `threshold=1.04`, high-stretch `hop4=0.05`; ROFT/RO fault-only | DeepSeek high-stretch only at the highest sampled path stretch | Best current targeted composite. DeepSeek failed-JCT MAE improves `12.59 -> 12.01` and factor MAE improves `0.110 -> 0.099`; ROFT and RO stay unchanged. |

Interpretation:

- Path-stretch awareness helps, but the hop4 weight is non-monotonic under faulted contention. Lower is not always faster or closer to NS3.
- ROFT should not receive the same high-stretch override as DeepSeek; its `15%` point worsened under the first high-stretch sweep.
- The current best composite is still a small correction, not a complete fix. The remaining DeepSeek `15%` absolute gap is still about `23us`, so the next real model improvement likely needs a better PXN same-rail contention model rather than another scalar sweep.

### Bottleneck Trace Check

To explain the non-monotonic DeepSeek high-stretch result, the FlowSim bottleneck trace was extended with:

- `pxn_generated`
- `cross_server`
- `same_rail`
- `path_weight`
- `bottleneck_active_chunks`
- `bottleneck_total_weight`

Trace experiment:

- Input topology: DeepSeek `10%`, seed `1`, same failed topology in both runs.
- Reference run: default fault-only `hop4=0.20`.
- Probe run: DeepSeek high-stretch `hop4=0.05`.
- Output: `flowsim_bottleneck_trace_deepseek_p10_seed1_h020_vs_h005/`.

Observed JCT:

| Run | JCT |
|---|---:|
| `fault_h020` | `107us` |
| `deepseek_h005` | `109us` |

Bottleneck summary:

| Run | Scope | Local NVSwitch | GPU-switch | Switch-switch | PXN | Same rail |
|---|---|---:|---:|---:|---:|---:|
| `fault_h020` | all | `52.6%` | `17.1%` | `30.3%` | `93.9%` | `47.4%` |
| `deepseek_h005` | all | `52.6%` | `26.4%` | `21.0%` | `93.9%` | `47.4%` |
| `fault_h020` | tail p99 | `46.7%` | `53.3%` | `0.0%` | `100.0%` | `53.3%` |
| `deepseek_h005` | tail p99 | `66.3%` | `33.7%` | `0.0%` | `100.0%` | `33.7%` |

Interpretation:

- Lowering `hop4` does reduce switch-switch pressure, but it moves the bottleneck to GPU-switch and local NVSwitch legs.
- The tail is already not switch-switch limited in either run. Tail rows are PXN-generated local/gpu-switch work, so a pure same-rail switch-switch scalar cannot fully match NS3.
- This explains the non-monotonic behavior: `hop4=0.05` can improve the `15%` sample but worsen `10%`, depending on whether the bottleneck transition helps or hurts that sample's tail.
- The next model change should target PXN leg overlap/local-leg contention rather than further reducing switch-switch weights.

Next candidate:

- Do not continue a broad scalar sweep on `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4`.
- Implement a middle PXN timing model between the current `serial` and full `overlap` modes. The target behavior is local-leg pipelining: the remote same-rail fabric leg should not wait for the entire local NVLink/NVSwitch leg, but it also should not launch fully concurrently with all local work.
- Keep this as an experimental `FLOWSIM_PXN_TIMING` mode, separate from the current validated default, and validate first on DeepSeek `10%/15%` seed-level traces before any multi-topology sweep.

## Local-Pipeline PXN Timing Probe

Implemented experimental FlowSim timing mode:

- `FLOWSIM_PXN_TIMING=local_pipeline`
- `FLOWSIM_PXN_LOCAL_PIPELINE_DELAY_NS=<delay>`
- CLI exposure in `scripts/run_flowsim_fault_256_alltoall.py`:
  - `--flowsim-pxn-timing local_pipeline`
  - `--pxn-local-pipeline-delay-ns 6000`

Model:

- Current `serial`: send the next PXN leg only after the previous leg completes plus `AS_SEND_LAT`.
- Current `overlap`: launch every PXN leg concurrently.
- New `local_pipeline`: launch PXN legs in order, but stagger launches by a fixed delay. Completion of the original flow waits for all generated legs.

DeepSeek smoke with 256 global all-to-all `64KiB`, `10%`, seed `1`:

| Timing | Delay | JCT | Status |
|---|---:|---:|---|
| `serial` | n/a | `23us` | success |
| `local_pipeline` | `3000ns` | n/a | timeout at `120s` |
| `local_pipeline` | `6000ns` | `19us` | success |
| `local_pipeline` | `9000ns` | `22us` | success |
| `local_pipeline` | `12000ns` | `28us` | success |

Interpretation:

- The useful region is not "as much overlap as possible". Too-early launch (`3000ns`) creates excessive event/queue pressure in FlowSim and can fail to finish within the short timeout.
- `6000ns` is the best first probe: it improves the small workload while still completing.

DeepSeek full 256 global all-to-all `1MiB`, seed `1`, fault-only weights (`hop4=0.20`, `direct=0.20`):

| Link failure | FlowSim serial | FlowSim local-pipeline `6000ns` | NS3 | Serial - NS3 | Local-pipeline - NS3 |
|---:|---:|---:|---:|---:|---:|
| `10%` | `107us` | `100us` | `93us` | `+14us` | `+7us` |
| `15%` | `123us` | `105us` | `105us` | `+18us` | `+0us` |

Interpretation:

- The local-pipeline model directly attacks the mismatch exposed by the bottleneck trace: PXN local/GPU-switch leg serialization.
- It cuts the DeepSeek `10%` seed1 absolute error in half and exactly matches the DeepSeek `15%` seed1 NS3 JCT.
- This is stronger evidence than the previous scalar hop-weight probes, because the improvement comes from timing/overlap semantics rather than pretending the same physical fabric links have a different effective bandwidth.

Current caveats:

- Full bottleneck trace for the local-pipeline `1MiB` run was not kept in the fast loop because trace-enabled full all-to-all is too slow for iteration.
- `local_pipeline` is experimental and should not replace the default serial mode until it is checked on ROFT and RO guardrails.
- The next sweep should be small and targeted: DeepSeek/ROFT/RO at `1%`, `5%`, `10%`, `15%`, `3` seeds, `delay=6000ns`, then compare against the existing fault-only and NS3 rows.

### Targeted Guardrail Sweep

Completed sweep:

- Output: `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_deepseek_roft_ro_p01_p05_p10_p15_s3/`
- Topologies: DeepSeek, ROFT, RO.
- Rates: `1%`, `5%`, `10%`, `15%`.
- Seeds: `1..3`.
- Status: `36/36` success, no timeout.
- Baseline calibration:
  - `FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.3`
  - `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.22`
  - `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.25`
- Fault override:
  - `FLOWSIM_DIRECT_CROSS_RAIL_SWITCH_SWITCH_WEIGHT=0.20`
  - `FLOWSIM_PXN_SAME_RAIL_SWITCH_SWITCH_WEIGHT_HOPS4=0.20`
- Timing:
  - `FLOWSIM_PXN_TIMING=local_pipeline`
  - `FLOWSIM_PXN_LOCAL_PIPELINE_DELAY_NS=6000`

Baseline JCTs in this run:

| Topology | FlowSim local-pipeline baseline | NS3 baseline reference |
|---|---:|---:|
| DeepSeek | `51us` | `51us` |
| ROFT | `55us` | `55us` |
| RO | `49us` | `73us` |

Comparison against the previous serial fault-only policy:

| Topology | Local failed-JCT MAE | Serial failed-JCT MAE | Local factor MAE | Serial factor MAE | Local failed-JCT bias | Serial failed-JCT bias |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek | `4.39` | `12.59` | `0.086` | `0.110` | `+1.68` | `+12.59` |
| ROFT | `2.35` | `5.98` | `0.043` | `0.109` | `-1.10` | `+5.98` |
| RO | `12.32` | `18.65` | `0.698` | `0.749` | `-8.48` | `-18.65` |

Key detail rows:

| Topology | Rate | Local JCT | Serial JCT | NS3 JCT | Local err | Serial err |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek | `5%` | `76.67` | `87.33` | `77.40` | `-0.73` | `+9.93` |
| DeepSeek | `10%` | `99.67` | `109.67` | `96.50` | `+3.17` | `+13.17` |
| DeepSeek | `15%` | `116.67` | `133.00` | `107.70` | `+8.97` | `+25.30` |
| ROFT | `10%` | `95.33` | `106.33` | `101.20` | `-5.87` | `+5.13` |
| ROFT | `15%` | `118.67` | `127.67` | `117.20` | `+1.47` | `+10.47` |
| RO | `10%` | `127.33` | `119.67` | `148.90` | `-21.57` | `-29.23` |
| RO | `15%` | `195.67` | `175.67` | `188.00` | `+7.67` | `-12.33` |

Interpretation:

- `local_pipeline d6000` is a real improvement for DeepSeek and ROFT. It fixes both the no-fault baseline under the calibrated baseline knobs and the faulted failed-JCT response much better than serial PXN timing.
- DeepSeek `15%` still has a high-tail seed (`seed=3`): NS3 is also high for that seed (`133us`), while FlowSim local-pipeline is `138us`. The residual is therefore much smaller than the mean table alone suggests.
- RO improves in absolute failed-JCT MAE, but the normalized factor remains very poor because the FlowSim RO baseline is still too low (`49us` vs NS3 `73us`). This is a baseline/factor mismatch, not primarily a PXN leg timing mismatch.
- Do not treat this as a final global policy yet. It is a strong candidate for the PXN timing model, but RO still needs a separate RO baseline or fault-response correction.

Next step:

- Run the same `local_pipeline d6000` calibrated policy on the remaining topologies (Meta, HPN, Zcube) at the same four rates and three seeds before any full `1%..15%`, `10`-seed sweep.
- If Meta/HPN/Zcube do not regress materially, promote `local_pipeline d6000` to the next full six-topology FlowSim candidate.
- Keep RO as a separate guardrail: absolute JCT improves, but normalized degradation remains the active mismatch.

### Six-Topology Candidate Check

Completed the matching remaining-topology sweep:

- Output: `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_meta_hpn_zcube_p01_p05_p10_p15_s3/`
- Topologies: Meta, HPN, Zcube.
- Rates: `1%`, `5%`, `10%`, `15%`.
- Seeds: `1..3`.
- Status: `36/36` success, no timeout.

Combined six-topology report:

- `flowsim_local_pipeline_d6000_six_topology_p01_p05_p10_p15_s3_comparison/six_topology_local_pipeline_d6000_comparison.md`
- Detail CSV: `flowsim_local_pipeline_d6000_six_topology_p01_p05_p10_p15_s3_comparison/six_topology_local_pipeline_d6000_detail.csv`
- Aggregate CSV: `flowsim_local_pipeline_d6000_six_topology_p01_p05_p10_p15_s3_comparison/six_topology_local_pipeline_d6000_aggregate.csv`

Aggregate comparison against the previous complete `w0.3 + pxn_same_rail_w0.75` policy:

| Topology | Local failed-JCT MAE | Previous failed-JCT MAE | Local factor MAE | Previous factor MAE | Local bias | Previous bias |
|---|---:|---:|---:|---:|---:|---:|
| ROFT | `2.35` | `24.35` | `0.043` | `0.077` | `-1.10` | `+24.35` |
| HPN | `2.52` | `11.70` | `0.142` | `0.254` | `+0.43` | `+11.70` |
| DeepSeek | `4.39` | `115.72` | `0.086` | `0.093` | `+1.68` | `+115.72` |
| Meta | `2.62` | `6.25` | `0.354` | `0.486` | `-1.52` | `+6.25` |
| Zcube | `3.88` | `5.62` | `0.782` | `0.779` | `+1.48` | `+1.38` |
| RO | `12.32` | `8.68` | `0.698` | `1.188` | `-8.48` | `+0.67` |
| ALL | `4.68` | `28.72` | `0.351` | `0.479` | `-1.25` | `+26.68` |

Interpretation:

- The `local_pipeline d6000` candidate is much better on absolute failed JCT overall (`28.72 -> 4.68` MAE across the 24 topology-rate points).
- It also improves overall factor MAE (`0.479 -> 0.351`), but the remaining factor error is concentrated in Zcube, RO, and Meta.
- Zcube's absolute JCT is close to NS3, but its baseline is too low (`32us`), so factor remains high. This is a baseline normalization problem rather than a failed-JCT problem.
- RO is mixed: factor improves materially, but absolute failed-JCT MAE worsens versus the previous full policy (`8.68 -> 12.32`). Still, local-pipeline removes the previous policy's large positive bias and makes RO less systematically high.
- This candidate is strong enough for a full `1%..15%`, `10`-seed six-topology sweep, while keeping RO/Zcube factor mismatch as the next analysis track.

Next full candidate command:

```bash
python3 scripts/run_flowsim_fault_256_alltoall.py \
  --workload my_workloads/synthetic_alltoall_global_world_size256_1MiB.txt \
  --output-dir experiments/fault_tolerance/flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10 \
  --samples 10 \
  --jobs 4 \
  --threads 4 \
  --flowsim-pxn-timing local_pipeline \
  --pxn-local-pipeline-delay-ns 6000 \
  --cross-rail-switch-switch-weight 0.3 \
  --direct-cross-rail-switch-switch-weight 0.22 \
  --pxn-same-rail-switch-switch-hop-weights 4=0.25 \
  --fault-direct-cross-rail-switch-switch-weight 0.2 \
  --fault-pxn-same-rail-switch-switch-hop-weights 4=0.2 \
  --run-timeout-seconds 900 \
  --resume
```

Full sweep status:

- Output: `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/`
- tmux session: `flowsim_lp_d6000_full_s10` completed and exited
- Live status: `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/RUN_STATUS.md`
- Partial comparison: `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/PARTIAL_COMPARISON.md`
- Full comparison: `flowsim_256_alltoall_local_pipeline_d6000_baselinecalib_p01_p15_s10/FULL_COMPARISON.md`
- Current observed state: full sweep is complete with `900/900` successful fault samples and `90/90` topology-rate summary rows.
- Initial live check: `41/900` rows completed, all `success`; completed full groups are Meta `1%..4%` with local failed-JCT MAE `2.92` versus previous policy `8.73` on the same groups.
- Follow-up live check: `55/900` rows completed, all `success`; completed full groups are Meta `1%..5%`. On these completed groups, local failed-JCT MAE is `3.26` versus previous policy `7.12`, and local factor MAE is `0.325` versus previous policy `0.373`.
- Follow-up live check: `75/900` rows completed, all `success`; completed full groups are Meta `1%..7%`. On these completed groups, local failed-JCT MAE is `4.00` versus previous policy `5.20`, and local factor MAE is `0.354` versus previous policy `0.429`. Local remains better overall but is slightly fast versus NS3 at higher Meta rates, so Meta `8%..15%` should be watched before declaring the full curve stable.
- Follow-up live check: `82/900` rows completed, all `success`; completed full groups are Meta `1%..8%`. On these completed groups, local failed-JCT MAE is `4.26` versus previous policy `4.66`, and local factor MAE is `0.364` versus previous policy `0.450`. The important change is bias: local is now systematically fast (`-4.26us`) while previous is systematically slow (`+4.36us`), so any next correction should be topology-aware rather than another global PXN timing change.
- Follow-up live check: `100/900` rows completed, all `success`; completed full groups are Meta `1%..10%`. On these completed groups, local failed-JCT MAE is essentially tied with previous (`4.21` versus `4.23`), but local factor MAE remains better (`0.377` versus `0.480`). This reinforces that `local_pipeline d6000` is not uniformly better for every topology/rate in absolute JCT; its strongest value is fixing PXN-heavy topologies and improving normalized behavior, while Meta may need a small topology-specific correction if absolute JCT is prioritized.
- Follow-up live check: `131/900` rows completed, all `success`; completed full groups are Meta `1%..13%`. On these completed groups, local failed-JCT MAE is slightly worse than previous (`4.30` versus `3.87`) because local is consistently fast (`-4.30us`) while previous is consistently slow (`+3.68us`). Local factor MAE remains much better (`0.399` versus `0.519`). This makes Meta a clear example where absolute JCT and normalized factor point in different directions.
- Follow-up live check: `153/900` rows completed, all `success`; Meta is now complete for `1%..15%`, `10` seeds per rate, and HPN has started. On the full Meta curve, local failed-JCT MAE is slightly worse than previous (`4.24` versus `3.86`), while local factor MAE is much better (`0.410` versus `0.540`). Meta should therefore not drive another global PXN timing change; it is a topology/metric tradeoff case.
- Follow-up live check: HPN has completed through `1%..8%`, giving `23` complete topology-rate groups in the partial report. Across these complete groups, local failed-JCT MAE is better than previous (`4.53` versus `6.25`) and local factor MAE is also better overall (`0.347` versus `0.426`). HPN itself shows a different tradeoff from Meta: local absolute JCT improves (`5.08` versus `10.72` MAE), but HPN factor MAE is slightly worse (`0.229` versus `0.212`) because the local-pipeline curve is fast relative to NS3. The HPN absolute error shrinks at higher rates (`7%`: `-3.4us`, `8%`: `-2.5us`), so its residual factor mismatch is mostly baseline normalization rather than failed-JCT shape.
- Final full check: `900/900` rows completed, all `success`. Across all `90` topology-rate groups, `local_pipeline d6000` improves failed-JCT MAE from `28.34` to `6.40`, reduces positive bias from `+26.69us` to a mild fast bias of `-5.86us`, and improves factor MAE from `0.487` to `0.320`.
- Per-topology final view: DeepSeek is now close (`3.80us` failed-JCT MAE, `0.075` factor MAE), HPN is also close (`3.71us`, `0.189`), Zcube improves in both views (`3.93us`, `0.662`) but remains normalization-heavy, and Meta remains a metric tradeoff (`4.24us` failed-JCT MAE versus previous `3.86us`, but factor `0.410` versus previous `0.540`). ROFT improves strongly in absolute JCT (`4.91us` versus previous `23.90us`) but slightly worsens factor (`0.089` versus `0.069`). RO is the main residual conflict: local factor improves a lot (`0.498` versus `1.197`), but absolute failed-JCT MAE worsens (`17.82us` versus `6.86us`) because local is systematically fast (`-17.82us` bias).
- Next analysis track: keep `local_pipeline d6000` as the current best global FlowSim candidate, then diagnose RO separately. The likely next lever should be topology/path-class-specific for RO, not another global PXN timing delay, because global local-pipeline fixed DeepSeek/HPN/ROFT/Zcube absolute timing while RO moved in the opposite absolute-JCT direction.
