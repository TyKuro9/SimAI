# FlowSim PXN Timing Smoke Summary

| Topology | Serial JCT | Overlap JCT | Reduction | NS3 JCT | Serial p95 cross-rail | Overlap p95 cross-rail | NS3 grouped p95 cross-rail |
| -------- | ---------- | ----------- | --------- | ------- | --------------------- | ---------------------- | -------------------------- |
| Meta     | 166.000    | 155.000     | 6.627%    | 135.000 | 163,206               | 152,060                | 79,306                     |
| Zcube    | 166.000    | 164.000     | 1.205%    | 64.000  | 111,421               | 110,356                | 53,767                     |
| RO       | 464.000    | 445.000     | 4.095%    | 428.000 | 461,120               | 444,323                | 419,672                    |

Notes:
- `serial` is the existing store-and-forward PXN leg timing.
- `overlap` launches all physical PXN legs concurrently and completes the original flow after the slowest leg.
- The switch is experimental and enabled with `FLOWSIM_PXN_TIMING=overlap` or `AS_PXN_TIMING=overlap`.
