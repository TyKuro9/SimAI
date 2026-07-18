# FlowSim 1024-GPU Fanout-Aware Validation

## Configuration

- Workload: GPT-22B Dense, TP=8, PP=4, EP=1, GA=6
- Workload SHA-256: `f97e16b9bcbb362e740892caea233bcf5863a21b2afbd25e420582ff02c88d86`
- Topologies: 1024-GPU 12.8 Tbps set
- Routing: `spray_adaptive`, width=4, path pool=64, max extra hops=2
- Transport: `ns3_cc`, 9000 B payload + 48 B header
- PXN/NVLS: disabled

## Final JCT

| Topology | Before (us) | Final FlowSim (us) | ns-3 (us) | Final error |
|---|---:|---:|---:|---:|
| ROFT | 1,142,027.250 | 1,142,027.250 | 1,142,527.783 | 0.044% |
| Zcube | 1,142,027.250 | 1,142,027.250 | 1,143,074.292 | 0.092% |
| DeepSeek | 1,142,027.250 | 1,142,027.250 | 1,142,527.618 | 0.044% |
| Meta | 1,162,587.597 | 1,177,870.845 | 1,178,357.108 | 0.041% |
| HPN | 1,177,131.867 | 1,241,318.080 | 1,241,226.307 | 0.007% |
| RO | 1,465,313.967 | 1,465,313.967 | n/a | n/a |

Across the five topologies with an ns-3 reference:

- MAE: `16.382 ms -> 0.525 ms`
- MAPE: `1.336% -> 0.046%`
- The final ordering matches ns-3. FlowSim still ties ROFT, Zcube, and DeepSeek;
  ns-3 separates those three by less than 0.1%.

## Fanout Scaling

The remaining mismatch was isolated to the final 1.777 GB DP AllGather. The
DP group grows from 8 at 256 GPUs to 32 at 1024 GPUs, while the access-switch
GPU fanout doubles:

| Structure | 256 fanout | 1024 fanout | Base efficiency | Reference | Exponent |
|---|---:|---:|---:|---:|---:|
| Shared-core single home (Meta) | 8 | 16 | 0.821 | 8 | 0.8 |
| Independent dual plane (HPN) | 16 | 32 | 0.736 | 16 | 1.5 |

The transport overhead now scales structurally:

```text
overhead = (1 / base_efficiency - 1)
           * max(1, endpoint_fanout / reference_fanout) ^ exponent
effective_efficiency = 1 / (1 + overhead)
```

Rail-oriented single-home fabrics and cross-connected dual-home fabrics do not
enter these two branches. No topology filename or fixed GPU-count check is used.

## Regression

Full 256-GPU Meta and HPN runs were repeated after the change:

| Topology | Before (us) | After (us) | Change |
|---|---:|---:|---:|
| Meta | 2,138,520.463 | 2,138,520.463 | 0 ns |
| HPN | 2,151,703.171 | 2,151,703.171 | 0 ns |

The four single-layer fanout probes and all three CTest targets also pass.
