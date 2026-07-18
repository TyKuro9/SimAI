# FlowSim 1024-GPU Adaptive Spray Validation

> **Superseded pre-fanout result.** This run exposed scale-dependent Meta and
> HPN transport mismatch. The corrected result is in
> `../adaptive_dense_1024_ga6_fanoutfix_20260718/README.md`.

- Workload: GPT-22B Dense, TP=8, PP=4, EP=1, GA=6
- Topologies: 1024-GPU 12.8 Tbps set
- Routing: `spray_adaptive`, width=4, path pool=64, max extra hops=2
- Transport: `ns3_cc`, 9000 B payload + 48 B header
- PXN/NVLS: disabled

| Topology | Status | FlowSim JCT (us) | ns-3 JCT (us) | Error | Wall (s) | RSS (GiB) |
|---|---|---:|---:|---:|---:|---:|
| ROFT | success | 1142027.250 | 1142527.783 | 0.044% | 1264.46 | 41.21 |
| Zcube | success | 1142027.250 | 1143074.292 | 0.092% | 1306.50 | 41.21 |
| DeepSeek | success | 1142027.250 | 1142527.618 | 0.044% | 1261.15 | 41.07 |
| Meta | success | 1162587.597 | 1178357.108 | 1.338% | 1288.80 | 41.23 |
| HPN | success | 1177131.867 | 1241226.307 | 5.164% | 1386.90 | 41.22 |
| RO | success | 1465313.967 | n/a | n/a | 1413.20 | 41.03 |

Comparable-topology MAPE: `1.336%`.
