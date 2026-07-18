# NS3 QP Spray, 256-GPU Topology

The path-dispersion metrics below include fabric flows only; same-server transfers are excluded.
Path coverage compares observed paths with the largest local next-hop choice set, capped by spray width.
Workload: `/tmp/zcube_dual_path_dp_smoke.txt`

| Topology | Policy | Status | JCT (us) | vs ECMP | Logical FCT p95 (ns) | Mean unique paths | Path coverage | Avoidable collision | Link max/mean | Link COV | Dynamic bindings | Flowlet decisions | Flowlet switches | Predicted path score p95 (ns) |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Zcube | spray_adaptive | success | 68.257 | n/a | 7088.0 | 2.916 | 1.458 | 0.000 | 1.002 | 0.003 | 7168 | n/a | n/a | 4621.0 |
