# Fault-Only Correction Error By Path Stretch

Source CSV:

- `faultonly_error_by_path_stretch.csv`

This checks whether the remaining mismatch after `fault hop4=0.20/direct=0.20` is tied to failure-induced path stretch.

## Table

| Topology | Rate | FlowSim path stretch | NS3 path stretch | Stretch delta | Failed-JCT error | Factor error |
|---|---:|---:|---:|---:|---:|---:|
| DeepSeek | 1% | 1.0017 | 1.0020 | -0.0003 | +1.97 | -0.068 |
| DeepSeek | 5% | 1.0176 | 1.0141 | +0.0034 | +9.93 | +0.042 |
| DeepSeek | 10% | 1.0334 | 1.0332 | +0.0002 | +13.17 | +0.066 |
| DeepSeek | 15% | 1.0485 | 1.0545 | -0.0060 | +25.30 | +0.263 |
| ROFT | 1% | 1.0076 | 1.0088 | -0.0012 | +2.63 | +0.048 |
| ROFT | 5% | 1.0575 | 1.0488 | +0.0087 | +5.70 | +0.104 |
| ROFT | 10% | 1.0950 | 1.0953 | -0.0003 | +5.13 | +0.093 |
| ROFT | 15% | 1.1243 | 1.1366 | -0.0123 | +10.47 | +0.190 |
| RO | 1% | 1.0022 | 1.0026 | -0.0003 | -21.47 | +0.233 |
| RO | 5% | 1.0236 | 1.0190 | +0.0045 | -11.57 | +0.666 |
| RO | 10% | 1.0468 | 1.0463 | +0.0005 | -29.23 | +0.680 |
| RO | 15% | 1.0763 | 1.0807 | -0.0044 | -49.43 | +0.909 |

## Correlation

| Topology | Corr(path stretch, failed-JCT error) | Corr(path stretch, factor error) |
|---|---:|---:|
| DeepSeek | +0.973 | +0.949 |
| ROFT | +0.879 | +0.879 |
| RO | -0.851 | +0.921 |

## Interpretation

- DeepSeek and ROFT have a clear high-stretch residual: as failure-induced path stretch rises, FlowSim remains increasingly slower than NS3 even after fault-only speedup.
- RO is different. Its factor error rises with stretch, but absolute failed JCT is already below NS3 and gets worse at high stretch. Applying the same high-stretch speedup to RO would be the wrong direction for absolute JCT.
- The next correction should therefore be topology/path-class-aware:
  - DeepSeek/ROFT: test stronger failed-run correction only for higher path stretch samples.
  - RO: keep as a separate guardrail and avoid global failed-run speedup.

## Next Candidate

Use the existing `--fault-*` runner support, but run DeepSeek/ROFT separately with a high-stretch-oriented override. Do not apply it to RO until there is a RO-specific absolute-JCT correction.
