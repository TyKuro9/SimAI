# FlowSim PXN-Leg Calibration

| Topology | Variant          | Local | Switch | Baseline | Failed | NS3 failed | Factor | NS3 factor | Failed err | Factor err |
| -------- | ---------------- | ----- | ------ | -------- | ------ | ---------- | ------ | ---------- | ---------- | ---------- |
| DeepSeek | default          | 1.0   | 1.0    | 143.0    | 336.0  | 105.000    | 2.350  | 2.059      | 231.0      | 0.291      |
| DeepSeek | localx2          | 2.0   | 1.0    | 142.0    | 330.0  | 105.000    | 2.324  | 2.059      | 225.0      | 0.265      |
| DeepSeek | localx2_switchx2 | 2.0   | 2.0    | 76.0     | 176.0  | 105.000    | 2.316  | 2.059      | 71.0       | 0.257      |
| DeepSeek | switchx2         | 1.0   | 2.0    | 76.0     | 176.0  | 105.000    | 2.316  | 2.059      | 71.0       | 0.257      |
| RO       | default          | 1.0   | 1.0    | 54.0     | 281.0  | 253.000    | 5.204  | 3.466      | 28.0       | 1.738      |
| RO       | localx2          | 2.0   | 1.0    | 53.0     | 284.0  | 253.000    | 5.358  | 3.466      | 31.0       | 1.893      |
| RO       | localx2_switchx2 | 2.0   | 2.0    | 32.0     | 152.0  | 253.000    | 4.750  | 3.466      | 101.0      | 1.284      |
| RO       | switchx2         | 1.0   | 2.0    | 33.0     | 151.0  | 253.000    | 4.576  | 3.466      | 102.0      | 1.110      |

Notes:
- Variants use FlowSim diagnostic bandwidth multipliers for link categories.
- The failed topology is the 15% link-failure seed1 topology from the full fault sweep.
- This is a targeted sensitivity test, not a proposed physical bandwidth change.
