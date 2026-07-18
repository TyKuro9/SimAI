# NS3 1024-GPU GA=6 Spray JCT

JCT is read from the final `total time` in `EndToEnd.csv`. ASTRA-Sim reports this value in microseconds.

PXN is disabled. Runs use JCT-only mode, spray width 4, and 8 NS3 threads unless the CSV records different command-line values.

| Workload | Topology | Policy | Status | JCT (us) | JCT (s) | vs QP dynamic | Wall time (s) |
|---|---|---|---|---:|---:|---:|---:|
| Dense | DeepSeek | spray_flowlet | timeout | n/a | n/a | n/a | 129604.0 |
| Dense | Zcube | spray_flowlet | success | 1752934.824 | 1.752935 | n/a | 65893.3 |
| MoE | DeepSeek | spray_flowlet | timeout | n/a | n/a | n/a | 129608.4 |
| MoE | Zcube | spray_flowlet | timeout | n/a | n/a | n/a | 129608.0 |
