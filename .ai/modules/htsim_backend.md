# Module: htsim Backend

## Responsibilities

- Provide a parallel htsim-based backend without replacing NS-3.
- Reuse existing SimAI workload/topology/config inputs at the frontend level.
- Drive ASTRA-sim callbacks through htsim `EventList` so `Workload::report()` can still produce `EndToEnd.csv`.
- Support RoCE route-strategy experiments, especially deterministic per-packet Spray.

## Main Files

- `extern/network_backend/htsim`
- `astra-sim-alibabacloud/astra-sim/network_frontend/htsim/HtsimAstra.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/htsim/HtsimNetwork.cc`
- `astra-sim-alibabacloud/astra-sim/network_frontend/htsim/HtsimNetwork.h`
- `astra-sim-alibabacloud/build/simai_htsim/*`

## Key Interfaces

- `./scripts/build.sh -c htsim`
- `bin/SimAI_htsim`
- `bin/SimAI_htsim -w <workload> -n <topology> -c <config> -o <result-dir> -r single|ecmp|spray_rr`
- `HTSIM_ROUTE_STRATEGY=single|ecmp|spray_rr`
- `HTSIM_LINK_BW_GBPS=<gbps>` for the ASTRA-facing htsim completion estimator.

## Current Implementation Notes

- htsim is a git submodule fixed to `Broadcom/csg-htsim@841d9e7be46bb968eece766aa4b6c044c7799f67`.
- The ASTRA-facing htsim frontend parses the first line of existing SimAI topology files for node counts, GPU type, GPU-per-server, NVSwitch count, switch count, link count, and first-link bandwidth/latency.
- The frontend uses htsim `EventList` for scheduling and preserves the NS-3-style `sentHash`, `recvHash`, `expeRecvHash`, and `receiver_pending_queue` callback matching behavior.
- htsim RoCE `RoceSrc` now supports a vector of routes and selects the next route per data packet for Spray-style transmission.
- htsim native `datacenter/htsim_roce` now accepts multi-path strategies such as `-strat perm` for RoCE instead of aborting.
- ACK/NACK packets still use the stable reverse route configured on the sink.

## Inputs

- workload file under `my_workloads/`
- SimAI topology file under `mytopo/`
- optional config file under `myconfig/`
- result directory for `EndToEnd.csv`

## Outputs

- `EndToEnd.csv` from ASTRA `Workload::report()`
- htsim native logs when running `extern/network_backend/htsim/sim/datacenter/htsim_roce`
- `bin/SimAI_htsim` symlink after `./scripts/build.sh -c htsim`

## Verification

- `./scripts/build.sh -c htsim` builds `bin/SimAI_htsim`.
- `make -C extern/network_backend/htsim/sim/datacenter htsim_roce` builds the native htsim RoCE datacenter binary.
- Native htsim smoke:
  - `extern/network_backend/htsim/sim/datacenter/htsim_roce -nodes 16 -topo extern/network_backend/htsim/sim/datacenter/topologies/leaf_spine_tiny.topo -tm extern/network_backend/htsim/sim/datacenter/connection_matrices/one.cm -strat perm -paths 2 -end 1000 -o /tmp/htsim_roce_smoke.log`
  - verified one RoCE flow completed.
- SimAI htsim smoke:
  - `bin/SimAI_htsim ... -r spray_rr -o /tmp/simai_htsim_smoke`
  - verified `/tmp/simai_htsim_smoke/EndToEnd.csv` had 1813 rows.

## Modification Risk

- High if changing callback matching because upper-stack stream completion depends on send/recv handler ordering and `ncclFlowTag` propagation.
- Medium if changing topology parsing because existing SimAI topology files encode GPU/NVSwitch/switch counts in the first two lines.
- Medium if changing htsim RoCE route ownership because native htsim routes are pointer-heavy and route copies must append transport endpoints with `Route(orig, dst)`.
- Low for adding additional htsim route strategies when they only change `RoceSrc::choose_route()`.
