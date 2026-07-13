# FlowSim PXN-Leg Calibration

| Topology | Variant   | Timing  | Local | Switch | PXN same-rail | Baseline | Failed  | NS3 failed | Factor | NS3 factor | Failed err | Factor err |
| -------- | --------- | ------- | ----- | ------ | ------------- | -------- | ------- | ---------- | ------ | ---------- | ---------- | ---------- |
| DeepSeek | overlap   | overlap | 1.0   | 1.0    | 1.000         | 138.0    | 317.0   | 105.000    | 2.297  | 2.059      | 212.0      | 0.238      |
| DeepSeek | pxn_w0p5  | serial  | 1.000 | 1.000  | 0.500         | 85.000   | 186.000 | 105.000    | 2.188  | 2.059      | 81.0       | 0.129      |
| DeepSeek | pxn_w0p75 | serial  | 1.000 | 1.000  | 0.750         | 114.000  | 259.000 | 105.000    | 2.272  | 2.059      | 154.0      | 0.213      |
| DeepSeek | serial    | serial  | 1.0   | 1.0    | 1.000         | 143.0    | 336.0   | 105.000    | 2.350  | 2.059      | 231.0      | 0.291      |
| RO       | overlap   | overlap | 1.0   | 1.0    | 1.000         | 49.0     | 263.0   | 253.000    | 5.367  | 3.466      | 10.0       | 1.902      |
| RO       | pxn_w0p5  | serial  | 1.000 | 1.000  | 0.500         | 34.000   | 162.000 | 253.000    | 4.765  | 3.466      | 91.0       | 1.299      |
| RO       | pxn_w0p75 | serial  | 1.000 | 1.000  | 0.750         | 44.000   | 225.000 | 253.000    | 5.114  | 3.466      | 28.0       | 1.648      |
| RO       | serial    | serial  | 1.0   | 1.0    | 1.000         | 54.0     | 281.0   | 253.000    | 5.204  | 3.466      | 28.0       | 1.738      |

Notes:
- Variants use FlowSim diagnostic bandwidth multipliers for link categories.
- The failed topology is the 15% link-failure seed1 topology from the full fault sweep.
- This is a targeted sensitivity test, not a proposed physical bandwidth change.
