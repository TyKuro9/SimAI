# NS3 QP Spray, 256-GPU Topology

The path-dispersion metrics below include fabric flows only; same-server transfers are excluded.
Path coverage compares observed paths with the largest local next-hop choice set, capped by spray width.
Workload: `/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2/my_workloads/synthetic_alltoall_global_world_size256_64KiB_smoke.txt`

| Topology | Policy | Status | JCT (s) | vs ECMP | Logical FCT p95 (ns) | Mean unique paths | Path coverage | Avoidable collision | Link max/mean | Link COV | Dynamic bindings | Flowlet decisions | Flowlet switches | Predicted path score p95 (ns) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Zcube | spray_dual_table | success | 9.197 | n/a | 6254.0 | 1.677 | 0.838 | 0.323 | 1.835 | 0.562 | 253952 | 0 | 0 | 4590.0 |
