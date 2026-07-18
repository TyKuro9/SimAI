# NS3 QP Spray, 256-GPU Topology

The path-dispersion metrics below include fabric flows only; same-server transfers are excluded.
Path coverage compares observed paths with the largest local next-hop choice set, capped by spray width.
Workload: `/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2/my_workloads/H100-gpt_7B-world_size256-tp8-pp4-ep1-gbs24-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-True.txt`

| Topology | Policy | Status | JCT (us) | vs ECMP | Logical FCT p95 (ns) | Mean unique paths | Path coverage | Avoidable collision | Link max/mean | Link COV | Dynamic bindings | Flowlet decisions | Flowlet switches | Predicted path score p95 (ns) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| HPN | spray_dual_table | success | 472506.846 | n/a | 4768.0 | n/a | n/a | n/a | n/a | n/a | 0 | n/a | n/a | n/a |
| DeepSeek | spray_dual_table | success | 452354.475 | n/a | 4768.0 | n/a | n/a | n/a | n/a | n/a | 0 | n/a | n/a | n/a |
| Zcube | spray_dual_table | success | 488823.024 | n/a | 4768.0 | n/a | n/a | n/a | n/a | n/a | 0 | 0 | 0 | n/a |
