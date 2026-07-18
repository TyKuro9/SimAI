# NS3 Dynamic Chunk 256-GPU DeepSeek/ZCube A/B

This short diagnostic isolates network behavior with one 64 MiB AllGather on
256 GPUs. It uses the same NS3 binary for both topologies and both routing
policies. PXN is disabled, spray width is 4, dynamic chunk count is 8, and each
run uses four NS3 threads. Runs are JCT-only, so this data set does not contain
FCT or path telemetry.

| Topology | Policy | JCT (us) | Dynamic vs adaptive | ZCube vs DeepSeek |
|---|---|---:|---:|---:|
| DeepSeek | `spray_adaptive` | 1233.741 | baseline | baseline |
| DeepSeek | `spray_dynamic_chunk` | 1252.722 | +1.538% | baseline |
| ZCube | `spray_adaptive` | 1231.859 | baseline | -0.153% |
| ZCube | `spray_dynamic_chunk` | 1251.592 | +1.602% | -0.090% |

The result shows two effects. First, ZCube is slightly faster than DeepSeek
under both policies for this communication-only workload. Second, splitting
each logical flow into eight chunks adds about 1.5-1.6% JCT in both topologies,
so the short-run overhead is mostly policy-wide rather than ZCube-specific.
The dynamic policy also narrows ZCube's advantage, which means its path
selection gain does not yet repay the extra QP/chunk completion overhead in
this uncongested probe.

## Reproducibility

- Raw output: `experiments/ns3_spray/dynamic_chunk_256_deepseek_zcube_ab_20260718`
- Binary SHA256: `0b0a931ad6eb91c74fa1f0854c1da6891a6aa2ab452fceac68a69efb9fd2c23e`
- Workload SHA256: `06f03a1ece989d9f83b05aaf2d3418d4909a0cce01bf28661764b8387d1bbe4f`
- DeepSeek topology SHA256: `fadbbf468d6ad26d8b9f98ec4d47bcb5ed3cdcee6201b1288f37e4b4173973be`
- ZCube topology SHA256: `28c7f567781259d16c97c449aea824e47fb275d44e9263e5256408d66d3e885e`

