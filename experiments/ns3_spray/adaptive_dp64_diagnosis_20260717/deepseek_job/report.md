# NS3 QP Spray, 256-GPU Topology

The path-dispersion metrics below include fabric flows only; same-server transfers are excluded.
Path coverage compares observed paths with the largest local next-hop choice set, capped by spray width.
Workload: `/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2/my_workloads/synthetic_allgather_world_size256_64MiB_probe.txt`

| Topology | Policy | Status | JCT (us) | vs ECMP | Logical FCT p95 (ns) | Mean unique paths | Path coverage | Avoidable collision | Link max/mean | Link COV | Dynamic bindings | Flowlet decisions | Flowlet switches | Predicted path score p95 (ns) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DeepSeek | spray_adaptive | success | 1233.754 | n/a | 174367.0 | 2.134 | 0.909 | 0.306 | 1.336 | 0.341 | 0 | n/a | n/a | n/a |
