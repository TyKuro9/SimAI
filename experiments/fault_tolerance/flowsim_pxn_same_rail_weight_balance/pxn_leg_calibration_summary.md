# FlowSim PXN-Leg Calibration

| Topology | Variant   | Timing | Local | Switch | PXN same-rail | Baseline | Failed  | NS3 failed | Factor | NS3 factor | Failed err | Factor err |
| -------- | --------- | ------ | ----- | ------ | ------------- | -------- | ------- | ---------- | ------ | ---------- | ---------- | ---------- |
| DeepSeek | default   | serial | 1.000 | 1.000  | 1.000         | 143.000  | 336.000 | 105.000    | 2.350  | 2.059      | 231.0      | 0.291      |
| DeepSeek | pxn_w0p75 | serial | 1.000 | 1.000  | 0.750         | 114.000  | 259.000 | 105.000    | 2.272  | 2.059      | 154.0      | 0.213      |
| DeepSeek | pxn_w0p85 | serial | 1.000 | 1.000  | 0.850         | 126.000  | 288.000 | 105.000    | 2.286  | 2.059      | 183.0      | 0.227      |
| DeepSeek | pxn_w0p90 | serial | 1.000 | 1.000  | 0.900         | 131.000  | 302.000 | 105.000    | 2.305  | 2.059      | 197.0      | 0.247      |
| DeepSeek | pxn_w0p95 | serial | 1.000 | 1.000  | 0.950         | 137.000  | 322.000 | 105.000    | 2.350  | 2.059      | 217.0      | 0.292      |
| RO       | default   | serial | 1.000 | 1.000  | 1.000         | 54.000   | 281.000 | 253.000    | 5.204  | 3.466      | 28.0       | 1.738      |
| RO       | pxn_w0p75 | serial | 1.000 | 1.000  | 0.750         | 44.000   | 225.000 | 253.000    | 5.114  | 3.466      | 28.0       | 1.648      |
| RO       | pxn_w0p85 | serial | 1.000 | 1.000  | 0.850         | 48.000   | 247.000 | 253.000    | 5.146  | 3.466      | 6.0        | 1.680      |
| RO       | pxn_w0p90 | serial | 1.000 | 1.000  | 0.900         | 50.000   | 258.000 | 253.000    | 5.160  | 3.466      | 5.0        | 1.694      |
| RO       | pxn_w0p95 | serial | 1.000 | 1.000  | 0.950         | 52.000   | 270.000 | 253.000    | 5.192  | 3.466      | 17.0       | 1.727      |

Notes:
- Variants use FlowSim diagnostic bandwidth multipliers for link categories.
- The failed topology is the 15% link-failure seed1 topology from the full fault sweep.
- This is a targeted sensitivity test, not a proposed physical bandwidth change.
