# Dense256 Meta Simulator and Routing Comparison Plan

## Goal

Separate two effects that are currently mixed together:

1. Simulator/model difference: NS-3 vs htsim vs FlowSim under comparable routing assumptions.
2. Routing algorithm difference: ECMP vs packet spray variants within the same simulator, primarily htsim.

## Fixed Inputs

- Workload: `my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt`
- Workload type: dense, not MoE.
- Topology: `mytopo/Meta_Topo_256g_8gps_400Gbps_A100`
- htsim config: `myconfig/Meta256MoE.conf`
- NS-3 config: `experiments/cross_backend_dense256_meta_20260624_114003/ns3_rerun_20260624_143409/retry_fixed_conf/Meta256_run.conf`

## Experiment Matrix

### A. Simulator Difference, Route Held As Close As Possible

| Case | Backend | Route strategy | Status | Purpose |
| --- | --- | --- | --- | --- |
| A1 | NS-3 | ECMP | done | High-fidelity packet/QP/protocol baseline |
| A2 | htsim | ECMP | running/needed | Isolate htsim packet RoCE model from route-algorithm changes |
| A3 | FlowSim | fixed per-flow path from routing framework | done | Flow/chunk/link-sharing approximation baseline |

Why A2 matters: comparing NS-3 ECMP directly against htsim `spray_plb` mixes simulator difference and routing difference. htsim ECMP is the clean bridge.

### B. Routing Algorithm Difference Within htsim

| Case | Backend | Route strategy | Status | Purpose |
| --- | --- | --- | --- | --- |
| B1 | htsim | `single` | short smoke done | Single first-shortest-path baseline, mainly diagnostic |
| B2 | htsim | `ecmp` | full run needed | Stable per-flow hash path baseline |
| B3 | htsim | `spray_rr` | full run needed | Deterministic per-data-packet spray baseline |
| B4 | htsim | `spray_plb` | full done | Source-side adaptive PLB approximation |
| B5 | htsim | `spray_reps` | short smoke done | REPS-inspired path recycling, optional full run |
| B6 | htsim | `spray_oblivious` | short smoke done | Random per-packet stress baseline, not preferred for full runs |

Recommended full-run priority:

1. `ecmp`, because it enables NS-3 ECMP vs htsim ECMP.
2. `spray_rr`, because it is the clean deterministic packet-spray baseline.
3. `spray_plb`, already complete.
4. `spray_reps`, optional if we want a REPS-style adaptive comparison.
5. `spray_oblivious`, optional stress case only.

### C. FlowSim Interpretation

FlowSim should be compared as a simulator/model, not as a packet-routing algorithm implementation.

Current FlowSim route behavior:

- It calls `RoutingFramework::GetFlowSimPathByNodeIds(src,dst)`.
- That constructs a fixed `FlowKey` for each `(src,dst)` pair.
- Therefore, in current runs FlowSim uses a stable precomputed path per GPU pair.
- It does not implement packet-level ECMP or packet spray.
- It models flow/chunk completion over shared links, not RDMA packet/QP behavior.

So FlowSim is useful for fast topology trend screening, but should not be treated as an ECMP-vs-Spray routing experiment.

### D. Short Cross-Simulator Sanity Matrix

Before the full htsim ECMP and htsim `spray_rr` runs finish, use a short/capped workload to validate the comparison harness:

- runner: `run_short_cross_sim_compare.sh 20260626_short10_1mib_r2`
- workload: `/tmp/htsim_dense256_short10_1mib.txt`
- topology: `mytopo/Meta_Topo_256g_8gps_400Gbps_A100`
- output: `short_cross_sim_20260626_short10_1mib_r2/summary.md`

Completed cases:

| Case | Route | Rows | Total time | Exposed comm |
| --- | --- | ---: | ---: | ---: |
| FlowSim | fixed precomputed path per src-dst | 15 | 65580 | 492 |
| htsim ECMP | stable per-flow ECMP | 15 | 65367 | 279 |
| htsim `spray_rr` | deterministic per-packet RR spray | 15 | 65258 | 170 |
| NS-3 ECMP | switch-side ECMP | 15 | 65416 | 328 |

This is a sanity/trend experiment only; the final dense conclusion still requires the full htsim ECMP and htsim `spray_rr` runs.

## Existing Full Results

| Case | Output | EndToEnd rows |
| --- | --- | ---: |
| FlowSim | `flowsim/EndToEnd.csv` | 1267 |
| htsim `spray_plb` | `htsim_spray_plb_fixed_20260624_195704/EndToEnd.csv` | 1267 |
| NS-3 ECMP | `ns3_rerun_20260624_143409/EndToEnd.csv` | 1267 |

## New Runs To Launch

Sequential htsim full dense Meta route comparison:

1. `htsim_ecmp_full_<timestamp>/`
2. `htsim_spray_rr_full_<timestamp>/`

Both use:

```bash
env HTSIM_FLOW_RECLAIM_BATCH=262144 ./bin/SimAI_htsim \
  -w /home/zty/Topo/SimAI_TyKuro9/my_workloads/H100-gpt_22B-world_size256-tp8-pp8-ep1-gbs384-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-False.txt \
  -n /home/zty/Topo/SimAI_TyKuro9/mytopo/Meta_Topo_256g_8gps_400Gbps_A100 \
  -c /home/zty/Topo/SimAI_TyKuro9/myconfig/Meta256MoE.conf \
  -o <output-dir> \
  -r <ecmp|spray_rr>
```

## How To Read The Final Comparison

- NS-3 ECMP vs htsim ECMP: simulator/model difference.
- htsim ECMP vs htsim `spray_rr`: routing algorithm difference, stable flow ECMP vs deterministic packet spray.
- htsim ECMP vs htsim `spray_plb`: routing algorithm difference, stable flow ECMP vs source-side adaptive PLB.
- htsim `spray_rr` vs htsim `spray_plb`: deterministic packet spray vs adaptive packet path selection.
- FlowSim vs NS-3/htsim: model granularity difference, not packet routing difference.
