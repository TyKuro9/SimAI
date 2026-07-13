# Dense256 Meta Route Comparison Summary

| Case | Status | Model | Route | Rows | Progress | FCT rows | Total time | Exposed comm | DP | TP | Wall | RSS KB |
| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| NS-3 ECMP | complete | packet/QP/protocol | ECMP | 1267 | complete |  | 8101603.000 | 311149.000 | 130878.000 | 180268.000 | 10:24:10 | 42389416 |
| htsim ECMP | complete | packet RoCE | stable per-flow ECMP | 1267 | complete |  | 34772731.000 | 26982278.000 | 26336156.000 | 646119.000 | 18:28:05 | 27847320 |
| htsim ns3_ecmp | stopped | packet RoCE | per-hop ECMP source-route approximation | 0 | input_grad 1259/1262 (99.76%), ETA 0s | 36018734 |  |  |  |  |  |  |
| htsim ns3_ecmp nofct | stopped | packet RoCE | per-hop ECMP source-route approximation, FCT output disabled | 0 | input_grad 1259/1262 (99.76%), ETA 0s |  |  |  |  |  |  |  |
| htsim spray_rr | queued_or_missing | packet RoCE | deterministic per-packet RR spray | 0 |  |  |  |  |  |  |  |  |
| htsim spray_plb | complete | packet RoCE | source-side adaptive PLB | 1267 | complete |  | 8109357.000 | 318904.000 | 203984.000 | 114916.000 | 2:31:17 | 29812020 |
| FlowSim | complete | flow/chunk/link sharing | fixed precomputed path per src-dst | 1267 | complete |  | 8420705.000 | 630252.000 | 496810.000 | 133438.000 | 14:32.01 | 51131984 |

## 2026-07-06 htsim ns3_ecmp Diagnostic Update

- Both full htsim `ns3_ecmp` attempts, with and without FCT output, were stopped near `input_grad 1259/1262` with empty `EndToEnd.csv`; FCT I/O was not the root cause.
- Added focused repro tooling: `make_htsim_repro_workloads.py` and `run_htsim_ns3_ecmp_diagnostics.sh`.
- Compact repro `dense256_cap256m_core7`: old htsim `ecmp` completes with 12 rows and `all passes finished at time: 54483474`; original `ns3_ecmp` times out after 420s with 0 rows.
- htsim `ns3_ecmp` now has a conservative completion fix: forward route remains per-hop ECMP, ACK/NACK uses a stable reverse shortest path, and `RoceSrc` tail RTO is default-enabled only for `ns3_ecmp`.
- Fixed `ns3_ecmp` completes the repro with 12 rows, `all passes finished at time: 734051676`, wall `2:20.67`, RSS about 789 MB. This is a completion fix, not final numerical alignment with NS-3 queue/RDMA timing.

## Interpretation Guide

- NS-3 ECMP vs htsim ns3_ecmp compares NS-3 switch-side ECMP with the htsim per-hop ECMP source-route approximation.
- htsim ECMP is the older stable complete-path hash baseline, not switch-side ECMP.
- htsim ECMP vs htsim spray_rr isolates stable per-flow routing vs deterministic per-packet spray.
- htsim ECMP vs htsim spray_plb isolates stable per-flow routing vs source-side adaptive PLB.
- FlowSim should be read as a flow/chunk/link-sharing model with fixed per-src-dst paths, not as packet-level ECMP or Spray.
