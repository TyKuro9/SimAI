# NS3 1024-GPU GA=6 Spray Results

JCT is read from the final `total time` in `EndToEnd.csv`. ASTRA-Sim reports this value in microseconds.

PXN is disabled. Runs use the record mode, spray width, and NS3 thread count stored in the CSV and manifest. In `dp-fct` mode, `fct.txt` contains only real DP-group traffic.

| Workload | Topology | Policy | Record mode | Status | JCT (us) | JCT (s) | vs equal-path | Wall time (s) |
|---|---|---|---|---|---:|---:|---:|---:|
| Dense | ROFT | spray_dual_table | dp-fct | success | 1142526.541 | 1.142527 | +0.000% | 40324.5 |
| Dense | ROFT | spray_adaptive | dp-fct | success | 1142527.392 | 1.142527 | +0.000% | 40224.5 |
| Dense | Zcube | spray_dual_table | dp-fct | success | 1143126.484 | 1.143126 | +0.000% | 40919.7 |
| Dense | Zcube | spray_adaptive | dp-fct | success | 1143074.296 | 1.143074 | -0.005% | 39635.3 |
| Dense | DeepSeek | spray_dual_table | dp-fct | success | 1142526.543 | 1.142527 | +0.000% | 40511.1 |
| Dense | DeepSeek | spray_adaptive | dp-fct | success | 1142527.196 | 1.142527 | +0.000% | 39878.9 |
