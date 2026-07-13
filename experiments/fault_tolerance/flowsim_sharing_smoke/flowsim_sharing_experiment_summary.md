# FlowSim Sharing Experiment Summary

| Topology | Variant               | JCT     | JCT/serial | JCT/NS3 | p95 cross-rail | p95 cross-rail/NS3 | p95 same-rail/NS3 |
| -------- | --------------------- | ------- | ---------- | ------- | -------------- | ------------------ | ----------------- |
| Meta     | crossrail_switch_w0.5 | 149.000 | 0.898      | 1.104   | 103,640        | 1.307              | 1.322             |
| Meta     | serial                | 166.000 | 1.000      | 1.230   | 163,206        | 2.058              | 2.082             |
| Zcube    | crossrail_switch_w0.5 | 90.000  | 0.542      | 1.406   | 73,356         | 1.364              | 1.391             |
| Zcube    | ecmp_default          | 166.000 | 1.000      | 2.594   | 111,421        | 2.072              | 1.829             |
| Zcube    | ecmp_ns3ish           | 165.000 | 0.994      | 2.578   | 111,511        | 2.074              | 1.798             |
| Zcube    | serial                | 166.000 | 1.000      | 2.594   | 111,421        | 2.072              | 1.829             |
| Zcube    | switch_switch_x2      | 85.000  | 0.512      | 1.328   | 66,795         | 1.242              | 1.266             |
| RO       | crossrail_switch_w0.5 | 464.000 | 1.000      | 1.084   | 461,120        | 1.099              | 1.099             |
| RO       | serial                | 464.000 | 1.000      | 1.084   | 461,120        | 1.099              | 1.099             |
| RO       | switch_switch_x2      | 240.000 | 0.517      | 0.561   | 236,458        | 0.563              | 0.564             |

Notes:
- `serial` is the original FlowSim model.
- `ecmp_ns3ish` uses `FLOWSIM_ECMP_SEED=node FLOWSIM_ECMP_SRC_PORT=10000`.
- `switch_switch_x2` doubles all switch-switch effective bandwidth.
- `crossrail_switch_w0.5` weights physical cross-rail traffic as 0.5 competitors on switch-switch links.
