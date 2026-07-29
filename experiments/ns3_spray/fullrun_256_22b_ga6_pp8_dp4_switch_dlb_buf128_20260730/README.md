# 256-GPU 22B GA6 Full-Run

## Matrix

- Workloads: Dense and MoE
- Topologies: Zcube, HPN, DeepSeek, P2R
- Parallelism: TP8, PP8, DP4, GA6
- Global batch: 24 with micro-batch 1
- Model shape: GPT-22B, 48 layers, hidden size 6144
- Dense: EP1
- MoE: EP4, 8 experts, top-2, grouped GEMM

## Network Configuration

- Routing: `spray_switch_dlb`
- PXN: off
- Buffer: 128 MiB
- Fabric link delay: 5 us
- NVLink delay: 1 us
- Send window: enabled
- Selective per-lane credit: enabled
- Worker threads: 4 per run
- Concurrent runs: 8

Each run uses `--fct-only`. Once the runner has emitted JCT and the FCT file
has become idle, the launcher terminates simulator teardown, summarizes the
run, compresses `fct.txt` with `gzip -9`, verifies it with `gzip -t`, and
writes a SHA-256 checksum.
