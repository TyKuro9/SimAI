#!/usr/bin/env python3
"""Rerun no-fault NS3 baseline samples with detailed monitors."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from rerun_targeted_fct_mismatch import (
    DEFAULT_NS3_BIN,
    DEFAULT_WORKLOAD,
    count_lines,
    ns3_monitor_output,
    run_ns3,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "experiments" / "fault_tolerance" / "targeted_monitor_baseline"
DEFAULT_NS3_BASELINE = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "ns3_256_alltoall_p01_p15_s10_chain_pfc_resume_fix"
    / "baseline_jct.csv"
)
DEFAULT_FLOWSIM_BASELINE = (
    ROOT
    / "experiments"
    / "fault_tolerance"
    / "flowsim_256_alltoall_p01_p15_s10_chain"
    / "baseline_jct.csv"
)
TOPOLOGIES = ["Meta", "Zcube", "RO", "DeepSeek", "ROFT"]


def read_baseline(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="") as f:
        return {row["topology"]: row for row in csv.DictReader(f)}


def run(args: argparse.Namespace) -> int:
    args.output_dir = args.output_dir.resolve()
    args.workload = args.workload.resolve()
    args.ns3_bin = args.ns3_bin.resolve()
    ns3_baseline = read_baseline(args.ns3_baseline_csv.resolve())
    flowsim_baseline = read_baseline(args.flowsim_baseline_csv.resolve())

    rows = []
    selected_topologies = args.topologies or TOPOLOGIES
    for topology in selected_topologies:
        if topology not in ns3_baseline:
            raise SystemExit(f"missing NS3 baseline topology: {topology}")
        topo = Path(ns3_baseline[topology]["topology_file"])
        if not topo.exists():
            raise SystemExit(f"topology not found: {topo}")
        ns3_dir = args.output_dir / "ns3" / topology / "baseline"
        print(f"[NS3 BASELINE] {topology}", flush=True)
        ns3_jct = run_ns3(
            ns3_bin=args.ns3_bin,
            workload=args.workload,
            topology=topo,
            output_dir=ns3_dir,
            threads=args.threads,
            timeout=args.timeout,
            enable_trace=args.enable_trace,
            enable_monitors=True,
            monitor_start_us=args.monitor_start_us,
            monitor_end_us=args.monitor_end_us,
            qlen_interval_us=args.qlen_interval_us,
            bw_interval_us=args.bw_interval_us,
            qp_interval_us=args.qp_interval_us,
            jct_linger_timeout=args.jct_linger_timeout,
            resume=False,
        )
        flow_jct = flowsim_baseline.get(topology, {}).get("normal_jct", "missing")
        rows.append(
            {
                "topology": topology,
                "rate": 0.0,
                "seed": 0,
                "topology_file": str(topo),
                "flowsim_jct": flow_jct,
                "ns3_jct": ns3_jct if ns3_jct is not None else "missing",
                "flowsim_run_dir": flowsim_baseline.get(topology, {}).get(
                    "run_dir", "missing"
                ),
                "ns3_run_dir": str(ns3_dir),
                "flowsim_fct_lines": count_lines(
                    Path(flowsim_baseline.get(topology, {}).get("run_dir", ""))
                    / "fct.txt"
                ),
                "ns3_fct_lines": count_lines(ns3_dir / "fct.txt"),
                "ns3_send_lines": count_lines(ns3_dir / "send.txt"),
                "ns3_pfc_lines": count_lines(ns3_dir / "pfc.txt"),
                "ns3_trace_lines": count_lines(ns3_dir / "trace.tr"),
                "ns3_qlen_lines": count_lines(ns3_monitor_output(ns3_dir, "qlen")),
                "ns3_bw_lines": count_lines(ns3_monitor_output(ns3_dir, "bw")),
                "ns3_rate_lines": count_lines(ns3_monitor_output(ns3_dir, "rate")),
                "ns3_cnp_lines": count_lines(ns3_monitor_output(ns3_dir, "cnp")),
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / "targeted_fct_summary.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rerun no-fault baseline NS3 monitors")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ns3-baseline-csv", type=Path, default=DEFAULT_NS3_BASELINE)
    parser.add_argument(
        "--flowsim-baseline-csv", type=Path, default=DEFAULT_FLOWSIM_BASELINE
    )
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--ns3-bin", type=Path, default=DEFAULT_NS3_BIN)
    parser.add_argument("--topologies", nargs="+", choices=TOPOLOGIES)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--enable-trace", action="store_true")
    parser.add_argument("--monitor-start-us", type=int, default=0)
    parser.add_argument("--monitor-end-us", type=int, default=700)
    parser.add_argument("--qlen-interval-us", type=int, default=10)
    parser.add_argument("--bw-interval-us", type=int, default=10)
    parser.add_argument("--qp-interval-us", type=int, default=10)
    parser.add_argument("--jct-linger-timeout", type=int, default=60)
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
