# NS3 1024-GPU GA=6 Spray JCT

JCT is read from the final `total time` in `EndToEnd.csv`. ASTRA-Sim reports this value in microseconds.

PXN is disabled. Runs use JCT-only mode, spray width 4, and 8 NS3 threads unless the CSV records different command-line values.

| Workload | Topology | Policy | Status | JCT (us) | JCT (s) | vs QP dynamic | Wall time (s) |
|---|---|---|---|---:|---:|---:|---:|
| Dense | ROFT | spray_adaptive | success | 1142527.783 | 1.142528 | n/a | 26786.2 |
| Dense | Zcube | spray_adaptive | success | 1143074.292 | 1.143074 | n/a | 25969.5 |
| Dense | DeepSeek | spray_adaptive | success | 1142527.618 | 1.142528 | n/a | 25977.7 |
| Dense | Meta | spray_adaptive | success | 1178357.108 | 1.178357 | n/a | 30060.2 |
| Dense | HPN | spray_adaptive | success | 1241226.307 | 1.241226 | n/a | 26281.4 |
