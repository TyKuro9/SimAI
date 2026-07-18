# 1024-GPU GA=24 FlowSim Probe

## Configuration

- Topology: ROFT, 1024 GPUs, 8 GPUs/server, 16 PSWs, 400 Gbps scale-out links
- Workload: GPT-22B Dense, TP=8, PP=4, EP=1, MBS=1, GA=24, global batch=768
- Routing: `spray_adaptive`, width=4, adaptive path pool=64
- Transport: `ns3_cc`, 9000-byte payload plus 48-byte header
- PXN/NVLS: disabled
- Workload SHA256: `3e29c351fc6ce566dfecb9dbf7266ad13b9945893ebf84f385c73f5388862a7d`

The GA=24 workload contains 1211 records: a 4-record prefix, 24 50-record
microbatch blocks, and a 7-record suffix. The first block retains its startup
cost; blocks 2 through 24 use the validated steady-state block from the GA=6
source workload.

## Result

| Metric | GA=6 | GA=24 | Ratio |
|---|---:|---:|---:|
| JCT | 1.142027 s | 4.102579 s | 3.592x |
| Wall time | 1264.46 s | 7504.69 s | 5.935x |
| Peak RSS | 41.21 GiB | 159.00 GiB | 3.858x |

The JCT grows by less than 4x because the workload includes fixed startup and
tail work that is not repeated for every additional gradient-accumulation
block. The simulator cost grows faster than JCT: the larger workload expands
the event state and raises both memory pressure and event-processing time.

The run completed normally at `2026-07-18T12:54:46+08:00`. With the observed
159 GiB peak RSS, the remaining topologies should run serially on this host.
