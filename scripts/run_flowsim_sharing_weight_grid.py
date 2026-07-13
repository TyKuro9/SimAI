#!/usr/bin/env python3
"""Run a small FlowSim grid for cross-rail switch-switch sharing weights."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET_DIR = ROOT / "experiments" / "fault_tolerance" / "targeted_original_flow_mismatch"
DEFAULT_OUTPUT = ROOT / "experiments" / "fault_tolerance" / "flowsim_sharing_weight_grid"
DEFAULT_WORKLOAD = ROOT / "my_workloads" / "synthetic_alltoall_global_world_size256_1MiB.txt"
DEFAULT_FLOWSIM_BIN = Path("/home/zty/Topo/m4/SimAI/bin/SimAI_flowsim")


def parse_csv_list(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_weights(value: str) -> list[float]:
    weights = []
    for part in parse_csv_list(value):
        weight = float(part)
        if weight <= 0:
            raise argparse.ArgumentTypeError("weights must be positive")
        weights.append(weight)
    if not weights:
        raise argparse.ArgumentTypeError("at least one weight is required")
    return weights


def weight_label(weight: float) -> str:
    return f"w{weight:.6g}".replace(".", "p")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def read_total_time(path: Path) -> Optional[float]:
    if not path.exists() or path.stat().st_size == 0:
        return None
    rows = read_rows(path)
    if not rows:
        return None
    normalized = {key.strip(): value.strip() for key, value in rows[0].items()}
    value = normalized.get("Total time")
    return float(value) if value else None


def count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(errors="replace") as f:
        return sum(1 for _ in f)


def build_env(weight: float) -> dict[str, str]:
    env = os.environ.copy()
    env["AS_SEND_LAT"] = env.get("AS_SEND_LAT", "3")
    env["AS_NVLS_ENABLE"] = env.get("AS_NVLS_ENABLE", "0")
    env["AS_PXN_ENABLE"] = env.get("AS_PXN_ENABLE", "1")
    env["AS_PXN_POLICY"] = env.get("AS_PXN_POLICY", "fallback")
    env["FLOWSIM_CROSS_RAIL_SWITCH_SWITCH_WEIGHT"] = str(weight)
    return env


def run_flowsim(
    *,
    flowsim_bin: Path,
    workload: Path,
    topology_file: Path,
    output_dir: Path,
    threads: int,
    weight: float,
    timeout: Optional[int],
    resume: bool,
) -> Optional[float]:
    existing = read_total_time(output_dir / "EndToEnd.csv")
    if resume and existing is not None and count_lines(output_dir / "fct.txt") > 0:
        return existing

    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(flowsim_bin),
        "-t",
        str(threads),
        "-w",
        str(workload),
        "-n",
        str(topology_file),
        "-o",
        str(output_dir) + "/",
    ]
    with (output_dir / "run.log").open("w") as log:
        subprocess.run(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
            env=build_env(weight),
            timeout=timeout,
        )
    return read_total_time(output_dir / "EndToEnd.csv")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> int:
    target_dir = args.target_dir.resolve()
    workload = args.workload.resolve()
    flowsim_bin = args.flowsim_bin.resolve()
    output_dir = args.output_dir.resolve()
    targets = {row["topology"]: row for row in read_rows(target_dir / "targeted_fct_summary.csv")}
    rows: list[dict[str, object]] = []

    for topology in args.topologies:
        if topology not in targets:
            raise SystemExit(f"unknown topology in targeted summary: {topology}")
        target = targets[topology]
        topology_file = Path(target["topology_file"]).resolve()
        for weight in args.weights:
            run_dir = output_dir / topology / weight_label(weight)
            print(f"[FLOWSIM] topology={topology} weight={weight}", flush=True)
            jct = run_flowsim(
                flowsim_bin=flowsim_bin,
                workload=workload,
                topology_file=topology_file,
                output_dir=run_dir,
                threads=args.threads,
                weight=weight,
                timeout=args.timeout,
                resume=args.resume,
            )
            rows.append(
                {
                    "topology": topology,
                    "weight": weight,
                    "run_dir": str(run_dir),
                    "jct": jct if jct is not None else "missing",
                    "fct_lines": count_lines(run_dir / "fct.txt"),
                    "topology_file": str(topology_file),
                }
            )
            write_csv(output_dir / "flowsim_sharing_weight_grid_summary.csv", rows)

    write_csv(output_dir / "flowsim_sharing_weight_grid_summary.csv", rows)
    print(output_dir / "flowsim_sharing_weight_grid_summary.csv")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run FlowSim cross-rail switch-switch weight grid"
    )
    parser.add_argument("--target-dir", type=Path, default=DEFAULT_TARGET_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workload", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--flowsim-bin", type=Path, default=DEFAULT_FLOWSIM_BIN)
    parser.add_argument("--topologies", type=parse_csv_list, default=["Meta", "Zcube", "RO"])
    parser.add_argument("--weights", type=parse_weights, default=[0.4, 0.5, 0.6, 0.75, 1.0])
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
