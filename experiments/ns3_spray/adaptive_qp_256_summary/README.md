# Adaptive QP Spray: 256-GPU Results

## Summary

`spray_adaptive` binds each QP to the path with the lowest estimated completion
time. It keeps the binding fixed for the lifetime of the QP, so this is not
packet-level spraying and does not introduce packet reordering within a QP.

On the full GPT-22B Dense GA=12 workload, all six 256-GPU topologies complete
successfully. ROFT has the lowest JCT at 2.118948 seconds, followed by Zcube
at 2.119412 seconds. Their difference is only 0.463 ms, or 0.022% relative to
ROFT. DeepSeek is 0.241% above ROFT, while RO is the slowest at 2.424429
seconds, 14.417% above ROFT.

## Policy

For a dual-port GPU pair, the policy evaluates the four source-port and
destination-port combinations. In Zcube these combinations produce the
1/2/2/3-switch path family:

- Same endpoint switch: 2 fabric links, 1 switch.
- Directly connected endpoint switches: 3 fabric links, 2 switches.
- Same-partition endpoint switches through one relay: 4 fabric links,
  3 switches.

The per-QP score is:

```text
propagation latency
+ max over path edges((queued bytes + reserved QP bytes) * 8 / edge rate)
+ QP bytes * 8 / bottleneck rate
```

Selected QP bytes are reserved on every path edge and released at completion.
This lets a short path receive more QPs while it is lightly loaded, then moves
later QPs to the longer path when its predicted completion time becomes lower.
The pipelined score is limited to `spray_adaptive`; existing policies retain
their previous additive queue score.

## Results

All JCT values are simulated time from `EndToEnd.csv`. Wall time is recorded
only for reproducibility and is not a topology performance metric.

| Workload | Topology | Policy | JCT | Comparison |
|---|---|---|---:|---:|
| 64 MiB AllGather | Zcube | `spray_dual_table` | 1,237.607 us | baseline |
| 64 MiB AllGather | Zcube | `spray_adaptive` | 1,231.979 us | 0.455% lower than old Zcube |
| 64 MiB AllGather | DeepSeek | `spray_adaptive` | 1,233.759 us | Zcube is 0.144% lower |
| GPT-22B Dense GA=1 | Zcube | `spray_adaptive` | 310,348.236 us | 1.376% lower than DeepSeek |
| GPT-22B Dense GA=1 | DeepSeek | `spray_adaptive` | 314,678.283 us | baseline |
| GPT-22B Dense GA=12 | ROFT | `spray_adaptive` | 2,118,948.317 us | best |
| GPT-22B Dense GA=12 | Zcube | `spray_adaptive` | 2,119,411.632 us | 0.022% above ROFT |
| GPT-22B Dense GA=12 | DeepSeek | `spray_adaptive` | 2,124,044.494 us | 0.241% above ROFT |
| GPT-22B Dense GA=12 | Meta | `spray_adaptive` | 2,141,931.794 us | 1.085% above ROFT |
| GPT-22B Dense GA=12 | HPN | `spray_adaptive` | 2,151,332.432 us | 1.528% above ROFT |
| GPT-22B Dense GA=12 | RO | `spray_adaptive` | 2,424,428.772 us | 14.417% above ROFT |

The 64 MiB path diagnostic recorded 3,584 Zcube QPs on 1-switch paths and
3,584 on 3-switch paths. The old dual-table policy placed all 7,168 QPs on
2-switch paths. The GA=12 run used JCT-only mode and intentionally did not
retain FCT or per-QP route dumps.

The six GA=12 runs use the same workload and report the same 1,960,489 us of
total compute. The repository's canonical 256-GPU Meta topology carries an
`A100` header and DeepSeek carries an `H800` header; the other four carry
`H100`. These fields were preserved rather than silently relabeled. Because
the workload supplies identical compute timing, the measured JCT differences
here are dominated by exposed communication time.

Machine-readable values are in `results.csv`.

## Reproduction

Build and run from the SimAI repository root:

```bash
./scripts/build.sh -c ns3
/usr/bin/g++ -std=c++17 \
  astra-sim-alibabacloud/astra-sim/network_frontend/ns3/tests/routing_policy_test.cc \
  -o /tmp/routing_policy_test
/tmp/routing_policy_test

python3 scripts/run_ns3_ecmp_spray_256.py \
  --workload my_workloads/H100-gpt_22B-world_size256-tp8-pp4-ep1-gbs96-mbs1-seq2048-MOE-False-GEMM-False-flash_attn-True.txt \
  --output-dir experiments/ns3_spray/adaptive_dense_ga12 \
  --topologies Zcube DeepSeek HPN ROFT Meta RO \
  --policies spray_adaptive \
  --spray-width 4 \
  --threads 8 \
  --send-latency 3 \
  --jct-only \
  --timeout 43200
```

Formal results use the NS3 debug profile. The release-profile probe exited with
`SIGSEGV` before writing JCT, so it was excluded from all reported comparisons.

## Verification

- Routing-policy unit test: passed.
- Full NS3 debug build: passed.
- Adaptive path smoke test: passed.
- Legacy `spray_dual_table` 64 MiB regression: unchanged at 1,237.607 us.
- GPT-22B Dense GA=1 comparison: both topologies completed successfully.
- GPT-22B Dense GA=12 comparison: all six topologies completed with return
  code 0 and matching `EndToEnd.csv` and runner-summary JCT values.

Code checkpoints:

- SimAI: `7716880` (`Add adaptive QP spray experiments`)
- SimAI runner map: `5248356` (`Add remaining 256-GPU spray topologies`)
- ns-3-alibabacloud: `6497feb` (`Implement adaptive QP spray routing`)
