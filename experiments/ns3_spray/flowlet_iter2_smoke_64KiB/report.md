# NS3 QP Spray, 256-GPU Topology

The path-dispersion metrics below include fabric flows only; same-server transfers are excluded.
Path coverage compares observed paths with the largest local next-hop choice set, capped by spray width.
Workload: `/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2/my_workloads/synthetic_alltoall_global_world_size256_64KiB.txt`

| Topology | Policy | Status | JCT (s) | vs ECMP | Logical FCT p95 (ns) | Mean unique paths | Path coverage | Avoidable collision | Link max/mean | Link COV | Dynamic bindings | Flowlet decisions | Flowlet switches | Predicted path score p95 (ns) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Zcube | spray_flowlet | success | 9.233 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | 0 | 0 | n/a |
