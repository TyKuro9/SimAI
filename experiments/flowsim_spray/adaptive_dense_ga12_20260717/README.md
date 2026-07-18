# FlowSim Adaptive Spray: GPT-22B at 256 GPUs

> **Superseded pre-fix result.** FlowSim ignored `PP=4` in this run and built
> `DP=32` groups instead of the requested `DP=8` groups. Keep these files only
> as before-fix evidence. Corrected results are in
> `../adaptive_dense_ga12_ppfix_retry_20260717/README.md`.

## Scope

- Date: 2026-07-17
- Simulator: `/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim`
- Simulator SHA-256: `f23a97d41860a111fa9674647f29c7ac6c65471ccfcdf33a5fe56c38534da6cf`
- FlowSim source commit: `2c0b7a8` (`Implement adaptive QP spray in FlowSim`)
- Workload and all topology files come from `/home/zty/Topo/SimAI_TyKuro9_spray_algo_iter2`.
- Workload SHA-256: `29e8082dced64cdabea6e9da8e9506acc02e00898f485142216dbcb769ed746b`
- Workload shape: world size 256, TP=8, PP=4, EP=1, GA=12.
- FCT output was redirected to `/dev/null`; JCT and the normal `EndToEnd.csv` output were retained.

## Configuration

```text
FLOWSIM_ROUTING_POLICY=spray_adaptive
FLOWSIM_SPRAY_WIDTH=4
FLOWSIM_ADAPTIVE_PATH_COUNT=16
FLOWSIM_ADAPTIVE_MAX_EXTRA_HOPS=2
AS_SEND_LAT=3
AS_NVLS_ENABLE=0
AS_PXN_ENABLE=0
AS_PXN_POLICY=off
threads=4
```

## Results

| Rank | Topology | JCT (us) | JCT (s) | Relative to best | Exposed communication (us) | Wall time (s) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | Meta | 2,135,106 | 2.135106 | 0.0000% | 174,617 | 314.99 |
| 2 | RO | 2,135,137 | 2.135137 | 0.0015% | 174,648 | 306.00 |
| 3 | HPN | 2,135,168 | 2.135168 | 0.0029% | 174,679 | 313.06 |
| 3 | DeepSeek | 2,135,168 | 2.135168 | 0.0029% | 174,679 | 311.05 |
| 3 | ROFT | 2,135,168 | 2.135168 | 0.0029% | 174,679 | 311.76 |
| 6 | Zcube | 2,244,105 | 2.244105 | 5.1051% | 283,616 | 403.26 |

All six runs exited successfully. The model reports the same `1,960,489 us`
of compute time for every topology. Meta, RO, HPN, DeepSeek, and ROFT are
effectively tied: their full JCT spread is only `62 us` (`0.0029%`).

Zcube is slower because its exposed DP communication is `217,596 us`, about
twice the `108.6 ms` seen on the other topologies. TP communication and bubble
time are unchanged, so the `108,999 us` JCT gap is isolated to the DP
scale-out leg rather than compute or pipeline scheduling.

Wall time was measured while all six jobs ran concurrently. It is useful for
tracking simulator cost, but should not be treated as an isolated runtime
benchmark.

## Post-run Diagnosis

The 31 DP waves in this run were not a workload property. They came from a
FlowSim bug that hard-coded pipeline parallelism to one:

```text
pre-fix:  DP = 256 / (TP 8 * PP 1) = 32, so Ring AllGather has 31 waves
correct:  DP = 256 / (TP 8 * PP 4) = 8,  so Ring AllGather has 7 waves
```

The earlier stripe-barrier explanation for Meta's tiny lead was also rejected.
Grouping the trace by logical `src,dst` pair found no mixed-hop stripe groups
for Meta, RO, HPN, DeepSeek, or ROFT. The different hop lengths belonged to
different rank pairs, not to fast and slow stripes of the same logical flow.

The corrected run reduces the six-topology FlowSim-vs-NS-3 MAE from
`77,386 us` to `41,949 us` and changes RO from effectively tied for best to
the slowest FlowSim topology. See the corrected report for the valid ranking
and the remaining Zcube/RO model differences.
