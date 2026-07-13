# FlowSim/NS3 Mechanism Summary

This table combines the targeted original-flow FCT comparison, NS3 physical-leg reconstruction, and baseline-normalized monitor data.

| Topology | FlowSim JCT ratio | NS3 JCT ratio | FlowSim/NS3 p95 same-rail | FlowSim/NS3 p95 cross-rail | NS3 physical row ratio | Fault split originals | Fault cross-rail split | GPU-switch queue ratio | Switch-switch queue ratio | PFC events |
| -------- | ----------------- | ------------- | ------------------------- | -------------------------- | ---------------------- | --------------------- | ---------------------- | ---------------------- | ------------------------- | ---------- |
| Meta     | 0.938             | 2.755         | 2.082                     | 2.058                      | 1.258                  | 15,782                | 13,812                 | 6.974                  | 1.272                     | 0 -> 0     |
| RO       | 8.593             | 5.863         | 1.099                     | 1.099                      | 1.191                  | 58,444                | 55,552                 | 1.621                  | 8.345                     | 0 -> 116   |
| Zcube    | 5.188             | 1.362         | 1.829                     | 2.072                      | 1.061                  | 3,912                 | 3,420                  | 1.955                  | 1.248                     | 0 -> 0     |

Reading guide:
- `FlowSim/NS3 p95` compares FlowSim original-flow p95 FCT with NS3 physical legs grouped back to original flows.
- Values above 1 mean FlowSim is slower at the same original-flow grain.
- Queue ratios are fault/baseline ratios from the targeted NS3 monitor reruns.
