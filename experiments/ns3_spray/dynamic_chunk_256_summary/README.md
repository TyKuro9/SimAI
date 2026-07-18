# Dynamic Chunk Spray: 256-GPU Zcube Validation

## Setup

- Topology: `Zcube_n16_k2_256g_8gps_200Gbps_H100`
- Workload: `synthetic_allgather_world_size256_64MiB_probe.txt`
- Routing baseline: `spray_adaptive`, width 4
- Dynamic policy: `spray_dynamic_chunk`, width 4
- PXN/NVLS: disabled
- Saved telemetry: completion-level stripe path, NIC, FCT, and CNP metrics

## Result

The selected default is 8 chunks per logical fabric flow. Four persistent lanes
are assigned evenly across the two source NICs. A completed lane launches its
own next chunk, and the downstream path is rescored for that new QP.

The final dynamic result is `1251.591 us`, 1.61% above the unchanged adaptive
baseline (`1231.741 us`). It keeps source and destination NIC bytes at exactly
50/50, uses 7168 two-link and 7168 four-link paths, and never falls back to the
three-link cross pairing. The lane path changes between its two chunks in
45.26% of opportunities, confirming that the second QP is dynamically rescored.

Releasing only the accounting reservation when a QP finishes sending is the
key tail-latency fix. The switch route binding remains installed until receive
completion, so in-flight tail packets keep the same route. This reduced the
logical-flow span p95 from `241392 ns` to `175970 ns`.

See `results.csv` for the iteration comparison. Raw outputs are under the
corresponding `dynamic_chunk_*_64m_smoke_20260718` experiment directories.
